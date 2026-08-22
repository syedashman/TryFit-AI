from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.api.routes import catalog as catalog_route
from app.core.config import Settings
from app.main import app
from app.models.job import JobRecord
from app.services.storage import load_job, save_job


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
