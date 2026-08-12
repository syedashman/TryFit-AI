from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.pose_customization import (
    POSE_REFERENCES_DIR,
    PoseCustomizationError,
    generate_posed_reference,
)


def _fake_settings(project: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        google_cloud_project=project,
        google_cloud_location="us-central1",
        google_application_credentials=None,
        pose_provider="gemini",
    )


def test_bundled_pose_references_exist():
    for pose in ("front", "side", "back"):
        assert (POSE_REFERENCES_DIR / f"{pose}.jpg").exists()


def test_raises_on_unknown_pose(tmp_path: Path):
    with pytest.raises(PoseCustomizationError):
        generate_posed_reference(
            _fake_settings("demo-project"),
            identity_paths=[tmp_path / "a.jpg"],
            pose_name="diagonal",
            subject_description="a person",
            output_dir=tmp_path,
        )


def test_raises_when_no_project_configured(tmp_path: Path):
    with pytest.raises(PoseCustomizationError):
        generate_posed_reference(
            _fake_settings(None),
            identity_paths=[tmp_path / "a.jpg"],
            pose_name="front",
            subject_description="a person",
            output_dir=tmp_path,
        )