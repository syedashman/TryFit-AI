from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.providers.base import ProviderError, TryOnRequest
from app.providers.catvton import CatVTONProvider


def request(tmp_path: Path) -> TryOnRequest:
    person = tmp_path / "person.png"
    garment = tmp_path / "garment.png"
    person.write_bytes(b"x")
    garment.write_bytes(b"x")
    return TryOnRequest(
        person_image=person,
        garment_image=garment,
        cloth_type="overall",
        show_type="result only",
        num_inference_steps=50,
        guidance_scale=2.5,
        seed=42,
    )


def test_submit_function_uses_exact_live_argument_order(tmp_path, monkeypatch):
    provider = CatVTONProvider(Settings(_env_file=None))
    client = Mock()
    client.predict.return_value = {"path": str(tmp_path / "out.png")}
    monkeypatch.setattr("app.providers.catvton.handle_file", lambda p: {"path": p})

    req = request(tmp_path)
    result = provider._predict(
        client, "/submit_function", {"background": "p"}, req.garment_image, req
    )

    args = client.predict.call_args.args
    kwargs = client.predict.call_args.kwargs
    assert args[2:] == ("overall", 50.0, 2.5, 42.0, "result only")
    assert kwargs["api_name"] == "/submit_function"
    assert result.endpoint_used == "/submit_function"


def test_p2p_uses_five_arguments(tmp_path, monkeypatch):
    provider = CatVTONProvider(Settings(_env_file=None))
    client = Mock()
    client.predict.return_value = {"url": "https://example.com/out.png"}
    monkeypatch.setattr("app.providers.catvton.handle_file", lambda p: {"path": p})

    req = request(tmp_path)
    provider._predict(
        client, "/submit_function_p2p", {"background": "p"}, req.garment_image, req
    )
    assert len(client.predict.call_args.args) == 5


def test_unsupported_endpoint_has_structured_error(tmp_path, monkeypatch):
    provider = CatVTONProvider(Settings(_env_file=None))
    monkeypatch.setattr("app.providers.catvton.handle_file", lambda p: {"path": p})
    with pytest.raises(ProviderError) as exc:
        provider._predict(
            Mock(), "/wrong", {}, request(tmp_path).garment_image, request(tmp_path)
        )
    assert exc.value.code == "unsupported_catvton_endpoint"


def test_runtime_error_message_is_useful():
    message = CatVTONProvider._friendly_remote_error(
        RuntimeError("RuntimeError"), "/submit_function"
    )
    assert "internal RuntimeError" in message
    assert "/submit_function" in message
