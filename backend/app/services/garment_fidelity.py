"""Gemini-backed semantic garment-fidelity judge.

The local OpenCV validator in ``phase3c2_quality`` is a cheap, best-effort
structural signal. It is unreliable on real generated try-on outputs — a long
kurta/kameez rendered as a short shirt can slip through because the garment
region is still the right colour and roughly the right aspect. This module adds
a Gemini vision model as a *semantic* judge focused on commercial product
identity: does the generated garment still read as the SAME product the shopper
would receive?

Design constraints (do not regress these):

- Reuse the Gemini client/auth pattern from ``photo_category_check`` — do not
  duplicate credential handling.
- The local CV validator remains the fallback path. On any Gemini failure
  (no project configured, auth failure, timeout, malformed response) this
  falls back to ``garment_structure_metrics`` and marks the semantic signal as
  unavailable.
- A failed/unavailable judge must NEVER be silently reported as a perfect
  (all-preserved, confidence 1.0) result — that would let a broken candidate
  win selection. It also must never crash the job when a safe CV fallback
  exists.
- The judge only compares GARMENT/PRODUCT IDENTITY. It must ignore body shape,
  folds, perspective, pose, draping, and must not compare face/identity,
  background, or pose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.services.phase3c2_quality import garment_structure_metrics
from app.services.photo_category_check import (
    PhotoCategoryCheckError,
    _access_token,
    _encode_image,
)

# NOTE: Google periodically retires dated Gemini model aliases. If this judge
# starts failing with a "model not found" error, swap this for whatever Gemini
# Flash alias is current (see photo_category_check for the same note).
_GEMINI_MODEL = "gemini-2.5-flash"

# The structural boolean checks the judge answers. Any of these turning False
# for a drastic change is grounds for a hard reject.
_FIDELITY_FIELDS = (
    "garment_type_preserved",
    "length_preserved",
    "sleeve_preserved",
    "neckline_preserved",
    "silhouette_preserved",
    "major_details_preserved",
)

# Confidence below which we do not trust a hard reject from the judge. Keeps
# borderline/uncertain calls from blocking a genuine try-on.
_HARD_REJECT_MIN_CONFIDENCE = 0.6



def _unavailable_result(reason: str) -> dict[str, Any]:
    """A neutral 'semantic judge did not run' result.

    Crucially this is NOT a perfect score: every preservation flag is left
    unknown (``None``) and ``confidence`` is 0.0, so downstream selection never
    treats an unavailable judge as a passing candidate.
    """
    result: dict[str, Any] = {field: None for field in _FIDELITY_FIELDS}
    result.update(
        {
            "confidence": 0.0,
            "hard_reject": False,
            "reason": reason,
            "semantic_available": False,
            "source": "unavailable",
        }
    )
    return result


def _cv_fallback_result(
    garment_path: Path,
    candidate_path: Path,
    reason: str,
) -> dict[str, Any]:
    """Derive a fidelity verdict from the local CV validator.

    Used whenever the Gemini judge cannot run. The CV validator can only
    reliably speak to the long-garment/length signal, so only those two flags
    are populated; the remaining semantic flags stay unknown (``None``) rather
    than being optimistically set to preserved.
    """
    try:
        metrics = garment_structure_metrics(garment_path, candidate_path)
    except Exception as exc:  # noqa: BLE001
        # Even the CV fallback failed — stay unavailable, never crash and never
        # fabricate a passing score.
        return _unavailable_result(
            f"{reason}; CV fallback also failed: "
            f"{type(exc).__name__}: {exc}"
        )

    detection_reliable = bool(metrics.get("detection_reliable", False))
    long_violation = bool(metrics.get("long_garment_violation", False))
    confidence = float(metrics.get("confidence", 0.0))

    result: dict[str, Any] = {field: None for field in _FIDELITY_FIELDS}
    if detection_reliable:
        # The CV validator can only speak to garment length/silhouette.
        result["length_preserved"] = not long_violation
        result["silhouette_preserved"] = not long_violation

    result.update(
        {
            "confidence": confidence,
            "hard_reject": bool(long_violation),
            "reason": (
                "long_garment_shortened"
                if long_violation
                else reason
            ),
            "semantic_available": False,
            "source": "cv_fallback",
        }
    )
    return result


def _build_prompt() -> str:
    return (
        "You are a strict QUALITY GATE for a commercial virtual try-on tool. "
        "You are given two images: (1) the REFERENCE PRODUCT — the actual "
        "garment the shopper will receive, and (2) the GENERATED try-on — the "
        "same garment rendered onto a person. Your ONLY job is to decide "
        "whether the generated garment still reads as the SAME COMMERCIAL "
        "PRODUCT.\n\n"
        "Judge PRODUCT IDENTITY ONLY. Compare garment TYPE, overall LENGTH "
        "(e.g. long kurta/kameez vs short shirt), SLEEVE length, NECKLINE / "
        "collar style, overall SILHOUETTE, and MAJOR design details (prints, "
        "plackets, pockets, patterns).\n\n"
        "HARD-REJECT (a drastic product change) when, for example:\n"
        "- a long garment (kurta, kameez, gown, maxi, long coat) is rendered "
        "as a short shirt/top;\n"
        "- full/long sleeves become short or sleeveless (or vice versa);\n"
        "- the collar or neckline style is clearly changed;\n"
        "- a coat/jacket becomes a shirt, or the garment category otherwise "
        "changes;\n"
        "- major design details are dropped or replaced.\n\n"
        "IGNORE and DO NOT penalise: body shape or size, fabric folds and "
        "wrinkles, camera perspective, the person's pose, and natural garment "
        "draping. DO NOT compare the face/identity, the background, or the "
        "pose — only the garment as a product.\n\n"
        "Answer STRICTLY as JSON with EXACTLY this shape (booleans, a float in "
        "0..1, and a short reason string):\n"
        '{"garment_type_preserved": true|false, '
        '"length_preserved": true|false, '
        '"sleeve_preserved": true|false, '
        '"neckline_preserved": true|false, '
        '"silhouette_preserved": true|false, '
        '"major_details_preserved": true|false, '
        '"confidence": 0.0, '
        '"hard_reject": true|false, '
        '"reason": "short explanation"}\n'
        "Set hard_reject to true ONLY for a drastic product change like those "
        "listed above, and only when you are confident. Output the JSON "
        "object only, nothing else."
    )


def _coerce_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise the model's JSON into the stable result contract."""
    result: dict[str, Any] = {}
    for field in _FIDELITY_FIELDS:
        value = raw.get(field)
        result[field] = bool(value) if isinstance(value, bool) else value

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    model_hard_reject = bool(raw.get("hard_reject", False))
    # Any explicit preservation flag turning False is also a drastic change.
    any_flag_failed = any(
        result.get(field) is False for field in _FIDELITY_FIELDS
    )
    hard_reject = (
        (model_hard_reject or any_flag_failed)
        and confidence >= _HARD_REJECT_MIN_CONFIDENCE
    )

    reason = raw.get("reason")
    result.update(
        {
            "confidence": round(confidence, 4),
            "hard_reject": bool(hard_reject),
            "reason": (
                str(reason)
                if reason
                else ("drastic_garment_change" if hard_reject else None)
            ),
            "semantic_available": True,
            "source": "gemini",
        }
    )
    return result



def evaluate_garment_fidelity(
    settings: Settings,
    garment_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    """Semantic garment-fidelity verdict for a single generated candidate.

    Returns a dict with the boolean preservation flags, ``confidence``,
    ``hard_reject``, ``reason``, plus ``semantic_available`` and ``source``
    metadata. On any Gemini failure this falls back to the local CV validator
    and marks ``semantic_available`` False; it never fabricates a perfect score
    and never raises when a safe fallback exists.
    """
    garment_path = Path(garment_path)
    candidate_path = Path(candidate_path)

    if not settings.google_cloud_project:
        return _cv_fallback_result(
            garment_path,
            candidate_path,
            "semantic_judge_unavailable: no google_cloud_project configured",
        )

    try:
        garment_mime, garment_data = _encode_image(garment_path)
        candidate_mime, candidate_data = _encode_image(candidate_path)
    except Exception as exc:  # noqa: BLE001
        return _cv_fallback_result(
            garment_path,
            candidate_path,
            f"semantic_judge_unavailable: could not read images: "
            f"{type(exc).__name__}: {exc}",
        )

    try:
        token = _access_token(settings)
    except PhotoCategoryCheckError as exc:
        return _cv_fallback_result(
            garment_path,
            candidate_path,
            f"semantic_judge_unavailable: auth failed: {exc}",
        )

    location = settings.google_cloud_location
    project = settings.google_cloud_project
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/"
        f"publishers/google/models/{_GEMINI_MODEL}:generateContent"
    )

    parts: list[dict[str, Any]] = [
        {"text": _build_prompt()},
        {"text": "REFERENCE PRODUCT image:"},
        {"inline_data": {"mime_type": garment_mime, "data": garment_data}},
        {"text": "GENERATED try-on image:"},
        {"inline_data": {"mime_type": candidate_mime, "data": candidate_data}},
    ]

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        # API failure / timeout / malformed response: fall back to CV.
        return _cv_fallback_result(
            garment_path,
            candidate_path,
            f"semantic_judge_unavailable: gemini call failed: "
            f"{type(exc).__name__}: {exc}",
        )

    if not isinstance(raw, dict):
        return _cv_fallback_result(
            garment_path,
            candidate_path,
            "semantic_judge_unavailable: gemini returned non-object JSON",
        )

    return _coerce_result(raw)

