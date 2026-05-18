"""Shared image filter: drop decorative / low-info images across backends.

The 6 heuristics originated in `pdf_to_md.py` and have been generalized so
docx / pptx / web / pdf can all share a single set of thresholds.

`page_size` (page width/height in any unit) and `render_size` (rendered
width/height in the same unit) are only available for PDF/PPT; pass None for
formats without a stable page concept (docx/web).
"""

from __future__ import annotations

import hashlib


# Default thresholds — chosen to filter logos, tracking pixels, decorative
# bars, and solid-color blocks while preserving content figures.
MIN_IMAGE_PIXELS = 100        # Minimum pixel dimension (width AND height)
MIN_IMAGE_AREA = 30000        # Minimum pixel area (~200x150)
MIN_IMAGE_BYTES = 2048        # Minimum image data size (2KB)
MIN_PAGE_RATIO = 0.05         # Minimum render size relative to page (5%)
MAX_ASPECT_RATIO = 12         # Maximum aspect ratio (decorative bars / separators)
MAX_LOW_INFO_BPP = 0.08       # Bytes-per-pixel threshold for low-info images
MAX_LOW_INFO_AREA = 500000    # Area threshold above which bpp filter is skipped


def _read_size_with_pillow(image_bytes: bytes) -> tuple[int, int] | None:
    """Return (width, height) by parsing the bytes with Pillow; None on failure."""
    try:
        from PIL import Image  # local import — Pillow is optional for some backends
        import io
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.size
    except Exception:
        return None


def should_keep_image_bytes(
    image_bytes: bytes,
    *,
    seen_hashes: set[str] | None = None,
) -> bool:
    """Filter from raw bytes only — width/height inferred via Pillow.

    Used by backends that don't have rendered size info (docx, html, epub, web).
    When Pillow is unavailable or the bytes can't be parsed, defaults to True
    (err on the side of keeping the image).
    """
    size = _read_size_with_pillow(image_bytes)
    if size is None:
        # Without dimensions we can still do the byte-size + dedup checks.
        if len(image_bytes) < MIN_IMAGE_BYTES:
            return False
        if seen_hashes is not None:
            img_hash = hashlib.md5(image_bytes).hexdigest()
            if img_hash in seen_hashes:
                return False
            seen_hashes.add(img_hash)
        return True
    width, height = size
    return should_keep_image(
        image_bytes,
        width,
        height,
        seen_hashes=seen_hashes,
    )


def should_keep_image(
    image_bytes: bytes,
    width: int,
    height: int,
    *,
    page_size: tuple[float, float] | None = None,
    render_size: tuple[float, float] | None = None,
    seen_hashes: set[str] | None = None,
) -> bool:
    """Return True if the image carries enough signal to be worth keeping.

    Args:
        image_bytes: Raw image payload (used for size, bpp, and dedup hashing).
        width: Pixel width.
        height: Pixel height.
        page_size: Optional (page_w, page_h) for page-relative-size filtering.
        render_size: Optional (render_w, render_h) in the same unit as page_size.
        seen_hashes: Optional set of already-seen MD5 hashes; mutated on hit.
    """
    if width < MIN_IMAGE_PIXELS or height < MIN_IMAGE_PIXELS:
        return False

    area = width * height
    if area < MIN_IMAGE_AREA:
        return False

    if len(image_bytes) < MIN_IMAGE_BYTES:
        return False

    # Deduplicate by content hash (repeated backgrounds, logos on every page)
    if seen_hashes is not None:
        img_hash = hashlib.md5(image_bytes).hexdigest()
        if img_hash in seen_hashes:
            return False
        seen_hashes.add(img_hash)

    # Page-relative size filter (PDF / PPT only)
    if page_size and render_size:
        page_w, page_h = page_size
        render_w, render_h = render_size
        if page_w > 0 and page_h > 0:
            if render_w / page_w < MIN_PAGE_RATIO and render_h / page_h < MIN_PAGE_RATIO:
                return False

    # Extreme aspect ratio = decorative bar / separator
    aspect = max(width, height) / max(min(width, height), 1)
    if aspect > MAX_ASPECT_RATIO:
        return False

    # Low bytes-per-pixel signals a solid color / gradient — only flag smaller
    # images, since large photos with uniform backgrounds may also score low.
    bpp = len(image_bytes) / area
    if bpp < MAX_LOW_INFO_BPP and area < MAX_LOW_INFO_AREA:
        return False

    return True
