from pathlib import Path

from app.providers.catvton import CatVTONProvider


def test_catvton_extracts_path_result():
    result = CatVTONProvider._extract_result({"path": "result.png", "url": None})
    assert result.image_path == Path("result.png")


def test_catvton_extracts_url_result():
    result = CatVTONProvider._extract_result("https://example.com/result.png")
    assert result.image_url == "https://example.com/result.png"
