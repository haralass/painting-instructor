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
