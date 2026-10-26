"""A contact sheet: every listing photo as a numbered thumbnail in one image.

The vision model takes at most a few dozen images per call, and a review that
compares finishes across the whole listing needs all of them at once. One sheet
of 50 small thumbnails is about 3,000 image tokens, and the model can still tell
hardwood from tile and white cabinets from wood.
"""

from __future__ import annotations

import base64
import io
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFont

THUMB_W = 240
COLUMNS = 8
LABEL_H = 26
TIMEOUT = 15.0


def fetch(url: str) -> Image.Image | None:
    try:
        r = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except (httpx.HTTPError, OSError):
        return None


def fetch_all(urls: list[str]) -> list[Image.Image | None]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fetch, urls))


def contact_sheet(urls: list[str], *, columns: int = COLUMNS, thumb_w: int = THUMB_W) -> Image.Image:
    """The photos numbered 1..n, left to right then down; a grey box stands in for a photo that did not load."""
    return sheet_from(fetch_all(urls), columns=columns, thumb_w=thumb_w)


def sheet_from(images: list[Image.Image | None], *, columns: int = COLUMNS, thumb_w: int = THUMB_W) -> Image.Image:
    images = [img.copy() if img is not None else None for img in images]
    thumb_h = round(thumb_w * 2 / 3)
    rows = max(1, -(-len(images) // columns))
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + LABEL_H)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    for n, img in enumerate(images):
        x, y = (n % columns) * thumb_w, (n // columns) * (thumb_h + LABEL_H)
        if img is None:
            draw.rectangle((x, y + LABEL_H, x + thumb_w - 1, y + LABEL_H + thumb_h - 1), fill="#cccccc")
        else:
            img.thumbnail((thumb_w, thumb_h))
            sheet.paste(img, (x + (thumb_w - img.width) // 2, y + LABEL_H + (thumb_h - img.height) // 2))
        draw.text((x + 6, y + 3), f"#{n + 1}", fill="black", font=font)
    return sheet


DRAWING_LIGHT_SHARE = 0.6


def light_share(img: Image.Image) -> float:
    """The share of pixels that are light and nearly grey: white paper with ink scores near 1, a photo well below 0.5."""
    small = img.convert("RGB")
    small.thumbnail((160, 160))
    hsv = np.asarray(small.convert("HSV"))
    if hsv.size == 0:
        return 0.0
    light = (hsv[:, :, 1] < 48) & (hsv[:, :, 2] > 190)
    return float(light.mean())


def looks_like_drawing(url: str) -> bool | None:
    """True for a plan or survey on a page, False for a photograph, None when the image did not load."""
    img = fetch(url)
    if img is None:
        return None
    return light_share(img) >= DRAWING_LIGHT_SHARE


def finish_histogram(img: Image.Image) -> np.ndarray:
    """A colour histogram of the lower 60% of the photo, where the floor and the lower walls are.

    Photos of one floor share finishes, so this is what "looks like the same floor" means
    in numbers: hardwood bedrooms sit near each other, the patterned-tile basement sits
    near the basement kitchen. HSV, 8 x 4 x 4 bins, normalized.
    """
    small = img.convert("RGB")
    small.thumbnail((128, 128))
    a = np.asarray(small.convert("HSV")).astype(float)
    lower = a[int(a.shape[0] * 0.4) :, :, :]
    h, _ = np.histogramdd(lower.reshape(-1, 3), bins=(8, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    h = h.flatten()
    return h / h.sum() if h.sum() else h


def chi2(a: np.ndarray, b: np.ndarray) -> float:
    return float(0.5 * np.sum((a - b) ** 2 / (a + b + 1e-9)))


PHOTO_MAX_PX = 1280


def photo_data_url(img: Image.Image, max_px: int = PHOTO_MAX_PX) -> str:
    """The photo as JPEG bytes in a data URL, at most `max_px` on the long side.

    The model gets the bytes, not the URL: a host that fetches the URL itself may
    serve a stale copy of the photo from its cache (the first photo of a listing
    that changed its photos came back as the old survey drawing), and the bytes are
    what the thumbnail and the drawing check were measured on.
    """
    img = img.convert("RGB")
    img.thumbnail((max_px, max_px))
    return data_url(img, quality=85)


def data_url(sheet: Image.Image, quality: int = 80) -> str:
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
