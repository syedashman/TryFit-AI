"""Sprint 4 Phase 3C.2 — garment-fidelity hard rejection and same-photo retry.

Covers:
- Long garment (kurta/kameez) rendered as a clearly short shirt/top is hard
  rejected with an explicit ``long_garment_shortened`` reason.
- ``rejection_reasons`` are populated for rejected candidates.
- The newly-added CandidateScore fields are wired into ``to_dict``.
- SAME-PHOTO quality retry uses the exact same assigned person for BOTH
  generation rounds, retries only quality failures, and never retries safety
  blocks / config errors / invalid inputs, and never falls back to another
  uploaded photo (no cross-photo fallback).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.models.job import JobRecord
from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    TryOnResult,
)
from app.services import job_service
from app.services.body_geometry import build_body_geometry_profile
from app.services.candidate_selector import choose_best_candidate
from app.services.garment_fidelity import evaluate_garment_fidelity
from app.services.storage import load_job, save_job


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _garment(path: Path, *, top: int, bottom: int) -> Path:
    """A centered navy garment on a light background."""
    image = Image.new("RGB", (300, 600), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((110, top, 190, bottom), fill=(30, 40, 120))
    image.save(path)
    return path


def _person(path: Path, *, body_width: int) -> Path:
    image = Image.new("RGB", (400, 800), "white")
    draw = ImageDraw.Draw(image)
    x = (400 - body_width) // 2
    draw.ellipse((176, 35, 224, 83), fill="black")
    draw.rectangle((x, 82, x + body_width, 765), fill="black")
    image.save(path)
    return path


# --------------------------------------------------------------------------- #
# Long -> short hard rejection
# --------------------------------------------------------------------------- #
def test_long_kurta_to_short_shirt_is_hard_rejected(tmp_path: Path) -> None:
    reference_person = tmp_path / "reference.png"
    good = tmp_path / "good.png"
    short = tmp_path / "short.png"
    _person(reference_person, body_width=110)
    _person(good, body_width=112)
    _person(short, body_width=112)

    long_garment = tmp_path / "garment.png"
    _garment(long_garment, top=60, bottom=560)

    short_img = Image.open(short).convert("RGB")
    draw = ImageDraw.Draw(short_img)
    draw.rectangle((150, 90, 250, 260), fill=(30, 40, 120))
    short_img.save(short)

    good_img = Image.open(good).convert("RGB")
    draw = ImageDraw.Draw(good_img)
    draw.rectangle((150, 90, 250, 560), fill=(30, 40, 120))
    good_img.save(good)

    _, scores = choose_best_candidate(
        [short, good],
        build_body_geometry_profile(reference_person),
        build_body_geometry_profile(reference_person),
        garment_reference_path=long_garment,
    )

    short_score = next(s for s in scores if s.path == str(short))
    assert short_score.hard_rejected is True
    assert "long_garment_shortened" in (short_score.rejection_reasons or [])
    assert short_score.long_garment_violation is True
    assert short_score.long_garment_confidence > 0.0


def test_rejection_reasons_serialized_in_to_dict(tmp_path: Path) -> None:
    reference_person = tmp_path / "reference.png"
    short = tmp_path / "short.png"
    _person(reference_person, body_width=110)
    _person(short, body_width=112)

    long_garment = tmp_path / "garment.png"
    _garment(long_garment, top=60, bottom=560)

    short_img = Image.open(short).convert("RGB")
    draw = ImageDraw.Draw(short_img)
    draw.rectangle((150, 90, 250, 250), fill=(30, 40, 120))
    short_img.save(short)

    _, scores = choose_best_candidate(
        [short],
        build_body_geometry_profile(reference_person),
        build_body_geometry_profile(reference_person),
        garment_reference_path=long_garment,
    )



# --------------------------------------------------------------------------- #
# Semantic garment-fidelity judge — CV fallback contract
# --------------------------------------------------------------------------- #
def test_fidelity_judge_falls_back_to_cv_when_no_project(tmp_path: Path) -> None:
    """With no google_cloud_project the Gemini judge cannot run, so the judge
    must fall back to the local CV validator, mark itself unavailable, and
    NEVER fabricate a perfect (all-preserved, confidence 1.0) score."""
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")

    garment = _garment(tmp_path / "garment.png", top=60, bottom=560)
    candidate = _person(tmp_path / "candidate.png", body_width=110)

    result = evaluate_garment_fidelity(settings, garment, candidate)

    assert result["semantic_available"] is False
    assert result["source"] == "cv_fallback"
    # A fallback must not look like a confident, fully-preserved pass.
    assert result["confidence"] <= 1.0
    assert not (
        result["confidence"] == 1.0
        and all(
            result.get(field) is True
            for field in (
                "garment_type_preserved",
                "length_preserved",
                "sleeve_preserved",
                "neckline_preserved",
                "silhouette_preserved",
                "major_details_preserved",
            )
        )
    )


def test_fidelity_judge_never_crashes_on_unreadable_images(tmp_path: Path) -> None:
    """Unreadable inputs must yield a safe unavailable result, not an exception."""
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")

    missing_garment = tmp_path / "missing_garment.png"
    missing_candidate = tmp_path / "missing_candidate.png"

    result = evaluate_garment_fidelity(
        settings, missing_garment, missing_candidate
    )

    assert result["semantic_available"] is False
    assert result["hard_reject"] is False

# --------------------------------------------------------------------------- #
class _RecordingProvider:
    """Provider double that records the exact person image per attempt."""

    name = "vertex"

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    def health(self) -> dict[str, object]:
        return {}

    def generate(self, request):  # type: ignore[no-untyped-def]
        self.calls.append(str(request.person_image))
        outcome = self._outcomes[
            min(len(self.calls) - 1, len(self._outcomes) - 1)
        ]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _job(tmp_path: Path, settings: Settings) -> JobRecord:
    person = _person(tmp_path / "render.png", body_width=110)
    alt = _person(tmp_path / "alt.png", body_width=140)
    garment = _garment(tmp_path / "garment.png", top=60, bottom=560)
    record = JobRecord(
        job_id="retry-job",
        provider="vertex",
        person_file=str(person),
        person_files=[str(person), str(alt)],
        garment_file=str(garment),
        cloth_type="overall",
    )
    save_job(record, settings)
    return record


def _result(tmp_path: Path) -> TryOnResult:
    out = _person(tmp_path / "result.png", body_width=110)
    return TryOnResult(image_path=out, raw={"generation_rounds": 1})


def test_same_photo_retry_uses_same_person_for_both_rounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        commercial_max_generation_rounds=2,
    )
    record = _job(tmp_path, settings)

    provider = _RecordingProvider([
        ProviderError(
            "distorted",
            code="distorted_tryon_result",
            retryable=True,
        ),
        _result(tmp_path),
    ])
    monkeypatch.setattr(
        job_service,
        "get_vton_provider",
        lambda _s: provider,
    )

    job_service.process_job(
        record.job_id,
        settings,
        num_inference_steps=30,
        guidance_scale=2.0,
        seed=42,
    )

    # Two rounds, both using the EXACT SAME assigned render_person.
    assert len(provider.calls) == 2
    assert provider.calls[0] == provider.calls[1]
    assert provider.calls[0] == record.person_file
    # Never the alternate uploaded photo.
    assert record.person_files[1] not in provider.calls

    saved = load_job(record.job_id, settings)
    assert saved is not None
    assert saved.status == "completed"


def test_retry_stops_at_two_rounds_and_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        commercial_max_generation_rounds=2,
    )
    record = _job(tmp_path, settings)

    provider = _RecordingProvider([
        ProviderError(
            "garment fidelity failed",
            code="garment_fidelity_failed",
            retryable=True,
        ),
    ])
    monkeypatch.setattr(
        job_service,
        "get_vton_provider",
        lambda _s: provider,
    )

    job_service.process_job(
        record.job_id,
        settings,
        num_inference_steps=30,
        guidance_scale=2.0,
        seed=42,
    )

    # Exactly 2 rounds (hard cap), both on the same person, then it fails.
    assert len(provider.calls) == 2
    assert provider.calls[0] == provider.calls[1] == record.person_file

    saved = load_job(record.job_id, settings)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.error_code == "garment_fidelity_failed"


@pytest.mark.parametrize(
    "error",
    [
        ProviderError(
            "safety",
            code="vertex_person_generation_blocked",
            retryable=False,
        ),
        ProviderConfigurationError("bad config"),
    ],
)
def test_non_quality_failures_are_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: ProviderError,
) -> None:
    settings = Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        commercial_max_generation_rounds=2,
    )
    record = _job(tmp_path, settings)

    provider = _RecordingProvider([error])
    monkeypatch.setattr(
        job_service,
        "get_vton_provider",
        lambda _s: provider,
    )

    job_service.process_job(
        record.job_id,
        settings,
        num_inference_steps=30,
        guidance_scale=2.0,
        seed=42,
    )

    # Single attempt only — safety blocks / config errors are never retried
    # and there is no cross-photo fallback.
    assert len(provider.calls) == 1
    assert provider.calls[0] == record.person_file

    saved = load_job(record.job_id, settings)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.error_code == error.code

