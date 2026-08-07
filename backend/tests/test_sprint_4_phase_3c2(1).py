from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.models.job import JobRecord
from app.services.phase3c2_quality import (
    build_phase3c2_report,
    garment_color_similarity,
    hash_similarity,
    perceptual_hash,
)
from app.services.storage import save_job


def _image(path: Path, color: tuple[int, int, int], stripe: bool = False) -> Path:
    image = Image.new("RGB", (180, 240), color)
    if stripe:
        for x in range(0, 180, 12):
            for y in range(240):
                image.putpixel((x, y), (255, 255, 255))
    image.save(path)
    return path


def test_perceptual_hash_identical_images(tmp_path: Path):
    first = _image(tmp_path / "first.png", (230, 160, 20), stripe=True)
    second = _image(tmp_path / "second.png", (230, 160, 20), stripe=True)
    assert hash_similarity(perceptual_hash(first), perceptual_hash(second)) == 1.0


def test_garment_color_similarity_is_bounded(tmp_path: Path):
    garment = _image(tmp_path / "garment.png", (235, 170, 25))
    result = _image(tmp_path / "result.png", (230, 165, 30))
    score = garment_color_similarity(garment, result)
    assert 0.0 <= score <= 1.0
    assert score > 0.8


def test_phase3c2_report_marks_duplicates(tmp_path: Path):
    garment = _image(tmp_path / "garment.png", (230, 160, 20), stripe=True)
    result = _image(tmp_path / "result.png", (230, 160, 20), stripe=True)
    sibling = _image(tmp_path / "sibling.png", (230, 160, 20), stripe=True)
    report = build_phase3c2_report(
        garment_path=garment,
        result_path=result,
        sibling_paths=[sibling],
        provider_metadata={"selected_final_geometry_score": 0.9},
    )
    assert report["duplicate_warning"] is True
    assert report["highest_sibling_similarity"] == 1.0
    assert report["phase"] == "sprint_4_phase_3c_2"


def test_phase3c2_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.phase3c2_retry_distorted_results is True
    assert settings.phase3c2_alternate_person_retries == 2
    assert settings.phase3c2_duplicate_similarity_threshold == 0.94


def test_batch_status_endpoint(client, test_settings, monkeypatch):
    from app.api.routes import catalog as catalog_routes
    monkeypatch.setattr(catalog_routes, "get_settings", lambda: test_settings)
    batch_id = "phase3c2-batch"
    for index, status in enumerate(("completed", "failed"), start=1):
        record = JobRecord(
            job_id=f"job-{index}",
            status=status,
            provider="vertex",
            person_file="person.png",
            garment_file="garment.png",
            provider_metadata={"batch_id": batch_id, "batch_index": index},
        )
        save_job(record, test_settings)
    response = client.get(f"/api/catalog/batch/{batch_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["expected_outputs"] == 2
    assert payload["completed_outputs"] == 1
    assert payload["failed_outputs"] == 1
    assert payload["all_finished"] is True
    assert payload["all_successful"] is False
