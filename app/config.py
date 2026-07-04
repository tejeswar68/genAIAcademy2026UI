"""Application configuration.

Centralizes tunable settings so screens and services never hard-code values.
Environment variables (optionally loaded from a local ``.env``) override the
defaults, which keeps deployments configurable without code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(key: str, default: float) -> float:
    """Read a float from the environment, falling back to ``default``."""
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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

    # Default map coordinates, stored as signed decimal degrees (WGS-84).
    #
    # Source (DMS): 17°29′48″N  78°21′41″E  (Hyderabad, IN)
    # DMS -> decimal:  deg + min/60 + sec/3600, negate for S / W.
    #   Lat: 17 + 29/60 + 48/3600 = 17.496667  (N -> positive)
    #   Lon: 78 + 21/60 + 41/3600 = 78.361389  (E -> positive)
    #
    # Displayed via ``coordinate_format`` ("%.6f") -> 6 decimals ≈ 0.11 m.
    default_latitude: float = field(
        default_factory=lambda: _env_float("CIVICEYE_DEFAULT_LAT", 17.496667)
    )
    default_longitude: float = field(
        default_factory=lambda: _env_float("CIVICEYE_DEFAULT_LON", 78.361389)
    )
    coordinate_format: str = "%.6f"


settings = Settings()
