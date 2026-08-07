from __future__ import annotations

from app.services.visual_quality import build_realism_directives


SUPPORTED_CLOTH_TYPES = {
    "upper",
    "lower",
    "overall",
}


def _normalize_text(
    value: str,
    fallback: str,
) -> str:
    value = (value or "").strip()
    return value if value else fallback


def build_commercial_instructions(
    description: str,
    cloth_type: str,
    color: str,
) -> str:
    """Build a stable commercial-quality prompt for the VTON provider."""

    garment = _normalize_text(
        description,
        "clothing",
    )

    garment_color = _normalize_text(
        color,
        "original color",
    )

    normalized_type = (
        cloth_type or ""
    ).strip().lower()

    scope = {
        "upper": (
            "Preserve the lower body, waist, hips, legs, "
            "and natural body proportions."
        ),
        "lower": (
            "Preserve the face, shoulders, chest, arms, "
            "and upper-body proportions."
        ),
        "overall": (
            "Preserve full-body height, torso-to-leg ratio, "
            "natural slimness, and overall body geometry."
        ),
    }.get(
        normalized_type,
        "Preserve the person's original body geometry.",
    )

    quality_rules = (
    "Maintain the person's identity, facial features, hairstyle, "
    "skin tone, pose, camera angle, lighting direction, and realistic anatomy. "
    "Keep shoulder width, arm thickness, torso length, leg length, "
    "head-to-body ratio, and body silhouette unchanged. "
    "Do not add muscles. "
    "Do not widen the chest, enlarge muscles, shorten the body, "
    "compress the legs, stretch the torso, change body type, "
    "or introduce unrealistic folds or artifacts. "
    "The garment must fit naturally with commercial fashion quality. "
    "Preserve the complete product identity and every visible component exactly, including "
    "garment category, silhouette, length, neckline, collar, sleeves, cuffs, closures, "
    "embroidery, print, texture, fabric, trim, layers, and matching bottoms. "
    "Never turn a complete outfit into a shirt, never remove garment pieces, and never invent a different design."
)

    return (
        f"Apply the {garment} in {garment_color}. "
        f"{scope} {quality_rules} "
        f"{build_realism_directives(normalized_type)}"
    )