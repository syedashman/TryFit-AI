from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.services.body_geometry import (
    BodyGeometryProfile,
    build_body_geometry_profile,
    distortion_penalties,
    geometry_similarity,
)
from app.services.phase3c2_quality import (
    GarmentQualityProfile,
    garment_color_similarity,
    garment_structure_metrics,
    get_garment_quality_profile,
)

# Neutral fallback used when a validation signal cannot be computed. A failed
# validator must NEVER become a perfect (1.0) score, because that would let a
# broken/unmeasurable candidate win selection. 0.5 keeps it competitive but not
# preferred, and the failure is recorded in `validation_errors` for debugging.
NEUTRAL_VALIDATION_SCORE = 0.5

# Candidate scoring weights. Starting values from the garment-consistency spec;
# exposed here so they can be tuned without touching the scoring logic.
WEIGHT_RENDER_GEOMETRY = 0.30
WEIGHT_FULL_BODY_GEOMETRY = 0.10
WEIGHT_GARMENT_COLOR = 0.20
WEIGHT_GARMENT_STRUCTURE = 0.25
WEIGHT_GARMENT_LENGTH = 0.15

# Hard-rejection thresholds for garment fidelity (separate from body geometry).
COLOR_HARD_REJECT_BELOW = 0.55
STRUCTURE_HARD_REJECT_BELOW = 0.40
LENGTH_HARD_REJECT_BELOW = 0.40
IDENTITY_HARD_REJECT_BELOW = 0.32

# Penalty applied to a hard-rejected candidate's final score so an eligible
# candidate is always preferred when one exists.
HARD_REJECT_PENALTY = 0.30


@dataclass(slots=True)
class CandidateScore:
    index: int
    path: str
    geometry_similarity: float
    full_body_similarity: float
    final_score: float
    hard_rejected: bool
    penalties: dict[str, float]
    candidate_profile: dict[str, object]
    identity_score: float = 1.0
    identity_reliable: bool = False
    catalog_face_score: float = 0.0
    catalog_leakage: bool = False
    garment_color_score: float = 1.0
    garment_structure_score: float = 1.0
    garment_length_score: float = 1.0
    long_garment_violation: bool = False
    long_garment_confidence: float = 0.0
    semantic_fidelity: dict[str, object] | None = None
    rejection_reasons: list[str] | None = None
    validation_errors: dict[str, str] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "index": self.index,
            "path": self.path,
            "geometry_similarity":
                self.geometry_similarity,
            "full_body_similarity":
                self.full_body_similarity,
            "garment_color_score":
                self.garment_color_score,
            "garment_structure_score":
                self.garment_structure_score,
            "garment_length_score":
                self.garment_length_score,
            "long_garment_violation":
                self.long_garment_violation,
            "long_garment_confidence":
                self.long_garment_confidence,
            "final_score": self.final_score,
            "identity_score": self.identity_score,
            "identity_reliable": self.identity_reliable,
            "catalog_face_score": self.catalog_face_score,
            "catalog_leakage": self.catalog_leakage,
            "hard_rejected":
                self.hard_rejected,
            "rejection_reasons":
                list(self.rejection_reasons or []),
            "penalties": self.penalties,
            "candidate_profile":
                self.candidate_profile,
        }

        if self.semantic_fidelity is not None:
            payload["semantic_fidelity"] = (
                self.semantic_fidelity
            )

        if self.validation_errors:
            payload["validation_errors"] = (
                self.validation_errors
            )

        if self.error:
            payload["error"] = self.error

        return payload


class NoEligibleCandidateError(ValueError):
    """Raised when every evaluated candidate fails a hard quality gate."""

    def __init__(self, scores: list[CandidateScore]) -> None:
        self.scores = scores
        super().__init__("No eligible candidate passed the quality gates.")


_FACE_DETECTORS: list[cv2.CascadeClassifier] | None = None
_FACE_CROP_CACHE: dict[str, np.ndarray | None] = {}


def _get_face_detectors() -> list[cv2.CascadeClassifier]:
    global _FACE_DETECTORS
    if _FACE_DETECTORS is None:
        _FACE_DETECTORS = [
            cv2.CascadeClassifier(
                str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
            ),
            cv2.CascadeClassifier(
                str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml")
            ),
        ]
    return _FACE_DETECTORS


def _crop_face(path: Path | None) -> np.ndarray | None:
    if path is None:
        return None
    path_obj = Path(path)
    key = str(path_obj.resolve()) if path_obj.exists() else str(path_obj)
    if key in _FACE_CROP_CACHE:
        return _FACE_CROP_CACHE[key]
    if not path_obj.exists() or not path_obj.is_file():
        return None
    image = cv2.imread(str(path_obj), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    faces = []
    for detector in _get_face_detectors():
        detected = detector.detectMultiScale(
            image,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(24, 24),
        )
        if len(detected):
            faces = detected
            break
    if len(faces) == 0:
        if len(_FACE_CROP_CACHE) > 64:
            _FACE_CROP_CACHE.clear()
        _FACE_CROP_CACHE[key] = None
        return None
    x, y, width, height = max(faces, key=lambda item: item[2] * item[3])
    padding_x = int(width * 0.45)
    padding_y = int(height * 0.65)
    left = max(0, x - padding_x)
    top = max(0, y - padding_y)
    right = min(image.shape[1], x + width + padding_x)
    bottom = min(image.shape[0], y + height + padding_y)
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        if len(_FACE_CROP_CACHE) > 64:
            _FACE_CROP_CACHE.clear()
        _FACE_CROP_CACHE[key] = None
        return None
    result = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    if len(_FACE_CROP_CACHE) > 64:
        _FACE_CROP_CACHE.clear()
    _FACE_CROP_CACHE[key] = result
    return result


def _compare_cropped_faces(
    reference: np.ndarray | None,
    candidate: np.ndarray | None,
) -> tuple[float, bool]:
    if reference is None or candidate is None:
        return 0.5, False

    def normalized(value: np.ndarray) -> np.ndarray:
        value = value - float(value.mean())
        norm = float(np.linalg.norm(value))
        return value / norm if norm > 0.0 else value

    reference_edges = cv2.Laplacian(reference, cv2.CV_32F)
    candidate_edges = cv2.Laplacian(candidate, cv2.CV_32F)
    pixel_similarity = float(
        np.dot(
            normalized(reference).ravel(),
            normalized(candidate).ravel(),
        )
    )
    edge_similarity = float(
        np.dot(
            normalized(reference_edges).ravel(),
            normalized(candidate_edges).ravel(),
        )
    )
    similarity = 0.35 * pixel_similarity + 0.65 * edge_similarity
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0)), True


def _face_identity_signal(
    reference_path: Path,
    candidate_path: Path,
) -> tuple[float, bool]:
    """Compare detected head regions without treating missing detections as failure."""
    return _compare_cropped_faces(_crop_face(reference_path), _crop_face(candidate_path))


def _hard_reject(
    penalties: dict[str, float],
) -> bool:
    """Reject only when distortion evidence is strong."""
    canvas_changed = (
        penalties.get(
            "canvas_aspect_change",
            0.0,
        )
        > 0.20
    )

    compressed_and_wide = (
        penalties.get(
            "height_compression",
            0.0,
        )
        > 0.24
        and penalties.get(
            "body_widening",
            0.0,
        )
        > 0.12
    )

    extreme_compression = (
        penalties.get(
            "height_compression",
            0.0,
        )
        > 0.38
    )

    extreme_widening = (
        penalties.get(
            "body_widening",
            0.0,
        )
        > 0.32
    )

    return bool(
        canvas_changed
        or compressed_and_wide
        or extreme_compression
        or extreme_widening
    )


def choose_best_candidate(
    candidate_paths: list[Path],
    render_reference: BodyGeometryProfile,
    full_body_reference:
        BodyGeometryProfile | None = None,
    garment_reference_path: Path | None = None,
    identity_reference_path: Path | None = None,
    catalog_identity_reference_path: Path | None = None,
) -> tuple[Path, list[CandidateScore]]:
    if not candidate_paths:
        raise ValueError(
            "At least one candidate is required."
        )

    normalized_paths = [
        Path(path)
        for path in candidate_paths
    ]

    ref_face = _crop_face(identity_reference_path) if identity_reference_path else None
    cat_face = _crop_face(catalog_identity_reference_path) if catalog_identity_reference_path else None
    garment_profile = get_garment_quality_profile(garment_reference_path) if garment_reference_path else None

    scores: list[CandidateScore] = []

    for index, path in enumerate(
        normalized_paths
    ):
        if not path.exists() or not path.is_file():
            scores.append(
                CandidateScore(
                    index=index,
                    path=str(path),
                    geometry_similarity=0.0,
                    full_body_similarity=0.0,
                    final_score=0.0,
                    hard_rejected=True,
                    penalties={},
                    candidate_profile={},
                    error=(
                        "Candidate image does not "
                        "exist or is not a file."
                    ),
                )
            )
            continue

        try:
            candidate = (
                build_body_geometry_profile(
                    path
                )
            )

            render_score = (
                geometry_similarity(
                    render_reference,
                    candidate,
                )
            )

            full_score = (
                geometry_similarity(
                    full_body_reference,
                    candidate,
                )
                if full_body_reference
                is not None
                else render_score
            )

            penalties = (
                distortion_penalties(
                    render_reference,
                    candidate,
                )
            )

            # Body-geometry distortion is tracked independently of garment
            # fidelity so the provider can tell the two failure classes apart
            # (distorted_tryon_result vs garment_fidelity_failed).
            geometry_rejected = _hard_reject(penalties)

            validation_errors: dict[str, str] = {}

            identity_score = 1.0
            identity_reliable = False
            if identity_reference_path is not None:
                identity_score, identity_reliable = _face_identity_signal(
                    identity_reference_path,
                    path,
                )
            catalog_face_score = 0.0
            catalog_leakage = False
            if catalog_identity_reference_path is not None:
                catalog_face_score, catalog_face_reliable = (
                    _face_identity_signal(
                        catalog_identity_reference_path,
                        path,
                    )
                )
                catalog_leakage = bool(
                    identity_reliable
                    and catalog_face_reliable
                    and catalog_face_score >= 0.60
                    and catalog_face_score > identity_score + 0.08
                )

            # --- Garment color validation ---
            # A validator failure must NOT become a perfect score. Fall back to
            # a neutral 0.5 and record the failure for debugging.
            color_score = 1.0
            if garment_profile is not None:
                try:
                    color_score = float(
                        garment_color_similarity(
                            garment_profile,
                            path,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    color_score = (
                        NEUTRAL_VALIDATION_SCORE
                    )
                    validation_errors["color"] = (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

            # --- Garment structure / length validation ---
            structure_score = 1.0
            length_score = 1.0
            long_garment_violation = False
            long_garment_confidence = 0.0
            semantic_fidelity: dict[str, object] | None = None
            if garment_profile is not None:
                try:
                    metrics = garment_structure_metrics(
                        garment_profile,
                        path,
                    )
                    structure_score = float(
                        metrics["structure_score"]
                    )
                    length_score = float(
                        metrics["length_score"]
                    )
                    long_garment_violation = bool(
                        metrics[
                            "long_garment_violation"
                        ]
                    )
                    long_garment_confidence = float(
                        metrics.get("confidence", 0.0)
                    )
                    semantic_fidelity = {
                        "structure_score": structure_score,
                        "length_score": length_score,
                        "length_ratio": float(
                            metrics.get("length_ratio", 1.0)
                        ),
                        "reference_aspect": float(
                            metrics.get("reference_aspect", 0.0)
                        ),
                        "candidate_aspect": float(
                            metrics.get("candidate_aspect", 0.0)
                        ),
                        "long_garment_confidence":
                            long_garment_confidence,
                        "detection_reliable": bool(
                            metrics.get("detection_reliable", False)
                        ),
                    }
                except Exception as exc:  # noqa: BLE001
                    structure_score = (
                        NEUTRAL_VALIDATION_SCORE
                    )
                    length_score = (
                        NEUTRAL_VALIDATION_SCORE
                    )
                    long_garment_violation = False
                    long_garment_confidence = 0.0
                    semantic_fidelity = None
                    validation_errors["structure"] = (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

            final_score = (
                WEIGHT_RENDER_GEOMETRY * render_score
                + WEIGHT_FULL_BODY_GEOMETRY
                * full_score
                + WEIGHT_GARMENT_COLOR * color_score
                + WEIGHT_GARMENT_STRUCTURE
                * structure_score
                + WEIGHT_GARMENT_LENGTH
                * length_score
            )

            # Build the explicit rejection reasons. A candidate is hard
            # rejected only when the underlying evidence is reliable; small,
            # harmless differences do not trip these thresholds. Each reason
            # maps 1:1 to a stable code consumed by the provider and API.
            rejection_reasons: list[str] = []
            if geometry_rejected:
                rejection_reasons.append(
                    "geometry_distortion"
                )
            if color_score < COLOR_HARD_REJECT_BELOW:
                rejection_reasons.append(
                    "garment_color_mismatch"
                )
            if (
                structure_score
                < STRUCTURE_HARD_REJECT_BELOW
            ):
                rejection_reasons.append(
                    "garment_structure_mismatch"
                )
            if (
                length_score
                < LENGTH_HARD_REJECT_BELOW
            ):
                rejection_reasons.append(
                    "garment_length_mismatch"
                )
            if long_garment_violation:
                rejection_reasons.append(
                    "long_garment_shortened"
                )
            if (
                identity_reliable
                and identity_score < IDENTITY_HARD_REJECT_BELOW
            ):
                rejection_reasons.append(
                    "identity_fidelity_failed"
                )
            if catalog_leakage:
                rejection_reasons.append(
                    "catalog_identity_leakage"
                )

            hard_rejected = bool(rejection_reasons)

            if hard_rejected:
                final_score -= HARD_REJECT_PENALTY

            scores.append(
                CandidateScore(
                    index=index,
                    path=str(path),
                    geometry_similarity=float(
                        render_score
                    ),
                    full_body_similarity=float(
                        full_score
                    ),
                    garment_color_score=round(
                        float(color_score), 4
                    ),
                    garment_structure_score=round(
                        float(structure_score), 4
                    ),
                    garment_length_score=round(
                        float(length_score), 4
                    ),
                    long_garment_violation=bool(
                        long_garment_violation
                    ),
                    long_garment_confidence=round(
                        float(long_garment_confidence),
                        4,
                    ),
                    semantic_fidelity=(
                        semantic_fidelity
                    ),
                    rejection_reasons=(
                        rejection_reasons or None
                    ),
                    validation_errors=(
                        validation_errors
                        or None
                    ),
                    final_score=round(
                        max(
                            0.0,
                            final_score,
                        ),
                        4,
                    ),
                    hard_rejected=(
                        hard_rejected
                    ),
                    penalties={
                        key: float(value)
                        for key, value
                        in penalties.items()
                    },
                    candidate_profile=(
                        candidate.to_dict()
                    ),
                    identity_score=round(identity_score, 4),
                    identity_reliable=identity_reliable,
                    catalog_face_score=round(catalog_face_score, 4),
                    catalog_leakage=catalog_leakage,
                )
            )

        except Exception as exc:
            scores.append(
                CandidateScore(
                    index=index,
                    path=str(path),
                    geometry_similarity=0.0,
                    full_body_similarity=0.0,
                    final_score=0.0,
                    hard_rejected=True,
                    penalties={},
                    candidate_profile={},
                    error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )
            )

    valid_scores = [
        item
        for item in scores
        if item.error is None
    ]

    if not valid_scores:
        details = "; ".join(
            (
                f"candidate {item.index}: "
                f"{item.error}"
            )
            for item in scores
        )

        raise ValueError(
            "No valid candidate images could "
            f"be evaluated. {details}"
        )

    eligible = [
        item
        for item in valid_scores
        if not item.hard_rejected
    ]

    if not eligible:
        raise NoEligibleCandidateError(scores)

    pool = eligible

    winner = max(
        pool,
        key=lambda item: (
            item.final_score,
            item.geometry_similarity,
            item.full_body_similarity,
            -item.index,
        ),
    )

    return (
        normalized_paths[winner.index],
        scores,
    )
