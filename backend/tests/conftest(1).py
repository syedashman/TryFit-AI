from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        vton_provider="catvton",
        hf_space="test/space",
        hf_api_name="/submit_function_p2p",
    )


@pytest.fixture
def client(test_settings: Settings):
    app.dependency_overrides = {}
    get_settings.cache_clear()

    original = get_settings

    def override_settings() -> Settings:
        return test_settings

    # Routes call get_settings directly, so temporarily replace cached state
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
