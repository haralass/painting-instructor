from __future__ import annotations
import os
from pathlib import Path

# Single source of truth for output paths. The env var is read at call time so
# tests can override OUTPUTS_DIR without importlib.reload() — a reload here
# poisons every module that already holds these functions, because reloaded
# definitions share the same module __globals__ dict.


def outputs_root() -> Path:
    """Absolute path to the outputs directory."""
    return Path(os.getenv("OUTPUTS_DIR", "outputs")).resolve()


def job_dir(job_id: str) -> Path:
    """Absolute path to a specific job's output directory."""
    return outputs_root() / job_id


def rel_to_outputs(abs_path: str | Path) -> str | None:
    """Convert an absolute path to a path relative to outputs root, or None."""
    if not abs_path:
        return None
    try:
        return str(Path(abs_path).relative_to(outputs_root()))
    except ValueError:
        return str(Path(abs_path).name)


def job_asset_url(rel_path: str | None) -> str | None:
    """Convert a path relative to outputs root to a /outputs/... URL."""
    if not rel_path:
        return None
    return f"/outputs/{rel_path}"
