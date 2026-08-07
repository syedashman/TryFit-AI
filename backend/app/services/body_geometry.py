from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


@dataclass(slots=True)
class BodyGeometryProfile:
    source_file: str
    width: int
    height: int
    aspect_ratio: float
    foreground_width_ratio: float
    foreground_height_ratio: float
    upper_width_ratio: float
    middle_width_ratio: float
    lower_width_ratio: float
    vertical_center_ratio: float
    horizontal_center_ratio: float
    subject_aspect_ratio: float
    detector: str

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


BBox = tuple[int, int, int, int]


def _clamp_bbox(
    bbox: BBox,
    width: int,
    height: int,
) -> BBox:
    left, top, right, bottom = bbox

    left = max(0, min(width - 1, int(left)))
    top = max(0, min(height - 1, int(top)))
    right = max(left + 1, min(width, int(right)))
    bottom = max(top + 1, min(height, int(bottom)))

    return left, top, right, bottom


def _largest_center_component(
    mask: np.ndarray,
) -> BBox | None:
    count, _, stats, centroids = (
        cv2.connectedComponentsWithStats(
            mask,
            connectivity=8,
        )
    )

    if count <= 1:
        return None

    height, width = mask.shape
    image_area = max(1, width * height)

    candidates: list[
        tuple[float, BBox]
    ] = []

    for index in range(1, count):
        x, y, box_width, box_height, area = (
            stats[index]
        )

        if (
            area < image_area * 0.025
            or box_height < height * 0.20
        ):
            continue

        center_x, center_y = centroids[index]

        center_distance = (
            abs(center_x / max(1, width) - 0.5)
            + 0.45
            * abs(
                center_y / max(1, height)
                - 0.52
            )
        )

        vertical_bonus = min(
            1.0,
            box_height / max(1, height),
        )

        score = (
            area / image_area
            + 0.35 * vertical_bonus
            - 0.25 * center_distance
        )

        candidates.append(
            (
                score,
                (
                    int(x),
                    int(y),
                    int(x + box_width),
                    int(y + box_height),
                ),
            )
        )

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: item[0],
    )[1]


def _hog_person_bbox(
    rgb: np.ndarray,
) -> BBox | None:
    height, width = rgb.shape[:2]

    if height < 128 or width < 64:
        return None

    scale = min(
        1.0,
        720.0 / max(height, width),
    )

    if scale < 1.0:
        small = cv2.resize(
            rgb,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        small = rgb

    bgr = cv2.cvtColor(
        small,
        cv2.COLOR_RGB2BGR,
    )

    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(
        cv2.HOGDescriptor_getDefaultPeopleDetector()
    )

    boxes, weights = hog.detectMultiScale(
        bgr,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )

    if len(boxes) == 0:
        return None

    small_height, small_width = (
        small.shape[:2]
    )

    flattened_weights = np.asarray(
        weights,
        dtype=np.float32,
    ).reshape(-1)

    ranked: list[
        tuple[float, BBox]
    ] = []

    for index, box in enumerate(boxes):
        x, y, box_width, box_height = (
            map(int, box)
        )

        weight = (
            float(flattened_weights[index])
            if index < len(flattened_weights)
            else 0.0
        )

        center_x = (
            x + box_width / 2
        ) / max(1, small_width)

        area_ratio = (
            box_width * box_height
        ) / max(
            1,
            small_width * small_height,
        )

        score = (
            weight
            + 2.0 * area_ratio
            - abs(center_x - 0.5)
        )

        ranked.append(
            (
                score,
                (
                    x,
                    y,
                    x + box_width,
                    y + box_height,
                ),
            )
        )

    _, bbox = max(
        ranked,
        key=lambda item: item[0],
    )

    if scale < 1.0:
        bbox = tuple(
            int(round(value / scale))
            for value in bbox
        )

    return _clamp_bbox(
        bbox,
        width,
        height,
    )


def _saliency_bbox(
    rgb: np.ndarray,
) -> BBox:
    height, width = rgb.shape[:2]

    border_height = max(
        2,
        height // 30,
    )
    border_width = max(
        2,
        width // 30,
    )

    border = np.concatenate(
        (
            rgb[:border_height].reshape(-1, 3),
            rgb[-border_height:].reshape(-1, 3),
            rgb[:, :border_width].reshape(-1, 3),
            rgb[:, -border_width:].reshape(-1, 3),
        ),
        axis=0,
    )

    background_color = np.median(
        border,
        axis=0,
    )

    distance = np.linalg.norm(
        rgb.astype(np.float32)
        - background_color.astype(np.float32),
        axis=2,
    )

    threshold = max(
        28.0,
        float(np.percentile(distance, 55)),
    )

    mask = (
        distance >= threshold
    ).astype(np.uint8) * 255

    center_prior = np.zeros_like(mask)

    left_limit = int(width * 0.12)
    right_limit = max(
        left_limit + 1,
        int(width * 0.88),
    )

    center_prior[
        :,
        left_limit:right_limit,
    ] = 255

    mask = cv2.bitwise_and(
        mask,
        center_prior,
    )

    kernel_height = max(
        3,
        height // 140,
    )
    kernel_width = max(
        3,
        width // 140,
    )

    kernel = np.ones(
        (kernel_height, kernel_width),
        dtype=np.uint8,
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=3,
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel,
        iterations=1,
    )

    bbox = _largest_center_component(mask)

    if bbox is None:
        return 0, 0, width, height

    return _clamp_bbox(
        bbox,
        width,
        height,
    )


def _subject_bbox(
    rgb: np.ndarray,
) -> tuple[BBox, str]:
    hog_bbox = _hog_person_bbox(rgb)

    if hog_bbox is not None:
        return (
            hog_bbox,
            "opencv_hog_person",
        )

    return (
        _saliency_bbox(rgb),
        "central_saliency",
    )


def _band_width_ratio(
    mask: np.ndarray,
    bbox: BBox,
    y0: float,
    y1: float,
) -> float:
    left, top, right, bottom = bbox

    subject = mask[
        top:bottom,
        left:right,
    ]

    if subject.size == 0:
        return 1.0

    subject_height, subject_width = (
        subject.shape
    )

    start = max(
        0,
        min(
            subject_height - 1,
            int(subject_height * y0),
        ),
    )

    end = max(
        start + 1,
        min(
            subject_height,
            int(subject_height * y1),
        ),
    )

    band = subject[start:end]

    columns = np.where(
        np.any(band > 0, axis=0)
    )[0]

    if columns.size == 0:
        return 1.0

    occupied_width = (
        int(columns[-1])
        - int(columns[0])
        + 1
    )

    return round(
        occupied_width
        / max(1, subject_width),
        4,
    )


def build_body_geometry_profile(
    path: Path,
) -> BodyGeometryProfile:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Geometry image does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Geometry image path is not a file: {path}"
        )

    try:
        with Image.open(path) as opened:
            rgb = np.asarray(
                opened.convert("RGB")
            )

    except UnidentifiedImageError as exc:
        raise ValueError(
            f"Unsupported or invalid geometry image: {path}"
        ) from exc

    except OSError as exc:
        raise ValueError(
            f"Could not read geometry image {path}: {exc}"
        ) from exc

    height, width = rgb.shape[:2]

    if height < 2 or width < 2:
        raise ValueError(
            f"Geometry image is too small: {path}"
        )

    bbox, detector = _subject_bbox(rgb)

    left, top, right, bottom = (
        _clamp_bbox(
            bbox,
            width,
            height,
        )
    )

    box_width = max(
        1,
        right - left,
    )
    box_height = max(
        1,
        bottom - top,
    )

    gray = cv2.cvtColor(
        rgb,
        cv2.COLOR_RGB2GRAY,
    )

    edges = cv2.Canny(
        gray,
        40,
        120,
    )

    mask = cv2.dilate(
        edges,
        np.ones((5, 5), dtype=np.uint8),
        iterations=2,
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((11, 11), dtype=np.uint8),
        iterations=2,
    )

    roi_mask = np.zeros_like(mask)

    roi_mask[
        top:bottom,
        left:right,
    ] = mask[
        top:bottom,
        left:right,
    ]

    minimum_mask_pixels = max(
        1,
        int(width * height * 0.01),
    )

    if (
        np.count_nonzero(roi_mask)
        < minimum_mask_pixels
    ):
        roi_mask[
            top:bottom,
            left:right,
        ] = 255

    return BodyGeometryProfile(
        source_file=str(path),
        width=width,
        height=height,
        aspect_ratio=round(
            width / max(1, height),
            4,
        ),
        foreground_width_ratio=round(
            box_width / max(1, width),
            4,
        ),
        foreground_height_ratio=round(
            box_height / max(1, height),
            4,
        ),
        upper_width_ratio=_band_width_ratio(
            roi_mask,
            (left, top, right, bottom),
            0.16,
            0.40,
        ),
        middle_width_ratio=_band_width_ratio(
            roi_mask,
            (left, top, right, bottom),
            0.40,
            0.68,
        ),
        lower_width_ratio=_band_width_ratio(
            roi_mask,
            (left, top, right, bottom),
            0.68,
            0.96,
        ),
        vertical_center_ratio=round(
            ((top + bottom) / 2)
            / max(1, height),
            4,
        ),
        horizontal_center_ratio=round(
            ((left + right) / 2)
            / max(1, width),
            4,
        ),
        subject_aspect_ratio=round(
            box_width / max(1, box_height),
            4,
        ),
        detector=detector,
    )


def profile_distance(
    reference: BodyGeometryProfile,
    candidate: BodyGeometryProfile,
) -> float:
    pairs: Iterable[
        tuple[float, float, float]
    ] = (
        (
            reference.foreground_width_ratio,
            candidate.foreground_width_ratio,
            0.22,
        ),
        (
            reference.foreground_height_ratio,
            candidate.foreground_height_ratio,
            0.27,
        ),
        (
            reference.subject_aspect_ratio,
            candidate.subject_aspect_ratio,
            0.18,
        ),
        (
            reference.upper_width_ratio,
            candidate.upper_width_ratio,
            0.13,
        ),
        (
            reference.middle_width_ratio,
            candidate.middle_width_ratio,
            0.10,
        ),
        (
            reference.lower_width_ratio,
            candidate.lower_width_ratio,
            0.04,
        ),
        (
            reference.vertical_center_ratio,
            candidate.vertical_center_ratio,
            0.04,
        ),
        (
            reference.horizontal_center_ratio,
            candidate.horizontal_center_ratio,
            0.02,
        ),
        (
            reference.aspect_ratio,
            candidate.aspect_ratio,
            0.10,
        ),
    )

    total = 0.0

    for expected, actual, weight in pairs:
        denominator = max(
            0.08,
            abs(expected),
        )

        normalized_difference = min(
            1.0,
            abs(expected - actual)
            / denominator,
        )

        total += (
            normalized_difference * weight
        )

    return round(total, 6)


def distortion_penalties(
    reference: BodyGeometryProfile,
    candidate: BodyGeometryProfile,
) -> dict[str, float]:
    def excess(
        actual: float,
        expected: float,
        tolerance: float,
        direction: str,
    ) -> float:
        ratio = actual / max(
            expected,
            0.05,
        )

        if direction == "high":
            return max(
                0.0,
                ratio - tolerance,
            )

        return max(
            0.0,
            tolerance - ratio,
        )

    aspect_change = (
        abs(
            candidate.aspect_ratio
            - reference.aspect_ratio
        )
        / max(
            reference.aspect_ratio,
            0.08,
        )
    )

    return {
        "height_compression": round(
            excess(
                candidate.foreground_height_ratio,
                reference.foreground_height_ratio,
                0.97,
                "low",
            ),
            4,
        ),
        "body_widening": round(
            excess(
                candidate.foreground_width_ratio,
                reference.foreground_width_ratio,
                1.06,
                "high",
            ),
            4,
        ),
        "shoulder_widening": round(
            excess(
                candidate.upper_width_ratio,
                reference.upper_width_ratio,
                1.08,
                "high",
            ),
            4,
        ),
        "torso_widening": round(
            excess(
                candidate.middle_width_ratio,
                reference.middle_width_ratio,
                1.08,
                "high",
            ),
            4,
        ),
        "canvas_aspect_change": round(
            max(
                0.0,
                aspect_change - 0.08,
            ),
            4,
        ),
    }


def geometry_similarity(
    reference: BodyGeometryProfile,
    candidate: BodyGeometryProfile,
) -> float:
    base_similarity = max(
        0.0,
        1.0
        - profile_distance(
            reference,
            candidate,
        ),
    )

    penalties = distortion_penalties(
        reference,
        candidate,
    )

    weighted_penalty = (
        0.42
        * penalties["height_compression"]
        + 0.26
        * penalties["body_widening"]
        + 0.18
        * penalties["shoulder_widening"]
        + 0.10
        * penalties["torso_widening"]
        + 0.18
        * penalties["canvas_aspect_change"]
    )

    return round(
        max(
            0.0,
            base_similarity
            - min(0.45, weighted_penalty),
        ),
        4,
    )