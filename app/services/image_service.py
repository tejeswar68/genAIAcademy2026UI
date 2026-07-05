"""Image handling utilities.

Keeps PIL/IO concerns out of the screen layer so the UI stays declarative and
this logic stays unit-testable without a running Streamlit session.
"""
from __future__ import annotations

from typing import BinaryIO, Sequence

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

# Cap total pixels so a small "decompression bomb" (e.g. a few-KB PNG that
# expands to gigapixels) can't exhaust memory when decoded. 50 MP comfortably
# covers real drone snapshots. Pillow also warns past its own DecompressionBomb
# threshold; we enforce a hard limit and reject rather than warn.
_MAX_PIXELS = 50_000_000


class ImageLoadError(Exception):
    """Raised when an uploaded file cannot be decoded as an image."""


def load_image(uploaded_file: BinaryIO) -> Image.Image:
    """Decode an uploaded file into a PIL image.

    Args:
        uploaded_file: A file-like object (e.g. Streamlit's UploadedFile).

    Returns:
        The decoded image.

    Raises:
        ImageLoadError: If the bytes are not a valid image or exceed the pixel
            limit (decompression-bomb guard).
    """
    try:
        image = Image.open(uploaded_file)
        # Check declared dimensions from the header before fully decoding.
        width, height = image.size
        if width * height > _MAX_PIXELS:
            raise ImageLoadError("The image is too large to process.")
        image.load()  # Force decode now so errors surface here, not later.
        return image
    except Image.DecompressionBombError as exc:
        raise ImageLoadError("The image is too large to process.") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError("The uploaded file is not a valid image.") from exc


# Severity -> outline color for detection boxes (RGB).
_SEVERITY_COLOR = {
    "High": (220, 38, 38),      # red
    "Medium": (234, 179, 8),    # amber
    "Low": (34, 197, 94),       # green
}
_DEFAULT_COLOR = (37, 99, 235)  # blue
_WATERMARK_TEXT = "CivicEye AI"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort TrueType font, falling back to PIL's bitmap default.

    The bundled default font ignores ``size``; we try a few common system
    TrueType paths first so labels scale with the image.
    """
    for path in (
        "DejaVuSans-Bold.ttf",  # Pillow bundles this; resolvable by name
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def annotate_detections(
    image: Image.Image,
    detections: Sequence,
    *,
    watermark: bool = True,
) -> Image.Image:
    """Return a copy of ``image`` with detection boxes + labels drawn on it.

    Each detection is expected to expose ``box`` ([ymin, xmin, ymax, xmax] on a
    0-1000 scale), ``severity``, ``issue_type`` and ``confidence`` (mirrors the
    analysis ``Detection``). Detections without a valid box are skipped. When
    ``watermark`` is set, a "CivicEye AI" tag is stamped in the bottom-left so
    exported screenshots are branded and traceable.
    """
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    width, height = annotated.size

    # Scale line width and font to the image so boxes read on large snapshots.
    line_w = max(2, round(min(width, height) / 200))
    label_font = _load_font(max(14, round(min(width, height) / 45)))

    for det in detections:
        box = getattr(det, "box", None) or []
        if len(box) != 4:
            continue
        ymin, xmin, ymax, xmax = box
        left, right = xmin / 1000 * width, xmax / 1000 * width
        top, bottom = ymin / 1000 * height, ymax / 1000 * height
        color = _SEVERITY_COLOR.get(getattr(det, "severity", ""), _DEFAULT_COLOR)

        draw.rectangle([left, top, right, bottom], outline=color, width=line_w)

        # Label above the box (or just inside the top if there's no room).
        conf = getattr(det, "confidence", 0.0) or 0.0
        label = f"{getattr(det, 'issue_type', 'Issue')} · {conf:.0%}"
        tb = draw.textbbox((0, 0), label, font=label_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = max(2, line_w)
        ly = top - th - 2 * pad
        if ly < 0:
            ly = top + pad
        draw.rectangle([left, ly, left + tw + 2 * pad, ly + th + 2 * pad], fill=color)
        draw.text((left + pad, ly + pad), label, fill=(255, 255, 255), font=label_font)

    if watermark:
        _stamp_watermark(draw, width, height)
    return annotated


def _stamp_watermark(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Draw the CivicEye AI watermark in the bottom-left corner."""
    font = _load_font(max(12, round(min(width, height) / 55)))
    tb = draw.textbbox((0, 0), _WATERMARK_TEXT, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    pad = max(4, round(min(width, height) / 150))
    x, y = pad, height - th - 3 * pad
    # Semi-opaque dark plate behind the text for legibility on any background.
    draw.rectangle([x, y, x + tw + 2 * pad, y + th + 2 * pad], fill=(17, 24, 39))
    draw.text((x + pad, y + pad), _WATERMARK_TEXT, fill=(255, 255, 255), font=font)
