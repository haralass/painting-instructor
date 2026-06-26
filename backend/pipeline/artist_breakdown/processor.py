from __future__ import annotations
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sklearn.cluster import MiniBatchKMeans
from skimage import color as skcolor

from ...utils.fonts import get_font as _font


def notan(img: Image.Image, zones: int = 3) -> Image.Image:
    """
    Notan value study — the first thing every artist does.
    Uses LAB L* channel (perceptual luminance) for accurate zone boundaries.
    zones=2: shadow / light
    zones=3: shadow / midtone / light  (standard)
    zones=5: shadow / low-mid / midtone / high-mid / highlight
    zones=7: seven evenly-spaced perceptual zones

    Thresholds are adaptive: derived from the image histogram so that
    each zone contains roughly equal visual area.
    """
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    L   = skcolor.rgb2lab(arr)[:, :, 0]   # L* in [0, 100]

    # Adaptive thresholds: equal-quantile splits on the L histogram
    flat = L.ravel()
    quantiles = np.linspace(0, 100, zones + 1)
    cuts = [float(np.percentile(flat, q)) for q in quantiles]
    # Ensure strict ordering and clamp to [0, 100]
    cuts[0]  = 0.0
    cuts[-1] = 100.0

    # Perceptual grey tones from shadow to highlight
    gray_values = [int(round(15 + 225 * i / (zones - 1))) for i in range(zones)]

    H, W = L.shape
    out  = np.zeros((H, W, 3), dtype=np.uint8)
    for i, gv in enumerate(gray_values):
        lo, hi = cuts[i], cuts[i + 1]
        mask = (L >= lo) & (L < hi) if i < zones - 1 else (L >= lo)
        out[mask] = (gv, gv, gv)

    return Image.fromarray(out)


def color_palette(img: Image.Image, n_colors: int = 32) -> Image.Image:
    """Dominant palette sorted by area — LAB K-means++, hex + percentage labels."""
    arr = np.array(img.convert("RGB").resize((300, 300)), dtype=np.float32) / 255.0
    lab = skcolor.rgb2lab(arr).reshape(-1, 3)
    km  = MiniBatchKMeans(n_clusters=n_colors, init='k-means++', n_init=8, random_state=42).fit(lab)
    pal = (skcolor.lab2rgb(km.cluster_centers_.reshape(1, -1, 3))[0] * 255).astype(np.uint8)
    cnt = np.bincount(km.labels_, minlength=n_colors)
    order = np.argsort(-cnt)
    pct   = cnt / cnt.sum() * 100

    sw, sh = 48, 72
    img_w  = sw * n_colors
    out    = Image.new("RGB", (img_w, sh + 28), (245, 245, 245))
    dr     = ImageDraw.Draw(out)
    fn     = _font(7)

    for rank, idx in enumerate(order):
        r, g, b = pal[idx].tolist()
        x0 = rank * sw
        dr.rectangle([x0, 0, x0 + sw - 1, sh - 1], fill=(r, g, b))
        dr.text((x0 + 2, sh + 2),  f"#{r:02X}{g:02X}{b:02X}", fill=(30, 30, 30), font=fn)
        dr.text((x0 + 2, sh + 13), f"{pct[idx]:.1f}%",        fill=(80, 80, 80), font=fn)

    return out


def color_temperature(img: Image.Image) -> Image.Image:
    """
    Per-pixel colour temperature approximation.

    Uses LAB b* channel (index 2, blue-yellow axis) combined with a*
    (index 1, green-red axis) and luminance to classify pixels:
      warm  → b* > threshold  (yellow/orange biased)
      cool  → b* < -threshold (blue biased)
      neutral → low chroma (|a*| and |b*| small)

    This is an approximation, not absolute scientific classification —
    labelled as "Colour temperature approximation" accordingly.
    """
    arr     = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    lab     = skcolor.rgb2lab(arr)
    # LAB channels: 0=L*, 1=a* (green−red), 2=b* (blue−yellow)
    a_ch    = lab[:, :, 1]   # a*: negative=green, positive=red
    b_ch    = lab[:, :, 2]   # b*: negative=blue,  positive=yellow/warm
    chroma  = np.hypot(a_ch, b_ch)

    gray    = skcolor.rgb2gray(arr)

    H, W    = b_ch.shape
    overlay = np.zeros((H, W, 3), dtype=np.float32)
    warm_c  = np.array([1.0, 0.42, 0.0])    # orange
    cool_c  = np.array([0.0, 0.47, 1.0])    # blue
    neut_c  = np.array([0.75, 0.75, 0.75])

    # Low chroma → neutral regardless of hue angle
    neutral_threshold = 8.0   # LAB chroma units
    warm_threshold    = 4.0   # b* units above zero

    neut_m = chroma < neutral_threshold
    warm_m = ~neut_m & (b_ch > warm_threshold)
    cool_m = ~neut_m & ~warm_m

    overlay[warm_m] = warm_c
    overlay[cool_m] = cool_c
    overlay[neut_m] = neut_c

    gray3   = np.stack([gray] * 3, axis=-1)
    blended = np.clip(gray3 * 0.45 + overlay * 0.55, 0, 1)

    # legend bar
    leg_h  = 30
    legend = np.zeros((leg_h, W, 3), dtype=np.uint8)
    for px in range(W):
        t = px / W * 2 - 1   # −1 to +1
        c = cool_c if t < 0 else warm_c
        legend[:, px] = (abs(t) * c + (1 - abs(t)) * np.array([0.75] * 3)) * 255

    leg_img = Image.fromarray(legend)
    dr_leg  = ImageDraw.Draw(leg_img)
    fn_leg  = _font(9)
    dr_leg.text((4, 9),        "COOL (blue shadows)", fill=(255, 255, 255), font=fn_leg)
    dr_leg.text((W - 135, 9),  "WARM (yellow/orange light)", fill=(255, 255, 255), font=fn_leg)

    title_h  = 22
    title_bar = np.full((title_h, W, 3), 30, dtype=np.uint8)
    title_img = Image.fromarray(title_bar)
    dr_title  = ImageDraw.Draw(title_img)
    dr_title.text((4, 4), "Colour temperature approximation (LAB b* + chroma)", fill=(200, 200, 200), font=_font(8))

    main = Image.fromarray((blended * 255).astype(np.uint8))
    return Image.fromarray(np.vstack([np.array(title_img), np.array(main), np.array(leg_img)]))


def light_direction(img: Image.Image) -> Image.Image:
    """
    Light source direction via Sobel gradient orientation histogram.
    Overlay: 5 Gurney modeling zones color-coded on greyscale.
      - Highlight (white)
      - Halftone (light grey)
      - Core shadow (dark grey)
      - Reflected light (medium grey)
      - Cast shadow (near black)
    + Arrow indicating dominant light direction.
    """
    arr  = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    gray = (skcolor.rgb2gray(arr) * 255).astype(np.uint8)

    # Sobel gradient
    sx   = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
    sy   = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
    mag  = np.hypot(sx, sy)
    ang  = np.degrees(np.arctan2(-sy, sx)) % 360   # 0=right, 90=up, 180=left, 270=down

    # dominant light direction (weighted by gradient magnitude)
    hist, edges = np.histogram(ang, bins=36, range=(0, 360), weights=mag)
    dom_angle   = float(edges[hist.argmax()] + 5)   # bin center

    # 5-zone posterization on L-channel
    L    = skcolor.rgb2lab(arr)[:, :, 0]
    zone = np.zeros(L.shape, dtype=np.uint8)
    zone[(L >= 80)]              = 0   # highlight
    zone[(L >= 55) & (L < 80)]  = 1   # halftone
    zone[(L >= 35) & (L < 55)]  = 2   # core shadow
    zone[(L >= 15) & (L < 35)]  = 3   # reflected light
    zone[L < 15]                = 4   # cast shadow

    zone_colors = [
        (240, 240, 240),   # highlight
        (180, 180, 180),   # halftone
        ( 70,  70,  70),   # core shadow
        (110, 110, 110),   # reflected light
        ( 20,  20,  20),   # cast shadow
    ]
    out_arr = np.zeros((*L.shape, 3), dtype=np.uint8)
    for i, c in enumerate(zone_colors):
        out_arr[zone == i] = c

    out = Image.fromarray(out_arr)
    dr  = ImageDraw.Draw(out)
    fn  = _font(10)
    W, H = out.size

    # draw light direction arrow
    cx, cy = W // 2, H // 2
    r  = min(W, H) // 8
    rad = np.radians(dom_angle)
    ex, ey = int(cx + r * np.cos(rad)), int(cy - r * np.sin(rad))
    dr.line([(cx, cy), (ex, ey)], fill=(255, 200, 0), width=3)
    dr.ellipse([ex-5, ey-5, ex+5, ey+5], fill=(255, 200, 0))
    dr.text((4, 4), f"Light: {dom_angle:.0f}°", fill=(255, 200, 0), font=fn)

    labels = ["Highlight", "Halftone", "Core Shadow", "Reflected Light", "Cast Shadow"]
    for i, (label, color) in enumerate(zip(labels, zone_colors)):
        tc = (20, 20, 20) if max(color) > 140 else (220, 220, 220)
        dr.text((4, 20 + i * 18), label, fill=tc, font=fn)

    return out


def tonal_map(img: Image.Image) -> Image.Image:
    """Convenience wrapper — 3-zone Notan for pipeline compatibility."""
    return notan(img, zones=3)
