"""
Two friends on one instance must not see each other's work.

user_id is a browser-generated identifier, not authentication — these tests
pin the *separation* guarantee (and the 404-not-403 rule that keeps another
learner's project from even being detectable). Access control is Cloudflare
Access in front of the tunnel, not this.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ALICE = "u_alice_0000000000"
BOB = "u_bob_0000000000000"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
    from backend.projects import store as project_store
    return project_store


@pytest.fixture()
def client(store):
    from backend.api.main import app
    return TestClient(app)


def _mk(store, job_id: str, user_id: str | None):
    return store.create_project(
        job_id=job_id, reference_path=f"{job_id}/reference.jpg",
        medium="oil", skill_level="beginner", value_zones=5,
        settings={"palette_size": 12}, user_id=user_id,
    )


class TestStoreScoping:
    def test_list_returns_only_your_own(self, store):
        _mk(store, "job-a", ALICE)
        _mk(store, "job-b", BOB)
        assert [p["job_id"] for p in store.list_projects(user_id=ALICE)] == ["job-a"]
        assert [p["job_id"] for p in store.list_projects(user_id=BOB)] == ["job-b"]

    def test_get_someone_elses_project_reads_as_missing(self, store):
        a = _mk(store, "job-a", ALICE)
        assert store.get_project(a["id"], user_id=BOB) is None
        assert store.get_project_by_job("job-a", user_id=BOB) is None
        assert store.get_project(a["id"], user_id=ALICE) is not None

    def test_cannot_write_to_someone_elses_project(self, store):
        a = _mk(store, "job-a", ALICE)
        assert store.update_project(a["id"], title="stolen", user_id=BOB) is None
        assert store.get_project(a["id"], user_id=ALICE)["title"] != "stolen"

    def test_unowned_legacy_rows_are_invisible_to_identified_users(self, store):
        """Projects created before scoping must not leak once the box is shared."""
        legacy = _mk(store, "job-legacy", None)
        assert store.list_projects(user_id=ALICE) == []
        assert store.get_project(legacy["id"], user_id=ALICE) is None
        # …but local single-user use (no user_id at all) still sees everything.
        assert [p["job_id"] for p in store.list_projects()] == ["job-legacy"]

    def test_migration_keeps_existing_rows(self, store, monkeypatch):
        """Adding user_id to an existing db must not drop or corrupt rows."""
        import sqlite3
        _mk(store, "job-old", ALICE)
        # Simulate a pre-scoping database, which had neither the column nor
        # the index over it.
        with sqlite3.connect(store.db_path()) as conn:
            conn.execute("DROP INDEX IF EXISTS idx_projects_user")
            conn.execute("ALTER TABLE projects DROP COLUMN user_id")
            assert "user_id" not in {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        # Next connect runs the migration.
        rows = store.list_projects()
        assert [r["job_id"] for r in rows] == ["job-old"]
        assert rows[0]["user_id"] is None


class TestApiScoping:
    def test_projects_endpoint_filters_by_user(self, client, store):
        _mk(store, "job-a", ALICE)
        _mk(store, "job-b", BOB)

        alice = client.get("/projects", params={"user_id": ALICE}).json()
        assert [p["job_id"] for p in alice] == ["job-a"]

        bob = client.get("/projects", params={"user_id": BOB}).json()
        assert [p["job_id"] for p in bob] == ["job-b"]

    def test_other_users_project_is_404_not_403(self, client, store):
        a = _mk(store, "job-a", ALICE)
        r = client.get(f"/projects/{a['id']}", params={"user_id": BOB})
        assert r.status_code == 404, "403 would confirm the project exists"

        r = client.get("/projects/by-job/job-a", params={"user_id": BOB})
        assert r.status_code == 404

    def test_other_users_project_cannot_be_patched_or_progressed(self, client, store):
        a = _mk(store, "job-a", ALICE)

        r = client.patch(f"/projects/{a['id']}", params={"user_id": BOB}, json={"title": "stolen"})
        assert r.status_code == 404

        r = client.post(f"/projects/{a['id']}/progress", params={"user_id": BOB},
                        json={"step_id": "s1", "status": "completed"})
        assert r.status_code == 404

        r = client.post(f"/projects/{a['id']}/checkpoints", params={"user_id": BOB},
                        json={"type": "drawing", "status": "open"})
        assert r.status_code == 404

        assert client.get(f"/projects/{a['id']}", params={"user_id": ALICE}).json()["title"] != "stolen"

    def test_upload_records_the_uploader(self, client, store, tmp_path):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (120, 90, 60)).save(buf, format="JPEG")
        buf.seek(0)
        r = client.post(
            "/jobs/",
            files={"file": ("ref.jpg", buf, "image/jpeg")},
            data={"medium": "oil", "user_id": ALICE},
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        assert store.get_project_by_job(job_id, user_id=ALICE) is not None
        assert store.get_project_by_job(job_id, user_id=BOB) is None
