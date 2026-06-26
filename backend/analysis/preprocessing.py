from __future__ import annotations
import cv2
import numpy as np
from PIL import Image
from skimage import color as skcolor


class ImageCache:
    """
    Holds all derived representations of one image so each is computed once.
    Pass this object through the analysis pipeline instead of re-deriving.
    """

    def __init__(self, img: Image.Image) -> None:
        self.img    = img
        self.W, self.H = img.size

        self.rgb    = np.array(img.convert("RGB"), dtype=np.uint8)
        self.bgr    = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2BGR)

        rgb_f       = self.rgb.astype(np.float32) / 255.0
        self.lab    = skcolor.rgb2lab(rgb_f)           # (H, W, 3) float64
        self.L      = self.lab[:, :, 0]               # L* in [0, 100]
        self.a      = self.lab[:, :, 1]               # a* green−red
        self.b      = self.lab[:, :, 2]               # b* blue−yellow

        self.gray   = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2GRAY)
        self.gray_f = self.gray.astype(np.float32) / 255.0

        # Gradient magnitude (Sobel) — used by edge classification
        sx          = cv2.Sobel(self.gray, cv2.CV_64F, 1, 0, ksize=3)
        sy          = cv2.Sobel(self.gray, cv2.CV_64F, 0, 1, ksize=3)
        self.grad   = np.hypot(sx, sy).astype(np.float32)

        # Bilateral-smoothed for segmentation (computed lazily)
        self._smooth: np.ndarray | None = None

    @property
    def smooth(self) -> np.ndarray:
        """
        Edge-preserving bilateral-smoothed RGB.

        For large images (>= 600px side), filtering is applied at a capped
        working resolution and scaled back — this keeps runtime O(P_cap) rather
        than O(P_full) while preserving edge quality.
        """
        if self._smooth is None:
            _SMOOTH_CAP = 600   # max side for bilateral filtering
            H, W = self.H, self.W
            bgr = self.bgr

            # Downscale if needed
            scale = 1.0
            max_side = max(H, W)
            if max_side > _SMOOTH_CAP:
                scale = _SMOOTH_CAP / max_side
                small_w = max(1, int(W * scale))
                small_h = max(1, int(H * scale))
                bgr = cv2.resize(bgr, (small_w, small_h), interpolation=cv2.INTER_AREA)

            lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
            for _ in range(3):
                lab = cv2.bilateralFilter(lab, d=7, sigmaColor=60, sigmaSpace=60)
            bgr_smooth = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

            # Upscale back to original resolution if we downscaled
            if scale < 1.0:
                bgr_smooth = cv2.resize(bgr_smooth, (W, H), interpolation=cv2.INTER_LINEAR)

            self._smooth = cv2.cvtColor(bgr_smooth, cv2.COLOR_BGR2RGB)
        return self._smooth


def prepare(img: Image.Image) -> ImageCache:
    return ImageCache(img)
