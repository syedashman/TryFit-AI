from __future__ import annotations

import base64
import json
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.core.config import Settings
from app.services.http_client import get_http_client

# gemini-2.5-flash-image ("nano banana") does identity-preserving image
# editing/generation and is broadly available via the Vertex AI *global*
# endpoint (unlike the gated imagen-3.0-capability-001 model, which returns
# 404 for most projects without a special access grant). If this model is
# renamed/retired, check
# https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-image
_POSE_MODEL = "gemini-2.5-flash-image"
_POSE_MODEL_LOCATION = "global"
_IDENTITY_REVIEW_MODEL = "gemini-2.5-flash"

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


@dataclass(frozen=True, slots=True)
class IdentityPreservationReview:
    identity: str
    visible_body: str
    confidence: float
    reason: str

    @property
    def should_reject(self) -> bool:
        return self.confidence >= 0.70 and (
            self.identity == "mismatch"
            or self.visible_body == "drifted"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "visible_body": self.visible_body,
            "confidence": self.confidence,
            "reason": self.reason,
            "rejected": self.should_reject,
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


def _encode_face_crop(path: Path) -> tuple[str, str] | None:
    image = cv2.imdecode(
        np.frombuffer(path.read_bytes(), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    if image is None:
        return None

    detector = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    faces = detector.detectMultiScale(
        cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(20, 20),
    )
    if not len(faces):
        return None

    x, y, width, height = max(faces, key=lambda box: box[2] * box[3])
    side = int(max(width, height) * 2.0)
    center_x = x + width // 2
    center_y = y + height // 2
    left = max(0, center_x - side // 2)
    top = max(0, center_y - side // 2)
    right = min(image.shape[1], center_x + side // 2)
    bottom = min(image.shape[0], center_y + side // 2)
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return None

    resized = cv2.resize(crop, (384, 384), interpolation=cv2.INTER_CUBIC)
    encoded, data = cv2.imencode(
        ".jpg",
        resized,
        [cv2.IMWRITE_JPEG_QUALITY, 92],
    )
    if not encoded:
        return None
    return "image/jpeg", base64.b64encode(data).decode("ascii")


def _body_geometry_instructions(
    body_geometry: dict[str, object] | None,
) -> str:
    if not body_geometry:
        return ""

    measurements: list[str] = []
    for field in (
        "foreground_width_ratio",
        "foreground_height_ratio",
        "upper_width_ratio",
        "middle_width_ratio",
        "lower_width_ratio",
        "subject_aspect_ratio",
    ):
        value = body_geometry.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not 0.0 < value <= 2.0:
            continue
        if field.endswith("_width_ratio") and value == 1.0:
            continue
        measurements.append(f"{field}={value:.4f}")

    if not measurements:
        return ""

    return (
        "Image analysis of the first image measured these visible-source "
        "geometry ratios: "
        + ", ".join(measurements)
        + ". Treat them only as constraints on body regions actually visible "
        "in the first image; do not treat missing regions as measurements."
    )


def generate_posed_reference(
    settings: Settings,
    identity_paths: list[Path],
    pose_name: str,
    subject_description: str,
    output_dir: Path,
    body_geometry: dict[str, object] | None = None,
) -> Path:
    """Generate a full-body image of the same person in a fixed target pose.

    Uses the uploaded photo and a text-only pose description. The bundled pose
    photographs are deliberately not sent to Gemini, so their identity,
    clothing, and body shape cannot leak into the generated person.
    """
    if pose_name not in POSE_PROMPTS:
        raise PoseCustomizationError(f"Unknown pose '{pose_name}'.")

    if not settings.google_cloud_project:
        raise PoseCustomizationError("GOOGLE_CLOUD_PROJECT is not configured.")

    identity_image = identity_paths[0]
    identity_mime, identity_b64 = _encode(identity_image)

    prompt = (
        f"The only person shown is {subject_description} from the uploaded "
        "image. Preserve this exact person's visible facial identity, age, "
        "skin tone, hair, build, and all visible body proportions. Do not "
        "beautify, idealize, slim, widen, or otherwise change the person. "
        "Keep body dimensions and silhouette grounded in the uploaded image; "
        "infer only body parts that are not visible and only as needed to "
        "complete the requested pose. No other person's image is provided "
        "or may be used as an appearance reference. "
        f"Render this same person in the following target pose: "
        f"{POSE_PROMPTS[pose_name]} Generate a photorealistic full-body "
        "photo, with the person head to feet and clear headroom above the head, "
        "plain neutral studio background, soft even lighting. CRITICAL: "
        "replace clothing with plain solid light-grey short-sleeve t-shirt "
        "and plain solid dark-grey trousers, without patterns, prints, "
        "embroidery, scarves, or draped fabric. Use simple plain footwear. "
        "Output only the image."
    )
    geometry_instructions = _body_geometry_instructions(body_geometry)
    if geometry_instructions:
        prompt += " " + geometry_instructions

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": identity_mime, "data": identity_b64}},
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
            response = get_http_client().post(
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


def verify_person_preservation(
    settings: Settings,
    source_image: Path,
    result_image: Path,
) -> IdentityPreservationReview:
    """Use Gemini only when local face comparison flags possible identity drift."""
    if not settings.google_cloud_project:
        raise PoseCustomizationError(
            "GOOGLE_CLOUD_PROJECT is required for identity-preservation review."
        )

    source_mime, source_b64 = _encode(source_image)
    result_mime, result_b64 = _encode(result_image)
    source_face = _encode_face_crop(source_image)
    result_face = _encode_face_crop(result_image)
    face_parts: list[dict[str, object]] = []
    if source_face is not None and result_face is not None:
        face_parts = [
            {
                "text": (
                    "Image 3 is an enlarged crop of the source person's face:"
                )
            },
            {
                "inline_data": {
                    "mime_type": source_face[0],
                    "data": source_face[1],
                }
            },
            {
                "text": (
                    "Image 4 is an enlarged crop of the generated person's face:"
                )
            },
            {
                "inline_data": {
                    "mime_type": result_face[0],
                    "data": result_face[1],
                }
            },
        ]
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": source_mime, "data": source_b64}},
                    {"inline_data": {"mime_type": result_mime, "data": result_b64}},
                    {
                        "text": (
                            "Compare image 2 with image 1. Image 1 is the user's "
                            "source photo; image 2 is the try-on result and may "
                            "have a different pose, framing, background, lighting, "
                            "and clothing. When images 3 and 4 are present, they "
                            "are enlarged face crops from images 1 and 2. Compare "
                            "facial structure and distinctive features in those "
                            "crops; do not call two people a match solely because "
                            "their age, gender, hairstyle, or skin tone is similar. "
                            "Judge whether the visible face and recognizable "
                            "identity are the same person, and whether body "
                            "proportions in regions visible in both full images "
                            "were preserved. If facial identity cannot be verified, "
                            "return uncertain rather than match. Do not penalize "
                            "or infer differences for body regions not visible in "
                            "image 1. Return only JSON with fields "
                            '"identity" (match, mismatch, or uncertain), '
                            '"visible_body" (preserved, drifted, or uncertain), '
                            '"confidence" (number 0 through 1), and '
                            '"reason" (short string).'
                        )
                    },
                    *face_parts,
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT"],
            "responseMimeType": "application/json",
        },
    }
    token = _access_token(settings)
    project = settings.google_cloud_project
    location = settings.google_cloud_location
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/"
        f"publishers/google/models/{_IDENTITY_REVIEW_MODEL}:generateContent"
    )
    try:
        response = get_http_client().post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PoseCustomizationError(
            f"Gemini identity-preservation review request failed: {exc}"
        ) from exc
    try:
        body = response.json()
        parts = body["candidates"][0]["content"]["parts"]
        response_text = next(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
        assessment = json.loads(response_text)
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise PoseCustomizationError(
            f"Gemini returned an invalid identity-preservation review: {exc}"
        ) from exc

    identity = assessment.get("identity")
    visible_body = assessment.get("visible_body")
    confidence = assessment.get("confidence")
    reason = assessment.get("reason")
    if (
        identity not in {"match", "mismatch", "uncertain"}
        or visible_body not in {"preserved", "drifted", "uncertain"}
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= confidence <= 1.0
        or not isinstance(reason, str)
    ):
        raise PoseCustomizationError(
            "Gemini returned an identity-preservation review with invalid fields."
        )

    return IdentityPreservationReview(
        identity=identity,
        visible_body=visible_body,
        confidence=float(confidence),
        reason=reason,
    )