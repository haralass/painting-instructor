"""
The checked-in frontend contract must always match the backend registry.

This is the drift guard: if anyone edits backend/capabilities.py or a medium
config without regenerating frontend/app/lib/contract.generated.ts, this
test fails with instructions.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GENERATED = REPO / "frontend" / "app" / "lib" / "contract.generated.ts"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_frontend_contract",
        REPO / "scripts" / "generate_frontend_contract.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generated_contract_matches_registry():
    gen = _load_generator()
    expected = gen.build()
    assert GENERATED.exists(), (
        "frontend/app/lib/contract.generated.ts is missing — run "
        ".venv/bin/python scripts/generate_frontend_contract.py"
    )
    assert GENERATED.read_text() == expected, (
        "contract.generated.ts is STALE relative to backend/capabilities.py. "
        "Run: .venv/bin/python scripts/generate_frontend_contract.py"
    )


def test_generated_contract_contains_every_workspace_capability():
    from backend.capabilities import CAPABILITIES
    text = GENERATED.read_text()
    for c in CAPABILITIES:
        if c.workspace or c.advertised:
            assert f'"{c.id}"' in text, f"{c.id} missing from generated contract"


def test_no_hand_maintained_catalogues_remain():
    """The old copies must not creep back: manifest.ts and the pages may only
    derive from the generated contract, never define their own catalogue."""
    manifest_ts = (REPO / "frontend/app/results/[jobId]/lib/manifest.ts").read_text()
    landing = (REPO / "frontend/app/page.tsx").read_text()
    gallery = (REPO / "frontend/app/gallery/page.tsx").read_text()

    # Catalogue *definitions* are banned; re-exports/imports are the point.
    for banned in ("STEP_LABELS: Record", "PAGE_LABELS: Record",
                   "CLASSIC_PAGE_KEYS = [", "LEVEL_LABELS: Record"):
        assert banned not in manifest_ts, f"hand-maintained catalogue in manifest.ts: {banned}"
    assert 'from "../../../lib/contract.generated"' in manifest_ts

    assert "OIL_FALLBACK" not in landing, "hand-maintained oil config copy in page.tsx"
    assert "ANALYSIS_TILES" not in landing, "hand-maintained study tiles in page.tsx"
    assert "Full Reference" not in landing
    assert 'from "./lib/contract.generated"' in landing

    assert "teaches:" not in gallery, "hand-maintained study list in gallery"
    assert 'from "../lib/contract.generated"' in gallery
