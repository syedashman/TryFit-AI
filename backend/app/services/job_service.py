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
from app.services.body_geometry import build_body_geometry_profile
from app.services.image_normalizer import normalize_for_provider
from app.services.person_validation import validate_person_images
from app.services.pose_customization import (
    PoseCustomizationError,
    generate_posed_reference,
    verify_person_preservation,
)
from app.services.storage import (
    load_job,
    save_job,
    list_batch_jobs,
)
from app.services.memory_metrics import log_memory

logger = logging.getLogger(__name__)
_IDENTITY_REVIEW_TRIGGER_SCORE = 0.82


def _needs_identity_review(
    metadata: dict[str, Any],
) -> bool:
    candidates = metadata.get("candidate_scores")
    if not isinstance(candidates, list):
        return True

    selected_index = metadata.get("selected_candidate_index")
    if isinstance(selected_index, bool) or not isinstance(selected_index, int):
        return True
    if selected_index < 0 or selected_index >= len(candidates):
        return True

    selected = candidates[selected_index]
    if not isinstance(selected, dict) or selected.get("identity_reliable") is not True:
        return True

    identity_score = selected.get("identity_score")
    if isinstance(identity_score, bool) or not isinstance(identity_score, (int, float)):
        return True

    geometry_score = selected.get(
        "full_body_similarity",
        selected.get("geometry_similarity"),
    )
    if isinstance(geometry_score, bool) or not isinstance(geometry_score, (int, float)):
        return True

    return (
        identity_score < _IDENTITY_REVIEW_TRIGGER_SCORE
        or geometry_score < 0.90
    )


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


def _prepare_pose_render_person(
    record: JobRecord,
    settings: Settings,
) -> tuple[Path, dict[str, object], Path | None]:
    original_person = Path(record.person_file)
    metadata = record.provider_metadata or {}
    pose_name = metadata.get("pose_reference_name")
    if not pose_name:
        return original_person, record.geometry_profile, None
    if not isinstance(pose_name, str):
        raise ProviderError(
            "The requested pose reference is invalid.",
            code="pose_reference_invalid",
            provider=record.provider,
            retryable=False,
        )

    category = str(metadata.get("catalog_category", "")).lower()
    subject_description = {
        "men": "an adult man",
        "women": "an adult woman",
        "kids": "a child",
    }.get(category, "a person")
    try:
        pose_image = generate_posed_reference(
            settings,
            [original_person],
            pose_name,
            subject_description,
            settings.storage_dir / "pose_cache",
            body_geometry=record.geometry_profile,
        )
    except PoseCustomizationError as exc:
        raise ProviderError(
            "Could not prepare this pose; the other Try Fit outputs are unaffected.",
            code="pose_synthesis_failed",
            provider=record.provider,
            retryable=True,
            details={"pose_reference_name": pose_name},
        ) from exc

    normalized_pose: Path | None = None
    try:
        normalized_pose = normalize_for_provider(
            pose_image,
            settings.storage_dir / "normalized",
            output_format=settings.provider_image_format,
            min_width=settings.person_min_width,
            min_height=settings.person_min_height,
            max_dimension=settings.effective_max_image_dimension,
        )
        report = validate_person_images(
            [normalized_pose],
            min_images=1,
            max_images=1,
            min_width=settings.person_min_width,
            min_height=settings.person_min_height,
            min_sharpness=settings.person_min_sharpness,
            identity_threshold=settings.identity_consistency_threshold,
            identity_hard_reject_threshold=settings.identity_hard_reject_threshold,
            cloth_type=record.cloth_type,
        )
        if not report.accepted:
            raise ProviderError(
                "The generated pose reference did not pass person-photo validation.",
                code="pose_reference_rejected",
                provider=record.provider,
                retryable=False,
                details={"validation": report.to_dict()},
            )
        geometry = build_body_geometry_profile(normalized_pose)
        return normalized_pose, geometry.to_dict(), normalized_pose
    except Exception:
        if normalized_pose is not None:
            normalized_pose.unlink(missing_ok=True)
        raise
    finally:
        pose_image.unlink(missing_ok=True)


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

    generated_render_person: Path | None = None
    try:
        provider = get_vton_provider(
            settings
        )

        original_person = Path(record.person_file)
        (
            render_person,
            render_geometry_profile,
            generated_render_person,
        ) = _prepare_pose_render_person(record, settings)

        if Path(record.garment_file).resolve() == original_person.resolve():
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
            person_images=(
                [render_person]
                if generated_render_person is not None
                else person_files
            ),
            geometry_reference_image=(
                render_person
            ),
            identity_reference_image=(
                original_person
                if generated_render_person is not None
                else None
            ),
            geometry_profile=render_geometry_profile,
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
                    settings.effective_max_generation_rounds
                ),
            ),
        )

        # Only these provider error codes justify a same-photo retry.
        RETRYABLE_QUALITY_CODES = {
            "distorted_tryon_result",
            "garment_fidelity_failed",
        }

        provider_calls = 0
        pose_fallback_attempted = False
        for attempt_index in range(max_attempts):
            # Keep each retry on the same assigned input; only the explicit
            # predefined-pose recovery below may switch back to the upload.
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
                "VTON attempt job=%s round=%s/%s",
                job_id,
                attempt_index + 1,
                max_attempts,
            )

            try:
                provider_calls += 1
                round_started = time.perf_counter()
                result = provider.generate(request)
                log_memory(f"after_vertex job={job_id}")
                logger.info(
                    "Provider attempt complete job=%s round=%s duration_seconds=%.2f",
                    job_id,
                    attempt_index + 1,
                    time.perf_counter() - round_started,
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
                if not is_retryable_quality:
                    raise
                if attempt_index < max_attempts - 1:
                    continue
                if generated_render_person is None or pose_fallback_attempted:
                    raise

                pose_fallback_attempted = True
                original_geometry = (
                    record.geometry_profile
                    if isinstance(record.geometry_profile, dict)
                    else build_body_geometry_profile(original_person).to_dict()
                )
                request.person_image = original_person
                request.person_images = [original_person]
                request.geometry_reference_image = original_person
                request.identity_reference_image = original_person
                request.geometry_profile = original_geometry
                request.seed = seed + max_attempts * 97
                request.attempt_index = max_attempts

                record.provider_metadata = {
                    **(
                        record.provider_metadata
                        if isinstance(record.provider_metadata, dict)
                        else {}
                    ),
                    "pose_fallback": {
                        "strategy": "uploaded_photo_original_pose",
                        "reason_code": attempt_error.code,
                        "reason": str(attempt_error),
                    },
                    "pose_source_strategy": "uploaded_photo_quality_fallback",
                }
                logger.warning(
                    "Predefined-pose candidates failed quality checks; "
                    "retrying uploaded photo job=%s pose=%s reason=%s",
                    job_id,
                    record.provider_metadata.get("pose_reference_name"),
                    attempt_error.code,
                )
                generated_render_person.unlink(missing_ok=True)
                generated_render_person = None

                fallback_attempt = len(retry_history) + 1
                try:
                    provider_calls += 1
                    result = provider.generate(request)
                    retry_history.append({
                        "attempt": fallback_attempt,
                        "round": "uploaded_photo_fallback",
                        "person_file": str(original_person),
                        "seed": request.seed,
                        "status": "provider_completed",
                    })
                except ProviderError as fallback_error:
                    retry_history.append({
                        "attempt": fallback_attempt,
                        "round": "uploaded_photo_fallback",
                        "person_file": str(original_person),
                        "seed": request.seed,
                        "status": "failed",
                        "error_code": fallback_error.code,
                        "error": str(fallback_error),
                    })
                    raise
                break

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
            if not settings.effective_debug_image_dumps:
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

        if (
            record.provider == "vertex"
            and final_path is not None
            and _needs_identity_review(metadata)
        ):
            try:
                identity_review = verify_person_preservation(
                    settings,
                    original_person,
                    final_path,
                )
            except PoseCustomizationError as exc:
                raise ProviderError(
                    "Could not verify that the try-on preserved the uploaded person.",
                    code="identity_preservation_review_failed",
                    provider=record.provider,
                    retryable=False,
                ) from exc

            metadata["identity_preservation_review"] = identity_review.to_dict()
            if identity_review.should_reject:
                record.provider_metadata = metadata
                raise ProviderError(
                    "The generated try-on changed the user's identity or visible body proportions.",
                    code="identity_preservation_failed",
                    provider=record.provider,
                    retryable=False,
                    details={"identity_preservation_review": identity_review.to_dict()},
                )

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
                for sibling in list_batch_jobs(batch_id, settings):
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

        if exc.code == "identity_preservation_failed":
            rejected_result_path = locals().get("final_path")
            if isinstance(rejected_result_path, Path):
                rejected_result_path.unlink(missing_ok=True)

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
        logger.info(
            "Job complete job=%s total_seconds=%.2f queue_wait_seconds=%.2f "
            "provider_calls=%s retry_count=%s",
            job_id,
            total_elapsed,
            queue_wait,
            locals().get("provider_calls", 0),
            max(0, locals().get("provider_calls", 0) - 1),
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

        if generated_render_person is not None:
            generated_render_person.unlink(missing_ok=True)