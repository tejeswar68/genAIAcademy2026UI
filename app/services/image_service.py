"""Image handling utilities.

Keeps PIL/IO concerns out of the screen layer so the UI stays declarative and
this logic stays unit-testable without a running Streamlit session.
"""
from __future__ import annotations

from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

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
