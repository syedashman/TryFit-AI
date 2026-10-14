from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from app.services.body_geometry import build_body_geometry_profile, distortion_penalties
from app.services.candidate_selector import (
    _geometry_evidence_reliable,
    _hard_reject,
    choose_best_candidate,
)


def _person(path: Path, *, width: int = 400, height: int = 800, body_width: int = 120) -> None:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    x = (width - body_width) // 2
    draw.ellipse((width // 2 - 24, 35, width // 2 + 24, 83), fill="black")
    draw.rectangle((x, 82, x + body_width, height - 35), fill="black")
    image.save(path)


def test_detector_miss_is_not_treated_as_distortion(tmp_path: Path) -> None:
    # Reproduces a real failure: the upload was measured by saliency (full frame)
    # while HOG latched onto a small box in the result, faking "height compression".
    source = tmp_path / "source.png"
    _person(source)
    reference = replace(
        build_body_geometry_profile(source),
        detector="central_saliency",
        foreground_height_ratio=1.0,
    )
    missed = replace(
        reference,
        detector="opencv_hog_person",
        foreground_height_ratio=0.2344,
    )

    assert _hard_reject(distortion_penalties(reference, missed)) is True
    assert _geometry_evidence_reliable(reference, missed) is False


def test_real_compression_with_same_detector_is_still_reliable(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _person(source)
    reference = replace(build_body_geometry_profile(source), foreground_height_ratio=0.9)
    squashed = replace(reference, foreground_height_ratio=0.5)

    assert _geometry_evidence_reliable(reference, squashed) is True
    assert _hard_reject(distortion_penalties(reference, squashed)) is True


def test_frontal_face_resemblance_is_not_catalog_leakage(tmp_path: Path, monkeypatch) -> None:
    # Scores observed on a correct result: the pixel/edge face signal rated the
    # catalog model only slightly closer than the real (head-tilted) shopper.
    source, catalog, candidate = (tmp_path / n for n in ("source.png", "catalog.png", "candidate.png"))
    for path in (source, catalog, candidate):
        _person(path)

    values = {
        (str(source), str(candidate)): (0.53, True),
        (str(catalog), str(candidate)): (0.63, True),
    }
    monkeypatch.setattr(
        "app.services.candidate_selector._face_identity_signal",
        lambda reference, path: values[(str(reference), str(path))],
    )

    winner, scores = choose_best_candidate(
        [candidate],
        build_body_geometry_profile(source),
        identity_reference_path=source,
        catalog_identity_reference_path=catalog,
    )

    assert winner == candidate
    assert scores[0].catalog_leakage is False


def test_result_preview_is_full_size_jpeg(tmp_path: Path) -> None:
    from app.services.visual_quality import preview_path_for, write_result_preview

    result = tmp_path / "job.png"
    _person(result, width=576, height=768)

    preview = write_result_preview(result)

    assert preview == preview_path_for(result) == tmp_path / "job-preview.jpg"
    with Image.open(preview) as image:
        assert image.format == "JPEG"
        assert image.size == (576, 768)
