from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import Settings
from app.models.job import JobRecord, utc_now_iso


_lock = Lock()

_ALLOWED_IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

_CONTENT_TYPE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def to_json_safe(
    value: Any,
) -> Any:
    """Recursively convert provider and scientific values to JSON-safe types."""

    if value is None or isinstance(
        value,
        (
            str,
            bool,
            int,
            float,
        ),
    ):
        return value

    if isinstance(value, Enum):
        return to_json_safe(
            value.value
        )

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(
                to_json_safe(key)
            ): to_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return [
            to_json_safe(item)
            for item in value
        ]

    item_method = getattr(
        value,
        "item",
        None,
    )

    if callable(item_method):
        try:
            item = item_method()
        except (
            TypeError,
            ValueError,
            RuntimeError,
        ):
            item = value

        if item is not value:
            return to_json_safe(item)

    tolist_method = getattr(
        value,
        "tolist",
        None,
    )

    if callable(tolist_method):
        try:
            return to_json_safe(
                tolist_method()
            )
        except (
            TypeError,
            ValueError,
            RuntimeError,
        ):
            pass

    raise TypeError(
        "Value of type "
        f"{type(value).__name__} "
        "is not JSON serializable"
    )


def ensure_storage(
    settings: Settings,
) -> None:
    for directory in (
        settings.jobs_dir,
        settings.uploads_dir,
        settings.results_dir,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def _safe_suffix(
    filename: str | None,
    content_type: str | None,
) -> str:
    suffix = Path(
        filename or ""
    ).suffix.lower()

    if suffix in _ALLOWED_IMAGE_SUFFIXES:
        return suffix

    normalized_content_type = (
        content_type or ""
    ).split(
        ";",
        1,
    )[0].strip().lower()

    return _CONTENT_TYPE_SUFFIXES.get(
        normalized_content_type,
        ".bin",
    )


def _safe_prefix(
    prefix: str,
) -> str:
    normalized = "".join(
        character
        if character.isalnum()
        or character in {
            "-",
            "_",
        }
        else "_"
        for character in (
            prefix or "upload"
        ).strip()
    )

    normalized = normalized.strip(
        "._"
    )

    return (
        normalized[:80]
        or "upload"
    )


async def save_upload(
    upload: UploadFile,
    settings: Settings,
    prefix: str,
) -> Path:
    ensure_storage(settings)

    suffix = _safe_suffix(
        upload.filename,
        upload.content_type,
    )

    destination = (
        settings.uploads_dir
        / (
            f"{_safe_prefix(prefix)}_"
            f"{uuid4().hex}{suffix}"
        )
    )

    max_bytes = int(
        settings.max_image_size_mb
        * 1024
        * 1024
    )

    if max_bytes <= 0:
        raise ValueError(
            "Maximum upload size must be greater than zero."
        )

    size = 0
    completed = False

    try:
        with destination.open(
            "xb"
        ) as output:
            while True:
                chunk = await upload.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                size += len(chunk)

                if size > max_bytes:
                    raise ValueError(
                        "Image exceeds maximum size of "
                        f"{settings.max_image_size_mb} MB."
                    )

                output.write(chunk)

        if size == 0:
            raise ValueError(
                "Uploaded image is empty."
            )

        completed = True

        return destination

    finally:
        try:
            await upload.close()
        finally:
            if not completed:
                destination.unlink(
                    missing_ok=True
                )


def _safe_job_id(
    job_id: str,
) -> str:
    normalized = (
        job_id or ""
    ).strip()

    if not normalized:
        raise ValueError(
            "Job ID cannot be empty."
        )

    if any(
        character in normalized
        for character in (
            "/",
            "\\",
            "\x00",
        )
    ):
        raise ValueError(
            "Job ID contains invalid characters."
        )

    if normalized in {
        ".",
        "..",
    }:
        raise ValueError(
            "Job ID is invalid."
        )

    return normalized


def job_path(
    job_id: str,
    settings: Settings,
) -> Path:
    safe_job_id = _safe_job_id(
        job_id
    )

    return (
        settings.jobs_dir
        / f"{safe_job_id}.json"
    )


def save_job(
    record: JobRecord,
    settings: Settings,
) -> None:
    ensure_storage(settings)

    record.updated_at = (
        utc_now_iso()
    )

    target = job_path(
        record.job_id,
        settings,
    )

    temporary = (
        target.parent
        / (
            f".{target.name}."
            f"{uuid4().hex}.tmp"
        )
    )

    payload = to_json_safe(
        record.model_dump(
            mode="python"
        )
    )

    serialized = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )

    with _lock:
        try:
            temporary.write_text(
                serialized,
                encoding="utf-8",
            )

            temporary.replace(
                target
            )

        finally:
            temporary.unlink(
                missing_ok=True
            )


def load_job(
    job_id: str,
    settings: Settings,
) -> JobRecord | None:
    target = job_path(
        job_id,
        settings,
    )

    if not target.exists():
        return None

    if not target.is_file():
        raise ValueError(
            f"Job path is not a file: {target}"
        )

    with _lock:
        try:
            raw = target.read_text(
                encoding="utf-8"
            )

            data: dict[str, Any] = (
                json.loads(raw)
            )

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Job file is corrupted: {target}"
            ) from exc

        except OSError as exc:
            raise OSError(
                f"Could not read job file: {target}"
            ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Job file does not contain an object: {target}"
        )

    try:
        return JobRecord.model_validate(
            data
        )

    except ValidationError as exc:
        raise ValueError(
            f"Job file has invalid data: {target}"
        ) from exc

def list_jobs(
    settings: Settings,
    *,
    limit: int = 20,
) -> list[JobRecord]:
    """Return newest valid job records without exposing malformed files."""
    ensure_storage(settings)
    bounded_limit = max(1, min(int(limit), 100))
    records: list[JobRecord] = []
    files = sorted(
        settings.jobs_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        if len(records) >= bounded_limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(JobRecord.model_validate(payload))
        except (OSError, json.JSONDecodeError, ValidationError):
            continue
    return records
