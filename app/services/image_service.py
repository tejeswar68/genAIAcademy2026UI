"""Image handling utilities.

Keeps PIL/IO concerns out of the screen layer so the UI stays declarative and
this logic stays unit-testable without a running Streamlit session.
"""
from __future__ import annotations

from typing import BinaryIO

from PIL import Image, UnidentifiedImageError


class ImageLoadError(Exception):
    """Raised when an uploaded file cannot be decoded as an image."""


def load_image(uploaded_file: BinaryIO) -> Image.Image:
    """Decode an uploaded file into a PIL image.

    Args:
        uploaded_file: A file-like object (e.g. Streamlit's UploadedFile).

    Returns:
        The decoded image.

    Raises:
        ImageLoadError: If the bytes are not a valid image.
    """
    try:
        image = Image.open(uploaded_file)
        image.load()  # Force decode now so errors surface here, not later.
        return image
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError("The uploaded file is not a valid image.") from exc
