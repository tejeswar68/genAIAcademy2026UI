"""Reported Incidents screen.

Lists civic incidents rebuilt from the snapshots the backend has stored in
Cloud Storage (image + geo-tag + persisted analysis). Fully dynamic: reflects
the live bucket across sessions and devices, not just the current session.

Presented as a filterable grid of snapshot cards. Selecting a card opens a
detail view with the snapshot image and its full per-agent analysis.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from app import styles
from app.screens import _common
from app.services import incident_store

# Session-state key: object_name of the snapshot whose detail view is open.
_SELECTED = "incident_selected"


def _parse_dt(raw) -> datetime | None:
    """Parse a snapshot timestamp (ISO-8601 or ``YYYY-MM-DD HH:MM UTC``)."""
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return None


def _reported_date(snap: dict) -> date | None:
    """Calendar date a snapshot was reported (for the date filter)."""
    dt = _parse_dt(snap.get("reported"))
    return dt.date() if dt else None


def _format_reported(raw) -> str:
    """Human-readable ``YYYY-MM-DD HH:MM UTC`` (best-effort)."""
    dt = _parse_dt(raw)
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else str(raw)


def render() -> None:
    """Render the reported-incidents screen (grid, or detail if one is open)."""
    _common.live_header(
        "Reported Incidents",
        "Civic issues detected from analyzed drone snapshots.",
        refresh_key="refresh_incidents",
    )

    snapshots = incident_store.all_snapshots()
    if not snapshots:
        st.info(
            "No incidents yet. Upload and analyze a drone snapshot to populate "
            "this list.",
            icon="🛰️",
        )
        return

    # A selected snapshot takes over the screen with its detail view.
    selected = st.session_state.get(_SELECTED)
    if selected:
        match = next((s for s in snapshots if s["object_name"] == selected), None)
        if match is not None:
            _render_detail(match)
            return
        # Selection no longer exists (refreshed/deleted) — fall back to the grid.
        st.session_state[_SELECTED] = None

    _render_grid(snapshots)


# --- Grid view -----------------------------------------------------------

def _render_grid(snapshots: list[dict]) -> None:
    """Render summary metrics, the date filter, and the card grid."""
    # Summary metrics (over the unfiltered set).
    total_issues = sum(s["issue_count"] for s in snapshots)
    high = sum(1 for s in snapshots if s["top_severity"] == "High")
    m1, m2, m3 = st.columns(3)
    m1.metric("Snapshots", len(snapshots))
    m2.metric("Total Issues", total_issues)
    m3.metric("High Severity", high)

    filtered = _date_filter(snapshots)

    st.write("")
    if not filtered:
        st.info("No snapshots in the selected date range.", icon="📅")
        return

    # Three-column responsive card grid.
    cols = st.columns(3, gap="medium")
    for i, snap in enumerate(filtered):
        with cols[i % 3]:
            _render_card(snap)


def _date_filter(snapshots: list[dict]) -> list[dict]:
    """Render a date-range picker and return the snapshots within it."""
    dates = sorted({d for s in snapshots if (d := _reported_date(s)) is not None})
    if not dates:
        return snapshots

    lo, hi = dates[0], dates[-1]
    with st.container(border=True):
        styles.card_title("Filter by date")
        chosen = st.date_input(
            "Reported between",
            value=(lo, hi),
            min_value=lo,
            max_value=hi,
            key="incident_date_range",
        )

    # date_input returns a single date until both ends are picked.
    if isinstance(chosen, (tuple, list)):
        if len(chosen) != 2:
            return snapshots
        start, end = chosen
    else:
        start = end = chosen

    return [
        s for s in snapshots
        if (d := _reported_date(s)) is not None and start <= d <= end
    ]


def _render_card(snap: dict) -> None:
    """Render one snapshot as a clickable summary card."""
    with st.container(border=True):
        badge = styles.severity_badge(snap["top_severity"])
        issues = snap["issue_count"]
        label = f"{issues} issue{'s' if issues != 1 else ''}"
        st.markdown(
            f"""
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem">
                <span class="ce-agent-name">{label}</span>{badge}
            </div>
            <div class="ce-agent-sub">
                📍 {snap['lat']:.4f}, {snap['lon']:.4f}<br>
                🕑 {_format_reported(snap['reported'])}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if snap["summary"]:
            st.caption(snap["summary"])
        if st.button(
            "View details",
            key=f"open_{snap['object_name']}",
            width="stretch",
        ):
            st.session_state[_SELECTED] = snap["object_name"]
            st.rerun()


# --- Detail view ---------------------------------------------------------

def _render_detail(snap: dict) -> None:
    """Render the full detail view for one selected snapshot."""
    if st.button("← Back to incidents", key="back_to_grid"):
        st.session_state[_SELECTED] = None
        st.rerun()

    st.write("")
    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.container(border=True):
            styles.card_title("Snapshot")
            image_bytes = incident_store.snapshot_image(snap["object_name"])
            if image_bytes:
                st.image(image_bytes, width="stretch")
            else:
                st.info("Image unavailable.", icon="🖼️")
            st.caption(
                f"📍 {snap['lat']:.4f}, {snap['lon']:.4f} · "
                f"🕑 {_format_reported(snap['reported'])}"
            )

    with right:
        _common.map_card(
            # map_card expects lat/lon columns; wrap this snapshot as one point.
            _one_point(snap),
            "Location",
        )

    st.write("")
    with st.container(border=True):
        styles.card_title(f"Detected Issues ({snap['issue_count']})")
        detections = snap["detections"]
        if not detections:
            st.info("No civic issues detected in this snapshot.")
        for det in detections:
            _render_detection(det)

    if snap["summary"]:
        st.write("")
        st.markdown("**✨ Gemini Recommendation**")
        st.info(snap["summary"])


def _one_point(snap: dict):
    """A single-row DataFrame with lat/lon for the location map."""
    import pandas as pd

    return pd.DataFrame({"lat": [snap["lat"]], "lon": [snap["lon"]]})


def _render_detection(det: dict) -> None:
    """Render one detected issue as a detailed row."""
    confidence = float(det["confidence"])
    sub = f"{det['agent']} · confidence {confidence:.0%} · {det['status']}"
    st.markdown(
        f"""
        <div class="ce-agent">
            <div class="ce-agent-icon">🔎</div>
            <div style="flex:1">
                <div class="ce-agent-name">{det['type']}
                    <span style="opacity:0.55;font-weight:500">· {det['id']}</span></div>
                <div class="ce-agent-sub">{sub}</div>
            </div>
            {styles.severity_badge(str(det['severity']))}
        </div>
        """,
        unsafe_allow_html=True,
    )
