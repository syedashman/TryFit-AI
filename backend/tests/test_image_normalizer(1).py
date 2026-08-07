from pathlib import Path

from PIL import Image

from app.services.image_normalizer import normalize_for_provider


def test_rgba_can_be_normalized_to_jpeg(tmp_path: Path):
    source = tmp_path / "rgba.png"
    Image.new("RGBA", (20, 20), (255, 0, 0, 100)).save(source)

    result = normalize_for_provider(
        source, tmp_path / "normalized", output_format="JPEG"
    )

    with Image.open(result) as image:
        assert image.mode == "RGB"
        assert image.format == "JPEG"


def test_rgba_is_preserved_safely_as_png(tmp_path: Path):
    source = tmp_path / "rgba.png"
    Image.new("RGBA", (20, 20), (0, 255, 0, 100)).save(source)

    result = normalize_for_provider(source, tmp_path / "normalized")

    with Image.open(result) as image:
        assert image.mode == "RGBA"
        assert image.format == "PNG"
