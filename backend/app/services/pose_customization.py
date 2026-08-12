from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from pathlib import Path

import httpx

from app.core.config import Settings

# gemini-2.5-flash-image ("nano banana") does identity-preserving image
# editing/generation and is broadly available via the Vertex AI *global*
# endpoint (unlike the gated imagen-3.0-capability-001 model, which returns
# 404 for most projects without a special access grant). If this model is
# renamed/retired, check
# https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-image
_POSE_MODEL = "gemini-2.5-flash-image"
_POSE_MODEL_LOCATION = "global"

POSE_REFERENCES_DIR = Path(__file__).resolve().parent.parent / "static" / "pose_references"

POSE_PROMPTS = {
    "front": (
        "standing upright, full body clearly visible head to feet, "
        "facing the camera directly, body squared to the camera, arms "
        "relaxed and hanging naturally at the sides, feet together or "
        "slightly apart, head level and looking straight at the camera. "
        "This must be a full-body standing photograph, not a close-up, "
        "not a portrait crop. NOT sitting, NOT crouching, NOT kneeling, "
        "NOT leaning."
    ),
    "side": (
        "standing upright, full body clearly visible head to feet, body "
        "turned about 45 degrees to one side relative to the camera (a "
        "3/4 side profile view), head turned slightly back toward the "
        "camera so the face is still visible, one arm relaxed at the side "
        "and the other hand resting lightly near the hip or pocket. This "
        "must be a full-body standing photograph, not a close-up, not a "
        "portrait crop. NOT sitting, NOT crouching, NOT kneeling, NOT "
        "facing straight at the camera."
    ),
    "back": (
        "standing upright with their ENTIRE BACK facing the camera. This "
        "is a rear/back view photograph: the camera is positioned BEHIND "
        "the person, looking at the back of their head and body. Their "
        "face, eyes, nose, and mouth must NOT be visible anywhere in the "
        "frame — only the back of the head, hair, back, and the backs of "
        "the arms and legs are visible. Arms relaxed at the sides. This is "
        "mandatory: if the face is visible, the image is wrong. NOT "
        "facing the camera, NOT a front view, NOT a 3/4 view, NOT sitting, "
        "NOT crouching."
    ),
}


class PoseCustomizationError(Exception):
    """Raised when the pose-normalization step cannot be completed."""


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
        raise PoseCustomizationError(f"Google authentication failed: {exc}") from exc


def _encode(path: Path) -> tuple[str, str]:
    mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return mime_type, base64.b64encode(path.read_bytes()).decode("ascii")


def generate_posed_reference(
    settings: Settings,
    identity_paths: list[Path],
    pose_name: str,
    subject_description: str,
    output_dir: Path,
) -> Path:
    """Generate a full-body image of the same person in a fixed target pose.

    Uses Gemini 2.5 Flash Image: the shopper's uploaded photo is passed as
    identity reference, plus a bundled reference photo showing the target
    body pose, with a text instruction to render the same person (same
    face, same body) in that pose, full body, neutral background. Raises
    PoseCustomizationError on any failure — callers should catch this and
    fall back to the shopper's own best photo rather than blocking
    generation entirely.
    """
    if pose_name not in POSE_PROMPTS:
        raise PoseCustomizationError(f"Unknown pose '{pose_name}'.")

    if not settings.google_cloud_project:
        raise PoseCustomizationError("GOOGLE_CLOUD_PROJECT is not configured.")

    control_image_path = POSE_REFERENCES_DIR / f"{pose_name}.jpg"
    if not control_image_path.exists():
        raise PoseCustomizationError(f"Missing bundled pose reference for '{pose_name}'.")

    identity_image = identity_paths[0]
    identity_mime, identity_b64 = _encode(identity_image)
    control_mime, control_b64 = _encode(control_image_path)

    prompt = (
        f"The first image shows {subject_description} — this is the exact "
        "real person to render, not a similar-looking person. Study their "
        "exact facial structure, eyes, eyebrows, nose shape, mouth, "
        "jawline, facial hair (if any), skin tone, and hairstyle/hair "
        "color closely before generating anything. Keep every one of "
        "those features identical in the output — this must be "
        "unmistakably recognizable as the same individual, not a generic "
        "or idealized face. The second image shows only a body pose "
        "reference (ignore its clothing, its face, and its identity "
        "entirely, use it only for body posture and camera framing). "
        f"Generate a new photorealistic full-body photo of the person from "
        f"the first image, {POSE_PROMPTS[pose_name]}, matching the body "
        "pose and camera framing of the second image. The output must show "
        "the person head to feet with clear headroom above the head, "
        "plain neutral studio background, soft even lighting. CRITICAL: "
        "do NOT dress them in the same outfit, pattern, print, color, or "
        "fabric shown in the first image — completely replace their "
        "clothing with a plain solid light-grey short-sleeve t-shirt and "
        "plain solid dark-grey trousers, no patterns, no prints, no "
        "embroidery, no dupatta or scarf, nothing draped over the "
        "shoulders. This plain outfit will be digitally replaced with a "
        "different garment in a later step, so it must stay completely "
        "plain and simple. On their feet, simple formal brown leather "
        "loafers (not sneakers, not sandals, not barefoot) — this exact "
        "same shoe style every time. Output only the image."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": identity_mime, "data": identity_b64}},
                    {"inline_data": {"mime_type": control_mime, "data": control_b64}},
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    token = _access_token(settings)
    project = settings.google_cloud_project
    url = (
        f"https://aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{_POSE_MODEL_LOCATION}/"
        f"publishers/google/models/{_POSE_MODEL}:generateContent"
    )

    last_error: Exception | None = None
    image_bytes: bytes | None = None
    for attempt in range(2):
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            body = response.json()
            parts = body["candidates"][0]["content"]["parts"]
            image_b64 = None
            for part in parts:
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    image_b64 = inline_data["data"]
                    break
            if not image_b64:
                raise PoseCustomizationError("Gemini image response had no image data.")
            image_bytes = base64.b64decode(image_b64)
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if image_bytes is None:
        raise PoseCustomizationError(
            f"Gemini pose generation request failed after retry: {last_error}"
        ) from last_error

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = mimetypes.guess_extension("image/png") or ".png"
    out_path = output_dir / f"pose_{pose_name}_{uuid.uuid4().hex}{ext}"
    out_path.write_bytes(image_bytes)
    return out_path