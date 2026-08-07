from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.body_geometry import (
    BodyGeometryProfile,
    build_body_geometry_profile,
    distortion_penalties,
    geometry_similarity,
)


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
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "index": self.index,
            "path": self.path,
            "geometry_similarity":
                self.geometry_similarity,
            "full_body_similarity":
                self.full_body_similarity,
            "final_score": self.final_score,
            "hard_rejected":
                self.hard_rejected,
            "penalties": self.penalties,
            "candidate_profile":
                self.candidate_profile,
        }

        if self.error:
            payload["error"] = self.error

        return payload


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
) -> tuple[Path, list[CandidateScore]]:
    if not candidate_paths:
        raise ValueError(
            "At least one candidate is required."
        )

    normalized_paths = [
        Path(path)
        for path in candidate_paths
    ]

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

            hard_rejected = (
                _hard_reject(penalties)
            )

            final_score = (
                0.70 * render_score
                + 0.30 * full_score
            )

            if hard_rejected:
                final_score -= 0.30

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

    # When all valid candidates are distorted,
    # return the best rejected candidate. The
    # provider will raise the commercial-quality
    # error using its selected score.
    pool = (
        eligible
        if eligible
        else valid_scores
    )

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