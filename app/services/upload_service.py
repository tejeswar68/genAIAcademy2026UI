"""Backend upload client.

Sends an uploaded snapshot to the CivicEYEAI storage backend (a Cloud Run
function) which stores it in Cloud Storage and returns its ``gs://`` location.

Kept isolated from the UI and fully optional: if no backend URL is configured
the caller treats upload as skipped, so the app still runs on the local mock.
"""
from __future__ import annotations

import json
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
    # Analysis the backend stored (real Gemini result when enabled, else the
    # client-supplied mock echoed back). ``analysis_source`` is one of
    # ``"gemini" | "client" | "error" | "none"``.
    analysis: dict | None = None
    analysis_source: str = "none"
    # Whether the backend persisted this snapshot as an incident. False when no
    # civic issue was detected (off-topic or clean scene) — nothing is stored.
    stored: bool = True


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


def backend_url() -> str:
    """Public accessor for the resolved backend base URL (may be empty)."""
    return _backend_url()


def auth_headers() -> dict[str, str]:
    """Return the ``X-API-Key`` header when a key is configured, else empty."""
    api_key = _api_key()
    return {"X-API-Key": api_key} if api_key else {}


def upload_snapshot(
    image_bytes: bytes,
    *,
    filename: str,
    content_type: str,
    latitude: float,
    longitude: float,
    analysis: dict | None = None,
) -> UploadResult:
    """POST the snapshot to the backend for Cloud Storage upload.

    ``analysis`` (if given) is sent as a JSON form field and persisted as
    object metadata, so the read screens can rebuild incidents from the bucket.

    Raises:
        UploadError: If no backend is configured or the request fails.
    """
    url = _backend_url()
    if not url:
        raise UploadError("No upload backend configured.")

    headers = auth_headers()

    data = {"latitude": str(latitude), "longitude": str(longitude)}
    if analysis is not None:
        data["analysis"] = json.dumps(analysis, separators=(",", ":"))

    try:
        response = requests.post(
            url,
            files={"image": (filename, image_bytes, content_type)},
            data=data,
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
        analysis=payload.get("analysis"),
        analysis_source=payload.get("analysis_source", "none"),
        stored=bool(payload.get("stored", True)),
    )
