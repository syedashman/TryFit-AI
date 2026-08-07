import pytest

from app.core.config import Settings
from app.providers.base import ProviderConfigurationError, TryOnRequest
from app.providers.vertex import VertexTryOnProvider


def test_vertex_health_reports_missing_settings():
    provider = VertexTryOnProvider(Settings(vton_provider="vertex", _env_file=None))
    health = provider.health()
    assert health["configured"] is False
    assert "GOOGLE_CLOUD_PROJECT" in health["missing_settings"]


def test_vertex_generate_fails_cleanly_when_unconfigured(tmp_path):
    provider = VertexTryOnProvider(Settings(vton_provider="vertex", _env_file=None))
    request = TryOnRequest(
        person_image=tmp_path / "person.png",
        garment_image=tmp_path / "garment.png",
    )
    with pytest.raises(ProviderConfigurationError):
        provider.generate(request)
