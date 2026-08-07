from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CommercialQualityReport:
    score: float
    accepted: bool
    reason: str
    geometry_score: float
    hard_rejected: bool
    selected_candidate_index: int = 0
    threshold: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "accepted": self.accepted,
            "reason": self.reason,
            "geometry_score": self.geometry_score,
            "hard_rejected": self.hard_rejected,
            "selected_candidate_index":
                self.selected_candidate_index,
            "threshold": self.threshold,
        }


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    if parsed != parsed:
        return default

    return parsed


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _selected_candidate(
    metadata: dict[str, Any],
) -> tuple[int, dict[str, Any] | None]:
    selected_index = _safe_int(
        metadata.get(
            "selected_candidate_index",
            0,
        ),
        0,
    )

    candidates = metadata.get(
        "candidate_scores"
    )

    if not isinstance(candidates, list):
        return selected_index, None

    if (
        selected_index < 0
        or selected_index >= len(candidates)
    ):
        return selected_index, None

    selected = candidates[selected_index]

    if not isinstance(selected, dict):
        return selected_index, None

    return selected_index, selected


def evaluate_candidate(
    metadata: dict[str, Any],
    threshold: float,
) -> CommercialQualityReport:
    """Evaluate provider metadata against the commercial threshold."""
    normalized_threshold = _safe_float(
        threshold,
        0.0,
    )

    if not 0.0 <= normalized_threshold <= 1.0:
        raise ValueError(
            "Commercial quality threshold "
            "must be between 0 and 1."
        )

    if not isinstance(metadata, dict):
        metadata = {}

    selected_index, selected = (
        _selected_candidate(metadata)
    )

    score = _safe_float(
        metadata.get(
            "selected_final_geometry_score"
        ),
        -1.0,
    )

    if score < 0.0 and selected is not None:
        score = _safe_float(
            selected.get("final_score"),
            0.0,
        )

    score = max(
        0.0,
        min(1.0, score),
    )

    geometry_score = _safe_float(
        metadata.get(
            "selected_geometry_similarity"
        ),
        -1.0,
    )

    if (
        geometry_score < 0.0
        and selected is not None
    ):
        geometry_score = _safe_float(
            selected.get(
                "geometry_similarity"
            ),
            score,
        )

    if geometry_score < 0.0:
        geometry_score = score

    geometry_score = max(
        0.0,
        min(1.0, geometry_score),
    )

    hard_rejected = False

    if selected is not None:
        hard_rejected = bool(
            selected.get(
                "hard_rejected",
                False,
            )
        )

    hard_rejected = bool(
        metadata.get(
            "selected_hard_rejected",
            hard_rejected,
        )
    )

    accepted = (
        score >= normalized_threshold
        and not hard_rejected
    )

    if accepted:
        reason = (
            "commercial_quality_passed"
        )
    elif hard_rejected:
        reason = (
            "distorted_candidate_rejected"
        )
    elif not metadata:
        reason = (
            "quality_metadata_missing"
        )
    else:
        reason = (
            "quality_below_threshold"
        )

    return CommercialQualityReport(
        score=round(score, 4),
        accepted=accepted,
        reason=reason,
        geometry_score=round(
            geometry_score,
            4,
        ),
        hard_rejected=hard_rejected,
        selected_candidate_index=(
            selected_index
        ),
        threshold=round(
            normalized_threshold,
            4,
        ),
    )