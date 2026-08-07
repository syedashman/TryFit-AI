from app.core.config import Settings
from app.providers.catvton import CatVTONProvider
from app.providers.factory import get_vton_provider
from app.providers.vertex import VertexTryOnProvider


def test_factory_returns_catvton():
    settings = Settings(vton_provider="catvton", _env_file=None)
    assert isinstance(get_vton_provider(settings), CatVTONProvider)


def test_factory_returns_vertex():
    settings = Settings(vton_provider="vertex", _env_file=None)
    assert isinstance(get_vton_provider(settings), VertexTryOnProvider)
