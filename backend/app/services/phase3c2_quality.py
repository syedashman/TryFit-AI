from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


@dataclass(slots=True)
class GarmentQualityProfile:
    path: str
    garment_mean_hsv: np.ndarray
    reference_bbox: dict[str, float] | None
    target_rgb: np.ndarray | None


_GARMENT_PROFILE_CACHE: dict[str, GarmentQualityProfile] = {}


def get_garment_quality_profile(garment: Path | str | GarmentQualityProfile) -> GarmentQualityProfile:
    if isinstance(garment, GarmentQualityProfile):
        return garment
    key = str(Path(garment).resolve())
    if key in _GARMENT_PROFILE_CACHE:
        return _GARMENT_PROFILE_CACHE[key]

    garment_rgb = _rgb(Path(garment))
    garment_pixels = _garment_pixels(garment_rgb)
    garment_hsv = cv2.cvtColor(garment_pixels.reshape(1, -1, 3), cv2.COLOR_RGB2HSV).astype(np.float32)
    garment_mean_hsv = garment_hsv.reshape(-1, 3).mean(axis=0)
    target_rgb = garment_pixels.reshape(-1, 3).astype(np.float32).mean(axis=0)
    reference_bbox = _bbox_metrics(_foreground_mask(garment_rgb))

    profile = GarmentQualityProfile(
        path=key,
        garment_mean_hsv=garment_mean_hsv,
        reference_bbox=reference_bbox,
        target_rgb=target_rgb,
    )
    if len(_GARMENT_PROFILE_CACHE) > 32:
        _GARMENT_PROFILE_CACHE.clear()
    _GARMENT_PROFILE_CACHE[key] = profile
    return profile


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


def _estimate_background_rgb(image: np.ndarray) -> np.ndarray:
    """Estimate background color from a thin border strip (rarely garment)."""
    height, width = image.shape[:2]
    strip = max(4, int(min(height, width) * 0.04))
    border_pixels = np.concatenate([
        image[:strip, :, :].reshape(-1, 3),
        image[-strip:, :, :].reshape(-1, 3),
        image[:, :strip, :].reshape(-1, 3),
        image[:, -strip:, :].reshape(-1, 3),
    ])
    return np.median(border_pixels, axis=0)


def _garment_pixels(image: np.ndarray) -> np.ndarray:
    """Isolate pixels that differ from the estimated background, within the
    central body region. Works for garments of any color (including near-
    black or near-white) since it compares against the *actual* background
    color rather than assuming background is light or dark."""
    height, width = image.shape[:2]
    crop = image[int(height * 0.12): int(height * 0.92), int(width * 0.18): int(width * 0.82)]
    background_rgb = _estimate_background_rgb(image)
    flat = crop.reshape(-1, 3).astype(np.float32)
    distance = np.linalg.norm(flat - background_rgb, axis=1)
    threshold = 35.0
    garment_pixels = flat[distance > threshold]
    if len(garment_pixels) < max(30, int(len(flat) * 0.03)):
        # Not enough contrast from background detected; fall back to the
        # full crop rather than an empty/tiny sample.
        garment_pixels = flat
    return garment_pixels.astype(np.uint8)


def garment_color_similarity(garment: Path | str | GarmentQualityProfile, result_path: Path) -> float:
    """Estimate outfit color preservation by comparing garment-only pixels
    (background subtracted) between the reference garment photo and the
    generated result, so a wrong-color swap (e.g. black vs white) is
    reliably detected regardless of how much of the frame is background."""
    profile = get_garment_quality_profile(garment)
    result = _rgb(result_path)

    result_pixels = _garment_pixels(result)
    result_hsv = cv2.cvtColor(result_pixels.reshape(1, -1, 3), cv2.COLOR_RGB2HSV).astype(np.float32)
    result_mean = result_hsv.reshape(-1, 3).mean(axis=0)

    hue_delta = min(abs(float(profile.garment_mean_hsv[0] - result_mean[0])), 180.0 - abs(float(profile.garment_mean_hsv[0] - result_mean[0]))) / 90.0
    sat_delta = abs(float(profile.garment_mean_hsv[1] - result_mean[1])) / 255.0
    val_delta = abs(float(profile.garment_mean_hsv[2] - result_mean[2])) / 255.0

    # Brightness (value) carries most of the signal for neutral garments
    # (black/white/grey), where hue is unreliable/near-random.
    score = max(0.0, 1.0 - (0.15 * hue_delta + 0.15 * sat_delta + 0.70 * val_delta))
    return round(score, 4)

def _foreground_mask(image: np.ndarray, threshold: float = 35.0) -> np.ndarray:
    """Boolean mask of pixels that differ from the estimated background."""
    background_rgb = _estimate_background_rgb(image)
    distance = np.linalg.norm(image.astype(np.float32) - background_rgb, axis=2)
    return distance > threshold


def _color_region_mask(
    image: np.ndarray,
    target_rgb: np.ndarray,
    tolerance: float = 60.0,
) -> np.ndarray:
    """Boolean mask of pixels close (in RGB) to the reference garment color.

    Used to locate where the garment appears on the generated person so we can
    measure its vertical extent (a long kameez covers the thighs, a short shirt
    stops at the waist)."""
    distance = np.linalg.norm(image.astype(np.float32) - target_rgb, axis=2)
    return distance < tolerance


def _bbox_metrics(mask: np.ndarray) -> dict[str, float] | None:
    """Return aspect ratio and vertical coverage of a mask's bounding box.

    Returns None when too few pixels are present for a reliable estimate, so
    callers can fall back to neutral (non-punishing) values."""
    ys, xs = np.where(mask)
    if len(ys) < 40:
        return None
    height = float(ys.max() - ys.min() + 1)
    width = float(xs.max() - xs.min() + 1)
    frame_h, frame_w = mask.shape[:2]
    return {
        "aspect": round(width / max(1.0, height), 4),
        "vertical_coverage": round(height / float(frame_h), 4),
        "horizontal_coverage": round(width / float(frame_w), 4),
    }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(max(low, min(high, value)))


def garment_structure_metrics(
    garment: Path | str | GarmentQualityProfile,
    result_path: Path,
) -> dict[str, Any]:
    """Conservative structural validation signal for garment fidelity.

    Compares the reference garment's silhouette (bounding-box aspect ratio and
    vertical coverage) against where the same-colored garment appears on the
    generated person. This is intentionally lenient: it is designed to catch
    strong structural changes (e.g. a long garment converted into a short
    shirt), NOT to perfectly classify garment semantics. When detection is
    unreliable it returns neutral scores and does not flag a violation.

    Returns:
        {
            "structure_score": float,   # 0..1, silhouette aspect agreement
            "length_score": float,      # 0..1, garment vertical-length agreement
            "reference_aspect": float,
            "candidate_aspect": float,
            "long_garment_violation": bool,
            "detection_reliable": bool,
        }
    """
    neutral: dict[str, Any] = {
        "structure_score": 0.5,
        "length_score": 0.5,
        "reference_aspect": 0.0,
        "candidate_aspect": 0.0,
        "long_garment_violation": False,
        "detection_reliable": False,
        "confidence": 0.0,
        "length_ratio": 1.0,
    }

    profile = get_garment_quality_profile(garment)
    if profile.reference_bbox is None or profile.target_rgb is None:
        return neutral

    result = _rgb(result_path)
    reference = profile.reference_bbox

    # Dominant garment color, used to locate the garment on the generated body.
    target_rgb = profile.target_rgb
    candidate = _bbox_metrics(_color_region_mask(result, target_rgb))
    if candidate is None:
        # Could not confidently locate the garment on the result; stay neutral.
        neutral["reference_aspect"] = reference["aspect"]
        return neutral

    reference_aspect = reference["aspect"]
    candidate_aspect = candidate["aspect"]
    reference_cov = reference["vertical_coverage"]
    candidate_cov = candidate["vertical_coverage"]

    # Silhouette agreement via bounding-box aspect ratio. Normalization is
    # deliberately generous so only large silhouette changes reduce the score.
    aspect_diff = abs(reference_aspect - candidate_aspect)
    structure_score = _clamp(1.0 - aspect_diff / 1.2)

    # Length agreement: full score when the candidate garment reaches at least
    # 75% of the reference garment's relative vertical extent.
    length_ratio = candidate_cov / max(reference_cov, 1e-3)
    length_score = _clamp(length_ratio / 0.75)

    # Long-garment preservation. A long kurta/kameez is tall (high vertical
    # coverage) and narrow (aspect <= ~0.9). When the reference is clearly a
    # long garment, we require the candidate to keep a meaningful fraction of
    # that length. This is stronger than the old "candidate_cov <= 0.35"
    # absolute rule: a dark long kurta rendered as a dark short shirt keeps a
    # high COLOR score but its garment region collapses to a much smaller
    # vertical extent, which `length_ratio` captures directly.
    reference_long = reference_cov >= 0.55 and reference_aspect <= 0.95

    # How confidently we believe the reference is a long garment. Taller and
    # narrower references give higher confidence; this scales the violation
    # so borderline garments do not trip a hard reject.
    length_conf = _clamp((reference_cov - 0.55) / 0.25)
    aspect_conf = _clamp((0.95 - reference_aspect) / 0.35)
    confidence = round(min(length_conf, aspect_conf), 4) if reference_long else 0.0

    # Violation when a clearly-long reference garment is shortened to well
    # under ~60% of its relative length. Small wearing/pose/perspective
    # differences keep length_ratio near 1.0 and do NOT trip this.
    long_garment_violation = bool(
        reference_long
        and confidence >= 0.35
        and length_ratio <= 0.60
    )

    return {
        "structure_score": round(structure_score, 4),
        "length_score": round(length_score, 4),
        "reference_aspect": reference_aspect,
        "candidate_aspect": candidate_aspect,
        "long_garment_violation": long_garment_violation,
        "detection_reliable": True,
        "confidence": confidence,
        "length_ratio": round(float(length_ratio), 4),
    }


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
