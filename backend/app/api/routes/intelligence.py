from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.routes.catalog import _catalog_root, _clean_category, _files
from app.api.routes.jobs import _validate_upload
from app.core.config import get_settings
from app.services.autonomous_analysis import analyze_person_set, analyze_product
from app.services.storage import save_upload

router = APIRouter(prefix="/intelligence", tags=["phase-3c1-intelligence"])


@router.get("/capabilities", operation_id="get_intelligence_capabilities")
def capabilities() -> dict[str, object]:
    return {
        "phase": "Sprint 4 Phase 3C.1",
        "analysis_version": "3C.1",
        "zero_manual_metadata": True,
        "provider_neutral": True,
        "features": [
            "automatic product scope classification", "reference pose-family analysis",
            "camera-angle analysis", "dominant color analysis", "person-photo quality ranking",
            "automatic best-input recommendation", "product-lock signature generation",
        ],
    }


@router.post("/catalog-product", operation_id="analyze_catalog_product")
def analyze_catalog_product(
    category: str = Form(...), product_number: str = Form(...), color: str = Form(...),
    garment_description: str = Form("complete outfit"),
    cloth_type: Literal["upper", "lower", "overall"] = Form("overall"),
) -> dict[str, object]:
    category_name = _clean_category(category)
    product_dir = (_catalog_root() / category_name / product_number).resolve()
    root = _catalog_root().resolve()
    if root not in product_dir.parents or not product_dir.exists():
        raise HTTPException(status_code=404, detail="Catalog product not found.")
    color_dirs = {p.name.lower(): p for p in product_dir.iterdir() if p.is_dir()}
    chosen = color_dirs.get(color.strip().lower()) if color_dirs else product_dir
    if chosen is None:
        raise HTTPException(status_code=404, detail="Catalog color not found.")
    paths = _files(chosen)
    if not paths:
        raise HTTPException(status_code=422, detail="No garment references found.")
    return analyze_product(paths, garment_description, cloth_type, color, category_name).to_dict()


@router.post("/person-set", operation_id="analyze_person_photo_set")
async def analyze_person_photo_set(
    person_images: Annotated[list[UploadFile], File(description="Upload 3 to 5 person images")],
) -> dict[str, object]:
    settings = get_settings()
    if not settings.min_person_images <= len(person_images) <= settings.max_person_images:
        raise HTTPException(status_code=422, detail="Upload 3 to 5 person images.")
    paths: list[Path] = []
    try:
        for index, upload in enumerate(person_images, start=1):
            _validate_upload(upload, settings.allowed_image_types)
            paths.append(await save_upload(upload, settings, f"analysis_person_{index}"))
        return analyze_person_set(paths)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
