from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.pose_customization import (
    POSE_REFERENCES_DIR,
    PoseCustomizationError,
    generate_posed_reference,
)
from app.services import pose_customization


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


def test_pose_stage_uses_only_user_image_and_source_geometry(
    tmp_path: Path,
    monkeypatch,
):
    user_photo = (
        Path(__file__).resolve().parents[1]
        / "SAMPLE_TEST_IMAGES"
        / "person_1_full_body.webp"
    )
    payloads: list[dict[str, object]] = []
    encoded_result = base64.b64encode(b"pose-result").decode("ascii")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": encoded_result,
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    class Client:
        def post(self, url, *, headers, json, timeout):
            payloads.append(json)
            return Response()

    settings = _fake_settings("demo-project")
    monkeypatch.setattr(pose_customization, "_access_token", lambda _: "token")
    monkeypatch.setattr(pose_customization, "get_http_client", lambda: Client())

    body_geometry = {
        "foreground_width_ratio": 0.32,
        "foreground_height_ratio": 0.61,
        "upper_width_ratio": 0.72,
        "middle_width_ratio": 0.68,
        "lower_width_ratio": 0.55,
        "subject_aspect_ratio": 0.52,
    }
    result_path = generate_posed_reference(
        settings,
        [user_photo],
        "front",
        "an adult man",
        tmp_path / "pose-cache",
        body_geometry=body_geometry,
    )

    request_parts = payloads[0]["contents"][0]["parts"]
    image_parts = [part for part in request_parts if "inline_data" in part]
    prompt = next(part["text"] for part in request_parts if "text" in part)
    assert len(image_parts) == 1
    assert image_parts[0]["inline_data"]["data"] == base64.b64encode(
        user_photo.read_bytes()
    ).decode("ascii")
    assert "only person shown" in prompt
    assert "Preserve this exact person's visible facial identity" in prompt
    assert "infer only body parts that are not visible" in prompt
    assert "No other person's image is provided" in prompt
    assert "foreground_width_ratio=0.3200" in prompt
    assert "lower_width_ratio=0.5500" in prompt
    assert result_path.read_bytes() == b"pose-result"


def test_identity_review_compares_only_source_and_tryon_images(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "source.jpg"
    result = tmp_path / "result.png"
    source.write_bytes(b"source")
    result.write_bytes(b"result")
    payloads: list[dict[str, object]] = []
    urls: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"identity":"mismatch",'
                                        '"visible_body":"drifted",'
                                        '"confidence":0.91,'
                                        '"reason":"Face and visible proportions changed."}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class Client:
        def post(self, url, *, headers, json, timeout):
            urls.append(url)
            payloads.append(json)
            return Response()

    monkeypatch.setattr(pose_customization, "_access_token", lambda _: "token")
    monkeypatch.setattr(pose_customization, "get_http_client", lambda: Client())
    monkeypatch.setattr(
        pose_customization,
        "_encode_face_crop",
        lambda path: (
            "image/jpeg",
            base64.b64encode(path.stem.encode()).decode(),
        ),
    )

    review = pose_customization.verify_person_preservation(
        _fake_settings("demo-project"),
        source,
        result,
    )

    parts = payloads[0]["contents"][0]["parts"]
    image_parts = [part for part in parts if "inline_data" in part]
    assert urls == [
        "https://us-central1-aiplatform.googleapis.com/v1/"
        "projects/demo-project/locations/us-central1/"
        "publishers/google/models/gemini-2.5-flash:generateContent"
    ]
    assert len(image_parts) == 4
    assert image_parts[0]["inline_data"]["data"] == base64.b64encode(b"source").decode()
    assert image_parts[1]["inline_data"]["data"] == base64.b64encode(b"result").decode()
    assert image_parts[2]["inline_data"]["data"] == base64.b64encode(b"source").decode()
    assert image_parts[3]["inline_data"]["data"] == base64.b64encode(b"result").decode()
    assert "do not call two people a match solely because" in parts[2]["text"]
    assert review.identity == "mismatch"
    assert review.visible_body == "drifted"
    assert review.should_reject


def test_identity_review_does_not_reject_uncertain_or_low_confidence():
    assert not pose_customization.IdentityPreservationReview(
        identity="uncertain",
        visible_body="uncertain",
        confidence=0.95,
        reason="Not enough visible evidence.",
    ).should_reject
    assert not pose_customization.IdentityPreservationReview(
        identity="mismatch",
        visible_body="preserved",
        confidence=0.60,
        reason="Low confidence.",
    ).should_reject


def test_local_identity_screen_triggers_secondary_review():
    from app.services.job_service import _needs_identity_review

    assert not _needs_identity_review(
        {
            "candidate_scores": [
                {
                    "identity_reliable": True,
                    "identity_score": 0.9,
                    "full_body_similarity": 0.95,
                }
            ],
            "selected_candidate_index": 0,
        }
    )
    assert _needs_identity_review(
        {
            "candidate_scores": [
                {
                    "identity_reliable": True,
                    "identity_score": 0.6,
                    "full_body_similarity": 0.95,
                }
            ],
            "selected_candidate_index": 0,
        }
    )
    assert _needs_identity_review(
        {
            "candidate_scores": [
                {
                    "identity_reliable": True,
                    "identity_score": 0.9,
                    "full_body_similarity": 0.6,
                }
            ],
            "selected_candidate_index": 0,
        }
    )
    assert _needs_identity_review({})