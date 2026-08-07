from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings

# NOTE: Google periodically retires dated Gemini model aliases (see
# https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini
# for the current list). If this check starts failing with a "model not
# found" error, swap this for whatever Gemini Flash alias is current.
_GEMINI_MODEL = "gemini-2.5-flash"

_CATEGORY_REQUIREMENTS = {
    "men": "an adult man",
    "women": "an adult woman",
    "kids": "a child (not an adult)",
}

_MISMATCH_MESSAGES = {
    "men": "This product is for men. Please upload a photo of yourself that shows an adult man.",
    "women": "This product is for women. Please upload a photo of yourself that shows an adult woman.",
    "kids": "This product is for kids. Please upload a photo that shows a child, not an adult.",
}

_NOT_A_PERSON_MESSAGE = (
    "We couldn't find a clear photo of a person in your upload. "
    "Please upload real photos of yourself, not scenery, objects, or other images."
)


class PhotoCategoryCheckError(Exception):
    """Raised when the photo category check itself fails to run (config/auth/etc)."""


def _access_token(settings: Settings) -> str:
    credentials_path = settings.google_application_credentials
    if credentials_path:
        resolved = str(Path(credentials_path).expanduser().resolve())
        if Path(resolved).exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = resolved

    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleAuthRequest

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(GoogleAuthRequest())
        token = getattr(credentials, "token", None)
        if not token:
            raise RuntimeError("Google authentication returned no access token.")
        return token
    except Exception as exc:  # noqa: BLE001
        raise PhotoCategoryCheckError(
            f"Google authentication failed for photo category check: {exc}"
        ) from exc


def _encode_image(path: Path) -> tuple[str, str]:
    mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return mime_type, data


def _build_prompt(category: str) -> str:
    requirement = _CATEGORY_REQUIREMENTS.get(category, "a person")
    return (
        "You are a photo-quality gate for a virtual try-on tool. "
        f"The shopper selected a product from the '{category}' category, which "
        f"is designed to be worn by {requirement}. "
        "Look at the attached photo(s) of the shopper. Answer strictly as JSON, "
        'with this exact shape: {"is_person": true|false, "age_group": '
        '"adult"|"child"|"unclear", "presentation": "masculine"|"feminine"|"unclear"}. '
        '"is_person" is false if the image is not a real photo of a human being '
        "(e.g. it's a landscape, object, drawing, or screenshot). "
        "Only output the JSON object, nothing else."
    )


def check_photos_match_category(
    settings: Settings,
    person_paths: list[Path],
    category: str,
) -> tuple[bool, str | None]:
    """Returns (ok, error_message). error_message is None when ok is True.

    Best-effort check via a Gemini vision call. If the check itself cannot
    run (e.g. no credentials configured), it fails open (returns ok=True)
    rather than blocking every generation on an infrastructure problem.
    """
    category = category.lower()
    if category not in _CATEGORY_REQUIREMENTS:
        return True, None

    if not settings.google_cloud_project:
        return True, None

    sample_paths = person_paths[:2]  # keep the request small/cheap
    parts: list[dict[str, Any]] = [{"text": _build_prompt(category)}]
    for path in sample_paths:
        try:
            mime_type, data = _encode_image(path)
        except Exception:  # noqa: BLE001
            continue
        parts.append(
            {"inline_data": {"mime_type": mime_type, "data": data}}
        )

    if len(parts) == 1:
        # No images could be read at all — let normal upload validation
        # handle that failure instead of double-reporting it here.
        return True, None

    try:
        token = _access_token(settings)
    except PhotoCategoryCheckError:
        return True, None

    location = settings.google_cloud_location
    project = settings.google_cloud_project
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/"
        f"publishers/google/models/{_GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 128,
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
        text = (
            body["candidates"][0]["content"]["parts"][0]["text"]
        )
        result = json.loads(text)
    except Exception:  # noqa: BLE001
        # Fail open: an infra/parsing hiccup shouldn't block a genuine try-on.
        return True, None

    is_person = bool(result.get("is_person", True))
    if not is_person:
        return False, _NOT_A_PERSON_MESSAGE

    age_group = str(result.get("age_group", "unclear")).lower()
    presentation = str(result.get("presentation", "unclear")).lower()

    if category == "kids":
        if age_group == "adult":
            return False, _MISMATCH_MESSAGES["kids"]
        return True, None

    # men / women: only hard-block on a confident, clear mismatch —
    # "unclear" answers pass through rather than blocking a real shopper.
    if age_group == "child":
        return False, _MISMATCH_MESSAGES[category]

    expected_presentation = "masculine" if category == "men" else "feminine"
    opposite_presentation = "feminine" if category == "men" else "masculine"
    if presentation == opposite_presentation:
        return False, _MISMATCH_MESSAGES[category]

    return True, None