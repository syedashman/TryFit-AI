from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.services.commercial_prompt import build_commercial_instructions
from app.services.garment_analyzer import analyze_garment
from app.services.quality_engine import evaluate_candidate


def test_commercial_prompt_blocks_known_distortions() -> None:
    text = build_commercial_instructions("brown kurta", "overall", "brown")
    assert "Do not add muscles" in text
    assert "compress the legs" in text
    assert "body silhouette" in text


def test_garment_analyzer_detects_full_outfit_and_color(tmp_path: Path) -> None:
    path = tmp_path / "garment.png"
    Image.new("RGB", (100, 200), (95, 55, 35)).save(path)
    result = analyze_garment(path, "men brown kurta shalwar", "upper")
    assert result.cloth_type == "overall"
    assert result.category == "full_outfit"
    assert result.dominant_color_name == "brown"


def test_quality_engine_rejects_below_threshold() -> None:
    report = evaluate_candidate({
        "selected_candidate_index": 0,
        "selected_final_geometry_score": 0.72,
        "candidate_scores": [{"hard_rejected": False}],
    }, 0.86)
    assert report.accepted is False
    assert report.reason == "quality_below_threshold"


def test_quality_engine_accepts_good_candidate() -> None:
    report = evaluate_candidate({
        "selected_candidate_index": 0,
        "selected_final_geometry_score": 0.93,
        "candidate_scores": [{"hard_rejected": False}],
    }, 0.86)
    assert report.accepted is True


def test_phase4_settings_validate() -> None:
    settings = Settings(
        commercial_quality_threshold=0.9,
        commercial_max_generation_rounds=2,
    )
    assert settings.commercial_api_enabled is True
    assert settings.commercial_quality_threshold == 0.9
