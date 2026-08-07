import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_phase_1_3_defaults():
    settings = Settings(_env_file=None)
    assert settings.hf_api_name == "/submit_function"
    assert settings.hf_fallback_api_name == "/submit_function_p2p"
    assert settings.hf_cloth_type == "overall"
    assert settings.hf_show_type == "result only"


def test_blank_token_becomes_none():
    settings = Settings(_env_file=None, hf_token="   ")
    assert settings.hf_token is None


def test_invalid_cloth_type_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, hf_cloth_type="dress")


def test_invalid_show_type_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, hf_show_type="everything")
