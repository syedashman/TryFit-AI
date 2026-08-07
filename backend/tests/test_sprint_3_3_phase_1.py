from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.models.job import JobRecord
from app.services.storage import save_job


def test_quality_presets():
    settings = Settings(_env_file=None)
    assert settings.quality_preset("fast")["num_inference_steps"] == 30
    assert settings.quality_preset("balanced")["guidance_scale"] == 2.5
    assert settings.quality_preset("high")["num_inference_steps"] == 70


def test_provider_route_has_unique_operation_ids():
    operation_ids = []
    for route in app.routes:
        operation_id = getattr(route, "operation_id", None)
        if operation_id:
            operation_ids.append(operation_id)
    assert len(operation_ids) == len(set(operation_ids))


def test_result_route_rejects_path_outside_results(tmp_path: Path):
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    unsafe = tmp_path / "outside.png"
    unsafe.write_bytes(b"x")
    record = JobRecord(
        job_id="unsafe",
        status="completed",
        provider="vertex",
        person_file="person.png",
        garment_file="garment.png",
        result_file=str(unsafe),
    )
    save_job(record, settings)

    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: settings
    # routes call cached getter directly, therefore prime cache through env-neutral patch
    import app.api.routes.jobs as jobs_module
    original = jobs_module.get_settings
    jobs_module.get_settings = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/jobs/unsafe/result")
        assert response.status_code == 403
    finally:
        jobs_module.get_settings = original
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_blank_optional_numbers_are_none():
    from app.api.routes.jobs import _optional_float, _optional_int

    assert _optional_int("", "seed") is None
    assert _optional_int("   ", "seed") is None
    assert _optional_float("", "guidance_scale") is None
    assert _optional_int("42", "seed") == 42
    assert _optional_float("2.5", "guidance_scale") == 2.5
