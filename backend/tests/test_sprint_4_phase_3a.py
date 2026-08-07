from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.job import JobRecord
from app.services.storage import list_jobs, save_job


def test_premium_ui_is_served() -> None:
    client = TestClient(app)
    response = client.get("/app")
    assert response.status_code == 200
    assert "TryFit AI Studio" in response.text
    assert "Before" in response.text
    assert "RECENT GENERATIONS" in response.text


def test_ui_assets_are_served() -> None:
    client = TestClient(app)
    css = client.get("/static/styles.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200
    assert "--accent" in css.text
    assert js.status_code == 200
    assert "pollJob" in js.text


def test_health_reports_phase_3a() -> None:
    client = TestClient(app)
    payload = client.get("/api/health").json()
    assert payload["sprint"] == "4"
    assert payload["phase"] == "3A"


def test_recent_history_returns_newest_first(tmp_path: Path, monkeypatch) -> None:
    from app.core.config import Settings
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    monkeypatch.setattr("app.api.routes.jobs.get_settings", lambda: settings)
    first = JobRecord(job_id="a", provider="vertex", person_file="p", garment_file="g", created_at="2026-01-01T00:00:00+00:00")
    second = JobRecord(job_id="b", provider="vertex", person_file="p", garment_file="g", created_at="2026-01-02T00:00:00+00:00")
    save_job(first, settings)
    save_job(second, settings)
    client = TestClient(app)
    response = client.get("/api/jobs/history/recent?limit=1")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_jobs_ignores_invalid_json(tmp_path: Path) -> None:
    from app.core.config import Settings
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    (settings.jobs_dir / "broken.json").write_text("not json", encoding="utf-8")
    assert list_jobs(settings) == []
