"""Project-state store + endpoints (save/continue foundation, brief §18)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
    from backend.projects import store as project_store
    return project_store


@pytest.fixture()
def client(store):
    from backend.api.main import app
    return TestClient(app)


def _mk(store, job_id="job-1"):
    return store.create_project(
        job_id=job_id, reference_path=f"{job_id}/reference.jpg",
        medium="oil", skill_level="beginner", value_zones=5,
        settings={"palette_size": 12},
    )


def test_create_get_list_roundtrip(store):
    p = _mk(store)
    assert p["medium"] == "oil"
    assert p["settings"] == {"palette_size": 12}
    assert store.get_project(p["id"]) == p
    assert store.get_project_by_job("job-1")["id"] == p["id"]
    assert [x["id"] for x in store.list_projects()] == [p["id"]]


def test_update_title_and_capability(store):
    p = _mk(store)
    updated = store.update_project(p["id"], title="Harbour at dusk",
                                   current_capability="notan")
    assert updated["title"] == "Harbour at dusk"
    assert updated["current_capability"] == "notan"
    assert store.update_project("nope", title="x") is None


def test_lesson_progress_upsert_and_validation(store):
    p = _mk(store)
    store.set_step_status(p["id"], "s1", "in_progress")
    store.set_step_status(p["id"], "s1", "completed", {"minutes": 12})
    rows = store.get_lesson_progress(p["id"])
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["data"] == {"minutes": 12}
    with pytest.raises(ValueError):
        store.set_step_status(p["id"], "s1", "vibing")


def test_checkpoints_use_schema_vocabulary(store):
    p = _mk(store)
    cp = store.upsert_checkpoint(p["id"], "silhouette")
    assert cp["status"] == "open"
    passed = store.upsert_checkpoint(p["id"], "silhouette", "passed",
                                     checkpoint_id=cp["id"])
    assert passed["status"] == "passed"
    assert len(store.get_checkpoints(p["id"])) == 1
    with pytest.raises(ValueError):
        store.upsert_checkpoint(p["id"], "mood")


def test_corrections_and_attempts(store):
    p = _mk(store)
    store.add_correction(p["id"], "line_art", {"region": 4, "action": "merge"})
    store.add_attempt(p["id"], "job-1/critique/attempt_1/attempt.jpg",
                      critique={"priority": "values"})
    assert store.get_corrections(p["id"])[0]["capability_id"] == "line_art"
    assert store.get_attempts(p["id"])[0]["critique"] == {"priority": "values"}


def test_selections_persist(store):
    p = _mk(store)
    store.add_selection(p["id"], {"selection_id": "abc", "bbox": {"x": 10, "y": 20, "w": 30, "h": 40}})
    sels = store.get_selections(p["id"])
    assert len(sels) == 1 and sels[0]["data"]["selection_id"] == "abc"
    assert sels[0]["data"]["bbox"]["w"] == 30


def test_list_projects_summary_has_progress_and_latest_priority(store):
    p = _mk(store)
    store.set_step_status(p["id"], "s1", "completed")
    store.set_step_status(p["id"], "s2", "completed")
    # a structured priority dict (as the critique now emits)
    store.add_attempt(p["id"], "job-1/att.jpg",
                      critique={"priority": {"component": "proportion",
                                             "message": "The figure is too narrow."}})
    summary = store.list_projects()[0]
    assert summary["completed_steps"] == 2
    assert summary["latest_priority"] == "The figure is too narrow."


def test_recent_ordering_follows_activity(store):
    a = _mk(store, "job-a")
    b = _mk(store, "job-b")
    import time
    time.sleep(1.1)  # second-resolution timestamps
    store.set_step_status(a["id"], "s1", "completed")
    assert [x["id"] for x in store.list_projects()][0] == a["id"]


# ── API surface ───────────────────────────────────────────────────────────────

def test_endpoints_roundtrip(store, client):
    p = _mk(store, "job-api")
    assert client.get("/projects").json()[0]["id"] == p["id"]

    r = client.patch(f"/projects/{p['id']}",
                     json={"current_capability": "dot_to_dot"})
    assert r.status_code == 200 and r.json()["current_capability"] == "dot_to_dot"

    # Historical ids resolve through the migration map; junk does not.
    r = client.patch(f"/projects/{p['id']}",
                     json={"current_capability": "dot_to_dot_classic"})
    assert r.status_code == 200
    assert client.patch(f"/projects/{p['id']}",
                        json={"current_capability": "florp"}).status_code == 422

    assert client.post(f"/projects/{p['id']}/progress",
                       json={"step_id": "s1", "status": "completed"}).status_code == 200
    assert client.post(f"/projects/{p['id']}/checkpoints",
                       json={"type": "values", "status": "open"}).status_code == 200

    full = client.get(f"/projects/{p['id']}").json()
    assert full["lesson_progress"][0]["step_id"] == "s1"
    assert full["checkpoints"][0]["type"] == "values"

    assert client.get("/projects/does-not-exist").status_code == 404

    # by-job resolution (the lesson player knows the job id, not the project id)
    byjob = client.get("/projects/by-job/job-api")
    assert byjob.status_code == 200 and byjob.json()["id"] == p["id"]
    assert "lesson_progress" in byjob.json() and "checkpoints" in byjob.json()
    assert client.get("/projects/by-job/no-such-job").status_code == 404


# ── Resume path: finished jobs must open without the broker ──────────────────

def test_finished_job_resumes_from_disk_manifest(store, client):
    """Celery results expire from Redis; the on-disk manifest is the durable
    record a saved project resumes from (brief §18)."""
    import json, os
    from pathlib import Path
    out_root = Path(os.environ["OUTPUTS_DIR"])
    job_dir = out_root / "resume-job"
    job_dir.mkdir(parents=True)
    (job_dir / "manifest.json").write_text(json.dumps({
        "job_id": "resume-job",
        "pages": ["resume-job/notan.png"],
        "video": "resume-job/tutorial.mp4",
        "pdf": None,
    }))
    body = client.get("/jobs/resume-job").json()
    assert body["status"] == "completed"
    assert body["result"]["manifest"] == "/outputs/resume-job/manifest.json"
    assert body["result"]["pages"] == ["/outputs/resume-job/notan.png"]
    assert body["result"]["video"] == "/outputs/resume-job/tutorial.mp4"


def test_analysis_ready_manifest_reports_processing(store, client):
    import json, os
    from pathlib import Path
    out_root = Path(os.environ["OUTPUTS_DIR"])
    job_dir = out_root / "midway-job"
    job_dir.mkdir(parents=True)
    (job_dir / "manifest.json").write_text(json.dumps({
        "job_id": "midway-job", "status": "analysis_ready", "pages": [],
    }))
    body = client.get("/jobs/midway-job").json()
    assert body["status"] == "processing"
    assert body["analysis_ready"] is True
