"""Incident view over live Cloud Storage snapshots.

The "Issue Database / Geo-Spatial Store" from the architecture diagram. Rather
than an in-memory session list, incidents are derived on demand from the
snapshots the backend has stored in Cloud Storage: each snapshot carries its
analysis (detections + summary) as object metadata, and every detection becomes
one incident row. The Reported Incidents and Dashboard screens read from here,
so they reflect the real bucket across sessions and devices.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services import snapshot_service

_COLUMNS = [
    "id", "type", "sub_type", "agent", "severity", "confidence",
    "status", "lat", "lon", "reported",
]


def _incident_id(object_name: str, index: int) -> str:
    """Stable, readable id for a detection within a snapshot object."""
    # e.g. snapshots/2026/07/04/<uuid>.jpg -> INC-<uuid8>-<index>
    stem = object_name.rsplit("/", 1)[-1].split(".")[0]
    return f"INC-{stem[:8]}-{index + 1}"


def _rows_from_snapshot(snap: snapshot_service.Snapshot) -> list[dict]:
    """Flatten one snapshot's persisted analysis into incident rows."""
    analysis = snap.analysis or {}
    detections = analysis.get("detections", []) if isinstance(analysis, dict) else []
    reported = (
        analysis.get("analyzed_at") if isinstance(analysis, dict) else None
    ) or snap.uploaded_at

    rows: list[dict] = []
    for i, det in enumerate(detections):
        rows.append(
            {
                "id": _incident_id(snap.object_name, i),
                "type": det.get("issue_type", "Unknown"),
                "sub_type": det.get("sub_type", ""),
                "agent": det.get("agent", ""),
                "severity": det.get("severity", "Low"),
                "confidence": float(det.get("confidence", 0.0) or 0.0),
                "status": det.get("status", "Open"),
                "lat": snap.latitude,
                "lon": snap.longitude,
                "reported": reported,
            }
        )
    return rows


def _rows_from_bq(incidents: list[dict]) -> list[dict]:
    """Map BigQuery incident rows onto the DataFrame's ``_COLUMNS`` shape."""
    return [
        {
            "id": inc.get("incident_id", ""),
            "type": inc.get("issue_type", "Unknown"),
            "sub_type": inc.get("sub_type", ""),
            "agent": inc.get("agent", ""),
            "severity": inc.get("severity", "Low"),
            "confidence": float(inc.get("confidence", 0.0) or 0.0),
            "status": inc.get("status", "Open"),
            "lat": float(inc.get("latitude", 0.0) or 0.0),
            "lon": float(inc.get("longitude", 0.0) or 0.0),
            "reported": inc.get("reported_at", ""),
        }
        for inc in incidents
    ]


@st.cache_data(ttl=30, show_spinner=False)
def all_incidents() -> pd.DataFrame:
    """Return every incident, preferring the BigQuery Civic Intelligence DB.

    Reads from BigQuery via the backend (a single indexed query — low latency)
    and falls back to deriving incidents from Cloud Storage snapshot metadata
    when BigQuery is disabled or unreachable. Cached briefly (30s); cleared by
    :func:`refresh` after a new upload. Returns an empty DataFrame (correct
    columns) when nothing is available, so screens degrade gracefully.
    """
    if not snapshot_service.is_enabled():
        return pd.DataFrame(columns=_COLUMNS)

    # Preferred path: BigQuery (box 8). ``None`` means BQ is off on the backend.
    try:
        bq_incidents = snapshot_service.list_incidents_bq()
        if bq_incidents is not None:
            return pd.DataFrame(_rows_from_bq(bq_incidents), columns=_COLUMNS)
    except snapshot_service.SnapshotError:
        pass  # fall through to the Cloud Storage-derived path

    # Fallback: derive incidents from snapshot object metadata.
    try:
        snapshots = snapshot_service.list_snapshots()
    except snapshot_service.SnapshotError:
        return pd.DataFrame(columns=_COLUMNS)

    rows: list[dict] = []
    for snap in snapshots:
        rows.extend(_rows_from_snapshot(snap))
    return pd.DataFrame(rows, columns=_COLUMNS)


_SEVERITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _snapshot_view(snap: snapshot_service.Snapshot) -> dict:
    """Snapshot-level summary for the incident cards (one card per snapshot)."""
    rows = _rows_from_snapshot(snap)
    analysis = snap.analysis or {}
    summary = analysis.get("summary", "") if isinstance(analysis, dict) else ""
    reported = rows[0]["reported"] if rows else snap.uploaded_at
    top_severity = "Low"
    for row in rows:
        if _SEVERITY_ORDER.get(row["severity"], 0) > _SEVERITY_ORDER.get(top_severity, 0):
            top_severity = row["severity"]
    return {
        "object_name": snap.object_name,
        "image_url": snap.image_url,
        "lat": snap.latitude,
        "lon": snap.longitude,
        "reported": reported,
        "summary": summary,
        "detections": rows,          # per-detection incident rows for the detail view
        "issue_count": len(rows),
        "top_severity": top_severity,
    }


@st.cache_data(ttl=30, show_spinner=False)
def all_snapshots() -> list[dict]:
    """Return live snapshots (newest first) as card-ready dicts.

    One entry per stored drone snapshot, carrying its geo-tag, Gemini summary,
    detected incidents, and image URL — everything the cards + detail view need.
    Empty list when the backend is not configured or unreachable.
    """
    if not snapshot_service.is_enabled():
        return []
    try:
        snapshots = snapshot_service.list_snapshots()
    except snapshot_service.SnapshotError:
        return []
    return [_snapshot_view(snap) for snap in snapshots]


@st.cache_data(ttl=300, show_spinner=False)
def snapshot_image(object_name: str) -> bytes | None:
    """Fetch (and cache) one snapshot's image bytes through the backend proxy.

    Cached longer than the listing (images are immutable once stored). Returns
    ``None`` if the backend is unreachable so the detail view degrades to text.
    """
    try:
        return snapshot_service.fetch_image(object_name)
    except snapshot_service.SnapshotError:
        return None


def refresh() -> None:
    """Invalidate the cached incident data so the next read re-fetches."""
    all_incidents.clear()
    all_snapshots.clear()
