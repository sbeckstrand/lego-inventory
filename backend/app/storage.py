"""Asset storage for set images.

Writes under ``settings.assets_dir`` (a local bind mount in dev, an NFS-backed
volume in k8s). Returns paths relative to that dir so they can be served at
``/assets/...`` regardless of where the mount actually lives.

Images are normalised to a transparent PNG and downscaled. Rebrickable serves
some set images as opaque JPEGs (solid white background) and others as
transparent PNGs; to make every set sit on the same background in the UI, the
near-uniform border background of opaque images is made transparent.
"""
from __future__ import annotations

import io
import os

import httpx
from PIL import Image, ImageChops, ImageDraw

from .config import get_settings

settings = get_settings()

_MAX_DIM = 800
# How far a pixel's colour can sit from the corner background and still be
# flood-filled away. Higher = more aggressive background removal.
_BG_THRESHOLD = 36


def _sets_dir() -> str:
    path = os.path.join(settings.assets_dir, "sets")
    os.makedirs(path, exist_ok=True)
    return path


def _has_transparency(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA"):
        return im.getchannel("A").getextrema()[0] < 255
    return im.mode == "P" and "transparency" in im.info


def _strip_background(im: Image.Image) -> Image.Image:
    """Make the border-connected, near-uniform background transparent.

    Flood-fills inward from each corner, so interior regions that happen to be
    the background colour (e.g. white bricks) are left opaque.
    """
    im = im.convert("RGBA")
    rgb = im.convert("RGB")
    w, h = rgb.size
    marker = (255, 0, 255)
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(rgb, corner, marker, thresh=_BG_THRESHOLD)
    # Pixels now exactly equal to the marker are background -> alpha 0.
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, marker))
    alpha = diff.convert("L").point(lambda p: 0 if p == 0 else 255)
    im.putalpha(alpha)
    return im


def _normalize(content: bytes) -> bytes:
    im = Image.open(io.BytesIO(content))
    im.thumbnail((_MAX_DIM, _MAX_DIM), Image.Resampling.LANCZOS)
    im = im.convert("RGBA") if _has_transparency(im) else _strip_background(im)
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def download_set_image(set_num: str, image_url: str | None) -> str | None:
    """Download, normalise to a transparent PNG, and cache a set's image.

    Returns the path relative to the assets dir, or None on any failure
    (image caching is best-effort).
    """
    if not image_url:
        return None

    filename = f"{set_num}.png"
    dest = os.path.join(_sets_dir(), filename)
    rel_path = os.path.join("sets", filename)

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
        png = _normalize(resp.content)
        with open(dest, "wb") as fh:
            fh.write(png)
    except Exception:  # noqa: BLE001 — image caching is best-effort
        return None

    return rel_path
