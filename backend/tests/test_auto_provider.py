from pathlib import Path
from unittest.mock import Mock

from app.core.config import Settings
from app.providers.auto import AutoFallbackProvider
from app.providers.base import ProviderError, TryOnRequest, TryOnResult


def test_auto_provider_falls_back(monkeypatch, tmp_path):
    first = Mock()
    first.generate.side_effect = ProviderError("first failed", code="first")
    second = Mock()
    second.generate.return_value = TryOnResult(
        image_path=tmp_path / "result.png",
        endpoint_used="/submit_function",
    )

    def fake_provider(name, settings):
        return first if name == "vertex" else second

    monkeypatch.setattr("app.providers.auto.get_named_provider", fake_provider)

    settings = Settings(
        _env_file=None,
        vton_provider="auto",
        provider_fallback_order=["vertex", "catvton"],
    )
    provider = AutoFallbackProvider(settings)
    request = TryOnRequest(
        person_image=Path("person.png"),
        garment_image=Path("garment.png"),
    )
    result = provider.generate(request)
    assert result.endpoint_used == "catvton:/submit_function"
    assert first.generate.called
    assert second.generate.called
