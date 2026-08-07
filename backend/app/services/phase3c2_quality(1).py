from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


def _rgb(path: Path, size: tuple[int, int] = (256, 256)) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB").resize(size), dtype=np.uint8)


def perceptual_hash(path: Path, hash_size: int = 16) -> str:
    """Return a compact difference hash used for duplicate-result detection."""
    with Image.open(path) as image:
        gray = np.asarray(
            image.convert("L").resize((hash_size + 1, hash_size)),
            dtype=np.int16,
        )
    bits = gray[:, 1:] > gray[:, :-1]
    packed = np.packbits(bits.reshape(-1))
    return packed.tobytes().hex()


def hash_similarity(first: str, second: str) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0
    left = bytes.fromhex(first)
    right = bytes.fromhex(second)
    differing = sum((a ^ b).bit_count() for a, b in zip(left, right))
    total = max(1, len(left) * 8)
    return round(1.0 - differing / total, 4)


def _hsv_histogram(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    # Central body region suppresses most background while retaining the outfit.
    crop = image[int(height * 0.12): int(height * 0.92), int(width * 0.18): int(width * 0.82)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    return histogram


def garment_color_similarity(garment_path: Path, result_path: Path) -> float:
    """Estimate outfit color/palette preservation without requiring a paid model."""
    garment = _rgb(garment_path)
    result = _rgb(result_path)
    correlation = cv2.compareHist(_hsv_histogram(garment), _hsv_histogram(result), cv2.HISTCMP_CORREL)
    correlation_score = max(0.0, min(1.0, (float(correlation) + 1.0) / 2.0))
    garment_hsv = cv2.cvtColor(garment, cv2.COLOR_RGB2HSV).astype(np.float32)
    result_hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV).astype(np.float32)
    garment_mean = garment_hsv.reshape(-1, 3).mean(axis=0)
    result_mean = result_hsv.reshape(-1, 3).mean(axis=0)
    hue_delta = min(abs(float(garment_mean[0] - result_mean[0])), 180.0 - abs(float(garment_mean[0] - result_mean[0]))) / 90.0
    sat_delta = abs(float(garment_mean[1] - result_mean[1])) / 255.0
    val_delta = abs(float(garment_mean[2] - result_mean[2])) / 255.0
    mean_score = max(0.0, 1.0 - (0.55 * hue_delta + 0.30 * sat_delta + 0.15 * val_delta))
    return round(0.35 * correlation_score + 0.65 * mean_score, 4)


def pose_diversity_score(result_path: Path, sibling_paths: list[Path]) -> tuple[float, str, float]:
    current_hash = perceptual_hash(result_path)
    if not sibling_paths:
        return 1.0, current_hash, 0.0
    similarities = [hash_similarity(current_hash, perceptual_hash(path)) for path in sibling_paths if path.exists()]
    highest = max(similarities, default=0.0)
    return round(1.0 - highest, 4), current_hash, round(highest, 4)


def build_phase3c2_report(
    *,
    garment_path: Path,
    result_path: Path,
    sibling_paths: list[Path],
    provider_metadata: dict[str, Any],
) -> dict[str, Any]:
    diversity, image_hash, highest_duplicate_similarity = pose_diversity_score(result_path, sibling_paths)
    color_similarity = garment_color_similarity(garment_path, result_path)
    geometry = provider_metadata.get("selected_final_geometry_score", 0.0)
    try:
        geometry_score = max(0.0, min(1.0, float(geometry)))
    except (TypeError, ValueError):
        geometry_score = 0.0
    composite = 0.50 * geometry_score + 0.35 * color_similarity + 0.15 * diversity
    return {
        "phase": "sprint_4_phase_3c_2",
        "geometry_score": round(geometry_score, 4),
        "garment_color_similarity": color_similarity,
        "pose_diversity_score": diversity,
        "highest_sibling_similarity": highest_duplicate_similarity,
        "perceptual_hash": image_hash,
        "duplicate_warning": highest_duplicate_similarity >= 0.94,
        "product_integrity_warning": color_similarity < 0.45,
        "commercial_composite_score": round(composite, 4),
        "limitations": "Pose diversity and product integrity are validation signals; Vertex Virtual Try-On itself does not guarantee reference-pose transfer.",
    }
