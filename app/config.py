"""Application configuration.

Centralizes tunable settings so screens and services never hard-code values.
Environment variables (optionally loaded from a local ``.env``) override the
defaults, which keeps deployments configurable without code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Load a local ``.env`` (if present) into the environment before settings are
# read. On Streamlit Community Cloud there is no ``.env`` — config comes from
# ``st.secrets`` / env vars — so a missing file is a no-op. Without this, a
# local ``.env`` is silently ignored and the backend upload is skipped.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # dotenv is optional; env vars still work without it.
    pass


@dataclass(frozen=True)
class Settings:
    """Immutable, process-wide application settings."""

    app_title: str = os.getenv("CIVICEYE_APP_TITLE", "CivicEYEAI")
    app_icon: str = os.getenv("CIVICEYE_APP_ICON", "🛰️")
    app_subtitle: str = os.getenv(
        "CIVICEYE_APP_SUBTITLE",
        "Upload a drone snapshot, geo-tag it, and run AI civic analysis.",
    )

    # Accepted upload formats (Streamlit file_uploader ``type`` argument).
    allowed_image_types: tuple[str, ...] = ("jpg", "png", "jpeg")

    # Backend upload endpoint (Cloud Run function). When set, uploaded snapshots
    # are POSTed here for storage in Cloud Storage. Empty -> upload is skipped
    # and the UI runs on the local mock only.
    upload_url: str = os.getenv("CIVICEYE_UPLOAD_URL", "")

    # Shared secret sent as the ``X-API-Key`` header to authenticate with the
    # backend. Prefer Streamlit secrets in production; empty -> no auth header.
    api_key: str = os.getenv("CIVICEYE_API_KEY", "")

    # Coordinates are entered per-snapshot by the operator — there are no
    # default map coordinates. Displayed with 6 decimals (≈ 0.11 m).
    coordinate_format: str = "%.6f"


settings = Settings()
