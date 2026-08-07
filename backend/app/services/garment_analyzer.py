from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(slots=True)
class GarmentAnalysis:
    dominant_color_rgb: tuple[int, int, int]
    dominant_color_name: str
    category: str
    cloth_type: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_COLOR_PALETTE: dict[str, tuple[int, int, int]] = {
    "black": (25, 25, 25),
    "white": (235, 235, 235),
    "gray": (128, 128, 128),
    "brown": (105, 70, 45),
    "navy": (35, 50, 90),
    "blue": (55, 105, 180),
    "green": (65, 120, 70),
    "olive": (105, 110, 55),
    "maroon": (110, 35, 50),
    "red": (190, 55, 55),
    "pink": (210, 125, 155),
    "purple": (115, 70, 145),
    "orange": (210, 115, 45),
    "yellow": (220, 190, 55),
    "beige": (190, 170, 135),
    "cream": (225, 215, 185),
    "teal": (45, 125, 125),
}


_CATEGORY_RULES: tuple[
    tuple[tuple[str, ...], str, str],
    ...,
] = (
    (
        (
            "shalwar kameez",
            "salwar kameez",
            "three piece",
            "3 piece",
            "2 piece",
            "co ord",
            "coord set",
            "kurta pajama",
            "kurta shalwar",
            "dress",
            "abaya",
            "gown",
            "jumpsuit",
            "romper",
            "suit",
        ),
        "full_outfit",
        "overall",
    ),
    (
        (
            "shirt",
            "t-shirt",
            "tshirt",
            "top",
            "jacket",
            "hoodie",
            "blouse",
            "kurti",
            "kurta",
            "sweater",
            "coat",
            "waistcoat",
        ),
        "upper_garment",
        "upper",
    ),
    (
        (
            "pant",
            "pants",
            "trouser",
            "trousers",
            "jean",
            "jeans",
            "skirt",
            "short",
            "shorts",
            "legging",
            "leggings",
            "pajama",
            "shalwar",
            "salwar",
        ),
        "lower_garment",
        "lower",
    ),
)


def _color_name(
    rgb: tuple[int, int, int],
) -> str:
    return min(
        _COLOR_PALETTE,
        key=lambda name: sum(
            (
                rgb[index]
                - _COLOR_PALETTE[name][index]
            )
            ** 2
            for index in range(3)
        ),
    )


def _normalized_cloth_type(
    requested_cloth_type: str,
) -> str:
    normalized = (
        requested_cloth_type or ""
    ).strip().lower()

    if normalized not in {
        "upper",
        "lower",
        "overall",
    }:
        return "overall"

    return normalized


def _load_pixels(
    path: Path,
) -> np.ndarray:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Garment image does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Garment image path is not a file: {path}"
        )

    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(
                opened
            ).convert("RGBA")

            image.thumbnail(
                (160, 160),
                Image.Resampling.LANCZOS,
            )

            rgba = np.asarray(
                image,
                dtype=np.uint8,
            )

    except UnidentifiedImageError as exc:
        raise ValueError(
            f"Unsupported or invalid garment image: {path}"
        ) from exc

    except OSError as exc:
        raise ValueError(
            f"Could not read garment image {path}: {exc}"
        ) from exc

    if rgba.size == 0:
        raise ValueError(
            f"Garment image contains no pixels: {path}"
        )

    alpha = rgba[:, :, 3].reshape(-1)
    rgb = rgba[:, :, :3].reshape(-1, 3)

    visible = rgb[alpha > 20]

    if visible.size == 0:
        visible = rgb

    return visible


def _dominant_rgb(
    pixels: np.ndarray,
) -> tuple[int, int, int]:
    brightness = np.mean(
        pixels,
        axis=1,
    )

    # Remove near-white and near-black backgrounds when enough garment
    # pixels remain. This is intentionally conservative so light garments
    # are not discarded completely.
    useful = pixels[
        (brightness < 242)
        & (brightness > 12)
    ]

    minimum_useful = max(
        40,
        int(len(pixels) * 0.05),
    )

    if len(useful) < minimum_useful:
        useful = pixels

    median = np.median(
        useful,
        axis=0,
    )

    return tuple(
        int(
            max(
                0,
                min(255, round(value)),
            )
        )
        for value in median
    )


def _infer_category(
    description: str,
    requested_cloth_type: str,
) -> tuple[str, str, float]:
    text = (
        description or ""
    ).strip().lower()

    requested = _normalized_cloth_type(
        requested_cloth_type
    )

    for words, category, inferred_type in _CATEGORY_RULES:
        if any(
            word in text
            for word in words
        ):
            confidence = (
                0.86
                if inferred_type == requested
                else 0.78
            )

            return (
                category,
                inferred_type,
                confidence,
            )

    fallback_category = {
        "upper": "upper_garment",
        "lower": "lower_garment",
        "overall": "full_outfit",
    }[requested]

    return (
        fallback_category,
        requested,
        0.60,
    )


def analyze_garment(
    path: Path,
    description: str,
    requested_cloth_type: str,
) -> GarmentAnalysis:
    pixels = _load_pixels(
        Path(path)
    )

    dominant_rgb = _dominant_rgb(
        pixels
    )

    category, cloth_type, confidence = (
        _infer_category(
            description,
            requested_cloth_type,
        )
    )

    return GarmentAnalysis(
        dominant_color_rgb=dominant_rgb,
        dominant_color_name=_color_name(
            dominant_rgb
        ),
        category=category,
        cloth_type=cloth_type,
        confidence=round(
            max(
                0.0,
                min(1.0, confidence),
            ),
            4,
        ),
    )