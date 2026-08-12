from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import (
    Image,
    ImageFilter,
    ImageOps,
    ImageStat,
    UnidentifiedImageError,
)

from app.services.body_geometry import (
    build_body_geometry_profile,
)


SUPPORTED_CLOTH_TYPES = {
    "upper",
    "lower",
    "overall",
}


@dataclass(slots=True)
class ImageValidation:
    path: str
    width: int
    height: int
    aspect_ratio: float
    sharpness: float
    brightness: float
    contrast: float
    body_visibility_score: float
    subject_height_ratio: float
    subject_aspect_ratio: float
    geometry_detector: str
    face_quality_score: float
    framing: str
    quality_score: float
    selection_score: float
    reference_role: str | None
    accepted: bool
    issues: list[str]


@dataclass(slots=True)
class PersonValidationReport:
    accepted: bool
    image_count: int
    selected_index: int | None
    selected_file: str | None
    selected_framing: str | None
    selection_mode: str
    selection_reason: str | None
    identity_reference_index: int | None
    geometry_reference_index: int | None
    pose_reference_index: int | None
    identity_consistency_score: float
    identity_check_method: str
    images: list[ImageValidation]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "image_count": self.image_count,
            "selected_index": self.selected_index,
            "selected_file": self.selected_file,
            "selected_framing": self.selected_framing,
            "selection_mode": self.selection_mode,
            "selection_reason": self.selection_reason,
            "identity_reference_index":
                self.identity_reference_index,
            "geometry_reference_index":
                self.geometry_reference_index,
            "pose_reference_index":
                self.pose_reference_index,
            "identity_consistency_score":
                self.identity_consistency_score,
            "identity_check_method":
                self.identity_check_method,
            "images": [
                asdict(item)
                for item in self.images
            ],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def _normalize_cloth_type(
    cloth_type: str,
) -> str:
    normalized = (
        cloth_type or ""
    ).strip().lower()

    if normalized not in SUPPORTED_CLOTH_TYPES:
        return "overall"

    return normalized


def _append_unique(
    target: list[str],
    message: str,
) -> None:
    if message not in target:
        target.append(message)


def _edge_variance(
    image: Image.Image,
) -> float:
    gray = image.convert("L")

    gray.thumbnail(
        (256, 256),
        Image.Resampling.LANCZOS,
    )

    edges = gray.filter(
        ImageFilter.FIND_EDGES
    )

    variance = ImageStat.Stat(
        edges
    ).var[0]

    return float(variance)


def _upper_body_signature(
    image: Image.Image,
) -> list[float]:
    """
    Build a lightweight visual-consistency signature.

    This is not biometric face recognition. It is used only to detect
    obviously unrelated uploads by comparing broad visual information
    from the upper-body region.
    """

    width, height = image.size

    if width <= 0 or height <= 0:
        return []

    crop_box = (
        int(width * 0.15),
        int(height * 0.02),
        int(width * 0.85),
        int(height * 0.62),
    )

    crop = (
        image.convert("RGB")
        .crop(crop_box)
        .resize(
            (24, 24),
            Image.Resampling.LANCZOS,
        )
    )

    signature: list[float] = []

    for channel in crop.split():
        histogram = channel.histogram()
        total = max(
            sum(histogram),
            1,
        )

        for start in range(
            0,
            256,
            32,
        ):
            signature.append(
                sum(
                    histogram[
                        start:start + 32
                    ]
                )
                / total
            )

    gray = crop.convert("L").resize(
        (12, 12),
        Image.Resampling.LANCZOS,
    )

    signature.extend(
        float(value) / 255.0
        for value in gray.getdata()
    )

    return signature


def _cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:
    if (
        not first
        or not second
        or len(first) != len(second)
    ):
        return 0.0

    dot = sum(
        a * b
        for a, b in zip(
            first,
            second,
        )
    )

    norm_a = sum(
        value * value
        for value in first
    ) ** 0.5

    norm_b = sum(
        value * value
        for value in second
    ) ** 0.5

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0

    return _clamp(
        dot / (norm_a * norm_b)
    )


def _body_visibility_score(
    width: int,
    height: int,
) -> float:
    if width <= 0 or height <= 0:
        return 0.0

    ratio = height / max(width, 1)

    if ratio >= 1.70:
        return 1.0

    if ratio >= 1.55:
        return 0.94

    if ratio >= 1.25:
        return 0.82

    if ratio >= 1.00:
        return 0.62

    return 0.35


def _skin_metrics(
    image: Image.Image,
) -> tuple[float, float]:
    """
    Estimate approximate skin-colored coverage.

    The values are used only for framing selection. They must not be
    interpreted as demographic or identity information.
    """

    sample = (
        image.convert("YCbCr")
        .resize(
            (96, 144),
            Image.Resampling.BILINEAR,
        )
    )

    pixels = list(
        sample.getdata()
    )

    skin = 0
    upper_skin = 0

    sample_width = 96
    upper_limit = 72

    for index, pixel in enumerate(pixels):
        _, cb, cr = pixel

        is_skin = (
            77 <= cb <= 127
            and 133 <= cr <= 180
        )

        if not is_skin:
            continue

        skin += 1

        row = index // sample_width

        if row < upper_limit:
            upper_skin += 1

    total = max(
        len(pixels),
        1,
    )

    upper_total = max(
        sample_width * upper_limit,
        1,
    )

    return (
        skin / total,
        upper_skin / upper_total,
    )


def _classify_framing(
    image: Image.Image,
    body_score: float,
    subject_height_ratio: float,
    subject_aspect_ratio: float,
    detector: str,
) -> tuple[str, float]:
    skin_fraction, upper_skin_fraction = (
        _skin_metrics(image)
    )

    face_score = _clamp(
        0.55
        * (
            skin_fraction
            / 0.20
        )
        + 0.45
        * (
            upper_skin_fraction
            / 0.24
        )
    )

    width, height = image.size

    canvas_tallness = (
        height / max(width, 1)
    )

    subject_height_ratio = _clamp(
        subject_height_ratio
    )

    subject_aspect_ratio = max(
        0.0,
        subject_aspect_ratio,
    )

    if detector == "opencv_hog_person":
        if (
            subject_height_ratio >= 0.58
            and subject_aspect_ratio <= 0.68
        ):
            return (
                "full_body",
                round(face_score, 4),
            )

        if (
            subject_height_ratio >= 0.46
            and subject_aspect_ratio <= 0.88
        ):
            return (
                "three_quarter",
                round(face_score, 4),
            )

    standing_shape = (
        subject_aspect_ratio <= 0.80
    )

    tall_canvas = (
        canvas_tallness >= 1.45
    )

    very_tall_canvas = (
        canvas_tallness >= 1.70
    )

    if (
        very_tall_canvas
        and subject_height_ratio >= 0.62
        and standing_shape
    ):
        framing = "full_body"

    elif (
        tall_canvas
        and subject_height_ratio >= 0.50
        and subject_aspect_ratio <= 0.92
    ):
        framing = "three_quarter"

    elif (
        body_score >= 0.95
        and skin_fraction < 0.36
    ):
        framing = "full_body"

    elif (
        body_score >= 0.78
        and skin_fraction < 0.36
    ):
        framing = "three_quarter"

    elif body_score >= 0.58:
        framing = "upper_body"

    else:
        framing = "face"

    return (
        framing,
        round(face_score, 4),
    )


def _geometry_priority(
    item: ImageValidation,
    cloth_type: str,
) -> tuple[float, ...]:
    """
    Rank the safest body-geometry reference.

    Full-body selection is not based only on the framing label because
    loose garments and long dresses can reduce detector confidence.
    """

    framing_rank = {
        "unknown": -1.0,
        "face": 0.0,
        "upper_body": 1.0,
        "three_quarter": 2.0,
        "full_body": 3.0,
    }

    canvas_tallness = (
        item.height
        / max(item.width, 1)
    )

    standing_shape = _clamp(
        (
            0.95
            - item.subject_aspect_ratio
        )
        / 0.55
    )

    detected_height = _clamp(
        item.subject_height_ratio
    )

    portrait_bonus = _clamp(
        (
            canvas_tallness
            - 1.05
        )
        / 0.85
    )

    body_evidence = (
        0.36 * detected_height
        + 0.28 * standing_shape
        + 0.24 * portrait_bonus
        + 0.12
        * item.body_visibility_score
    )

    garment_priority = (
        1.0
        if cloth_type in {
            "overall",
            "lower",
        }
        else 0.65
    )

    return (
        garment_priority
        * body_evidence,
        framing_rank.get(
            item.framing,
            -1.0,
        ),
        detected_height,
        portrait_bonus,
        item.body_visibility_score,
        item.quality_score,
    )


def _selection_mode(
    items: list[ImageValidation],
) -> str:
    if not items:
        return "none"

    framings = {
        item.framing
        for item in items
    }

    close_only = framings <= {
        "face",
        "upper_body",
    }

    body_only = framings <= {
        "three_quarter",
        "full_body",
    }

    if close_only:
        return "face_focus"

    if body_only:
        return "body_focus"

    return "balanced_mixed"


def _selection_score(
    item: ImageValidation,
    mode: str,
    cloth_type: str,
) -> float:
    if mode == "face_focus":
        if cloth_type in {
            "overall",
            "lower",
        }:
            return _clamp(
                0.42
                * item.quality_score
                + 0.48
                * item.body_visibility_score
                + 0.10
                * item.face_quality_score
            )

        return _clamp(
            0.65
            * item.quality_score
            + 0.35
            * item.face_quality_score
        )

    if mode == "body_focus":
        return _clamp(
            0.58
            * item.quality_score
            + 0.42
            * item.body_visibility_score
        )

    compatibility = (
        item.body_visibility_score
    )

    if cloth_type == "upper":
        compatibility = max(
            item.face_quality_score,
            (
                0.85
                if item.framing
                == "upper_body"
                else 0.0
            ),
        )

    elif cloth_type in {
        "lower",
        "overall",
    }:
        compatibility = max(
            item.body_visibility_score,
            item.subject_height_ratio,
        )

    return _clamp(
        0.68
        * item.quality_score
        + 0.22
        * compatibility
        + 0.10
        * item.face_quality_score
    )


def _calculate_quality_score(
    *,
    width: int,
    height: int,
    sharpness: float,
    brightness: float,
    contrast: float,
    visibility: float,
) -> float:
    resolution_score = (
        min(
            1.0,
            width / 800,
        )
        * min(
            1.0,
            height / 1000,
        )
    )

    sharpness_score = min(
        1.0,
        sharpness / 180.0,
    )

    exposure_score = _clamp(
        1.0
        - abs(
            brightness - 128.0
        )
        / 128.0
    )

    contrast_score = min(
        1.0,
        contrast / 64.0,
    )

    score = (
        0.30 * resolution_score
        + 0.30 * sharpness_score
        + 0.15 * exposure_score
        + 0.10 * contrast_score
        + 0.15 * visibility
    )

    return round(
        _clamp(score),
        4,
    )


def _unreadable_validation(
    path: Path,
    error: Exception,
) -> ImageValidation:
    return ImageValidation(
        path=str(path),
        width=0,
        height=0,
        aspect_ratio=0.0,
        sharpness=0.0,
        brightness=0.0,
        contrast=0.0,
        body_visibility_score=0.0,
        subject_height_ratio=0.0,
        subject_aspect_ratio=0.0,
        geometry_detector="unreadable",
        face_quality_score=0.0,
        framing="unknown",
        quality_score=0.0,
        selection_score=0.0,
        reference_role=None,
        accepted=False,
        issues=[
            f"Unreadable image: {error}"
        ],
    )


def _validate_configuration(
    *,
    min_images: int,
    max_images: int,
    min_width: int,
    min_height: int,
    min_sharpness: float,
    identity_threshold: float,
    identity_hard_reject_threshold: float,
) -> None:
    if min_images < 1:
        raise ValueError(
            "min_images must be at least 1."
        )

    if max_images < min_images:
        raise ValueError(
            "max_images must be greater than "
            "or equal to min_images."
        )

    if min_width < 1 or min_height < 1:
        raise ValueError(
            "Minimum image dimensions must "
            "be positive."
        )

    if min_sharpness < 0.0:
        raise ValueError(
            "min_sharpness cannot be negative."
        )

    if not 0.0 <= identity_threshold <= 1.0:
        raise ValueError(
            "identity_threshold must be "
            "between 0 and 1."
        )

    if not (
        0.0
        <= identity_hard_reject_threshold
        <= 1.0
    ):
        raise ValueError(
            "identity_hard_reject_threshold "
            "must be between 0 and 1."
        )

    # Thresholds are validated independently. Their relative
    # ordering is intentionally unrestricted because callers may lower
    # identity_threshold for test or permissive validation flows.


def validate_person_images(
    paths: list[Path],
    *,
    min_images: int = 3,
    max_images: int = 5,
    min_width: int = 400,
    min_height: int = 600,
    min_sharpness: float = 45.0,
    identity_threshold: float = 0.80,
    identity_hard_reject_threshold: float = 0.55,
    cloth_type: str = "overall",
) -> PersonValidationReport:
    _validate_configuration(
        min_images=min_images,
        max_images=max_images,
        min_width=min_width,
        min_height=min_height,
        min_sharpness=min_sharpness,
        identity_threshold=identity_threshold,
        identity_hard_reject_threshold=(
            identity_hard_reject_threshold
        ),
    )

    normalized_cloth_type = (
        _normalize_cloth_type(
            cloth_type
        )
    )

    normalized_paths = [
        Path(path)
        for path in paths
    ]

    errors: list[str] = []
    warnings: list[str] = []
    validations: list[
        ImageValidation
    ] = []
    signatures: list[
        list[float]
    ] = []

    path_count = len(
        normalized_paths
    )

    if (
        path_count < min_images
        or path_count > max_images
    ):
        errors.append(
            f"Upload between {min_images} "
            f"and {max_images} person images."
        )

    for image_index, path in enumerate(
        normalized_paths
    ):
        issues: list[str] = []

        try:
            if not path.exists():
                raise FileNotFoundError(
                    f"Image does not exist: {path}"
                )

            if not path.is_file():
                raise ValueError(
                    f"Image path is not a file: {path}"
                )

            with Image.open(path) as source:
                image = (
                    ImageOps.exif_transpose(
                        source
                    )
                    .convert("RGB")
                )

                width, height = (
                    image.size
                )

                if width <= 0 or height <= 0:
                    raise ValueError(
                        "Image has invalid dimensions."
                    )

                sharpness = (
                    _edge_variance(
                        image
                    )
                )

                grayscale = (
                    image.convert("L")
                )

                stats = ImageStat.Stat(
                    grayscale
                )

                brightness = float(
                    stats.mean[0]
                )

                contrast = float(
                    stats.stddev[0]
                )

                visibility = (
                    _body_visibility_score(
                        width,
                        height,
                    )
                )

                geometry = (
                    build_body_geometry_profile(
                        path
                    )
                )

                subject_height_ratio = (
                    _clamp(
                        float(
                            geometry
                            .foreground_height_ratio
                        )
                    )
                )

                subject_aspect_ratio = max(
                    0.0,
                    float(
                        geometry
                        .subject_aspect_ratio
                    ),
                )

                detector = str(
                    geometry.detector
                    or "unknown"
                )

                framing, face_quality = (
                    _classify_framing(
                        image,
                        visibility,
                        subject_height_ratio,
                        subject_aspect_ratio,
                        detector,
                    )
                )

                if framing == "full_body":
                    visibility = max(
                        visibility,
                        1.0,
                    )

                elif (
                    framing
                    == "three_quarter"
                ):
                    visibility = max(
                        visibility,
                        0.84,
                    )

                visibility = _clamp(
                    visibility
                )

                portrait_too_small = (
                    height >= width
                    and (
                        width < min_width
                        or height < min_height
                    )
                )

                landscape_too_small = (
                    height < width
                    and (
                        min(
                            width,
                            height,
                        )
                        < 350
                        or max(
                            width,
                            height,
                        )
                        < 500
                    )
                )

                if (
                    portrait_too_small
                    or landscape_too_small
                ):
                    issues.append(
                        "Resolution is too low "
                        f"({width}x{height}); use "
                        f"at least {min_width}x"
                        f"{min_height} for portrait "
                        "photos or a 350px short side "
                        "for landscape references."
                    )

                if sharpness < min_sharpness:
                    issues.append(
                        "Image appears blurry or "
                        "lacks detail."
                    )

                if brightness < 35:
                    issues.append(
                        "Image is too dark."
                    )

                elif brightness > 225:
                    issues.append(
                        "Image is overexposed."
                    )

                if contrast < 18:
                    issues.append(
                        "Image has very low contrast."
                    )

                if visibility < 0.5:
                    _append_unique(
                        warnings,
                        (
                            f"Image {image_index + 1} "
                            "is a wide/landscape crop; "
                            "it will mainly be used as "
                            "an identity reference."
                        ),
                    )

                quality_score = (
                    _calculate_quality_score(
                        width=width,
                        height=height,
                        sharpness=sharpness,
                        brightness=brightness,
                        contrast=contrast,
                        visibility=visibility,
                    )
                )

                validations.append(
                    ImageValidation(
                        path=str(path),
                        width=width,
                        height=height,
                        aspect_ratio=round(
                            width
                            / max(height, 1),
                            4,
                        ),
                        sharpness=round(
                            sharpness,
                            3,
                        ),
                        brightness=round(
                            brightness,
                            3,
                        ),
                        contrast=round(
                            contrast,
                            3,
                        ),
                        body_visibility_score=round(
                            visibility,
                            4,
                        ),
                        subject_height_ratio=round(
                            subject_height_ratio,
                            4,
                        ),
                        subject_aspect_ratio=round(
                            subject_aspect_ratio,
                            4,
                        ),
                        geometry_detector=detector,
                        face_quality_score=round(
                            face_quality,
                            4,
                        ),
                        framing=framing,
                        quality_score=quality_score,
                        selection_score=0.0,
                        reference_role=None,
                        accepted=not issues,
                        issues=issues,
                    )
                )

                signatures.append(
                    _upper_body_signature(
                        image
                    )
                )

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            FileNotFoundError,
        ) as exc:
            validations.append(
                _unreadable_validation(
                    path,
                    exc,
                )
            )

            signatures.append([])

        except Exception as exc:
            validations.append(
                _unreadable_validation(
                    path,
                    exc,
                )
            )

            signatures.append([])

    bad_images = [
        index + 1
        for index, item in enumerate(
            validations
        )
        if not item.accepted
    ]

    if bad_images:
        errors.append(
            "Person image validation failed "
            f"for image(s): {bad_images}."
        )

    similarities: list[float] = []

    usable_signatures = [
        (index, signature)
        for index, signature in enumerate(
            signatures
        )
        if signature
    ]

    for left in range(
        len(usable_signatures)
    ):
        for right in range(
            left + 1,
            len(usable_signatures),
        ):
            similarity = (
                _cosine_similarity(
                    usable_signatures[
                        left
                    ][1],
                    usable_signatures[
                        right
                    ][1],
                )
            )

            similarities.append(
                similarity
            )

    consistency = (
        round(
            mean(similarities),
            4,
        )
        if similarities
        else 0.0
    )

    enough_images_for_identity = (
        path_count >= min_images
        and len(usable_signatures)
        >= min_images
    )

    if (
        enough_images_for_identity
        and consistency
        < identity_hard_reject_threshold
    ):
        errors.append(
            "The uploaded photos appear "
            "strongly inconsistent. Upload "
            "3-5 clear photos of the same person."
        )

    elif (
        enough_images_for_identity
        and consistency
        < identity_threshold
    ):
        _append_unique(
            warnings,
            (
                "Identity confidence is moderate "
                "because framing, lighting, or "
                "camera distance differs. The "
                "images were accepted; clearer "
                "references may improve results."
            ),
        )

    accepted_items = [
        (index, item)
        for index, item in enumerate(
            validations
        )
        if item.accepted
    ]

    mode = (
        _selection_mode(
            [
                item
                for _, item in accepted_items
            ]
        )
        if accepted_items
        else "none"
    )

    for _, item in accepted_items:
        item.selection_score = round(
            _selection_score(
                item,
                mode,
                normalized_cloth_type,
            ),
            4,
        )

    selected_index: int | None = None
    selected_file: str | None = None
    selected_framing: str | None = None
    selection_reason: str | None = None

    identity_reference_index: (
        int | None
    ) = None

    geometry_reference_index: (
        int | None
    ) = None

    pose_reference_index: (
        int | None
    ) = None

    if accepted_items:
        selected_index, selected_item = max(
            accepted_items,
            key=lambda pair: (
                pair[1].selection_score,
                pair[1].quality_score,
            ),
        )

        selected_file = (
            selected_item.path
        )

        selected_framing = (
            selected_item.framing
        )

        selection_reason = (
            f"Selected image "
            f"{selected_index + 1} using "
            f"{mode}: framing="
            f"{selected_item.framing}, "
            f"quality="
            f"{selected_item.quality_score:.3f}, "
            f"face="
            f"{selected_item.face_quality_score:.3f}, "
            f"body="
            f"{selected_item.body_visibility_score:.3f}."
        )

        (
            identity_reference_index,
            identity_item,
        ) = max(
            accepted_items,
            key=lambda pair: (
                pair[1]
                .face_quality_score,
                pair[1].quality_score,
                pair[1].sharpness,
            ),
        )

        (
            geometry_reference_index,
            geometry_item,
        ) = max(
            accepted_items,
            key=lambda pair: (
                _geometry_priority(
                    pair[1],
                    normalized_cloth_type,
                )
            ),
        )

        (
            pose_reference_index,
            pose_item,
        ) = max(
            accepted_items,
            key=lambda pair: (
                (
                    1.0
                    if pair[1].framing
                    in {
                        "three_quarter",
                        "full_body",
                    }
                    else 0.0
                ),
                pair[1]
                .subject_height_ratio,
                pair[1]
                .quality_score,
            ),
        )

        identity_item.reference_role = (
            "identity_reference"
        )

        if (
            geometry_reference_index
            == identity_reference_index
        ):
            identity_item.reference_role = (
                "identity_and_geometry_reference"
            )

        else:
            geometry_item.reference_role = (
                "geometry_reference"
            )

        if pose_reference_index in {
            identity_reference_index,
            geometry_reference_index,
        }:
            current_role = (
                pose_item.reference_role
                or "reference"
            )

            if "pose" not in current_role:
                pose_item.reference_role = (
                    f"{current_role}_and_pose"
                )

        else:
            pose_item.reference_role = (
                "pose_reference"
            )

        if (
            normalized_cloth_type
            in {
                "overall",
                "lower",
            }
            and geometry_reference_index
            is not None
        ):
            selected_index = (
                geometry_reference_index
            )

            selected_item = validations[
                selected_index
            ]

            selected_file = (
                selected_item.path
            )

            selected_framing = (
                selected_item.framing
            )

            canvas_tallness = (
                selected_item.height
                / max(
                    selected_item.width,
                    1,
                )
            )

            selection_reason = (
                f"Selected image "
                f"{selected_index + 1} as "
                "geometry-first render "
                "reference: framing="
                f"{selected_item.framing}, "
                "subject_height="
                f"{selected_item.subject_height_ratio:.3f}, "
                "subject_aspect="
                f"{selected_item.subject_aspect_ratio:.3f}, "
                "canvas_tallness="
                f"{canvas_tallness:.3f}, "
                "quality="
                f"{selected_item.quality_score:.3f}, "
                "body="
                f"{selected_item.body_visibility_score:.3f}."
            )

    accepted = (
        not errors
        and selected_file is not None
    )

    return PersonValidationReport(
        accepted=accepted,
        image_count=path_count,
        selected_index=selected_index,
        selected_file=selected_file,
        selected_framing=(
            selected_framing
        ),
        selection_mode=mode,
        selection_reason=(
            selection_reason
        ),
        identity_reference_index=(
            identity_reference_index
        ),
        geometry_reference_index=(
            geometry_reference_index
        ),
        pose_reference_index=(
            pose_reference_index
        ),
        identity_consistency_score=float(
            consistency
        ),
        identity_check_method=(
            "adaptive_visual_consistency_"
            "geometry_render_priority_v9"
        ),
        images=validations,
        errors=errors,
        warnings=warnings,
    )