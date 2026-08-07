from pathlib import Path
from PIL import Image, ImageDraw
from app.core.config import Settings
from app.services.body_geometry import build_body_geometry_profile, geometry_similarity
from app.services.candidate_selector import choose_best_candidate

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
    _, scores = choose_best_candidate([candidate], build_body_geometry_profile(reference))
    data = scores[0].to_dict()
    assert "penalties" in data
    assert "candidate_profile" in data
    assert data["penalties"]["body_widening"] >= 0


def test_geometry_profile_has_subject_shape_metrics(tmp_path: Path) -> None:
    path = tmp_path / "person.png"
    _person(path, width=400, height=800, body_width=110)
    profile = build_body_geometry_profile(path)
    assert profile.subject_aspect_ratio > 0
    assert 0 <= profile.horizontal_center_ratio <= 1
    assert profile.detector in {"opencv_hog_person", "central_saliency"}
