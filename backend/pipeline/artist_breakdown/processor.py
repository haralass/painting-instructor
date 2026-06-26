from __future__ import annotations
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sklearn.cluster import MiniBatchKMeans
from skimage import color as skcolor


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in ["/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Arial.ttf"]:
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def notan(img: Image.Image, zones: int = 3) -> Image.Image:
    """
    Notan value study — the first thing every artist does.
    Uses LAB L-channel (perceptual luminance) for accurate zone boundaries.
    zones=2: shadow / light  (pure Notan)
    zones=3: shadow / midtone / light  (standard)
    zones=5: shadow / low-mid / midtone / high-mid / highlight
    """
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    L   = skcolor.rgb2lab(arr)[:, :, 0]   # 0-100

    cuts_2 = [50]
    cuts_3 = [33, 67]
    cuts_5 = [20, 40, 60, 80]
    cuts   = {2: cuts_2, 3: cuts_3, 5: cuts_5}.get(zones, cuts_3)

    values_5 = [
        (15,  15,  15),   # shadow
        (60,  60,  60),   # low midtone
        (120, 120, 120),  # midtone
        (185, 185, 185),  # high midtone
        (240, 240, 240),  # highlight
    ]
    # pick evenly-spaced values for requested zone count
    step = 5 // zones
    tones = [values_5[i*step] for i in range(zones)]

    H, W = L.shape
    out  = np.zeros((H, W, 3), dtype=np.uint8)
    thresholds = [0.0] + [c for c in cuts] + [100.0]
    for i, tone in enumerate(tones):
        lo, hi = thresholds[i], thresholds[i+1]
        out[(L >= lo) & (L < hi)] = tone

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
    Per-pixel warm/cool map using LAB b-channel (Gurney method).
    b > 0  → warm (yellow-orange light)
    b < 0  → cool (blue shadow)
    b ≈ 0  → neutral
    Overlay warm=orange, cool=blue at 55% opacity over greyscale.
    """
    arr     = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    lab     = skcolor.rgb2lab(arr)
    b_ch    = lab[:, :, 1]          # b-channel: warm+ cool-
    gray    = skcolor.rgb2gray(arr) # perceptual grey

    H, W    = b_ch.shape
    overlay = np.zeros((H, W, 3), dtype=np.float32)
    warm_c  = np.array([1.0, 0.42, 0.0])   # orange
    cool_c  = np.array([0.0, 0.47, 1.0])   # blue
    neut_c  = np.array([0.75, 0.75, 0.75])

    t_norm  = np.clip(b_ch / 60.0, -1.0, 1.0)   # -1=cool, +1=warm
    warm_m  = t_norm > 0.1
    cool_m  = t_norm < -0.1
    neut_m  = ~warm_m & ~cool_m

    overlay[warm_m] = warm_c
    overlay[cool_m] = cool_c
    overlay[neut_m] = neut_c

    gray3   = np.stack([gray]*3, axis=-1)
    blended = np.clip(gray3 * 0.45 + overlay * 0.55, 0, 1)

    # legend bar
    leg_h  = 30
    legend = np.zeros((leg_h, W, 3), dtype=np.uint8)
    for px in range(W):
        t = px / W * 2 - 1   # -1 to +1
        c = cool_c if t < 0 else warm_c
        legend[:, px] = (abs(t) * c + (1-abs(t)) * np.array([0.75]*3)) * 255

    leg_img = Image.fromarray(legend)
    dr_leg  = ImageDraw.Draw(leg_img)
    fn_leg  = _font(9)
    dr_leg.text((4, 9),      "COOL (shadows)", fill=(255,255,255), font=fn_leg)
    dr_leg.text((W - 115, 9), "WARM (lights)", fill=(255,255,255), font=fn_leg)

    main = Image.fromarray((blended * 255).astype(np.uint8))
    return Image.fromarray(np.vstack([np.array(main), np.array(leg_img)]))


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
