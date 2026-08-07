from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_OUTPUT_FORMATS = {"PNG", "JPEG"}


def normalize_for_provider(
    source: Path,
    destination_dir: Path,
    *,
    output_format: str = "PNG",
) -> Path:
    """Normalize an image for stable provider uploads.

    The function:

    - validates that the source is an existing file;
    - applies EXIF orientation;
    - converts unsupported color modes;
    - preserves transparency for PNG;
    - composites transparency onto white for JPEG;
    - writes a uniquely named normalized output file.
    """
    source = Path(source)
    destination_dir = Path(destination_dir)

    if not source.exists():
        raise FileNotFoundError(
            f"Image does not exist: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Image path is not a file: {source}"
        )

    normalized_format = output_format.strip().upper()

    if normalized_format == "JPG":
        normalized_format = "JPEG"

    if normalized_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            "Unsupported output format: "
            f"{output_format}. Supported formats are PNG and JPEG."
        )

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = (
        ".jpg"
        if normalized_format == "JPEG"
        else ".png"
    )

    destination = (
        destination_dir
        / f"{source.stem}_{uuid4().hex[:10]}{suffix}"
    )

    try:
        with Image.open(source) as opened_image:
            image = ImageOps.exif_transpose(
                opened_image
            )

            if normalized_format == "JPEG":
                normalized_image = (
                    _prepare_jpeg(image)
                )

                normalized_image.save(
                    destination,
                    format="JPEG",
                    quality=95,
                    optimize=True,
                    progressive=True,
                )

            else:
                normalized_image = (
                    _prepare_png(image)
                )

                normalized_image.save(
                    destination,
                    format="PNG",
                    optimize=True,
                )

    except UnidentifiedImageError as exc:
        raise ValueError(
            f"Unsupported or invalid image file: {source}"
        ) from exc

    except OSError as exc:
        raise ValueError(
            f"Could not normalize image {source}: {exc}"
        ) from exc

    return destination


def _has_transparency(image: Image.Image) -> bool:
    """Return whether the image contains transparency."""
    if image.mode in {"RGBA", "LA"}:
        return True

    if image.mode == "P":
        return "transparency" in image.info

    return False


def _prepare_jpeg(
    image: Image.Image,
) -> Image.Image:
    """Convert an image into JPEG-compatible RGB mode."""
    if _has_transparency(image):
        rgba = image.convert("RGBA")

        background = Image.new(
            "RGB",
            rgba.size,
            (255, 255, 255),
        )

        background.paste(
            rgba,
            mask=rgba.getchannel("A"),
        )

        return background

    return image.convert("RGB")


def _prepare_png(
    image: Image.Image,
) -> Image.Image:
    """Convert an image into a stable PNG-compatible mode."""
    if _has_transparency(image):
        return image.convert("RGBA")

    return image.convert("RGB")