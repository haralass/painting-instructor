from __future__ import annotations
import cv2
import numpy as np
import pywt
from PIL import Image, ImageDraw, ImageFont
from skimage import segmentation, graph as sk_graph, measure, color as skcolor
from sklearn.cluster import MiniBatchKMeans
from scipy import ndimage
from scipy.ndimage import distance_transform_edt
from shapely.geometry import Point, MultiPoint


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in ["/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Arial.ttf"]:
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def _bilateral_smooth(img_bgr: np.ndarray, passes: int = 4) -> np.ndarray:
    """
    Iterative bilateral filter in LAB space.
    Flattens color noise within zones, hardens inter-zone edges.
    d=9 avoids halos; sigmaColor=75 is sweet spot for portraits.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    for _ in range(passes):
        lab = cv2.bilateralFilter(lab, d=9, sigmaColor=75, sigmaSpace=75)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _face_zone_edges(img_rgb: np.ndarray) -> np.ndarray | None:
    """
    BiSeNet face parsing via facexlib — returns per-pixel zone label map.
    Zones: 0=bg, 1=skin, 2=l_brow, 3=r_brow, 4=l_eye, 5=r_eye,
           6=glasses, 7=l_ear, 8=r_ear, 9=earring, 10=nose,
           11=mouth, 12=u_lip, 13=l_lip, 14=neck, 15=neck_l,
           16=cloth, 17=hair, 18=hat
    Returns a (H,W) uint8 zone map, or None if facexlib unavailable.
    """
    try:
        import torch
        from facexlib.parsing import init_parsing_model
        H, W = img_rgb.shape[:2]
        model = init_parsing_model(model_name='bisenet', device='cpu')
        t = torch.from_numpy(img_rgb).permute(2, 0, 1).float().unsqueeze(0) / 255.0
        with torch.no_grad():
            raw = model(t)
        # facexlib may return (tensor,) or just tensor; unwrap to (C, H, W)
        logits = raw[0] if isinstance(raw, (list, tuple)) else raw
        if logits.dim() == 4:
            logits = logits[0]   # (1, C, H, W) → (C, H, W)
        zone = logits.argmax(0).cpu().numpy().astype(np.uint8)
        if zone.shape != (H, W):
            zone = cv2.resize(zone, (W, H), interpolation=cv2.INTER_NEAREST)
        return zone
    except Exception:
        return None


def _pole_of_inaccessibility(mask: np.ndarray) -> tuple[int, int]:
    """Distance-transform pole of inaccessibility — deepest interior point."""
    dt = distance_transform_edt(mask)
    idx = np.unravel_index(dt.argmax(), dt.shape)
    return int(idx[1]), int(idx[0])   # x, y


def _haar_smooth_contour(pts: np.ndarray, level: int = 2) -> np.ndarray:
    if len(pts) < 8:
        return pts
    x, y = pts[:, 0].astype(float), pts[:, 1].astype(float)
    for arr in (x, y):
        coeffs = pywt.wavedec(arr, "haar", level=level)
        for i in range(1, len(coeffs)):
            coeffs[i] = np.zeros_like(coeffs[i])
        arr[:] = pywt.waverec(coeffs, "haar")[: len(arr)]
    return np.stack([x, y], axis=1)


def process(
    img: Image.Image,
    n_colors: int = 32,
    min_region_px: int = 80,
    use_face_parsing: bool = True,
) -> Image.Image:
    """
    Photo → paint-by-numbers page (professional grade).

    Pipeline:
    1. Bilateral filter ×4 in LAB  — flatten noise, harden zone edges
    2. SLIC n_segments=2000         — fine enough to preserve eyebrows/lips
    3. RAG cut_threshold            — binary-search to ~n_colors regions
    4. BiSeNet face parsing         — freeze cross-zone edges for face features
    5. LAB K-means++ (32 colors)    — perceptually balanced palette
    6. Absorb micro-regions         — expand_labels
    7. Haar-smoothed cv2 contours   — crisp printable boundaries
    8. Pole-of-inaccessibility label placement
    """
    W, H = img.size
    img_bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    # 1. edge-preserving smoothing
    smooth_bgr = _bilateral_smooth(img_bgr)
    smooth_rgb = cv2.cvtColor(smooth_bgr, cv2.COLOR_BGR2RGB)

    # 2. SLIC — 2000 segments to preserve fine features
    labels_slic = segmentation.slic(
        smooth_rgb,
        n_segments=2000,
        compactness=15,
        sigma=1,
        start_label=1,
        enforce_connectivity=True,
        convert2lab=True,
    )

    # 3. face parsing — freeze cross-zone edges
    zone_map = _face_zone_edges(smooth_rgb) if use_face_parsing else None

    # 4. RAG merge with binary search toward n_colors
    lo, hi = 2.0, 100.0
    best_labels = labels_slic
    for _ in range(25):
        mid = (lo + hi) / 2.0
        g   = sk_graph.rag_mean_color(smooth_rgb, labels_slic)
        if zone_map is not None:
            # penalise edges that cross face-zone boundaries (weight → very high)
            for edge in g.edges():
                n1, n2 = edge
                mask1  = labels_slic == n1
                mask2  = labels_slic == n2
                z1 = int(np.bincount(zone_map[mask1].ravel()).argmax())
                z2 = int(np.bincount(zone_map[mask2].ravel()).argmax())
                if z1 != z2 and z1 != 0 and z2 != 0:
                    g[n1][n2]['weight'] = 1e6
        merged = sk_graph.cut_threshold(labels_slic, g, thresh=mid)
        n_reg  = len(np.unique(merged))
        if n_reg > n_colors:
            lo = mid
        else:
            hi = mid
            best_labels = merged

    # 5. LAB K-means on region mean colors → palette
    img_lab = skcolor.rgb2lab(smooth_rgb.astype(np.float32) / 255.0)
    regions = np.unique(best_labels); regions = regions[regions > 0]
    mean_lab = np.array([img_lab[best_labels == r].mean(0) for r in regions])
    km = MiniBatchKMeans(
        n_clusters=min(n_colors, len(regions)),
        init='k-means++', n_init=10, random_state=42
    ).fit(mean_lab)
    palette_rgb = (skcolor.lab2rgb(km.cluster_centers_.reshape(1, -1, 3))[0] * 255).astype(np.uint8)

    color_map = np.zeros((H, W), dtype=np.int32)
    for i, r in enumerate(regions):
        color_map[best_labels == r] = int(km.labels_[i]) + 1

    # 6. absorb micro-regions
    props = measure.regionprops(color_map)
    small = {p.label for p in props if p.area < min_region_px}
    if small:
        tmp = color_map.copy(); tmp[np.isin(tmp, list(small))] = 0
        color_map = segmentation.expand_labels(tmp, distance=60)

    # 7. render tinted regions + Haar contours
    out = Image.new("RGB", (W, H), "white")
    arr = np.array(out)
    for ci in range(1, n_colors + 1):
        mask = color_map == ci
        if not mask.any(): continue
        r, g, b = palette_rgb[ci - 1].tolist()
        arr[mask] = [int(c + (255-c)*0.5) for c in (r, g, b)]
    out = Image.fromarray(arr)
    dr  = ImageDraw.Draw(out)
    fn  = _font(9)
    kern = np.ones((3, 3), np.uint8)

    for ci in range(1, n_colors + 1):
        mask = (color_map == ci).astype(np.uint8) * 255
        if not mask.any(): continue
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for cnt in contours:
            pts = cnt.reshape(-1, 2).astype(float)
            if len(pts) < 6: continue
            step = max(1, len(pts) // 400)
            pts  = _haar_smooth_contour(pts[::step], level=2)
            pl   = [(int(p[0]), int(p[1])) for p in pts]
            if len(pl) > 1:
                dr.line(pl + [pl[0]], fill=(55, 55, 55), width=1)

    # 8. pole-of-inaccessibility label placement
    for ci in range(1, n_colors + 1):
        mask = (color_map == ci)
        if not mask.any(): continue
        cx, cy = _pole_of_inaccessibility(mask)
        r, g, b = palette_rgb[ci - 1].tolist()
        lum = 0.299*r + 0.587*g + 0.114*b
        tc  = (20, 20, 20) if lum > 140 else (240, 240, 240)
        dr.text((cx - 5, cy - 5), str(ci), fill=tc, font=fn)

    return out
