"""
Project-state store — the save/continue foundation (brief §18, Phase 1).

A painting project outlives its analysis job: it keeps the settings, the
reference, the learner's position in the lesson, checkpoint states, manual
corrections and progress-photo attempts. Phase 1 stores state; later phases
add behaviour on top of the same rows.

Implementation notes:
- stdlib sqlite3 (no new dependency), one file at <outputs_root>/projects.db,
  resolved at call time so test OUTPUTS_DIR overrides work like everywhere
  else in the codebase.
- WAL + busy_timeout: the API process is the only writer today, but WAL keeps
  a future worker-side writer safe.
- Rows carry ISO-8601 UTC timestamps and JSON blobs for forward-compatible
  detail fields (lesson-step data, checkpoint data, correction payloads).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..utils.paths import outputs_root

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id                 TEXT PRIMARY KEY,
    job_id             TEXT UNIQUE,
    title              TEXT NOT NULL DEFAULT '',
    reference_path     TEXT NOT NULL DEFAULT '',
    medium             TEXT NOT NULL DEFAULT 'oil',
    skill_level        TEXT NOT NULL DEFAULT 'intermediate',
    value_zones        INTEGER NOT NULL DEFAULT 5,
    settings_json      TEXT NOT NULL DEFAULT '{}',
    current_capability TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_progress (
    project_id TEXT NOT NULL,
    step_id    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending|in_progress|completed|skipped
    data_json  TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, step_id)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type       TEXT NOT NULL,      -- schemas/lesson.py CheckpointType
    status     TEXT NOT NULL DEFAULT 'open',      -- open|passed|needs_correction
    data_json  TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    data_json     TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    checkpoint_id TEXT,
    path          TEXT NOT NULL,
    critique_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_progress_project    ON lesson_progress(project_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_id);
CREATE INDEX IF NOT EXISTS idx_attempts_project    ON attempts(project_id);
"""

VALID_STEP_STATUSES = {"pending", "in_progress", "completed", "skipped"}
VALID_CHECKPOINT_STATUSES = {"open", "passed", "needs_correction"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    root = outputs_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "projects.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(_SCHEMA)
    return conn


def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["settings"] = json.loads(d.pop("settings_json") or "{}")
    return d


# ── Projects ──────────────────────────────────────────────────────────────────

def create_project(
    job_id: str,
    reference_path: str,
    medium: str,
    skill_level: str,
    value_zones: int,
    settings: dict | None = None,
    title: str = "",
) -> dict[str, Any]:
    now = _now()
    project_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, job_id, title, reference_path, medium, skill_level,"
            " value_zones, settings_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, job_id, title or f"{medium.title()} painting",
             reference_path, medium, skill_level, value_zones,
             json.dumps(settings or {}), now, now),
        )
    return get_project(project_id)  # type: ignore[return-value]


def get_project(project_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _row_to_project(row) if row else None


def get_project_by_job(job_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE job_id = ?", (job_id,)).fetchone()
    return _row_to_project(row) if row else None


def list_projects(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_project(r) for r in rows]


def update_project(project_id: str, *, title: str | None = None,
                   current_capability: str | None = None) -> Optional[dict[str, Any]]:
    sets, args = ["updated_at = ?"], [_now()]
    if title is not None:
        sets.append("title = ?"); args.append(title)
    if current_capability is not None:
        sets.append("current_capability = ?"); args.append(current_capability)
    args.append(project_id)
    with _connect() as conn:
        cur = conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", args)
        if cur.rowcount == 0:
            return None
    return get_project(project_id)


def _touch(conn: sqlite3.Connection, project_id: str) -> None:
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))


# ── Lesson progress ───────────────────────────────────────────────────────────

def set_step_status(project_id: str, step_id: str, status: str,
                    data: dict | None = None) -> dict[str, Any]:
    if status not in VALID_STEP_STATUSES:
        raise ValueError(f"invalid step status {status!r}")
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO lesson_progress (project_id, step_id, status, data_json, updated_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(project_id, step_id)"
            " DO UPDATE SET status = excluded.status, data_json = excluded.data_json,"
            "               updated_at = excluded.updated_at",
            (project_id, step_id, status, json.dumps(data or {}), now),
        )
        _touch(conn, project_id)
    return {"project_id": project_id, "step_id": step_id, "status": status}


def get_lesson_progress(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT step_id, status, data_json, updated_at FROM lesson_progress"
            " WHERE project_id = ? ORDER BY updated_at", (project_id,)
        ).fetchall()
    return [
        {"step_id": r["step_id"], "status": r["status"],
         "data": json.loads(r["data_json"]), "updated_at": r["updated_at"]}
        for r in rows
    ]


# ── Checkpoints ───────────────────────────────────────────────────────────────

def upsert_checkpoint(project_id: str, checkpoint_type: str, status: str = "open",
                      data: dict | None = None,
                      checkpoint_id: str | None = None) -> dict[str, Any]:
    from ..schemas.lesson import CheckpointType  # closed vocabulary
    if checkpoint_type not in CheckpointType.__args__:  # type: ignore[attr-defined]
        raise ValueError(f"invalid checkpoint type {checkpoint_type!r}")
    if status not in VALID_CHECKPOINT_STATUSES:
        raise ValueError(f"invalid checkpoint status {status!r}")
    now = _now()
    cid = checkpoint_id or str(uuid.uuid4())
    with _connect() as conn:
        existing = conn.execute("SELECT id FROM checkpoints WHERE id = ?", (cid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE checkpoints SET status = ?, data_json = ?, updated_at = ? WHERE id = ?",
                (status, json.dumps(data or {}), now, cid),
            )
        else:
            conn.execute(
                "INSERT INTO checkpoints (id, project_id, type, status, data_json,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (cid, project_id, checkpoint_type, status, json.dumps(data or {}), now, now),
            )
        _touch(conn, project_id)
    return {"id": cid, "project_id": project_id, "type": checkpoint_type, "status": status}


def get_checkpoints(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM checkpoints WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
    return [
        {"id": r["id"], "type": r["type"], "status": r["status"],
         "data": json.loads(r["data_json"]), "created_at": r["created_at"],
         "updated_at": r["updated_at"]}
        for r in rows
    ]


# ── Corrections & attempts ────────────────────────────────────────────────────

def add_correction(project_id: str, capability_id: str, data: dict) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO corrections (id, project_id, capability_id, data_json, created_at)"
            " VALUES (?,?,?,?,?)",
            (cid, project_id, capability_id, json.dumps(data), _now()),
        )
        _touch(conn, project_id)
    return {"id": cid, "project_id": project_id, "capability_id": capability_id}


def get_corrections(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM corrections WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
    return [
        {"id": r["id"], "capability_id": r["capability_id"],
         "data": json.loads(r["data_json"]), "created_at": r["created_at"]}
        for r in rows
    ]


def add_attempt(project_id: str, path: str, critique: dict | None = None,
                checkpoint_id: str | None = None) -> dict[str, Any]:
    aid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO attempts (id, project_id, checkpoint_id, path, critique_json,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (aid, project_id, checkpoint_id, path, json.dumps(critique or {}), _now()),
        )
        _touch(conn, project_id)
    return {"id": aid, "project_id": project_id, "path": path}


def get_attempts(project_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attempts WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
    return [
        {"id": r["id"], "checkpoint_id": r["checkpoint_id"], "path": r["path"],
         "critique": json.loads(r["critique_json"]), "created_at": r["created_at"]}
        for r in rows
    ]
