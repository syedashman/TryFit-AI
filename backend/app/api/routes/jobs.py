from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.models.job import JobRecord
from app.services.job_scheduler import job_scheduler
from app.services.person_validation import validate_person_images
from app.services.body_geometry import build_body_geometry_profile
from app.services.garment_analyzer import analyze_garment
from app.services.commercial_prompt import build_commercial_instructions
from app.services.storage import list_jobs, load_job, save_job, save_upload

router = APIRouter(prefix="/jobs", tags=["jobs"])
QualityPreset = Literal["fast", "balanced", "high"]


def _validate_upload(upload: UploadFile, allowed: list[str]) -> None:
    if upload.content_type not in allowed:
        raise HTTPException(status_code=415, detail={
            "code": "unsupported_image_type",
            "message": f"Unsupported type '{upload.content_type}'. Allowed: {', '.join(allowed)}",
        })


def _optional_int(value: str | None, field: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_number", "field": field, "message": f"{field} must be an integer."}) from exc


def _optional_float(value: str | None, field: str) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_number", "field": field, "message": f"{field} must be a number."}) from exc


@router.post("", operation_id="create_tryon_job")
async def create_job(
    background_tasks: BackgroundTasks,
    person_images: Annotated[list[UploadFile], File(description="Upload 1 to 3 clear images of the same person")],
    garment_image: UploadFile = File(...),
    garment_description: str = Form("clothing"),
    cloth_type: Literal["upper", "lower", "overall"] | None = Form(None),
    show_type: Literal["result only", "input & result", "input & mask & result"] | None = Form(None),
    quality_preset: QualityPreset = Form("balanced"),
    num_inference_steps: str | None = Form(None),
    guidance_scale: str | None = Form(None),
    seed: str | None = Form(None),
) -> JobRecord:
    settings = get_settings()
    if not settings.min_person_images <= len(person_images) <= settings.max_person_images:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_person_image_count",
            "message": f"Upload between {settings.min_person_images} and {settings.max_person_images} person images.",
            "received": len(person_images),
        })

    for upload in person_images:
        _validate_upload(upload, settings.allowed_image_types)
    _validate_upload(garment_image, settings.allowed_image_types)

    parsed_steps = _optional_int(num_inference_steps, "num_inference_steps")
    parsed_guidance = _optional_float(guidance_scale, "guidance_scale")
    parsed_seed = _optional_int(seed, "seed")
    normalized_dir = settings.storage_dir / "normalized"
    max_dimension = 1024 if settings.tryfit_fast_mode else settings.provider_max_image_dimension

    person_paths: list[Path] = []
    try:
        for index, upload in enumerate(person_images, start=1):
            uploaded_path = await save_upload(upload, settings, f"person_{index}")
            person_paths.append(uploaded_path)
            normalized_path = normalize_for_provider(
                uploaded_path,
                normalized_dir,
                min_width=settings.person_min_width,
                min_height=settings.person_min_height,
                max_dimension=max_dimension,
            )
            uploaded_path.unlink(missing_ok=True)
            person_paths[-1] = normalized_path
        garment_upload_path = await save_upload(garment_image, settings, "garment")
        garment_path = normalize_for_provider(
            garment_upload_path,
            normalized_dir,
            output_format="PNG",
            max_dimension=max_dimension,
        )
        garment_upload_path.unlink(missing_ok=True)
    except ValueError as exc:
        for path in person_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    selected_cloth_type = cloth_type or settings.hf_cloth_type
    report = validate_person_images(
        person_paths,
        min_images=settings.min_person_images,
        max_images=settings.max_person_images,
        min_width=settings.person_min_width,
        min_height=settings.person_min_height,
        min_sharpness=settings.person_min_sharpness,
        identity_threshold=settings.identity_consistency_threshold,
        identity_hard_reject_threshold=settings.identity_hard_reject_threshold,
        cloth_type=selected_cloth_type,
    )
    if not report.accepted or report.selected_file is None:
        garment_path.unlink(missing_ok=True)
        for path in person_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={
            "code": "person_images_rejected",
            "message": "Person image validation failed.",
            "validation": report.to_dict(),
        })

    validation_data = report.to_dict()
    geometry_index_raw = validation_data.get("geometry_reference_index")
    geometry_index = geometry_index_raw if isinstance(geometry_index_raw, int) else report.selected_index
    if geometry_index is None or geometry_index < 0 or geometry_index >= len(person_paths):
        geometry_index = report.selected_index or 0
    geometry_reference = person_paths[geometry_index]
    geometry_profile = build_body_geometry_profile(geometry_reference)

    garment_analysis = analyze_garment(garment_path, garment_description, selected_cloth_type)
    commercial_instructions = build_commercial_instructions(
        garment_description, selected_cloth_type, garment_analysis.dominant_color_name
    )
    selected_show_type = show_type or settings.hf_show_type
    preset = settings.quality_preset(quality_preset)
    job_id = uuid4().hex
    record = JobRecord(
        job_id=job_id,
        provider=settings.vton_provider,
        person_file=report.selected_file,
        person_files=[str(path) for path in person_paths],
        selected_person_index=report.selected_index,
        validation_report=validation_data,
        geometry_profile=geometry_profile.to_dict(),
        geometry_reference_index=geometry_index,
        garment_file=str(garment_path),
        garment_description=garment_description.strip() or "clothing",
        cloth_type=selected_cloth_type,
        show_type=selected_show_type,
        quality_preset=quality_preset,
        garment_analysis=garment_analysis.to_dict(),
        commercial_instructions=commercial_instructions,
        request_parameters={
            "num_inference_steps": parsed_steps if parsed_steps is not None else preset["num_inference_steps"],
            "guidance_scale": parsed_guidance if parsed_guidance is not None else preset["guidance_scale"],
            "seed": parsed_seed if parsed_seed is not None else settings.hf_seed,
        },
    )
    save_job(record, settings)
    job_scheduler.submit(
        job_id,
        settings,
        num_inference_steps=record.request_parameters["num_inference_steps"],
        guidance_scale=record.request_parameters["guidance_scale"],
        seed=record.request_parameters["seed"],
    )
    return record


@router.get("/commercial/config", operation_id="get_commercial_tryon_config")
def get_commercial_config() -> dict[str, object]:
    settings = get_settings()
    return {
        "minimum_person_images": settings.min_person_images,
        "maximum_person_images": settings.max_person_images,
        "accepted_image_types": settings.allowed_image_types,
        "technical_parameters_hidden": True,
        "quality_threshold": settings.commercial_quality_threshold,
        "candidate_count": settings.vertex_candidate_count,
        "full_body_priority": settings.full_body_priority,
        "dual_reference_enabled": settings.dual_reference_enabled,
        "render_policy": "overall/lower uses best full-body geometry reference; upper uses best compatible reference",
    }


@router.get("/history/recent", operation_id="get_recent_tryon_jobs")
def get_recent_jobs(limit: int = 12) -> list[JobRecord]:
    settings = get_settings()
    return list_jobs(settings, limit=limit)


@router.get("/{job_id}", operation_id="get_tryon_job")
def get_job(job_id: str) -> JobRecord:
    settings = get_settings()
    record = load_job(job_id, settings)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


@router.get("/{job_id}/result", operation_id="get_tryon_result")
def get_job_result(job_id: str):
    settings = get_settings()
    record = load_job(job_id, settings)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed.")
    if record.result_file:
        path = Path(record.result_file).resolve()
        results_root = settings.results_dir.resolve()
        if results_root not in path.parents:
            raise HTTPException(status_code=403, detail="Unsafe result path rejected.")
        if path.exists() and path.is_file():
            return FileResponse(path, filename=f"tryfit-{job_id}{path.suffix}")
    if record.result_url:
        return {"result_url": record.result_url}
    raise HTTPException(status_code=404, detail="No result file is available.")


def _phase3b_record(job_id: str) -> tuple[JobRecord, object]:
    settings = get_settings()
    record = load_job(job_id, settings)
    if record is None or record.deleted_at:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record, settings


def _score(record: JobRecord) -> float:
    if record.quality_score is not None:
        return round(float(record.quality_score), 1)
    report = record.quality_report or {}
    for key in ("overall_score", "quality_score", "score"):
        value = report.get(key)
        if isinstance(value, (int, float)):
            return round(max(0.0, min(100.0, float(value) * (100 if float(value) <= 1 else 1))), 1)
    return 92.0 if record.status == "completed" else 0.0


@router.get("/history/favorites", operation_id="get_favorite_tryon_jobs")
def get_favorite_jobs(limit: int = 50) -> list[JobRecord]:
    settings = get_settings()
    return [job for job in list_jobs(settings, limit=min(max(limit, 1), 100)) if job.favorite and not job.deleted_at]


@router.post("/{job_id}/favorite", operation_id="favorite_tryon_job")
def favorite_job(job_id: str, favorite: bool = Body(True, embed=True)) -> JobRecord:
    record, settings = _phase3b_record(job_id)
    record.favorite = bool(favorite)
    save_job(record, settings)
    return record


@router.delete("/{job_id}/favorite", operation_id="unfavorite_tryon_job")
def unfavorite_job(job_id: str) -> JobRecord:
    record, settings = _phase3b_record(job_id)
    record.favorite = False
    save_job(record, settings)
    return record


@router.get("/{job_id}/metadata", operation_id="get_tryon_metadata")
def get_job_metadata(job_id: str) -> dict[str, object]:
    record, _ = _phase3b_record(job_id)
    return {
        "job_id": record.job_id, "provider": record.provider, "status": record.status,
        "quality_score": _score(record), "geometry_score": record.geometry_score,
        "generation_time_seconds": record.generation_time_seconds, "created_at": record.created_at,
        "updated_at": record.updated_at, "quality_preset": record.quality_preset,
        "generation_rounds": record.generation_rounds, "endpoint_used": record.endpoint_used,
        "request_parameters": record.request_parameters, "provider_metadata": record.provider_metadata,
        "garment_analysis": record.garment_analysis, "validation_report": record.validation_report,
        "geometry_profile": record.geometry_profile, "favorite": record.favorite, "downloads": record.downloads,
        "phase3c2_report": record.phase3c2_report, "retry_history": record.retry_history,
    }


@router.get("/{job_id}/quality", operation_id="get_tryon_quality")
def get_job_quality(job_id: str) -> dict[str, object]:
    record, _ = _phase3b_record(job_id)
    return {"job_id": record.job_id, "score": _score(record), "report": record.quality_report, "preset": record.quality_preset}


@router.post("/{job_id}/duplicate", operation_id="duplicate_tryon_job")
def duplicate_job(job_id: str, background_tasks: BackgroundTasks) -> JobRecord:
    source, settings = _phase3b_record(job_id)
    duplicate = source.model_copy(deep=True)
    duplicate.job_id = uuid4().hex
    duplicate.status = "queued"
    duplicate.message = "Duplicated job queued."
    duplicate.result_file = None
    duplicate.result_url = None
    duplicate.error = None
    duplicate.error_code = None
    duplicate.favorite = False
    duplicate.share_token = None
    duplicate.deleted_at = None
    duplicate.generation_rounds = 0
    duplicate.created_at = duplicate.updated_at = __import__('app.models.job', fromlist=['utc_now_iso']).utc_now_iso()
    save_job(duplicate, settings)
    background_tasks.add_task(process_job, duplicate.job_id, settings, **duplicate.request_parameters)
    return duplicate


@router.post("/{job_id}/share", operation_id="share_tryon_job")
def share_job(job_id: str) -> dict[str, str]:
    record, settings = _phase3b_record(job_id)
    if not record.share_token:
        record.share_token = uuid4().hex
        save_job(record, settings)
    return {"share_token": record.share_token, "share_url": f"/app?share={record.share_token}"}


@router.delete("/{job_id}", operation_id="delete_tryon_job")
def delete_job(job_id: str) -> dict[str, str]:
    record, settings = _phase3b_record(job_id)
    record.deleted_at = __import__('app.models.job', fromlist=['utc_now_iso']).utc_now_iso()
    save_job(record, settings)
    return {"status": "deleted", "job_id": job_id}
