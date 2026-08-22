from pathlib import Path

from PIL import Image, ImageDraw

from app.services.person_validation import validate_person_images


def _make_portrait(path: Path, shift: int = 0) -> None:
    image = Image.new("RGB", (600, 900), (205, 190, 170))
    draw = ImageDraw.Draw(image)
    draw.ellipse((210 + shift, 80, 390 + shift, 270), fill=(170, 120, 90))
    draw.rectangle((170 + shift, 270, 430 + shift, 760), fill=(45, 55, 75))
    for offset in range(0, 600, 30):
        draw.line((0, offset, 600, offset + 200), fill=(120, 130, 140), width=2)
    image.save(path, quality=95)


def test_requires_three_to_five_images(tmp_path: Path) -> None:
    paths = []
    for index in range(2):
        path = tmp_path / f"person-{index}.jpg"
        _make_portrait(path, index)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0)
    assert report.accepted is False
    assert any("between 3 and 5" in error for error in report.errors)


def test_usable_small_person_dimensions_are_not_rejected(tmp_path: Path) -> None:
    paths = []
    for index, size in enumerate(((365, 547), (300, 450), (640, 1138))):
        path = tmp_path / f"small-person-{index}.jpg"
        image = Image.new("RGB", size, (205, 190, 170))
        draw = ImageDraw.Draw(image)
        draw.ellipse((size[0] * 0.3, size[1] * 0.1, size[0] * 0.7, size[1] * 0.35), fill=(170, 120, 90))
        draw.rectangle((size[0] * 0.25, size[1] * 0.35, size[0] * 0.75, size[1] * 0.85), fill=(45, 55, 75))
        image.save(path, quality=95)
        paths.append(path)

    report = validate_person_images(
        paths,
        min_sharpness=0,
        identity_threshold=0,
    )

    assert report.accepted is True
    assert all(
        not any("Resolution" in issue for issue in item.issues)
        for item in report.images
    )


def test_landscape_and_square_person_images_are_evaluated(tmp_path: Path) -> None:
    paths = []
    for index, size in enumerate(((900, 600), (700, 700), (1200, 800))):
        path = tmp_path / f"shape-{index}.jpg"
        image = Image.new("RGB", size, (205, 190, 170))
        draw = ImageDraw.Draw(image)
        draw.ellipse((size[0] * 0.3, size[1] * 0.1, size[0] * 0.7, size[1] * 0.5), fill=(170, 120, 90))
        draw.rectangle((size[0] * 0.2, size[1] * 0.5, size[0] * 0.8, size[1] * 0.9), fill=(45, 55, 75))
        image.save(path, quality=95)
        paths.append(path)

    report = validate_person_images(
        paths,
        min_sharpness=0,
        identity_threshold=0,
    )

    assert report.accepted is True
    assert [item.width for item in report.images] == [900, 700, 1200]
    assert [item.height for item in report.images] == [600, 700, 800]


def test_selects_best_of_valid_person_images(tmp_path: Path) -> None:
    paths = []
    for index in range(3):
        path = tmp_path / f"person-{index}.jpg"
        _make_portrait(path, index)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0.1)
    assert report.accepted is True
    assert report.selected_index in {0, 1, 2}
    assert report.selected_file is not None
    assert len(report.images) == 3


def test_low_resolution_images_are_rejected(tmp_path: Path) -> None:
    paths = []
    for index in range(3):
        path = tmp_path / f"small-{index}.jpg"
        Image.new("RGB", (120, 160), (100, 100, 100)).save(path)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0)
    assert report.accepted is False
    assert "validation failed" in " ".join(report.errors).lower()


def test_identity_signature_is_stable_for_small_shifts(tmp_path: Path) -> None:
    paths = []
    for shift in (0, 1, 2):
        path = tmp_path / f"shift-{shift}.jpg"
        _make_portrait(path, shift)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0.72)
    assert report.accepted is True
    assert report.identity_consistency_score >= 0.90


def _make_face_closeup(path: Path) -> None:
    image = Image.new("RGB", (700, 900), (180, 180, 180))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 70, 600, 650), fill=(190, 135, 105))
    draw.rectangle((80, 650, 620, 900), fill=(50, 60, 80))
    image.save(path, quality=95)


def _make_full_body(path: Path) -> None:
    image = Image.new("RGB", (600, 1100), (180, 180, 180))
    draw = ImageDraw.Draw(image)
    draw.ellipse((245, 60, 355, 180), fill=(190, 135, 105))
    draw.rectangle((195, 180, 405, 720), fill=(50, 60, 80))
    draw.rectangle((210, 720, 285, 1060), fill=(40, 45, 55))
    draw.rectangle((315, 720, 390, 1060), fill=(40, 45, 55))
    image.save(path, quality=95)


def test_adaptive_selection_prefers_best_face_when_all_are_closeups(tmp_path: Path) -> None:
    paths = []
    for index in range(3):
        path = tmp_path / f"face-{index}.jpg"
        _make_face_closeup(path)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0)
    assert report.accepted is True
    assert report.selection_mode == "face_focus"
    assert report.selected_framing in {"face", "upper_body"}


def test_adaptive_selection_uses_body_mode_for_full_body_set(tmp_path: Path) -> None:
    paths = []
    for index in range(3):
        path = tmp_path / f"body-{index}.jpg"
        _make_full_body(path)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0, cloth_type="overall")
    assert report.accepted is True
    assert report.selection_mode == "body_focus"
    assert report.selected_framing in {"full_body", "three_quarter"}


def test_mixed_set_uses_balanced_quality_mode(tmp_path: Path) -> None:
    paths = []
    for index, maker in enumerate((_make_face_closeup, _make_full_body, _make_portrait)):
        path = tmp_path / f"mixed-{index}.jpg"
        maker(path)
        paths.append(path)
    report = validate_person_images(paths, min_sharpness=0, identity_threshold=0, cloth_type="overall")
    assert report.accepted is True
    assert report.selection_mode == "balanced_mixed"
    assert report.selection_reason


def test_medium_identity_confidence_warns_but_accepts(tmp_path: Path) -> None:
    paths = []
    makers = (_make_face_closeup, _make_full_body, _make_portrait)
    for index, maker in enumerate(makers):
        path = tmp_path / f"varied-{index}.jpg"
        maker(path)
        paths.append(path)
    report = validate_person_images(
        paths,
        min_sharpness=0,
        identity_threshold=0.99,
        identity_hard_reject_threshold=0.0,
    )
    assert report.accepted is True
    assert report.warnings


def test_reference_roles_are_assigned(tmp_path: Path) -> None:
    paths = []
    for index, maker in enumerate((_make_face_closeup, _make_full_body, _make_portrait)):
        path = tmp_path / f"roles-{index}.jpg"
        maker(path)
        paths.append(path)
    report = validate_person_images(
        paths,
        min_sharpness=0,
        identity_threshold=0,
        identity_hard_reject_threshold=0,
    )
    assert report.identity_reference_index is not None
    assert report.geometry_reference_index is not None
    assert report.pose_reference_index is not None
    assert any(item.reference_role for item in report.images)


def test_landscape_upper_body_reference_is_accepted(tmp_path: Path) -> None:
    paths = []
    sizes = ((591, 1280), (960, 1280), (948, 575))
    for index, size in enumerate(sizes):
        path = tmp_path / f"reference-{index}.jpg"
        image = Image.new("RGB", size, (130, 115, 100))
        draw = ImageDraw.Draw(image)
        width, height = size
        cx = width // 2
        face_w = max(80, min(width // 3, 260))
        face_h = max(100, min(height // 3, 320))
        draw.ellipse(
            (cx - face_w // 2, 30, cx + face_w // 2, 30 + face_h),
            fill=(185, 130, 100),
        )
        draw.rectangle(
            (max(0, cx - width // 4), 30 + face_h, min(width, cx + width // 4), height),
            fill=(55, 50, 45),
        )
        image.save(path, quality=95)
        paths.append(path)

    report = validate_person_images(
        paths,
        min_height=500,
        min_sharpness=0,
        identity_threshold=0,
        identity_hard_reject_threshold=0,
    )
    assert report.accepted is True
    assert report.images[2].accepted is True
    assert report.images[2].framing in {"face", "upper_body"}
    assert report.images[2].selection_score > 0
    assert any("wide/landscape crop" in warning for warning in report.warnings)


def test_upper_body_framing_never_self_rejects(tmp_path: Path) -> None:
    paths = []
    for index in range(3):
        path = tmp_path / f"wide-{index}.jpg"
        image = Image.new("RGB", (900, 600), (120, 110, 100))
        draw = ImageDraw.Draw(image)
        draw.ellipse((330, 40, 570, 300), fill=(185, 130, 100))
        draw.rectangle((250, 300, 650, 600), fill=(50, 55, 65))
        image.save(path, quality=95)
        paths.append(path)

    report = validate_person_images(
        paths, min_height=500, min_sharpness=0, identity_threshold=0
    )
    assert report.accepted is True
    assert all(item.accepted for item in report.images)
    assert all("Use a portrait" not in issue for item in report.images for issue in item.issues)
