"""Backend upload client.

Sends an uploaded snapshot to the CivicEYEAI storage backend (a Cloud Run
function) which stores it in Cloud Storage and returns its ``gs://`` location.

Kept isolated from the UI and fully optional: if no backend URL is configured
the caller treats upload as skipped, so the app still runs on the local mock.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests
import streamlit as st

from app.config import settings

# Network timeout for the upload call (connect, read) in seconds.
_TIMEOUT = 30


class UploadError(Exception):
    """Raised when the snapshot could not be stored by the backend."""


@dataclass
class UploadResult:
    """Outcome of a backend upload."""

    gs_uri: str
    object_name: str
    bucket: str
    size_bytes: int


def _secret(name: str) -> str:
    """Read a value from Streamlit secrets, returning "" if unavailable.

    ``st.secrets`` raises when no secrets file exists, so this swallows that and
    lets the caller fall back to env/config.
    """
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        return ""
    return str(value) if value else ""


def _backend_url() -> str:
    """Resolve the backend URL from Streamlit secrets, then env/config.

    Streamlit Community Cloud exposes configuration via ``st.secrets``; local
    runs fall back to the ``CIVICEYE_UPLOAD_URL`` environment variable.
    """
    return _secret("CIVICEYE_UPLOAD_URL") or settings.upload_url


def _api_key() -> str:
    """Resolve the backend API key from Streamlit secrets, then env/config."""
    return _secret("CIVICEYE_API_KEY") or settings.api_key


def is_enabled() -> bool:
    """Whether a backend upload URL is configured."""
    return bool(_backend_url())


def upload_snapshot(
    image_bytes: bytes,
    *,
    filename: str,
    content_type: str,
    latitude: float,
    longitude: float,
) -> UploadResult:
    """POST the snapshot to the backend for Cloud Storage upload.

    Raises:
        UploadError: If no backend is configured or the request fails.
    """
    url = _backend_url()
    if not url:
        raise UploadError("No upload backend configured.")

    # Authenticate with the backend's shared secret when one is configured.
    headers = {}
    api_key = _api_key()
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.post(
            url,
            files={"image": (filename, image_bytes, content_type)},
            data={"latitude": str(latitude), "longitude": str(longitude)},
            headers=headers,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise UploadError(f"Upload request failed: {exc}") from exc
    except ValueError as exc:
        raise UploadError("Backend returned an invalid response.") from exc

    if not payload.get("success"):
        raise UploadError(payload.get("detail", "Backend rejected the upload."))

    return UploadResult(
        gs_uri=payload.get("gs_uri", ""),
        object_name=payload.get("object_name", ""),
        bucket=payload.get("bucket", ""),
        size_bytes=payload.get("size_bytes", 0),
    )
