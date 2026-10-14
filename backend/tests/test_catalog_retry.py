from __future__ import annotations

from pathlib import Path
import shutil

import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.api.routes import catalog as catalog_route
from app.core.config import Settings
from app.main import app
from app.models.job import JobRecord
from app.providers.base import ProviderError, TryOnResult
from app.services import job_service
from app.services.pose_customization import PoseCustomizationError
from app.services.storage import (
    list_batch_jobs,
    load_job,
    save_batch_job_ids,
    save_job,
)


def _job_record(tmp_path: Path, *, job_id: str = "retry-job-123") -> JobRecord:
    person_path = tmp_path / "person.png"
    garment_path = tmp_path / "garment.png"
    person_path.write_bytes(b"person")
    garment_path.write_bytes(b"garment")
    return JobRecord(
        job_id=job_id,
        provider="vertex",
        person_file=str(person_path),
        person_files=[str(person_path), str(person_path)],
        slot_index=1,
        selected_person_index=0,
        geometry_profile={"body": "ok"},
        geometry_reference_index=0,
        garment_file=str(garment_path),
        garment_description="long coat",
        cloth_type="overall",
        show_type="result only",
        quality_preset="balanced",
        request_parameters={"num_inference_steps": 20, "guidance_scale": 4.0, "seed": 99},
        provider_metadata={"batch_id": "batch-abc", "batch_index": 1, "batch_total": 2},
    )


def test_catalog_is_cached_and_sets_cache_headers(tmp_path: Path, monkeypatch) -> None:
    catalog_root = tmp_path / "catalog"
    image_dir = catalog_root / "Men" / "1" / "Default"
    image_dir.mkdir(parents=True)
    (image_dir / "01.webp").write_bytes(b"catalog image")

    scan_count = 0
    original_files = catalog_route._files

    def count_scans(path: Path) -> list[Path]:
        nonlocal scan_count
        scan_count += 1
        return original_files(path)

    catalog_route._build_catalog.cache_clear()
    monkeypatch.setattr(catalog_route, "_catalog_root", lambda: catalog_root)
    monkeypatch.setattr(catalog_route, "_files", count_scans)
    try:
        with TestClient(app) as client:
            first = client.get("/api/catalog")
            second = client.get("/api/catalog")

        assert first.status_code == 200
        assert first.json()["total_images"] == 1
        assert second.json() == first.json()
        assert "max-age=300" in first.headers["cache-control"]
        assert scan_count == 1
    finally:
        catalog_route._build_catalog.cache_clear()


def test_batch_job_index_avoids_directory_scan(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id="indexed-job")
    save_job(record, settings)
    save_batch_job_ids("batch-abc", [record.job_id], settings)

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("indexed batch lookup should not scan all jobs")

    monkeypatch.setattr("app.services.storage.list_jobs", unexpected_scan)

    assert [job.job_id for job in list_batch_jobs("batch-abc", settings)] == [
        record.job_id
    ]


@pytest.mark.parametrize("photo_count", [1, 2, 3])
def test_catalog_generate_maps_each_photo_to_its_own_same_pose_tryon(
    tmp_path: Path,
    monkeypatch,
    photo_count: int,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    catalog_root = tmp_path / "catalog"
    garment_dir = catalog_root / "Men" / "12" / "Default"
    garment_dir.mkdir(parents=True)
    garment_source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "pose_references"
        / "front.jpg"
    )
    (garment_dir / "01.jpg").write_bytes(garment_source.read_bytes())
    sample_dir = Path(__file__).resolve().parents[1] / "SAMPLE_TEST_IMAGES"
    person_source = sample_dir / "person_1_full_body.webp"
    submitted: list[str] = []

    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)
    monkeypatch.setattr(catalog_route, "_catalog_root", lambda: catalog_root)
    monkeypatch.setattr(
        catalog_route,
        "check_photos_match_category",
        lambda *_args: (True, None),
    )
    monkeypatch.setattr(
        catalog_route.job_scheduler,
        "submit",
        lambda job_id, settings_arg, **kwargs: submitted.append(job_id),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/catalog/generate",
            data={"category": "men", "product_number": "12", "color": "Default"},
            files=[
                (
                    "person_images",
                    (
                        person_source.name,
                        person_source.read_bytes(),
                        "image/webp",
                    ),
                )
                for _ in range(photo_count)
            ],
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    jobs = payload["jobs"]
    assert payload["expected_outputs"] == photo_count
    assert len(jobs) == len(submitted) == photo_count
    assert [job["provider_metadata"]["output_variant"] for job in jobs] == [
        "original"
    ] * photo_count
    assert [
        job["provider_metadata"]["pose_reference_name"] for job in jobs
    ] == [None] * photo_count
    assert [
        job["provider_metadata"]["pose_source_strategy"] for job in jobs
    ] == ["uploaded_photo_original_pose"] * photo_count
    assert [
        job["provider_metadata"]["person_source_index"] for job in jobs
    ] == list(range(photo_count))
    assert [job["selected_person_index"] for job in jobs] == [0] * photo_count
    assert [job["geometry_reference_index"] for job in jobs] == [0] * photo_count
    assert all(
        "Use the selected catalog image only as the garment reference."
        in job["garment_description"]
        for job in jobs
    )
    assert all("pose guide" not in job["garment_description"] for job in jobs)
    assert [job["person_file"] for job in jobs] == [
        job["person_files"][0] for job in jobs
    ]
    assert len({job["person_file"] for job in jobs}) == photo_count
    assert [
        job["validation_report"]["selected_file"] for job in jobs
    ] == [job["person_file"] for job in jobs]
    assert all(job["validation_report"]["image_count"] == 1 for job in jobs)


def test_catalog_generate_rejects_more_than_three_uploaded_photos(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/catalog/generate",
            data={"category": "men", "product_number": "12", "color": "Default"},
            files=[
                (
                    "person_images",
                    (f"person-{index}.webp", b"not-read-before-count-check", "image/webp"),
                )
                for index in range(4)
            ],
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_person_image_count"


def test_catalog_photo_jobs_fail_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    garment = tmp_path / "garment.png"
    Image.new("RGB", (120, 160), (20, 30, 40)).save(garment)
    records: list[JobRecord] = []
    for index in range(3):
        person = tmp_path / f"person-{index}.png"
        Image.new("RGB", (120, 160), (60 + index, 80, 100)).save(person)
        record = JobRecord(
            job_id=f"slot-{index}",
            provider="vertex",
            person_file=str(person),
            person_files=[str(person)],
            slot_index=index,
            geometry_profile={"source_file": str(person)},
            geometry_reference_index=0,
            garment_file=str(garment),
            provider_metadata={
                "batch_id": "independent-failures",
                "batch_index": index + 1,
                "batch_total": 3,
                "person_source_index": index,
                "pose_source_strategy": "uploaded_photo_original_pose",
            },
        )
        save_job(record, settings)
        records.append(record)

    class IsolatedProvider:
        name = "test"

        def generate(self, request):
            slot = request.slot_index
            assert slot is not None
            assert request.person_image == Path(records[slot].person_file)
            if slot == 1:
                raise ProviderError(
                    "Provider rejected this one image.",
                    code="provider_image_rejected",
                )
            result_path = tmp_path / f"provider-result-{slot}.png"
            shutil.copyfile(request.person_image, result_path)
            return TryOnResult(image_path=result_path)

    class Report:
        def to_dict(self):
            return {}

    monkeypatch.setattr(job_service, "get_vton_provider", lambda _settings: IsolatedProvider())
    monkeypatch.setattr(job_service, "_needs_identity_review", lambda _metadata: False)
    monkeypatch.setattr(
        job_service,
        "enhance_result_image",
        lambda *_args, **_kwargs: Report(),
    )
    monkeypatch.setattr(job_service, "evaluate_candidate", lambda *_args: Report())
    monkeypatch.setattr(job_service, "build_phase3c2_report", lambda **_kwargs: {})
    monkeypatch.setattr(job_service, "log_memory", lambda *_args: None)

    for record in records:
        job_service.process_job(
            record.job_id,
            settings,
            num_inference_steps=1,
            guidance_scale=1.0,
            seed=record.slot_index or 0,
        )

    saved = [load_job(record.job_id, settings) for record in records]
    assert [record.status for record in saved if record is not None] == [
        "completed",
        "failed",
        "completed",
    ]
    assert [record.person_file for record in saved if record is not None] == [
        record.person_file for record in records
    ]
    assert saved[1] is not None
    assert saved[1].error_code == "provider_image_rejected"


def test_pose_job_uses_user_photo_as_identity_and_pose_output_as_geometry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id="pose-success")
    record.provider_metadata.update(
        {"pose_reference_name": "side", "catalog_category": "Men"}
    )
    user_photo = Path(record.person_file)
    pose_image = tmp_path / "pose_cache" / "synthesized-pose.webp"
    pose_image.parent.mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[1]
        / "SAMPLE_TEST_IMAGES"
        / "person_1_full_body.webp",
        pose_image,
    )
    observed: dict[str, object] = {}

    def fake_synthesis(
        settings_arg,
        identity_paths,
        pose_name,
        subject,
        output_dir,
        *,
        body_geometry,
    ):
        observed.update(
            identity_paths=identity_paths,
            pose_name=pose_name,
            subject=subject,
            output_dir=output_dir,
            body_geometry=body_geometry,
        )
        return pose_image

    monkeypatch.setattr(job_service, "generate_posed_reference", fake_synthesis)

    render_person, geometry_profile, cleanup_path = (
        job_service._prepare_pose_render_person(record, settings)
    )

    assert observed["identity_paths"] == [user_photo]
    assert observed["pose_name"] == "side"
    assert observed["subject"] == "an adult man"
    assert observed["body_geometry"] == record.geometry_profile
    assert render_person != user_photo
    assert geometry_profile["foreground_height_ratio"] > 0
    assert cleanup_path == render_person
    assert pose_image.exists() is False
    cleanup_path.unlink(missing_ok=True)


def test_pose_synthesis_failure_is_scoped_to_that_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id="pose-failure")
    record.provider_metadata.update(
        {"pose_reference_name": "front", "catalog_category": "Men"}
    )

    def fail_pose(*args, **kwargs):
        raise PoseCustomizationError("pose synthesis unavailable")

    monkeypatch.setattr(job_service, "generate_posed_reference", fail_pose)

    with pytest.raises(ProviderError) as error:
        job_service._prepare_pose_render_person(record, settings)

    assert error.value.code == "pose_synthesis_failed"
    assert error.value.retryable is True
    assert error.value.details["pose_reference_name"] == "front"


@pytest.mark.parametrize("source_framing", ["face", "upper_body", "three_quarter"])
@pytest.mark.parametrize("pose_name", ["front", "side"])
def test_predefined_pose_accepts_cropped_source_images(
    tmp_path: Path,
    monkeypatch,
    source_framing: str,
    pose_name: str,
) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id=f"pose-{source_framing}-{pose_name}")
    record.provider_metadata.update(
        {
            "pose_reference_name": pose_name,
            "person_source_framing": source_framing,
        }
    )

    def fail_pose(*args, **kwargs):
        raise PoseCustomizationError("stop after cropped source is accepted")

    monkeypatch.setattr(job_service, "generate_posed_reference", fail_pose)

    with pytest.raises(ProviderError) as error:
        job_service._prepare_pose_render_person(record, settings)

    assert error.value.code == "pose_synthesis_failed"
    assert error.value.retryable is True
    assert error.value.details["pose_reference_name"] == pose_name


def test_original_variant_skips_pose_synthesis(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id="original-pose")
    record.provider_metadata["output_variant"] = "original"

    def unexpected_synthesis(*args, **kwargs):
        raise AssertionError("original output must not synthesize a pose")

    monkeypatch.setattr(job_service, "generate_posed_reference", unexpected_synthesis)

    render_person, geometry_profile, cleanup_path = (
        job_service._prepare_pose_render_person(record, settings)
    )

    assert render_person == Path(record.person_file)
    assert geometry_profile == record.geometry_profile
    assert cleanup_path is None


def test_catalog_retry_uses_scheduler_and_preserves_person_file(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path)
    save_job(record, settings)

    scheduled: dict[str, object] = {}

    def fake_submit(job_id: str, settings_arg: Settings, **kwargs):
        scheduled["job_id"] = job_id
        scheduled["settings"] = settings_arg
        scheduled["kwargs"] = kwargs

    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)
    monkeypatch.setattr(catalog_route.job_scheduler, "submit", fake_submit)

    with TestClient(app) as client:
        response = client.post(f"/api/catalog/retry/{record.job_id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["job_id"] != record.job_id
    assert payload["message"] == "Retrying this pose."
    assert scheduled["job_id"] == payload["job_id"]
    assert scheduled["kwargs"]["seed"] != record.request_parameters["seed"]

    saved = load_job(payload["job_id"], settings)
    assert saved is not None
    assert saved.person_file == record.person_file
    assert saved.person_files == record.person_files
    assert saved.slot_index == record.slot_index
    assert saved.parent_job_id == record.job_id
    assert saved.status == "queued"
    assert saved.provider_metadata["retried_from"] == record.job_id


def test_catalog_retry_invalid_job_id_returns_404(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.post("/api/catalog/retry/missing-job")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."


def test_catalog_batch_status_collapses_retry_into_original_slot(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    original = _job_record(tmp_path, job_id="original")
    original.slot_index = 1
    original.created_at = "2026-08-22T10:00:00+00:00"
    original.updated_at = original.created_at
    retry = original.model_copy(
        update={
            "job_id": "retry",
            "parent_job_id": "original",
            "created_at": "2026-08-22T10:01:00+00:00",
            "updated_at": "2026-08-22T10:01:00+00:00",
            "status": "completed",
            "result_file": str(tmp_path / "retry-result.png"),
        }
    )
    save_job(original, settings)
    save_job(retry, settings)

    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.get("/api/catalog/batch/batch-abc")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["expected_outputs"] == 1
    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["job_id"] == "retry"
    assert payload["jobs"][0]["slot_index"] == 1


def test_replace_photo_updates_only_target_job_slot(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    record = _job_record(tmp_path, job_id="replace-job")
    record.slot_index = 1
    save_job(record, settings)
    replacement = tmp_path / "replacement.png"
    image = Image.new("RGB", (600, 900), (180, 170, 160))
    draw = ImageDraw.Draw(image)
    draw.ellipse((220, 80, 380, 240), fill=(150, 100, 80))
    draw.rectangle((170, 240, 430, 780), fill=(30, 50, 80))
    for offset in range(0, 600, 20):
        draw.line((0, offset, 600, offset + 120), fill=(220, 220, 220), width=2)
    image.save(replacement)

    scheduled: dict[str, object] = {}
    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)
    monkeypatch.setattr(
        catalog_route.job_scheduler,
        "submit",
        lambda job_id, settings_arg, **kwargs: scheduled.update(job_id=job_id, kwargs=kwargs),
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/catalog/retry/{record.job_id}/replace-photo",
            files={"photo": ("replacement.png", replacement.read_bytes(), "image/png")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["job_id"] == record.job_id
    assert scheduled["job_id"] == record.job_id
    saved = load_job(record.job_id, settings)
    assert saved is not None
    assert saved.person_file != record.person_file
    assert saved.person_files[record.slot_index] == saved.person_file
    assert saved.slot_index == record.slot_index
    assert saved.status == "queued"
