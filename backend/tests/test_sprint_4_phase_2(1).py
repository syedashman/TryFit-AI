from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.services.commercial_prompt import build_commercial_instructions
from app.services.visual_quality import (
    build_realism_directives,
    enhance_result_image,
)


def test_prompt_contains_fabric_realism_rules() -> None:
    text = build_commercial_instructions("printed kurta", "overall", "red")
    assert "physically plausible fabric drape" in text
    assert "contact shadows" in text
    assert "texture smearing" in text
    assert "natural trouser or dress fall" in text


def test_scoped_directives_protect_untouched_regions() -> None:
    assert "lower body untouched" in build_realism_directives("upper")
    assert "upper body untouched" in build_realism_directives("lower")


def test_enhancement_preserves_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "result.png"
    image = Image.new("RGB", (320, 480), (125, 115, 105))
    draw = ImageDraw.Draw(image)
    for y in range(40, 440, 12):
        draw.line((80, y, 240, y), fill=(160, 70, 60), width=3)
    image.save(path)

    report = enhance_result_image(path)
    with Image.open(path) as result:
        assert result.size == (320, 480)
    assert report.applied is True
    assert report.width == 320
    assert report.height == 480
    assert report.profile == "conservative_fabric_refinement"


def test_disabled_enhancement_is_non_destructive(tmp_path: Path) -> None:
    path = tmp_path / "result.png"
    Image.new("RGBA", (64, 96), (10, 20, 30, 120)).save(path)
    before = path.read_bytes()
    report = enhance_result_image(path, enabled=False)
    assert path.read_bytes() == before
    assert report.applied is False


def test_invalid_enhancement_factor_rejected(tmp_path: Path) -> None:
    path = tmp_path / "result.png"
    Image.new("RGB", (32, 32), "white").save(path)
    with pytest.raises(ValueError):
        enhance_result_image(path, sharpness=0)


def test_settings_validate_visual_factors() -> None:
    settings = Settings(_env_file=None, visual_enhancement_contrast=1.1)
    assert settings.visual_enhancement_enabled is True
    with pytest.raises(ValueError):
        Settings(_env_file=None, visual_enhancement_color=3.0)
