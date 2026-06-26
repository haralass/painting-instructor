from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sklearn.cluster import MiniBatchKMeans
from skimage import color as skcolor


def _font(size: int = 7) -> ImageFont.FreeTypeFont:
    for p in [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def process(img: Image.Image, n_colors: int = 18, grid: int = 40) -> Image.Image:
    """Convert photo to numbered color-grid activity page."""
    W, H = img.size
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    lab = skcolor.rgb2lab(arr)
    cell_w, cell_h = W // grid, H // grid

    km = MiniBatchKMeans(n_clusters=n_colors, n_init=5, random_state=42)
    km.fit(lab.reshape(-1, 3))
    labels = km.labels_.reshape(H, W)
    palette = (skcolor.lab2rgb(km.cluster_centers_.reshape(1, -1, 3))[0] * 255).astype(np.uint8)

    out = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(out)
    fn = _font(7)

    for gy in range(H // cell_h):
        for gx in range(W // cell_w):
            x0, y0 = gx * cell_w, gy * cell_h
            x1, y1 = x0 + cell_w, y0 + cell_h
            cell_lab = lab[y0:y1, x0:x1].reshape(-1, 3)
            dists = np.linalg.norm(
                cell_lab[:, None, :] - km.cluster_centers_[None, :, :], axis=2
            )
            dom = np.bincount(dists.argmin(axis=1), minlength=n_colors).argmax()
            r, g, b = palette[dom].tolist()
            fill = tuple(int(c + (255 - c) * 0.5) for c in (r, g, b))
            out.paste(Image.new("RGB", (cell_w, cell_h), fill), (x0, y0))
            dr.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(160, 160, 160), width=1)
            dr.text((x0 + 2, y0 + 1), str(dom + 1), fill=(40, 40, 40), font=fn)

    return out
