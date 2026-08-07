from pathlib import Path

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app
from app.services.autonomous_analysis import analyze_image, analyze_person_set, analyze_product


def _image(path: Path, *, x: int = 180, color=(40, 80, 140)) -> Path:
    image = Image.new("RGB", (600, 900), (235, 235, 235))
    draw = ImageDraw.Draw(image)
    draw.ellipse((x, 80, x + 120, 200), fill=(190, 150, 125))
    draw.rectangle((x - 20, 200, x + 140, 700), fill=color)
    draw.rectangle((x, 700, x + 45, 860), fill=(50, 50, 50))
    draw.rectangle((x + 75, 700, x + 120, 860), fill=(50, 50, 50))
    image.save(path)
    return path


def test_capabilities_endpoint():
    response = TestClient(app).get("/api/intelligence/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["analysis_version"] == "3C.1"
    assert data["zero_manual_metadata"] is True
    assert data["provider_neutral"] is True


def test_image_and_person_analysis(tmp_path):
    paths = [_image(tmp_path / f"person_{i}.png", x=150 + i * 12) for i in range(3)]
    result = analyze_image(paths[0])
    assert result.width == 600
    assert result.height == 900
    assert 0 <= result.quality_score <= 1
    person = analyze_person_set(paths)
    assert person["image_count"] == 3
    assert person["best_image_index"] in (0, 1, 2)
    assert len(person["images"]) == 3


def test_product_lock_is_stable(tmp_path):
    paths = [_image(tmp_path / f"garment_{i}.png", color=(25, 40 + i * 3, 80)) for i in range(2)]
    first = analyze_product(paths, "complete shalwar kameez outfit", "overall", "Navy", "Men")
    second = analyze_product(paths, "complete shalwar kameez outfit", "overall", "Navy", "Men")
    assert first.product_type == "multi_piece_outfit"
    assert first.garment_scope == "complete_outfit"
    assert first.reference_count == 2
    assert first.product_lock_signature == second.product_lock_signature
    assert first.product_lock["selected_color_only"] is True
    assert "embroidery" in first.product_lock["preserve"]
