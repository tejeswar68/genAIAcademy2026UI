"""Backend read client — live snapshots from Cloud Storage.

Fetches the snapshots the backend has stored in Cloud Storage (image + geo-tag
+ persisted analysis) and exposes them to the Dashboard and Reported Incidents
screens. This replaces the old in-memory session store: the two read screens now
reflect what is actually in the bucket, across sessions and devices.

The bucket stays private — image bytes are fetched through the backend's image
proxy, never from GCS directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from app.services import upload_service

# Read calls are quick JSON/list operations; keep the timeout tight.
_TIMEOUT = 15


class SnapshotError(Exception):
    """Raised when snapshots cannot be fetched from the backend."""


@dataclass
class Snapshot:
    """One stored snapshot as returned by the backend ``/list`` endpoint."""

    object_name: str
    image_url: str                 # absolute URL through the backend proxy
    latitude: float
    longitude: float
    uploaded_at: str
    size_bytes: int
    content_type: str
    analysis: dict | None = field(default=None)


def is_enabled() -> bool:
    """Whether a backend is configured (shared with the upload client)."""
    return upload_service.is_enabled()


def _endpoint(suffix: str) -> str:
    """Build an absolute backend URL for a read path (``/list`` or ``/image``).

    The backend dispatches by path suffix, so appending works whether the
    configured URL is a bare service root or ends in ``/upload``.
    """
    base = upload_service.backend_url().rstrip("/")
    return f"{base}{suffix}"


def image_url(object_name: str) -> str:
    """Absolute URL to fetch one snapshot's bytes through the backend proxy."""
    return f"{_endpoint('/image')}?object={object_name}"


def list_incidents_bq() -> list[dict] | None:
    """Fetch incident rows from the backend's BigQuery-backed endpoint.

    Returns the incident dicts, or ``None`` when BigQuery is not enabled on the
    backend (so the caller falls back to deriving incidents from snapshots).

    Raises:
        SnapshotError: If the backend request itself fails.
    """
    if not upload_service.is_enabled():
        raise SnapshotError("No backend configured.")
    try:
        response = requests.get(
            _endpoint("/incidents"),
            headers=upload_service.auth_headers(),
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SnapshotError(f"Failed to fetch incidents: {exc}") from exc
    except ValueError as exc:
        raise SnapshotError("Backend returned an invalid response.") from exc

    if not payload.get("success"):
        raise SnapshotError(payload.get("detail", "Backend rejected the request."))
    if not payload.get("enabled"):
        return None  # BigQuery off — caller uses the snapshot-derived path
    return payload.get("incidents", [])


def fetch_image(object_name: str) -> bytes:
    """Fetch one snapshot's raw bytes through the backend image proxy.

    The proxy requires the shared ``X-API-Key`` header, so image bytes must be
    fetched here (with auth) rather than pointing ``st.image`` at the URL — a
    bare browser request to the proxy would be rejected as unauthorized.

    Raises:
        SnapshotError: If no backend is configured or the request fails.
    """
    if not upload_service.is_enabled():
        raise SnapshotError("No backend configured.")

    try:
        response = requests.get(
            _endpoint("/image"),
            params={"object": object_name},
            headers=upload_service.auth_headers(),
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SnapshotError(f"Failed to fetch image: {exc}") from exc
    return response.content


def list_snapshots() -> list[Snapshot]:
    """Fetch every stored snapshot (newest first) from the backend.

    Raises:
        SnapshotError: If no backend is configured or the request fails.
    """
    if not upload_service.is_enabled():
        raise SnapshotError("No backend configured.")

    try:
        response = requests.get(
            _endpoint("/list"),
            headers=upload_service.auth_headers(),
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SnapshotError(f"Failed to fetch snapshots: {exc}") from exc
    except ValueError as exc:
        raise SnapshotError("Backend returned an invalid response.") from exc

    if not payload.get("success"):
        raise SnapshotError(payload.get("detail", "Backend rejected the request."))

    snapshots: list[Snapshot] = []
    for item in payload.get("snapshots", []):
        object_name = item.get("object_name", "")
        snapshots.append(
            Snapshot(
                object_name=object_name,
                image_url=image_url(object_name),
                latitude=float(item.get("latitude", 0.0) or 0.0),
                longitude=float(item.get("longitude", 0.0) or 0.0),
                uploaded_at=item.get("uploaded_at", ""),
                size_bytes=int(item.get("size_bytes", 0) or 0),
                content_type=item.get("content_type", "image/jpeg"),
                analysis=item.get("analysis"),
            )
        )
    return snapshots
