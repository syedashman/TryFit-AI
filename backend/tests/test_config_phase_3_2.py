import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_phase_3_2_defaults():
    settings = Settings(_env_file=None)
    assert settings.vton_provider == "auto"
    assert settings.provider_fallback_order == ["vertex", "catvton"]
    assert settings.vertex_model == "virtual-try-on-001"
    assert settings.vertex_sample_count == 1


def test_vertex_sample_count_range():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vertex_sample_count=5)


def test_auto_provider_is_allowed():
    settings = Settings(_env_file=None, vton_provider="auto")
    assert settings.vton_provider == "auto"


def test_max_concurrent_jobs_has_safe_default():
    settings = Settings(_env_file=None)
    assert settings.max_concurrent_jobs == 2
    assert 1 <= settings.max_concurrent_jobs <= 3
