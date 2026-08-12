from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.photo_category_check import check_photos_match_category


def _fake_settings(project: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        google_cloud_project=project,
        google_cloud_location="us-central1",
        google_application_credentials=None,
    )


def test_fails_open_when_no_project_configured(tmp_path: Path):
    settings = _fake_settings(project=None)
    ok, message = check_photos_match_category(settings, [tmp_path / "a.jpg"], "men")
    assert ok is True
    assert message is None


def test_unknown_category_passes_through(tmp_path: Path):
    settings = _fake_settings(project="demo-project")
    ok, message = check_photos_match_category(settings, [tmp_path / "a.jpg"], "unisex")
    assert ok is True
    assert message is None


def test_fails_open_when_no_readable_images(tmp_path: Path):
    settings = _fake_settings(project="demo-project")
    missing_path = tmp_path / "does-not-exist.jpg"
    ok, message = check_photos_match_category(settings, [missing_path], "women")
    assert ok is True
    assert message is None
