from __future__ import annotations
import heapq
import logging
from collections import defaultdict

import cv2
import numpy as np
from skimage import segmentation
from skimage import color as skcolor
from scipy.ndimage import center_of_mass, mean as ndimage_mean, labeled_comprehension

from .models import Region
from .preprocessing import ImageCache
from .values import compute_value_zones

log = logging.getLogger(__name__)


class _UnionFind:
    """Union-Find with member tracking for merge-tree construction."""

    def __init__(self, n: int) -> None:
        self.parent: list[int] = list(range(n))
        self.rank: list[int] = [0] * n
        # Each node tracks the set of base SLIC labels it covers
        self.members: dict[int, set[int]] = {i: {i} for i in range(n)}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int, new_id: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Create new_id as the merged root
        self.parent.append(new_id)
        self.rank.append(0)
        combined = self.members.get(rx, set()) | self.members.get(ry, set())
        self.members[new_id] = combined
        self.parent[rx] = new_id
        self.parent[ry] = new_id


def build_region_hierarchy(
    cache: ImageCache,
    palette_size: int,
    detail_level: int,
    n_value_zones: int,
    value_colour_families: dict,
    seed: int = 42,
) -> tuple[dict[str, np.ndarray], list[Region]]:
    """
    Build a 5-level hierarchy using a single SLIC base segmentation +
    agglomerative merge tree.

    Raises on failure — caller (Celery task) is responsible for catching and
    setting task state to FAILURE.

    Returns
    -------
    label_maps : dict  "l1".."l5" → (H,W) int32 label array
    regions    : flat list of Region objects across all 5 levels
    """
    return _build_merge_tree_hierarchy(
        cache, palette_size, detail_level, n_value_zones, value_colour_families, seed
    )


def _compute_region_targets(cache: ImageCache, n_base: int) -> list[int]:
    """
    Adaptive region targets based on image complexity, independent of palette size.
    Uses gradient density as a proxy for structural complexity.
    """
    max_grad = float(cache.grad.max()) + 1e-6
    grad_density = float((cache.grad / max_grad).mean())   # 0–1

    # Lerp between simple and complex presets
    simple   = [4,  8,  20,  60, 150]
    complex_ = [8, 20,  60, 180, 400]
    targets = [
        max(s, min(c, int(s + (c - s) * grad_density)))
        for s, c in zip(simple, complex_)
    ]
    # Never exceed n_base/3 for the finest level
    targets[4] = min(targets[4], max(targets[3] + 2, n_base // 3))
    # Ensure strictly increasing
    for i in range(1, 5):
        targets[i] = max(targets[i], targets[i - 1] + 2)
    return targets


def _build_merge_tree_hierarchy(
    cache: ImageCache,
    palette_size: int,
    detail_level: int,
    n_value_zones: int,
    value_colour_families: dict,
    seed: int,
) -> tuple[dict[str, np.ndarray], list[Region]]:
    H, W = cache.H, cache.W
    smooth_rgb = cache.smooth
    zone_map, zones = compute_value_zones(cache, n_value_zones)
    lab_img = cache.lab
    grad = cache.grad

    # ── Base SLIC segmentation ────────────────────────────────────────────────
    n_base = max(200, min(1500, int((W * H) ** 0.5 // 4)))
    base_labels = segmentation.slic(
        smooth_rgb,
        n_segments=n_base,
        compactness=10,
        sigma=1,
        start_label=0,
        enforce_connectivity=True,
        convert2lab=True,
    )

    uniq_base = np.unique(base_labels)
    n_actual = len(uniq_base)
    # Re-index to 0..n_actual-1
    remap = np.zeros(int(base_labels.max()) + 1, dtype=np.int32)
    for new_idx, old_lbl in enumerate(uniq_base):
        remap[old_lbl] = new_idx
    base_labels = remap[base_labels]
    n_actual = int(base_labels.max()) + 1

    # ── Precompute per-superpixel stats ───────────────────────────────────────
    sp_area = np.bincount(base_labels.ravel(), minlength=n_actual)
    # Centroid
    sp_centroids = center_of_mass(
        np.ones((H, W), dtype=np.float32), base_labels, range(n_actual)
    )
    # Mean LAB via ndimage
    sp_L = ndimage_mean(lab_img[:, :, 0], base_labels, range(n_actual))
    sp_a = ndimage_mean(lab_img[:, :, 1], base_labels, range(n_actual))
    sp_b = ndimage_mean(lab_img[:, :, 2], base_labels, range(n_actual))
    sp_lab = np.column_stack([sp_L, sp_a, sp_b])  # (n_actual, 3)

    # ── Build RAG (Region Adjacency Graph) ────────────────────────────────────
    # Edge weight = LAB colour diff + 0.1 * normalised spatial distance
    adj: dict[tuple[int, int], float] = {}
    diag_dist = float(np.sqrt(H * H + W * W))

    for dy, dx in [(0, 1), (1, 0)]:
        a_map = base_labels[:-1, :]  if dy == 1 else base_labels[:, :-1]
        b_map = base_labels[1:, :]   if dy == 1 else base_labels[:, 1:]
        border = a_map != b_map
        a_lbls = a_map[border]
        b_lbls = b_map[border]
        pairs = np.column_stack([
            np.minimum(a_lbls, b_lbls),
            np.maximum(a_lbls, b_lbls),
        ])
        for p in np.unique(pairs, axis=0):
            i, j = int(p[0]), int(p[1])
            if (i, j) in adj:
                continue
            lab_diff = float(np.linalg.norm(sp_lab[i] - sp_lab[j]))
            cy_i, cx_i = sp_centroids[i]
            cy_j, cx_j = sp_centroids[j]
            sp_dist = float(np.sqrt((cy_i - cy_j) ** 2 + (cx_i - cx_j) ** 2)) / diag_dist
            adj[(i, j)] = lab_diff + 0.1 * sp_dist

    # ── Priority-queue agglomerative merge ────────────────────────────────────
    heap: list[tuple[float, int, int]] = [
        (cost, i, j) for (i, j), cost in adj.items()
    ]
    heapq.heapify(heap)

    uf = _UnionFind(n_actual)
    # merges: (node_a, node_b, cost, new_id)
    merges: list[tuple[int, int, float, int]] = []
    next_id = n_actual
    # Track active root → set of neighbours with edge cost
    root_adj: dict[int, dict[int, float]] = defaultdict(dict)
    for (i, j), cost in adj.items():
        root_adj[i][j] = cost
        root_adj[j][i] = cost

    # Track mean LAB per merged node (running average)
    node_lab = {i: sp_lab[i].copy() for i in range(n_actual)}
    node_area = {i: int(sp_area[i]) for i in range(n_actual)}
    node_centroid = {i: list(sp_centroids[i]) for i in range(n_actual)}

    n_remaining = n_actual
    processed: set[tuple[int, int]] = set()

    while heap and n_remaining > 1:
        cost, a, b = heapq.heappop(heap)
        ra = uf.find(a)
        rb = uf.find(b)
        if ra == rb:
            continue
        key = (min(ra, rb), max(ra, rb))
        if key in processed:
            continue
        processed.add(key)

        new_id = next_id
        next_id += 1
        n_remaining -= 1

        # Weighted mean LAB
        area_a = node_area.get(ra, 1)
        area_b = node_area.get(rb, 1)
        total = area_a + area_b
        lab_merged = (node_lab[ra] * area_a + node_lab[rb] * area_b) / total
        cy_merged = (node_centroid[ra][0] * area_a + node_centroid[rb][0] * area_b) / total
        cx_merged = (node_centroid[ra][1] * area_a + node_centroid[rb][1] * area_b) / total

        node_lab[new_id] = lab_merged
        node_area[new_id] = total
        node_centroid[new_id] = [cy_merged, cx_merged]

        uf.union(ra, rb, new_id)
        merges.append((ra, rb, cost, new_id))

        # Merge adjacency lists: new_id inherits all neighbours of ra + rb
        neighbours_a = set(root_adj.get(ra, {}).keys()) - {ra, rb}
        neighbours_b = set(root_adj.get(rb, {}).keys()) - {ra, rb}
        new_adj: dict[int, float] = {}
        for nb in neighbours_a | neighbours_b:
            nb_root = uf.find(nb)
            if nb_root == new_id:
                continue
            cost_a = root_adj.get(ra, {}).get(nb, None)
            cost_b = root_adj.get(rb, {}).get(nb, None)
            # Use minimum linkage
            candidates = [c for c in [cost_a, cost_b] if c is not None]
            if candidates:
                new_cost = min(candidates)
                new_adj[nb_root] = min(new_adj.get(nb_root, float("inf")), new_cost)

        for nb, new_cost in new_adj.items():
            root_adj[new_id][nb] = new_cost
            root_adj[nb][new_id] = new_cost
            heapq.heappush(heap, (new_cost, new_id, nb))

        # Clean up
        root_adj.pop(ra, None)
        root_adj.pop(rb, None)

    # ── Define 5 cut points ───────────────────────────────────────────────────
    cut_sizes = _compute_region_targets(cache, n_actual)

    # ── Produce label maps from merge sequence ────────────────────────────────
    level_label_maps = _cuts_to_label_maps(base_labels, merges, cut_sizes, n_actual, H, W)

    # ── Build Region objects ──────────────────────────────────────────────────
    all_regions: list[Region] = []
    region_id = 0

    # For parent mapping: scale "l{k}" → {source_label → region_id}
    scale_lbl_to_rid: dict[str, dict[int, int]] = {}

    for lvl_idx, (scale_name, label_map) in enumerate(level_label_maps.items()):
        level_regions, region_id = _extract_level_regions(
            label_map=label_map,
            scale=scale_name,
            level=lvl_idx,
            cache=cache,
            zone_map=zone_map,
            value_colour_families=value_colour_families,
            id_start=region_id,
            level_label_maps=level_label_maps,
            scale_lbl_to_rid=scale_lbl_to_rid,
        )
        all_regions.extend(level_regions)
        this_scale_map = {r.source_label: r.id for r in level_regions}
        scale_lbl_to_rid[scale_name] = this_scale_map

    return level_label_maps, all_regions


def _extract_level_regions(
    label_map: np.ndarray,
    scale: str,
    level: int,
    cache: ImageCache,
    zone_map: np.ndarray,
    value_colour_families: dict,
    id_start: int,
    level_label_maps: dict[str, np.ndarray],
    scale_lbl_to_rid: dict[str, dict[int, int]],
) -> tuple[list[Region], int]:
    """
    Vectorised region feature extraction — O(P + V) instead of O(P × V).
    """
    lab  = cache.lab.astype(np.float32)
    grad = cache.grad
    H, W = cache.H, cache.W

    unique = np.unique(label_map)
    n = len(unique)
    if n == 0:
        return [], id_start

    # --- Vectorised means via scipy.ndimage ---
    L_means  = ndimage_mean(lab[:, :, 0], label_map, unique)
    a_means  = ndimage_mean(lab[:, :, 1], label_map, unique)
    b_means  = ndimage_mean(lab[:, :, 2], label_map, unique)
    g_means  = ndimage_mean(grad,          label_map, unique)

    # --- Areas via bincount (fast) ---
    flat = label_map.ravel()
    max_lbl = int(unique.max()) + 1
    area_lut = np.bincount(flat, minlength=max_lbl)

    # --- Centroids via ndimage_mean on row/col indices ---
    ys_idx = np.broadcast_to(np.arange(H, dtype=np.float32)[:, None], (H, W))
    xs_idx = np.broadcast_to(np.arange(W, dtype=np.float32)[None, :], (H, W))
    cy_arr = ndimage_mean(ys_idx, label_map, unique)
    cx_arr = ndimage_mean(xs_idx, label_map, unique)

    # --- Value zone majority via labeled_comprehension ---
    n_zones = int(zone_map.max()) + 1

    def zone_mode(arr: np.ndarray) -> int:
        bc = np.bincount(arr.astype(np.int32), minlength=n_zones)
        return int(bc.argmax())

    vz_arr = labeled_comprehension(zone_map, label_map, unique, zone_mode, int, 0)

    # --- Texture score: std of L* within region (via variance = E[X^2] - E[X]^2) ---
    L_sq_means = ndimage_mean(lab[:, :, 0] ** 2, label_map, unique)
    texture_arr = np.sqrt(np.maximum(0.0, np.array(L_sq_means) - np.array(L_means) ** 2)) / 50.0
    texture_arr = np.clip(texture_arr, 0, 1)

    # --- Build Region objects ---
    centres_lab = value_colour_families.get("centres_lab")
    id_to_rank  = value_colour_families.get("cluster_id_to_rank", {})
    regions: list[Region] = []
    region_id = id_start

    for i, lbl in enumerate(unique):
        area = int(area_lut[lbl]) if lbl < max_lbl else 0
        if area == 0:
            continue

        mean_lab_arr = np.array([float(L_means[i]), float(a_means[i]), float(b_means[i])])
        rgb_f = skcolor.lab2rgb(mean_lab_arr.reshape(1, 1, 3))[0, 0] * 255
        mean_rgb = tuple(int(np.clip(v, 0, 255)) for v in rgb_f)

        importance = float(np.log1p(area) * (1 + float(g_means[i]) / 50.0) / 15.0)
        importance = min(1.0, importance)

        if centres_lab is not None and len(centres_lab):
            dists = np.linalg.norm(centres_lab - mean_lab_arr, axis=1)
            raw_idx = int(dists.argmin())
            cf_id   = id_to_rank.get(raw_idx, raw_idx)
        else:
            cf_id = 0

        cy_v = float(cy_arr[i])
        cx_v = float(cx_arr[i])

        # Parent: look up same centroid pixel in coarser level
        parent_id: int | None = None
        if level > 0:
            coarser_scale = f"l{level}"
            coarser_lm = level_label_maps.get(coarser_scale)
            coarser_map = scale_lbl_to_rid.get(coarser_scale)
            if coarser_lm is not None and coarser_map is not None:
                cy_i = int(np.clip(round(cy_v), 0, H - 1))
                cx_i = int(np.clip(round(cx_v), 0, W - 1))
                parent_lbl = int(coarser_lm[cy_i, cx_i])
                parent_id = coarser_map.get(parent_lbl)

        regions.append(Region(
            id=region_id,
            source_label=int(lbl),
            scale=scale,
            parent_id=parent_id,
            level=level,
            area=area,
            centroid=(cx_v, cy_v),
            bbox=(0, 0, W, H),   # TODO: bounding box if needed
            mean_lab=(float(L_means[i]), float(a_means[i]), float(b_means[i])),
            mean_rgb=mean_rgb,
            value_zone=int(vz_arr[i]),
            colour_family_id=cf_id,
            importance=importance,
            texture_score=float(texture_arr[i]),
        ))
        region_id += 1

    return regions, region_id


def _cuts_to_label_maps(
    base_labels: np.ndarray,
    merges: list[tuple[int, int, float, int]],
    cut_sizes: list[int],
    n_base: int,
    H: int,
    W: int,
) -> dict[str, np.ndarray]:
    """
    Walk the merge sequence; at each target region count, snapshot the label map.

    Returns dict "l1".."l5" → (H,W) int32 array.
    """
    # Track current root for each base label
    current_root = list(range(n_base))  # base_label → current root node

    # Map from node → representative base-label index (for label map output)
    # We use the root node ID as the output label value.

    # We walk merges from finest (last merge) to coarsest (first merge),
    # but we need coarse → fine. The merge list is in order of increasing cost
    # (coarsest structure merges last? No, minimum-cost-first means fine merges first).
    # Actually with min-heap: cheapest edges merge first → fine detail merges first,
    # large cost (cross-boundary) merges last.
    # So merges[0] is finest, merges[-1] is coarsest.
    # n_remaining starts at n_base, decreases by 1 each merge.
    # At merge index k: n_remaining = n_base - k.

    # Cut sizes are ordered coarse→fine: cut_sizes[0] is smallest (most merged)
    # We need to find the merge index where n_remaining == cut_size.
    # n_remaining after k merges = n_base - k
    # So k = n_base - cut_size → merge index k-1 is the last merge before that cut.

    # Sort cuts descending (finest first to process in merge order)
    cuts_with_idx = sorted(enumerate(cut_sizes), key=lambda x: x[1], reverse=True)

    # We need a Union-Find to track roots
    parent = list(range(len(merges) * 2 + n_base + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Initial: each base label is its own root
    # new_id nodes from merges need parent entries too
    for _, _, _, new_id in merges:
        while len(parent) <= new_id:
            parent.append(len(parent))

    # Apply merges and snapshot at each cut point
    snapshots: dict[int, np.ndarray] = {}  # cut_size → label_map

    merge_idx = 0
    n_remaining = n_base
    # We'll apply merges and take snapshots at each cut
    # Process in order of merge (finest-to-coarsest = many-regions to few-regions)
    # Cuts are sorted descending (most regions first = finest)
    cut_queue = list(cuts_with_idx)  # (original_idx, cut_size), sorted finest first

    # Take initial snapshot if needed (before any merges)
    while cut_queue and cut_queue[0][1] >= n_remaining:
        orig_idx, cs = cut_queue.pop(0)
        snap = _snapshot_labels(base_labels, parent, n_base, H, W)
        snapshots[cs] = snap

    for a, b, cost, new_id in merges:
        # Apply merge
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[ra] = new_id
            parent[rb] = new_id
            parent[new_id] = new_id
            n_remaining -= 1

        # Check if any cut size is now satisfied
        while cut_queue and cut_queue[0][1] >= n_remaining:
            orig_idx, cs = cut_queue.pop(0)
            snap = _snapshot_labels(base_labels, parent, n_base, H, W)
            snapshots[cs] = snap

    # Any remaining cuts (too fine — use the base labels)
    while cut_queue:
        orig_idx, cs = cut_queue.pop(0)
        if cs not in snapshots:
            snapshots[cs] = _snapshot_labels(base_labels, parent, n_base, H, W)

    # Build result dict in level order l1..l5
    result: dict[str, np.ndarray] = {}
    for lvl_idx, cut_size in enumerate(cut_sizes):
        scale_name = f"l{lvl_idx + 1}"
        lm = snapshots.get(cut_size)
        if lm is None:
            # Fall back to the finest snapshot we have
            lm = _snapshot_labels(base_labels, parent, n_base, H, W)
        result[scale_name] = lm

    return result


def _snapshot_labels(
    base_labels: np.ndarray,
    parent: list[int],
    n_base: int,
    H: int,
    W: int,
) -> np.ndarray:
    """Map base_labels → current root IDs as a (H,W) int32 array."""
    # Build LUT for base labels
    max_base = int(base_labels.max()) + 1
    lut = np.arange(max(max_base, n_base + 1), dtype=np.int32)
    for i in range(min(n_base, max_base)):
        # Find root of base label i
        x = i
        while x < len(parent) and parent[x] != x:
            parent[x] = parent[min(parent[x], len(parent) - 1)]
            x = parent[x]
        lut[i] = x

    out = lut[base_labels.clip(0, max_base - 1)]
    # Re-index to compact 0-based labels
    uniq = np.unique(out)
    remap2 = np.zeros(int(out.max()) + 1, dtype=np.int32)
    for new_i, old_v in enumerate(uniq):
        remap2[old_v] = new_i
    return remap2[out]


def _trivial_fallback(
    cache: ImageCache,
    n_value_zones: int,
    value_colour_families: dict,
) -> tuple[dict[str, np.ndarray], list[Region]]:
    """Return a single-region result (whole image) when merge tree fails."""
    H, W = cache.H, cache.W
    zone_map, zones = compute_value_zones(cache, n_value_zones)
    lm = np.zeros((H, W), dtype=np.int32)
    label_maps = {f"l{i}": lm for i in range(1, 6)}
    mean_lab = cache.lab.reshape(-1, 3).mean(axis=0)
    mean_rgb_f = skcolor.lab2rgb(mean_lab.reshape(1, 1, 3))[0, 0] * 255
    mean_rgb = tuple(int(np.clip(v, 0, 255)) for v in mean_rgb_f)
    region = Region(
        id=0,
        source_label=0,
        scale="l3",
        parent_id=None,
        level=0,
        area=H * W,
        centroid=(W / 2, H / 2),
        bbox=(0, 0, W, H),
        mean_lab=(float(mean_lab[0]), float(mean_lab[1]), float(mean_lab[2])),
        mean_rgb=mean_rgb,
        value_zone=0,
        colour_family_id=0,
        importance=1.0,
        texture_score=0.0,
    )
    return label_maps, [region]


def _nearest_colour_family(mean_lab: np.ndarray, families: dict) -> int:
    if not families:
        return 0
    centres = families.get("centres_lab")
    id_to_rank = families.get("cluster_id_to_rank", {})
    if centres is None or len(centres) == 0:
        return 0
    dists = np.linalg.norm(centres - mean_lab, axis=1)
    raw_idx = int(dists.argmin())
    return id_to_rank.get(raw_idx, raw_idx)


def _adapt_segments(base: int, W: int, H: int) -> int:
    """Scale segment count to image resolution (normalised to 800×600 reference)."""
    area = W * H
    ref = 800 * 600
    factor = area / ref
    return max(20, int(base * factor ** 0.5))
