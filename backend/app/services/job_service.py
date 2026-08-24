from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
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
from app.services.memory_metrics import log_memory

logger = logging.getLogger(__name__)


def _mark_job_stale_if_needed(record: Any, settings: Settings) -> bool:
    """Fail jobs that have remained queued/processing beyond a safe generation timeout."""
    if record is None or record.status not in {"queued", "processing"}:
        return False

    try:
        updated_at = datetime.fromisoformat(record.updated_at)
    except (TypeError, ValueError):
        updated_at = datetime.now(timezone.utc)

    stale_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
    if stale_seconds <= settings.job_stale_timeout_seconds:
        return False

    record.status = "failed"
    record.message = "This look took too long to create. Please retry."
    record.error = (
        "Job exceeded the allowed generation time and was marked failed to avoid a never-ending spinner."
    )
    record.error_code = "job_stale_timeout"
    record.provider_metadata = {
        **(record.provider_metadata if isinstance(record.provider_metadata, dict) else {}),
        "job_stale_timeout_seconds": settings.job_stale_timeout_seconds,
        "job_stale_elapsed_seconds": round(stale_seconds, 2),
    }
    save_job(record, settings)
    logger.warning(
        "Job %s marked stale after %.1fs; current status=%s",
        record.job_id,
        stale_seconds,
        record.status,
    )
    return True


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
    job_started = time.perf_counter()
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

    try:
        queue_wait = max(
            0.0,
            (datetime.now(timezone.utc) - datetime.fromisoformat(record.created_at)).total_seconds(),
        )
    except (TypeError, ValueError):
        queue_wait = 0.0

    if _mark_job_stale_if_needed(record, settings):
        logger.warning("Job %s was already stale before work started.", job_id)
        return

    print(f"[JOB] process_job entered job={job_id} status={record.status}")
    log_memory(f"before_vertex job={job_id}")
    logger.info("[JOB] process_job entered job=%s status=%s", job_id, record.status)

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

        render_person = Path(record.person_file)

        logger.info("[IDENTITY] job=%s", job_id)
        logger.info("[IDENTITY] original_person=%s", render_person)
        logger.info("[IDENTITY] vertex_person=%s", render_person)
        logger.info("[IDENTITY] garment_reference=%s", record.garment_file)
        if Path(record.garment_file).resolve() == render_person.resolve():
            raise ProviderError(
                "Person and garment references must be different files.",
                code="identity_reference_conflict",
                provider=record.provider,
                retryable=False,
            )

        person_files = [
            Path(item)
            for item in (
                record.person_files or []
            )
        ]

        print(f"[JOB] provider.generate starting job={job_id} provider={record.provider}")
        logger.info("[JOB] provider.generate starting job=%s provider=%s", job_id, record.provider)

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
                render_person
            ),
            geometry_profile=(
                record.geometry_profile
            ),
            commercial_instructions=(
                record.commercial_instructions
            ),
                job_id=job_id,
                slot_index=record.slot_index,
        )

        # SAME-PHOTO quality retry (Phase 3C.2).
        #
        # Both generation rounds use the EXACT SAME assigned render_person and
        # the same garment. We never switch to another uploaded photo, never
        # index into person_files[n], and never fall back to an alternate
        # person. Only genuine quality failures (a distorted body or a garment
        # fidelity failure) are retried; safety blocks, auth/config errors and
        # invalid inputs are raised immediately without a second attempt.
        retry_history: list[dict[str, Any]] = []
        result = None

        # Hard cap of 2 Vertex generation rounds for a single job.
        max_attempts = max(
            1,
            min(
                1 if settings.tryfit_fast_mode else 2,
                int(
                    settings
                    .commercial_max_generation_rounds
                ),
            ),
        )

        # Only these provider error codes justify a same-photo retry.
        RETRYABLE_QUALITY_CODES = {
            "distorted_tryon_result",
            "garment_fidelity_failed",
        }

        provider_calls = 0
        for attempt_index in range(max_attempts):
            # Same photo every round. render_person is the assigned photo and
            # is never reassigned inside this loop.
            request.person_image = render_person
            if record.cloth_type in {"overall", "lower"}:
                request.geometry_reference_image = render_person
            request.seed = seed + attempt_index * 97
            request.attempt_index = attempt_index

            logger.info(
                "VTON ROUND %s/%s",
                attempt_index + 1,
                max_attempts,
            )
            logger.info(
                "PERSON USED: %s",
                render_person,
            )
            print(f"VTON ROUND {attempt_index + 1}/{max_attempts}")
            print(f"PERSON USED: {render_person}")
            print(f"[JOB] provider.generate attempt={attempt_index + 1}/{max_attempts} job={job_id}")

            try:
                provider_calls += 1
                round_started = time.perf_counter()
                print(f"[PERF] job={job_id} vertex_round_{attempt_index + 1}_start")
                result = provider.generate(request)
                log_memory(f"after_vertex job={job_id}")
                print(
                    f"[PERF] job={job_id} vertex_round_{attempt_index + 1}_end "
                    f"duration={time.perf_counter() - round_started:.2f}s"
                )
                retry_history.append({
                    "attempt": attempt_index + 1,
                    "round": attempt_index + 1,
                    "person_file": str(render_person),
                    "seed": request.seed,
                    "status": "provider_completed",
                })
                break
            except ProviderError as attempt_error:
                retry_history.append({
                    "attempt": attempt_index + 1,
                    "round": attempt_index + 1,
                    "person_file": str(render_person),
                    "seed": request.seed,
                    "status": "failed",
                    "error_code": attempt_error.code,
                    "error": str(attempt_error),
                })

                # Retry only genuine quality failures, and only while another
                # round remains. Safety blocks, auth/config errors and invalid
                # inputs are never retried.
                is_retryable_quality = (
                    attempt_error.code
                    in RETRYABLE_QUALITY_CODES
                )
                if (
                    not is_retryable_quality
                    or attempt_index >= max_attempts - 1
                ):
                    raise

        if result is None:
            raise ProviderError(
                "Try Fit generation exhausted all Phase 3C.2 retry strategies.",
                code="phase3c2_retry_exhausted",
            )

        final_path: Path | None = None

        if result.image_path is not None:
            provider_result_path = Path(result.image_path)
            final_path = _copy_result_file(
                provider_result_path,
                job_id,
                settings,
            )
            if not settings.debug_image_dumps:
                provider_result_path.unlink(missing_ok=True)

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
                enabled=settings.visual_enhancement_enabled and not settings.tryfit_fast_mode,
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
        log_memory(f"after_candidate_processing job={job_id}")

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
        metadata["provider_calls"] = provider_calls
        metadata["generation_rounds"] = max(generation_rounds, len(retry_history))
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
            candidate_scores = error_details.get("candidate_scores")
            if isinstance(candidate_scores, list):
                for candidate in candidate_scores:
                    logger.info(
                        "CANDIDATE QUALITY job_id=%s slot_index=%s %s",
                        job_id,
                        record.slot_index,
                        candidate,
                    )
                logger.info(
                    "NO ELIGIBLE CANDIDATE job_id=%s slot_index=%s",
                    job_id,
                    record.slot_index,
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
        total_elapsed = time.perf_counter() - job_started
        meta = record.provider_metadata if isinstance(record.provider_metadata, dict) else {}
        upload_ms = float(meta.get("upload_ms", 0.0))
        normalize_ms = float(meta.get("normalize_ms", 0.0))
        person_validation_ms = float(meta.get("person_validation_ms", 0.0))
        gemini_ms = float(meta.get("gemini_ms", 0.0))
        geometry_ms = float(meta.get("geometry_ms", 0.0))
        garment_analysis_ms = float(meta.get("garment_analysis_ms", 0.0))
        decode_ms = float(meta.get("decode_ms", 0.0))
        vertex_ms = float(meta.get("vertex_request_seconds", 0.0)) * 1000.0
        candidate_decode_ms = float(meta.get("candidate_decode_ms", 0.0))
        candidate_validation_ms = float(meta.get("candidate_validation_seconds", 0.0)) * 1000.0
        identity_validation_ms = float(meta.get("identity_validation_ms", 0.0))
        garment_validation_ms = float(meta.get("garment_validation_ms", 0.0))
        candidate_selection_ms = candidate_validation_ms
        cleanup_ms = max(0.0, (total_elapsed - queue_wait) * 1000.0 - vertex_ms - candidate_validation_ms)

        print(
            f"[PERF DETAIL] "
            f"job={job_id} "
            f"queue_wait_ms={queue_wait * 1000:.1f} "
            f"upload_ms={upload_ms:.1f} "
            f"decode_ms={decode_ms:.1f} "
            f"normalize_ms={normalize_ms:.1f} "
            f"person_validation_ms={person_validation_ms:.1f} "
            f"geometry_ms={geometry_ms:.1f} "
            f"garment_analysis_ms={garment_analysis_ms:.1f} "
            f"gemini_ms={gemini_ms:.1f} "
            f"vertex_ms={vertex_ms:.1f} "
            f"candidate_decode_ms={candidate_decode_ms:.1f} "
            f"identity_validation_ms={identity_validation_ms:.1f} "
            f"garment_validation_ms={garment_validation_ms:.1f} "
            f"candidate_selection_ms={candidate_selection_ms:.1f} "
            f"cleanup_ms={cleanup_ms:.1f} "
            f"total_ms={total_elapsed * 1000:.1f}"
        )
        print(
            f"[PERF] job={job_id} total_job={total_elapsed:.2f}s "
            f"queue_wait={queue_wait:.2f}s "
            f"provider_calls={locals().get('provider_calls', 0)} "
            f"retry_count={max(0, locals().get('provider_calls', 0) - 1)}"
        )
        log_memory(f"after_job_cleanup job={job_id}")
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