from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.providers.base import (
    ProviderError,
    TryOnRequest,
)
from app.providers.factory import get_vton_provider
from app.services.quality_engine import (
    evaluate_candidate,
)
from app.services.visual_quality import enhance_result_image
from app.services.phase3c2_quality import build_phase3c2_report
from app.services.storage import (
    load_job,
    save_job,
    list_jobs,
)

logger = logging.getLogger(__name__)


def _safe_geometry_reference(
    record: Any,
) -> Path:
    """Return the safest body-length reference stored in the job."""
    selected_path = Path(
        record.person_file
    )

    geometry_index = (
        record.geometry_reference_index
    )

    if record.cloth_type not in {
        "overall",
        "lower",
    }:
        return selected_path

    if geometry_index is None:
        return selected_path

    person_files = list(
        record.person_files or []
    )

    if (
        geometry_index < 0
        or geometry_index >= len(person_files)
    ):
        logger.warning(
            (
                "Geometry reference index for job "
                "%s is invalid: %s"
            ),
            record.job_id,
            geometry_index,
        )
        return selected_path

    geometry_path = Path(
        person_files[geometry_index]
    )

    if not geometry_path.exists():
        logger.warning(
            (
                "Geometry reference for job %s "
                "does not exist: %s"
            ),
            record.job_id,
            geometry_path,
        )
        return selected_path

    if not geometry_path.is_file():
        logger.warning(
            (
                "Geometry reference for job %s "
                "is not a file: %s"
            ),
            record.job_id,
            geometry_path,
        )
        return selected_path

    return geometry_path


def _copy_result_file(
    source: Path,
    job_id: str,
    settings: Settings,
) -> Path:
    if not source.exists():
        raise FileNotFoundError(
            f"Provider result does not exist: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Provider result is not a file: {source}"
        )

    suffix = source.suffix.lower() or ".png"

    settings.results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_path = (
        settings.results_dir
        / f"{job_id}{suffix}"
    )

    temporary_path = (
        settings.results_dir
        / f".{job_id}{suffix}.tmp"
    )

    try:
        shutil.copy2(
            source,
            temporary_path,
        )

        temporary_path.replace(
            final_path
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True
        )
        raise

    return final_path


def _provider_metadata(
    result: Any,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    if isinstance(result.raw, dict):
        metadata.update(result.raw)

    result_metadata = getattr(
        result,
        "metadata",
        None,
    )

    if isinstance(result_metadata, dict):
        metadata.update(result_metadata)

    if result.endpoint_used:
        metadata.setdefault(
            "endpoint_used",
            result.endpoint_used,
        )

    return metadata


def process_job(
    job_id: str,
    settings: Settings,
    *,
    num_inference_steps: int,
    guidance_scale: float,
    seed: int,
) -> None:
    record = load_job(
        job_id,
        settings,
    )

    if record is None:
        logger.error(
            (
                "Job %s disappeared before "
                "processing."
            ),
            job_id,
        )
        return

    record.status = "processing"
    record.message = (
        f"Processing with {record.provider}."
    )
    record.error = None
    record.error_code = None

    save_job(
        record,
        settings,
    )

    try:
        provider = get_vton_provider(
            settings
        )

        geometry_reference = (
            _safe_geometry_reference(
                record
            )
        )

        if record.cloth_type in {
            "overall",
            "lower",
        }:
            render_person = geometry_reference
        else:
            render_person = Path(
                record.person_file
            )

        person_files = [
            Path(item)
            for item in (
                record.person_files or []
            )
        ]

        request = TryOnRequest(
            person_image=render_person,
            garment_image=Path(
                record.garment_file
            ),
            garment_description=(
                record.garment_description
            ),
            cloth_type=record.cloth_type,
            show_type=record.show_type,
            num_inference_steps=(
                num_inference_steps
            ),
            guidance_scale=guidance_scale,
            seed=seed,
            person_images=person_files,
            geometry_reference_image=(
                geometry_reference
            ),
            geometry_profile=(
                record.geometry_profile
            ),
            commercial_instructions=(
                record.commercial_instructions
            ),
        )

        retry_history: list[dict[str, Any]] = []
        result = None
        person_candidates = [render_person] + [
            path for path in person_files if path != render_person
        ]
        max_attempts = max(1, min(
            len(person_candidates),
            1 + int(settings.phase3c2_alternate_person_retries),
        ))

        for attempt_index in range(max_attempts):
            attempt_person = person_candidates[attempt_index]
            request.person_image = attempt_person
            if record.cloth_type in {"overall", "lower"}:
                request.geometry_reference_image = attempt_person
            request.seed = seed + attempt_index * 97
            try:
                result = provider.generate(request)
                retry_history.append({
                    "attempt": attempt_index + 1,
                    "person_file": str(attempt_person),
                    "seed": request.seed,
                    "status": "provider_completed",
                })
                break
            except ProviderError as attempt_error:
                retry_history.append({
                    "attempt": attempt_index + 1,
                    "person_file": str(attempt_person),
                    "seed": request.seed,
                    "status": "failed",
                    "error_code": attempt_error.code,
                    "error": str(attempt_error),
                })
                retryable_distortion = (
                    settings.phase3c2_retry_distorted_results
                    and attempt_error.code == "distorted_tryon_result"
                )
                if not retryable_distortion or attempt_index >= max_attempts - 1:
                    raise

        if result is None:
            raise ProviderError(
                "Try Fit generation exhausted all Phase 3C.2 retry strategies.",
                code="phase3c2_retry_exhausted",
            )

        final_path: Path | None = None

        if result.image_path is not None:
            final_path = _copy_result_file(
                Path(result.image_path),
                job_id,
                settings,
            )

        if (
            final_path is None
            and not result.image_url
        ):
            raise ProviderError(
                (
                    "Provider completed without "
                    "returning an image file or URL."
                ),
                code="empty_provider_result",
                provider=getattr(
                    provider,
                    "name",
                    None,
                ),
                retryable=False,
            )

        metadata = {
            **(record.provider_metadata if isinstance(record.provider_metadata, dict) else {}),
            **_provider_metadata(result),
        }

        if final_path is not None:
            enhancement = enhance_result_image(
                final_path,
                enabled=settings.visual_enhancement_enabled,
                sharpness=settings.visual_enhancement_sharpness,
                contrast=settings.visual_enhancement_contrast,
                color=settings.visual_enhancement_color,
            )
            metadata["visual_enhancement"] = enhancement.to_dict()

        generation_rounds_raw = (
            metadata.get(
                "generation_rounds",
                1,
            )
        )

        try:
            generation_rounds = max(
                1,
                int(generation_rounds_raw),
            )
        except (
            TypeError,
            ValueError,
        ):
            generation_rounds = 1

        quality = evaluate_candidate(
            metadata,
            settings
            .commercial_quality_threshold,
        )

        record.status = "completed"
        record.message = (
            "Virtual try-on completed."
        )
        record.endpoint_used = (
            result.endpoint_used
        )
        record.result_file = (
            str(final_path)
            if final_path
            else None
        )
        record.result_url = (
            result.image_url
        )
        record.provider_metadata = metadata
        record.generation_rounds = max(generation_rounds, len(retry_history))
        record.retry_history = retry_history
        record.quality_report = quality.to_dict()

        if final_path is not None:
            batch_id = None
            if isinstance(record.provider_metadata, dict):
                batch_id = record.provider_metadata.get("batch_id")
            sibling_paths: list[Path] = []
            if batch_id:
                for sibling in list_jobs(settings, limit=500):
                    if sibling.job_id == record.job_id or sibling.status != "completed":
                        continue
                    sibling_meta = sibling.provider_metadata if isinstance(sibling.provider_metadata, dict) else {}
                    if sibling_meta.get("batch_id") == batch_id and sibling.result_file:
                        path = Path(sibling.result_file)
                        if path.exists():
                            sibling_paths.append(path)
            report_3c2 = build_phase3c2_report(
                garment_path=Path(record.garment_file),
                result_path=final_path,
                sibling_paths=sibling_paths,
                provider_metadata=metadata,
            )
            record.phase3c2_report = report_3c2
            metadata["phase3c2_quality"] = report_3c2
        record.error = None
        record.error_code = None

    except ProviderError as exc:
        logger.exception(
            "VTON job %s failed",
            job_id,
        )

        record.status = "failed"
        record.message = (
            "Virtual try-on failed."
        )
        record.error = str(exc)
        record.error_code = exc.code

        error_details = getattr(
            exc,
            "details",
            None,
        )

        if isinstance(error_details, dict):
            record.provider_metadata = {
                **(
                    record.provider_metadata
                    if isinstance(
                        record.provider_metadata,
                        dict,
                    )
                    else {}
                ),
                "provider_error":
                    error_details,
                "retryable": bool(
                    getattr(
                        exc,
                        "retryable",
                        False,
                    )
                ),
            }

    except Exception as exc:
        logger.exception(
            (
                "Unexpected VTON job %s "
                "failure"
            ),
            job_id,
        )

        record.status = "failed"
        record.message = (
            "Virtual try-on failed unexpectedly."
        )
        record.error = str(exc)
        record.error_code = (
            "unexpected_error"
        )

    finally:
        try:
            save_job(
                record,
                settings,
            )

        except Exception:
            logger.exception(
                (
                    "Could not persist final state "
                    "for VTON job %s"
                ),
                job_id,
            )