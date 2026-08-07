from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageStat


@dataclass(slots=True)
class VisualEnhancementReport:
    applied: bool
    source_mode: str
    output_mode: str
    width: int
    height: int
    sharpness_before: float
    sharpness_after: float
    contrast_before: float
    contrast_after: float
    profile: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_realism_directives(cloth_type: str) -> str:
    normalized = (cloth_type or "").strip().lower()

    shared = (
        "Preserve the garment's original print scale, weave, seams, neckline, "
        "cuffs, hem and color. Create physically plausible fabric drape, soft "
        "gravity-driven folds, contact shadows and lighting that matches the "
        "person image. Keep clean garment boundaries without halos, melted "
        "fingers, duplicated limbs, texture smearing or painted-on fabric."
    )

    scoped = {
        "upper": (
            "Fit the shoulders, armholes, sleeves and torso naturally while "
            "keeping the waist and lower body untouched."
        ),
        "lower": (
            "Fit the waistband, hips, knees and ankle fall naturally while "
            "keeping the face, hair, hands and upper body untouched."
        ),
        "overall": (
            "Maintain continuous fabric flow from shoulders to hem, realistic "
            "sleeve articulation and natural trouser or dress fall at the ankles."
        ),
    }.get(normalized, "Keep the original body silhouette and anatomy unchanged.")

    return f"{scoped} {shared}"


def _detail_score(image: Image.Image) -> float:
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return round(float(ImageStat.Stat(edges).mean[0]) / 255.0, 4)


def _contrast_score(image: Image.Image) -> float:
    gray = image.convert("L")
    return round(min(1.0, float(ImageStat.Stat(gray).stddev[0]) / 64.0), 4)


def enhance_result_image(
    path: Path,
    *,
    enabled: bool = True,
    sharpness: float = 1.08,
    contrast: float = 1.03,
    color: float = 1.01,
) -> VisualEnhancementReport:
    """Apply conservative detail refinement without changing geometry or size."""
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Result image does not exist: {path}")

    if sharpness <= 0 or contrast <= 0 or color <= 0:
        raise ValueError("Visual enhancement factors must be positive.")

    with Image.open(path) as opened:
        image = opened.copy()
        source_mode = image.mode
        width, height = image.size
        before_detail = _detail_score(image)
        before_contrast = _contrast_score(image)

        if enabled:
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            working = image.convert("RGB")
            working = ImageEnhance.Contrast(working).enhance(contrast)
            working = ImageEnhance.Color(working).enhance(color)
            working = ImageEnhance.Sharpness(working).enhance(sharpness)
            working = working.filter(
                ImageFilter.UnsharpMask(radius=1.0, percent=35, threshold=3)
            )

            if alpha is not None:
                working = working.convert("RGBA")
                working.putalpha(alpha)

            save_kwargs: dict[str, object] = {}
            suffix = path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                working = working.convert("RGB")
                save_kwargs = {"quality": 95, "subsampling": 0, "optimize": True}
            elif suffix == ".png":
                save_kwargs = {"optimize": True}

            working.save(path, **save_kwargs)
            output = working
        else:
            output = image

        return VisualEnhancementReport(
            applied=enabled,
            source_mode=source_mode,
            output_mode=output.mode,
            width=width,
            height=height,
            sharpness_before=before_detail,
            sharpness_after=_detail_score(output),
            contrast_before=before_contrast,
            contrast_after=_contrast_score(output),
            profile="conservative_fabric_refinement",
        )
