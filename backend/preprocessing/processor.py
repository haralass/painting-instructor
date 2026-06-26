from __future__ import annotations
from pathlib import Path
from PIL import Image


def load_image(path: str | Path, max_side: int = 1200) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        s = max_side / max(w, h)
        img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
    return img


def quality_check(img: Image.Image, max_brisque: float = 55.0) -> tuple[bool, float]:
    """
    BRISQUE no-reference quality score via pyiqa.
    Returns (passes, score). Lower score = better quality.
    """
    try:
        import pyiqa
        import torch
        metric = pyiqa.create_metric("brisque")
        import numpy as np
        from torchvision import transforms
        t = transforms.ToTensor()(img).unsqueeze(0)
        score = float(metric(t).item())
        return score <= max_brisque, score
    except ImportError:
        return True, 0.0


def remove_background(img: Image.Image) -> Image.Image:
    """
    Background removal using BiRefNet (MIT license) via rembg.
    Returns RGBA image with background removed.
    """
    try:
        from rembg import remove, new_session
        session = new_session("birefnet-portrait")
        return remove(img, session=session)
    except ImportError:
        return img
