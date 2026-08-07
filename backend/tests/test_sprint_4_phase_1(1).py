from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.providers.auto import AutoFallbackProvider
from app.providers.base import ProviderError, TryOnRequest, TryOnResult
from app.services.provider_runtime import ProviderRuntimeRegistry, provider_runtime


def _request(tmp_path: Path) -> TryOnRequest:
    person = tmp_path / "person.png"
    garment = tmp_path / "garment.png"
    person.write_bytes(b"person")
    garment.write_bytes(b"garment")
    return TryOnRequest(person, garment)


def test_runtime_retries_retryable_provider_error() -> None:
    registry = ProviderRuntimeRegistry()
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ProviderError("temporary", retryable=True)
        return "ok"

    assert registry.execute(
        "vertex",
        operation,
        max_retries=1,
        backoff_seconds=0,
        failure_threshold=3,
        cooldown_seconds=30,
    ) == "ok"
    stats = registry.snapshot()["vertex"]
    assert stats["attempts"] == 2
    assert stats["retries"] == 1
    assert stats["successes"] == 1


def test_runtime_circuit_breaker_opens() -> None:
    registry = ProviderRuntimeRegistry()

    with pytest.raises(ProviderError):
        registry.execute(
            "catvton",
            lambda: (_ for _ in ()).throw(
                ProviderError("down", retryable=True)
            ),
            max_retries=0,
            backoff_seconds=0,
            failure_threshold=1,
            cooldown_seconds=30,
        )

    with pytest.raises(ProviderError) as exc:
        registry.execute(
            "catvton",
            lambda: "never",
            max_retries=0,
            backoff_seconds=0,
            failure_threshold=1,
            cooldown_seconds=30,
        )
    assert exc.value.code == "provider_circuit_open"


def test_health_cache_marks_cached() -> None:
    registry = ProviderRuntimeRegistry()
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return {"provider": "vertex", "configured": True}

    assert registry.cached_health("vertex", loader, ttl_seconds=30)["cached"] is False
    assert registry.cached_health("vertex", loader, ttl_seconds=30)["cached"] is True
    assert calls["count"] == 1


def test_auto_provider_falls_back_after_failure(tmp_path: Path, monkeypatch) -> None:
    provider_runtime.reset()
    settings = Settings(
        _env_file=None,
        provider_fallback_order=["vertex", "catvton"],
        provider_runtime_max_retries=0,
    )
    failing = Mock()
    failing.generate.side_effect = ProviderError("down", retryable=True)
    working = Mock()
    working.generate.return_value = TryOnResult(image_url="https://example.com/result.png")

    monkeypatch.setattr(
        "app.providers.auto.get_named_provider",
        lambda name, _: failing if name == "vertex" else working,
    )

    result = AutoFallbackProvider(settings).generate(_request(tmp_path))
    assert result.metadata["fallback_provider"] == "catvton"
    assert result.endpoint_used == "catvton"


def test_runtime_endpoints_are_available() -> None:
    client = TestClient(app)
    metrics = client.get("/api/runtime/metrics")
    diagnostics = client.get("/api/runtime/diagnostics")
    assert metrics.status_code == 200
    assert metrics.json()["sprint"] == "4"
    assert diagnostics.status_code == 200
    assert diagnostics.json()["phase"] == "3A"
