from __future__ import annotations

from pathlib import Path

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
    assert saved.status == "queued"
    assert saved.provider_metadata["retried_from"] == record.job_id


def test_catalog_retry_invalid_job_id_returns_404(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    monkeypatch.setattr(catalog_route, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.post("/api/catalog/retry/missing-job")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."
