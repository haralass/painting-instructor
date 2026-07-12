#!/usr/bin/env python3
"""
Generate the frontend contract from the backend capability registry.

    .venv/bin/python scripts/generate_frontend_contract.py

Writes frontend/app/lib/contract.generated.ts — the ONLY catalogue the
landing page, gallery and workspace may read. The file is checked in;
tests/test_contract_drift.py fails if it goes stale, so the four surfaces
can never disagree about what the product does again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backend.capabilities import registry_payload          # noqa: E402
from backend.teaching.mediums import MEDIUMS               # noqa: E402

OUT = REPO / "frontend" / "app" / "lib" / "contract.generated.ts"


def _ts(obj) -> str:
    """Stable, readable JSON for embedding in TS."""
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False)


def build() -> str:
    payload = registry_payload()
    caps = payload["capabilities"]

    # Frontend-facing capability cards (drop backend-only fields).
    cards = [
        {
            "id": c["id"], "name": c["name"], "category": c["category"],
            "description": c["description"], "why": c["why"], "tip": c["tip"],
            "advertised": c["advertised"], "workspace": c["workspace"],
            "modes": c["modes"], "supports": c["supports"],
            "sample": c["sample"],
        }
        for c in caps
    ]

    classic_page_keys = [c["id"] for c in caps if c["workspace"]]
    page_labels = {
        c["id"]: {"title": c["name"], "why": c["why"], "tip": c["tip"]}
        for c in caps if c["workspace"]
    }
    step_labels = {k: v["message"] for k, v in payload["steps"].items()}
    step_stage = {k: v["stage"] for k, v in payload["steps"].items()}
    detail_levels = payload["detail_levels"]
    level_labels = {str(d["level"]): d["label"] for d in detail_levels}

    # Per-medium stage fallbacks (shown before the live config arrives, or
    # when the backend is down) — generated from the real configs so the
    # landing page can never drift from what the lesson actually teaches.
    medium_fallbacks = {
        mid: {
            "name": cfg["name"],
            "stages": [
                {"order": s["order"], "name": s["name"],
                 "description": s["description"], "why": s.get("why", "")}
                for s in cfg.get("stages", [])
            ],
        }
        for mid, cfg in MEDIUMS.items()
    }

    return f"""// GENERATED FILE — DO NOT EDIT.
// Source of truth: backend/capabilities.py (+ backend/teaching/mediums/*).
// Regenerate with: .venv/bin/python scripts/generate_frontend_contract.py
// tests/test_contract_drift.py fails when this file is stale.

export type CapabilityModes = {{ study: boolean; lesson: boolean; check: boolean }};
export type CapabilitySupports = {{
  local_region: boolean; manual_correction: boolean; checkpoint: boolean;
}};
export type CapabilityCard = {{
  id: string; name: string; category: string;
  description: string; why: string; tip: string;
  advertised: boolean; workspace: boolean;
  modes: CapabilityModes; supports: CapabilitySupports;
  sample: string | null;
}};
export type DetailLevelInfo = {{
  level: number; label: string; description: string; regions_hint: string;
}};
export type MediumStageInfo = {{
  order: number; name: string; description: string; why: string;
}};

export const CAPABILITIES: CapabilityCard[] = {_ts(cards)};

/** Workspace-visible image studies, in display order. ACTIVE FILTER for manifest pages. */
export const CLASSIC_PAGE_KEYS: string[] = {_ts(classic_page_keys)};

export const PAGE_LABELS: Record<string, {{ title: string; why: string; tip: string }}> = {_ts(page_labels)};

export const STEP_LABELS: Record<string, string> = {_ts(step_labels)};

export const STEP_STAGE: Record<string, number> = {_ts(step_stage)};

export const DETAIL_LEVELS: DetailLevelInfo[] = {_ts(detail_levels)};

export const LEVEL_LABELS: Record<number, string> = {_ts(level_labels)};

export const MEDIUM_FALLBACKS: Record<string, {{ name: string; stages: MediumStageInfo[] }}> = {_ts(medium_fallbacks)};
"""


def main() -> int:
    content = build()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        current = OUT.read_text() if OUT.exists() else ""
        if current != content:
            print(f"STALE: {OUT} does not match the registry. Regenerate it.")
            return 1
        print("contract up to date")
        return 0
    OUT.write_text(content)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
