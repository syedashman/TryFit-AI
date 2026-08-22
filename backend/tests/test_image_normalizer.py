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


def test_person_dimensions_are_upscaled_without_stretching(tmp_path: Path):
    source = tmp_path / "person.jpg"
    Image.new("RGB", (365, 547), (120, 100, 90)).save(source)

    result = normalize_for_provider(
        source,
        tmp_path / "normalized",
        min_width=400,
        min_height=500,
        max_dimension=2048,
    )

    with Image.open(result) as image:
        assert image.size == (400, 599)
        assert image.width / image.height == 400 / 599


def test_large_person_dimensions_are_downscaled_without_stretching(tmp_path: Path):
    source = tmp_path / "large.jpg"
    Image.new("RGB", (4000, 3000), (120, 100, 90)).save(source)

    result = normalize_for_provider(
        source,
        tmp_path / "normalized",
        min_width=400,
        min_height=500,
        max_dimension=2048,
    )

    with Image.open(result) as image:
        assert image.size == (2048, 1536)
