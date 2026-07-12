"""Per-level label maps: the viewer's click-select must resolve pixels to
real regions of the merge-tree hierarchy (Phase 2)."""
from __future__ import annotations

import numpy as np
from PIL import Image


def test_label_maps_encode_region_ids(tmp_path):
    from backend.analysis.pipeline import run_hierarchical_analysis

    rng = np.random.default_rng(11)
    img = Image.fromarray(rng.integers(0, 255, (96, 128, 3), dtype=np.uint8))
    hier = run_hierarchical_analysis(
        img=img, out_dir=tmp_path, palette_size=8, value_zones=5, medium="oil",
    )

    label_maps = hier["label_maps"]
    assert set(label_maps), "no label maps were produced"

    import json
    regions = json.loads((tmp_path / "regions.json").read_text())
    by_id = {r["id"]: r for r in regions}

    for lvl, path in label_maps.items():
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.int32)
        ids = arr[..., 0] + (arr[..., 1] << 8) - 1        # 0 encodes "none"
        encoded = {int(i) for i in np.unique(ids) if i >= 0}
        assert encoded, f"level {lvl}: empty label map"
        for rid in encoded:
            assert rid in by_id, f"level {lvl}: encoded id {rid} not in regions.json"
            assert by_id[rid]["scale"] == f"l{lvl}", (
                f"level {lvl}: id {rid} belongs to scale {by_id[rid]['scale']}"
            )
        # Every pixel decodes within the same shared coordinate grid (§21.D).
        assert arr.shape[:2] == (96, 128)
