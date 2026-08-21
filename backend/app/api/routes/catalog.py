from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.api.routes.jobs import _optional_float, _optional_int, _validate_upload
from app.core.config import get_settings
from app.models.job import JobRecord
from app.services.body_geometry import build_body_geometry_profile, geometry_similarity
from app.services.commercial_prompt import build_commercial_instructions
from app.services.garment_analyzer import analyze_garment
from app.services.job_scheduler import job_scheduler
from app.services.person_validation import validate_person_images
from app.services.photo_category_check import check_photos_match_category
from app.services.storage import list_jobs, load_job, save_job, save_upload

router = APIRouter(prefix="/catalog", tags=["catalog"])
QualityPreset = Literal["fast", "balanced", "high"]


def _catalog_root() -> Path:
    return Path(__file__).resolve().parents[2] / "static" / "catalog"


def _clean_category(value: str) -> str:
    value = value.strip().lower()
    mapping = {"men": "Men", "women": "Women", "kids": "Kids"}
    if value not in mapping:
        raise HTTPException(status_code=422, detail="Unknown catalog category.")
    return mapping[value]


def _files(path: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".jfif"}
    return sorted([p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in allowed], key=lambda p: p.as_posix().lower())


def _product_payload(category: str, product_dir: Path) -> dict[str, object]:
    direct = [p for p in product_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".jfif"}]
    color_dirs = sorted([p for p in product_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    colors: list[dict[str, object]] = []
    if direct:
        assets = sorted(direct, key=lambda p: p.name.lower())
        colors.append({
            "name": "Default",
            "count": len(assets),
            "assets": [f"/static/catalog/{category}/{product_dir.name}/{p.name}" for p in assets],
        })
    for color_dir in color_dirs:
        assets = _files(color_dir)
        if assets:
            colors.append({
                "name": color_dir.name,
                "count": len(assets),
                "assets": [f"/static/catalog/{category}/{product_dir.name}/{p.relative_to(product_dir).as_posix()}" for p in assets],
            })
    all_assets = [asset for color in colors for asset in color["assets"]]
    return {
        "id": f"{category.lower()}-{product_dir.name}",
        "category": category,
        "name": f"{category} Outfit {product_dir.name}",
        "product_number": product_dir.name,
        "thumbnail": all_assets[0] if all_assets else None,
        "image_count": len(all_assets),
        "color_count": len(colors),
        "colors": colors,
    }


@router.get("", operation_id="get_catalog")
def get_catalog() -> dict[str, object]:
    root = _catalog_root()
    categories: dict[str, list[dict[str, object]]] = {}
    for category in ("Men", "Women", "Kids"):
        category_dir = root / category
        products = []
        if category_dir.exists():
            for product_dir in sorted([p for p in category_dir.iterdir() if p.is_dir()], key=lambda p: (int(p.name) if p.name.isdigit() else 9999, p.name)):
                payload = _product_payload(category, product_dir)
                if payload["image_count"]:
                    products.append(payload)
        categories[category.lower()] = products
    return {
        "categories": categories,
        "total_products": sum(len(items) for items in categories.values()),
        "total_images": sum(int(item["image_count"]) for items in categories.values() for item in items),
        "age_policy": "Age-neutral: newborns, children, adults and elderly people are accepted when the provider accepts the image.",
    }


@router.post("/generate", operation_id="generate_catalog_tryon")
async def generate_catalog_tryon(
    background_tasks: BackgroundTasks,
    person_images: Annotated[list[UploadFile], File(description="Upload 3 to 5 clear images of the same person")],
    category: str = Form(...),
    product_number: str = Form(...),
    color: str = Form(...),
    garment_description: str = Form("complete outfit"),
    cloth_type: Literal["upper", "lower", "overall"] = Form("overall"),
    quality_preset: QualityPreset = Form("balanced"),
    num_inference_steps: str | None = Form(None),
    guidance_scale: str | None = Form(None),
    seed: str | None = Form(None),
) -> dict[str, object]:
    settings = get_settings()
    if not 3 <= len(person_images) <= 5:
        raise HTTPException(status_code=422, detail={"code": "invalid_person_image_count", "message": "Upload a minimum of 3 and a maximum of 5 person images."})
    for upload in person_images:
        _validate_upload(upload, settings.allowed_image_types)

    category_name = _clean_category(category)
    product_dir = (_catalog_root() / category_name / product_number).resolve()
    root = _catalog_root().resolve()
    if root not in product_dir.parents or not product_dir.exists():
        raise HTTPException(status_code=404, detail="Catalog product not found.")

    color_dirs = {p.name.lower(): p for p in product_dir.iterdir() if p.is_dir()}
    if color.strip().lower() == "all":
        raise HTTPException(status_code=422, detail="Select one product color before generating Try Fit images.")
    if color_dirs:
        chosen = color_dirs.get(color.strip().lower())
        if chosen is None:
            raise HTTPException(status_code=404, detail="Catalog color not found.")
        garment_paths = _files(chosen)
    else:
        garment_paths = [p for p in _files(product_dir) if p.parent == product_dir]

    if not garment_paths:
        raise HTTPException(status_code=422, detail="No garment images are available for this selection.")

    parsed_steps = _optional_int(num_inference_steps, "num_inference_steps")
    parsed_guidance = _optional_float(guidance_scale, "guidance_scale")
    parsed_seed = _optional_int(seed, "seed")
    preset = settings.quality_preset(quality_preset)

    person_paths: list[Path] = []
    try:
        for index, upload in enumerate(person_images, start=1):
            person_paths.append(await save_upload(upload, settings, f"person_{index}"))
    except ValueError as exc:
        for path in person_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    report = validate_person_images(
        person_paths,
        min_images=settings.min_person_images,
        max_images=settings.max_person_images,
        min_width=settings.person_min_width,
        min_height=settings.person_min_height,
        min_sharpness=settings.person_min_sharpness,
        identity_threshold=settings.identity_consistency_threshold,
        identity_hard_reject_threshold=settings.identity_hard_reject_threshold,
        cloth_type=cloth_type,
    )
    if not report.accepted or report.selected_file is None:
        for path in person_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={"code": "person_images_rejected", "message": "Person image validation failed.", "validation": report.to_dict()})

    category_ok, category_error = check_photos_match_category(settings, person_paths, category_name)
    if not category_ok:
        for path in person_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={"code": "photo_category_mismatch", "message": category_error})

    validation_data = report.to_dict()
    geometry_index = validation_data.get("geometry_reference_index")
    if not isinstance(geometry_index, int) or geometry_index < 0 or geometry_index >= len(person_paths):
        geometry_index = report.selected_index or 0
    person_geometry_profiles = [build_body_geometry_profile(path) for path in person_paths]
    geometry_profile = person_geometry_profiles[geometry_index]

    best_matched_person_index = geometry_index
    primary_garment_path = garment_paths[0]
    relative = primary_garment_path.relative_to(product_dir)
    color_name = relative.parts[0] if len(relative.parts) > 1 else "Default"
    analysis = analyze_garment(primary_garment_path, garment_description, cloth_type)
    base_seed = parsed_seed if parsed_seed is not None else settings.hf_seed

    batch_id = uuid4().hex
    jobs: list[JobRecord] = []
    batch_started = time.perf_counter()
    print(
        f"[PERF] Batch {batch_id} queued: total_jobs={len(person_paths)} concurrency={settings.max_concurrent_jobs}"
    )
    print(f"[BATCH] created batch={batch_id} jobs={len(person_paths)} concurrency={settings.max_concurrent_jobs}")
    for index, person_path in enumerate(person_paths, start=1):
        job_id = uuid4().hex
        record = JobRecord(
            job_id=job_id,
            provider=settings.vton_provider,
            message=f"Queued {index} of {len(person_paths)}.",
            person_file=str(person_path),
            person_files=[str(path) for path in person_paths],
            selected_person_index=report.selected_index,
            validation_report=validation_data,
            geometry_profile=person_geometry_profiles[index - 1].to_dict(),
            geometry_reference_index=index - 1,
            garment_file=str(primary_garment_path),
            garment_description=(
                f"{garment_description}; category {category_name}; selected color {color_name}. "
                "Preserve the complete product identity exactly: all garment pieces, silhouette, length, neckline, "
                "collar, sleeves, cuffs, closures, embroidery, print, texture, fabric, trim, matching bottoms and layers. "
                "Never reinterpret a complete outfit as an upper-only shirt and never remove a product component. "
                "Keep the shopper's own uploaded pose, framing, and camera angle exactly as-is — only replace their "
                f"clothing with this product. Use catalog composition reference {primary_garment_path.stem}."
            ),
            cloth_type=cloth_type,
            show_type="result only",
            quality_preset=quality_preset,
            garment_analysis=analysis.to_dict(),
            commercial_instructions=build_commercial_instructions(garment_description, cloth_type, analysis.dominant_color_name),
            request_parameters={
                "num_inference_steps": parsed_steps if parsed_steps is not None else preset["num_inference_steps"],
                "guidance_scale": parsed_guidance if parsed_guidance is not None else preset["guidance_scale"],
                "seed": base_seed + index - 1,
            },
            provider_metadata={
                "batch_id": batch_id,
                "catalog_category": category_name,
                "catalog_product": product_number,
                "catalog_color": color_name,
                "catalog_pose": primary_garment_path.stem,
                "catalog_reference": f"/static/catalog/{category_name}/{product_number}/{relative.as_posix()}",
                "batch_index": index,
                "batch_total": len(person_paths),
                "person_source_index": index - 1,
                "person_source_framing": str(report.images[index - 1].framing) if index - 1 < len(report.images) else "unknown",
                "pose_source_strategy": "match_uploaded_photo_pose",
                "age_neutral_validation": True,
                "product_integrity_lock": True,
                "selected_color_only": True,
            },
        )
        save_job(record, settings)
        jobs.append(record)
        print(f"[JOB] scheduling job={job_id} batch={batch_id} index={index}/{len(person_paths)}")
        job_scheduler.submit(
            job_id,
            settings,
            num_inference_steps=record.request_parameters["num_inference_steps"],
            guidance_scale=record.request_parameters["guidance_scale"],
            seed=record.request_parameters["seed"],
        )

    batch_elapsed = time.perf_counter() - batch_started
    print(f"[PERF] Batch {batch_id} scheduling complete: elapsed={batch_elapsed:.2f}s")
    return {
        "batch_id": batch_id,
        "expected_outputs": len(jobs),
        "jobs": [job.model_dump() for job in jobs],
        "message": f"{len(jobs)} Try Fit images queued, one per uploaded photo.",
    }


@router.get("/batch/{batch_id}", operation_id="get_catalog_batch_status")
def get_catalog_batch_status(batch_id: str) -> dict[str, object]:
    settings = get_settings()
    jobs = []
    for record in list_jobs(settings, limit=500):
        metadata = record.provider_metadata if isinstance(record.provider_metadata, dict) else {}
        if metadata.get("batch_id") == batch_id:
            jobs.append(record)
    if not jobs:
        raise HTTPException(status_code=404, detail="Catalog batch not found.")
    jobs.sort(key=lambda item: int((item.provider_metadata or {}).get("batch_index", 0)))
    refreshed_jobs: list[JobRecord] = []
    for job in jobs:
        if job.status in {"queued", "processing"}:
            stale = job.updated_at
            try:
                updated_at = datetime.fromisoformat(stale)
            except ValueError:
                updated_at = datetime.now(timezone.utc)
            if (datetime.now(timezone.utc) - updated_at).total_seconds() > settings.job_stale_timeout_seconds:
                job.status = "failed"
                job.message = "This look took too long to create. Please retry."
                job.error = "Job exceeded the allowed generation time and was marked failed to avoid a never-ending spinner."
                job.error_code = "job_stale_timeout"
                save_job(job, settings)
        refreshed = load_job(job.job_id, settings)
        if refreshed is not None:
            refreshed_jobs.append(refreshed)
    jobs = refreshed_jobs
    counts = {status: sum(1 for item in jobs if item.status == status) for status in ("queued", "processing", "completed", "failed")}
    completed = counts["completed"]
    total = len(jobs)
    return {
        "batch_id": batch_id,
        "expected_outputs": total,
        "completed_outputs": completed,
        "failed_outputs": counts["failed"],
        "pending_outputs": counts["queued"] + counts["processing"],
        "progress_percent": round((completed + counts["failed"]) / max(1, total) * 100, 1),
        "all_finished": completed + counts["failed"] == total,
        "all_successful": completed == total,
        "counts": counts,
        "jobs": [item.model_dump() for item in jobs],
    }


@router.post("/retry/{job_id}", operation_id="retry_catalog_tryon_job")
def retry_catalog_tryon_job(job_id: str, background_tasks: BackgroundTasks) -> dict[str, object]:
    settings = get_settings()
    print(f"[RETRY] request job={job_id}")

    original = load_job(job_id, settings)
    if original is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    print(f"[RETRY] original person={original.person_file}")

    new_job_id = uuid4().hex
    new_seed = original.request_parameters.get("seed")
    if isinstance(new_seed, (int, float)):
        new_seed = int(new_seed) + 1000 + (hash(new_job_id) % 9000)
    else:
        new_seed = hash(new_job_id) % 100000

    new_metadata = dict(original.provider_metadata or {})
    new_metadata["retried_from"] = job_id

    record = JobRecord(
        job_id=new_job_id,
        status="queued",
        provider=original.provider,
        message="Retrying this pose.",
        person_file=original.person_file,
        person_files=list(original.person_files),
        selected_person_index=original.selected_person_index,
        validation_report=dict(original.validation_report),
        geometry_profile=dict(original.geometry_profile),
        geometry_reference_index=original.geometry_reference_index,
        garment_file=original.garment_file,
        garment_description=original.garment_description,
        cloth_type=original.cloth_type,
        show_type=original.show_type,
        quality_preset=original.quality_preset,
        garment_analysis=dict(original.garment_analysis),
        commercial_instructions=original.commercial_instructions,
        request_parameters={
            **original.request_parameters,
            "seed": new_seed,
        },
        provider_metadata=new_metadata,
        result_file=None,
        result_url=None,
        error=None,
        error_code=None,
        quality_report={},
        phase3c2_report={},
        retry_history=[],
        generation_rounds=0,
        quality_score=None,
        geometry_score=None,
        generation_time_seconds=None,
        endpoint_used=None,
        favorite=False,
        notes="",
        downloads=0,
        share_token=None,
        deleted_at=None,
    )
    save_job(record, settings)
    print(f"[RETRY] scheduling job={new_job_id}")
    job_scheduler.submit(
        new_job_id,
        settings,
        num_inference_steps=record.request_parameters.get("num_inference_steps", 0),
        guidance_scale=record.request_parameters.get("guidance_scale", 0.0),
        seed=new_seed,
    )
    print(f"[RETRY] scheduled job={new_job_id}")
    return {"job_id": new_job_id, "message": "Retrying this pose."}