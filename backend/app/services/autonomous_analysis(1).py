from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageStat

from app.services.body_geometry import build_body_geometry_profile


@dataclass(slots=True)
class ImageIntelligence:
    source_file: str
    width: int
    height: int
    orientation: str
    framing: str
    camera_angle: str
    pose_family: str
    dominant_colors: list[str]
    brightness: float
    contrast: float
    sharpness: float
    body_visibility_score: float
    quality_score: float
    usable: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ProductIntelligence:
    product_type: str
    garment_scope: str
    inferred_audience: str
    selected_color: str
    reference_count: int
    pose_families: list[str]
    camera_angles: list[str]
    dominant_colors: list[str]
    product_lock_signature: str
    product_lock: dict[str, object]
    references: list[dict[str, object]]
    analysis_version: str = "3C.1"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _color_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    if mx < 45:
        return "black"
    if mn > 220:
        return "white"
    if mx - mn < 18:
        return "gray"
    if r > g * 1.25 and r > b * 1.25:
        return "red" if r > 150 else "brown"
    if g > r * 1.2 and g > b * 1.15:
        return "green"
    if b > r * 1.2 and b > g * 1.15:
        return "blue"
    if r > 160 and g > 120 and b < 110:
        return "orange"
    if r > 150 and b > 130 and g < 150:
        return "pink"
    if r > 120 and b > 120:
        return "purple"
    if r > 150 and g > 150 and b < 130:
        return "yellow"
    return "neutral"


def _dominant_colors(image: Image.Image, count: int = 3) -> list[str]:
    sample = image.convert("RGB").resize((96, 96))
    quantized = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
    colors = quantized.getcolors(maxcolors=96 * 96) or []
    names: list[str] = []
    for _, rgb in sorted(colors, reverse=True):
        name = _color_name(rgb)
        if name not in names:
            names.append(name)
        if len(names) >= count:
            break
    return names or ["neutral"]


def analyze_image(path: Path) -> ImageIntelligence:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        gray = np.asarray(image.convert("L"), dtype=np.uint8)
        stat = ImageStat.Stat(image.convert("L"))
        brightness = float(stat.mean[0])
        contrast = float(stat.stddev[0])
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        colors = _dominant_colors(image)

    geometry = build_body_geometry_profile(path)
    subject_height = geometry.foreground_height_ratio
    subject_width = geometry.foreground_width_ratio
    aspect = width / max(1, height)
    orientation = "portrait" if aspect < 0.82 else "landscape" if aspect > 1.18 else "square"
    framing = "full_body" if subject_height >= 0.72 else "three_quarter" if subject_height >= 0.50 else "upper_body"
    camera_angle = "front" if abs(geometry.horizontal_center_ratio - 0.5) < 0.08 else "left_three_quarter" if geometry.horizontal_center_ratio < 0.5 else "right_three_quarter"
    if geometry.upper_width_ratio > geometry.lower_width_ratio * 1.35:
        pose = "upper_body_emphasis"
    elif geometry.lower_width_ratio > geometry.upper_width_ratio * 1.30:
        pose = "seated_or_wide_stance"
    elif geometry.subject_aspect_ratio < 0.34:
        pose = "side_or_narrow_stance"
    else:
        pose = "standing_neutral"

    body_visibility = max(0.0, min(1.0, 0.65 * subject_height + 0.35 * min(1.0, subject_width / 0.48)))
    sharp_score = min(1.0, sharpness / 450.0)
    exposure_score = max(0.0, 1.0 - abs(brightness - 135.0) / 135.0)
    resolution_score = min(1.0, (width * height) / (1000 * 1400))
    quality = 0.35 * body_visibility + 0.25 * sharp_score + 0.20 * exposure_score + 0.20 * resolution_score
    usable = quality >= 0.42 and width >= 400 and height >= 500
    return ImageIntelligence(
        source_file=str(path), width=width, height=height, orientation=orientation,
        framing=framing, camera_angle=camera_angle, pose_family=pose,
        dominant_colors=colors, brightness=round(brightness, 2), contrast=round(contrast, 2),
        sharpness=round(sharpness, 2), body_visibility_score=round(body_visibility, 4),
        quality_score=round(quality, 4), usable=usable,
    )


def _infer_product_type(description: str, cloth_type: str) -> tuple[str, str]:
    text = description.lower()
    if any(token in text for token in ("shalwar", "kameez", "3 piece", "three piece", "dupatta", "complete outfit", "suit")):
        return "multi_piece_outfit", "complete_outfit"
    if any(token in text for token in ("dress", "gown", "jumpsuit")):
        return "one_piece_dress", "complete_outfit"
    if cloth_type == "lower" or any(token in text for token in ("trouser", "pants", "skirt", "jeans")):
        return "lower_garment", "single_garment"
    if any(token in text for token in ("jacket", "coat", "hoodie")):
        return "outerwear", "layered_garment"
    return "upper_garment", "single_garment"


def analyze_product(paths: Iterable[Path], description: str, cloth_type: str, selected_color: str, audience: str = "unknown") -> ProductIntelligence:
    references = [analyze_image(path) for path in paths]
    if not references:
        raise ValueError("At least one garment reference is required.")
    product_type, scope = _infer_product_type(description, cloth_type)
    colors: list[str] = []
    for ref in references:
        for color in ref.dominant_colors:
            if color not in colors:
                colors.append(color)
    signature_payload = "|".join([
        product_type, scope, selected_color.lower(), str(len(references)),
        *sorted(ref.pose_family + ":" + ref.camera_angle + ":" + ",".join(ref.dominant_colors) for ref in references),
    ])
    signature = sha256(signature_payload.encode("utf-8")).hexdigest()
    lock = {
        "signature": signature,
        "selected_color_only": True,
        "reference_count": len(references),
        "required_components": scope,
        "preserve": ["silhouette", "color", "pattern", "embroidery", "neckline", "sleeves", "length", "closures", "layers", "matching_bottoms"],
        "average_reference_quality": round(mean(ref.quality_score for ref in references), 4),
    }
    return ProductIntelligence(
        product_type=product_type, garment_scope=scope, inferred_audience=audience,
        selected_color=selected_color, reference_count=len(references),
        pose_families=sorted({ref.pose_family for ref in references}),
        camera_angles=sorted({ref.camera_angle for ref in references}),
        dominant_colors=colors[:5], product_lock_signature=signature,
        product_lock=lock, references=[ref.to_dict() for ref in references],
    )


def analyze_person_set(paths: Iterable[Path]) -> dict[str, object]:
    analyses = [analyze_image(path) for path in paths]
    if not analyses:
        raise ValueError("At least one person image is required.")
    ranked = sorted(enumerate(analyses), key=lambda item: item[1].quality_score, reverse=True)
    return {
        "analysis_version": "3C.1",
        "image_count": len(analyses),
        "accepted_count": sum(1 for item in analyses if item.usable),
        "best_image_index": ranked[0][0],
        "recommended_indices": [index for index, item in ranked if item.usable],
        "pose_coverage": sorted({item.pose_family for item in analyses}),
        "camera_coverage": sorted({item.camera_angle for item in analyses}),
        "images": [item.to_dict() for item in analyses],
    }
