#!/usr/bin/env python3
"""
Assign unowned projects to a user id.

Projects created before user scoping existed have user_id = NULL. An
identified browser sees only its own rows, so those legacy projects are
invisible to everyone — deliberately, so that sharing the instance can never
expose whatever was already in the database.

Run this once, with your own id, to adopt them:

    # Your id, from the browser console on the app:
    #   localStorage.getItem("painter_user_id")
    .venv/bin/python scripts/claim_projects.py --user-id <that-uuid>

    # See what would change first:
    .venv/bin/python scripts/claim_projects.py --user-id u_xxx --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.projects.store import db_path  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-id", required=True, help="the browser id to assign the projects to")
    ap.add_argument("--dry-run", action="store_true", help="list what would change, change nothing")
    args = ap.parse_args()

    path = db_path()
    if not path.exists():
        print(f"No database at {path} — nothing to claim.")
        return 0

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, job_id, title, created_at FROM projects"
        " WHERE user_id IS NULL ORDER BY created_at"
    ).fetchall()

    if not rows:
        print("No unowned projects — nothing to claim.")
        return 0

    print(f"{len(rows)} unowned project(s) in {path}:")
    for r in rows:
        print(f"  {r['created_at']}  {r['title']:<22} job={r['job_id']}")

    if args.dry_run:
        print(f"\n--dry-run: would assign all of the above to {args.user_id!r}.")
        return 0

    with conn:
        conn.execute("UPDATE projects SET user_id = ? WHERE user_id IS NULL", (args.user_id,))
    print(f"\nAssigned {len(rows)} project(s) to {args.user_id!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
