from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from app.core.config import Settings
from app.services.body_geometry import build_body_geometry_profile, geometry_similarity
from app.services.candidate_selector import NoEligibleCandidateError, choose_best_candidate

def _person(path: Path, *, width: int, height: int, body_width: int) -> None:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    x = (width - body_width) // 2
    draw.ellipse((width // 2 - 24, 35, width // 2 + 24, 83), fill="black")
    draw.rectangle((x, 82, x + body_width, height - 35), fill="black")
    image.save(path)

def test_geometry_profile_prefers_reference_like_candidate(tmp_path: Path) -> None:
    reference, close, wide = (tmp_path / n for n in ("reference.png", "close.png", "wide.png"))
    _person(reference, width=400, height=800, body_width=120)
    _person(close, width=400, height=800, body_width=124)
    _person(wide, width=400, height=800, body_width=220)
    winner, scores = choose_best_candidate([wide, close], build_body_geometry_profile(reference))
    assert winner == close
    assert scores[1].geometry_similarity > scores[0].geometry_similarity

def test_geometry_similarity_is_bounded(tmp_path: Path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    _person(a, width=300, height=600, body_width=90)
    _person(b, width=300, height=600, body_width=130)
    score = geometry_similarity(build_body_geometry_profile(a), build_body_geometry_profile(b))
    assert 0.0 <= score <= 1.0

def test_phase3_settings() -> None:
    settings = Settings(_env_file=None, vertex_candidate_count=3, geometry_selection_enabled=True)
    assert settings.vertex_candidate_count == 3
    assert settings.geometry_selection_enabled is True

def test_selector_rejects_short_wide_candidate(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    natural = tmp_path / "natural.png"
    short_wide = tmp_path / "short-wide.png"
    _person(reference, width=400, height=800, body_width=105)
    _person(natural, width=400, height=800, body_width=108)
    image = Image.new("RGB", (400, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((176, 90, 224, 138), fill="black")
    draw.rectangle((105, 138, 295, 650), fill="black")
    image.save(short_wide)
    winner, scores = choose_best_candidate(
        [short_wide, natural],
        build_body_geometry_profile(reference),
        build_body_geometry_profile(reference),
    )
    assert winner == natural
    assert scores[0].final_score < scores[1].final_score


def test_candidate_score_contains_distortion_diagnostics(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    _person(reference, width=400, height=800, body_width=100)
    _person(candidate, width=400, height=800, body_width=180)
    with pytest.raises(NoEligibleCandidateError) as error:
        choose_best_candidate([candidate], build_body_geometry_profile(reference))
    data = error.value.scores[0].to_dict()
    assert "penalties" in data
    assert "candidate_profile" in data
    assert data["penalties"]["body_widening"] >= 0


def test_selector_chooses_best_eligible_candidate(tmp_path: Path, monkeypatch) -> None:
    reference, other = (tmp_path / n for n in ("reference.png", "other.png"))
    _person(reference, width=400, height=800, body_width=120)
    _person(other, width=400, height=800, body_width=122)
    reference_profile = build_body_geometry_profile(reference)
    monkeypatch.setattr(
        "app.services.candidate_selector.build_body_geometry_profile",
        lambda path: reference_profile,
    )
    monkeypatch.setattr(
        "app.services.candidate_selector._hard_reject",
        lambda penalties: False,
    )
    monkeypatch.setattr(
        "app.services.candidate_selector.distortion_penalties",
        lambda first, second: {},
    )
    monkeypatch.setattr(
        "app.services.candidate_selector.geometry_similarity",
        lambda first, second: 1.0,
    )

    winner, scores = choose_best_candidate(
        [reference, other],
        build_body_geometry_profile(reference),
    )

    assert winner == reference
    assert any(not score.hard_rejected for score in scores)


def test_selector_never_returns_all_hard_rejected_candidates(tmp_path: Path) -> None:
    reference, rejected = (tmp_path / n for n in ("reference.png", "rejected.png"))
    _person(reference, width=400, height=800, body_width=120)
    _person(rejected, width=400, height=800, body_width=280)

    with pytest.raises(NoEligibleCandidateError) as error:
        choose_best_candidate(
            [rejected],
            build_body_geometry_profile(reference),
        )

    assert all(score.hard_rejected for score in error.value.scores)


def test_selector_rejects_wrong_face_against_job_person(tmp_path: Path, monkeypatch) -> None:
    reference, wrong_face, correct_face = (
        tmp_path / n for n in ("reference.png", "wrong-face.png", "correct-face.png")
    )
    _person(reference, width=400, height=800, body_width=120)
    _person(wrong_face, width=400, height=800, body_width=120)
    _person(correct_face, width=400, height=800, body_width=120)

    identity_scores = {str(wrong_face): (0.10, True), str(correct_face): (0.95, True)}
    monkeypatch.setattr(
        "app.services.candidate_selector._face_identity_signal",
        lambda source, candidate: identity_scores[str(candidate)],
    )

    winner, scores = choose_best_candidate(
        [wrong_face, correct_face],
        build_body_geometry_profile(reference),
        identity_reference_path=reference,
    )

    assert winner == correct_face
    wrong_score = next(score for score in scores if score.path == str(wrong_face))
    assert wrong_score.hard_rejected is True
    assert "identity_fidelity_failed" in (wrong_score.rejection_reasons or [])


def test_selector_rejects_candidate_closer_to_catalog_face(tmp_path: Path, monkeypatch) -> None:
    source, catalog, candidate = (
        tmp_path / n for n in ("source.png", "catalog.png", "candidate.png")
    )
    _person(source, width=400, height=800, body_width=120)
    _person(catalog, width=400, height=800, body_width=120)
    _person(candidate, width=400, height=800, body_width=120)

    values = {
        (str(source), str(candidate)): (0.40, True),
        (str(catalog), str(candidate)): (0.91, True),
    }
    monkeypatch.setattr(
        "app.services.candidate_selector._face_identity_signal",
        lambda reference, path: values[(str(reference), str(path))],
    )

    with pytest.raises(NoEligibleCandidateError) as error:
        choose_best_candidate(
            [candidate],
            build_body_geometry_profile(source),
            identity_reference_path=source,
            catalog_identity_reference_path=catalog,
        )

    score = error.value.scores[0]
    assert score.catalog_leakage is True
    assert "catalog_identity_leakage" in (score.rejection_reasons or [])


def test_minor_face_variation_remains_eligible(tmp_path: Path, monkeypatch) -> None:
    source, candidate = tmp_path / "source.png", tmp_path / "candidate.png"
    _person(source, width=400, height=800, body_width=120)
    _person(candidate, width=400, height=800, body_width=120)
    monkeypatch.setattr(
        "app.services.candidate_selector._face_identity_signal",
        lambda reference, path: (0.70, True),
    )

    winner, scores = choose_best_candidate(
        [candidate],
        build_body_geometry_profile(source),
        identity_reference_path=source,
    )

    assert winner == candidate
    assert scores[0].hard_rejected is False


def test_geometry_profile_has_subject_shape_metrics(tmp_path: Path) -> None:
    path = tmp_path / "person.png"
    _person(path, width=400, height=800, body_width=110)
    profile = build_body_geometry_profile(path)
    assert profile.subject_aspect_ratio > 0
    assert 0 <= profile.horizontal_center_ratio <= 1
    assert profile.detector in {"opencv_hog_person", "central_saliency"}
