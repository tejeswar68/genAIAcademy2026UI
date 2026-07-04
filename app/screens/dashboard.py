"""Dashboard screen.

The "Presentation & Action Layer" from the architecture diagram: KPIs, a
severity breakdown, an issue-type breakdown, and a location heatmap-style map.
Reads live from Cloud Storage (via the incident store), so it reflects every
snapshot stored in the bucket across sessions.
"""
from __future__ import annotations

import streamlit as st

from app import styles
from app.screens import _common


def render() -> None:
    """Render the dashboard screen."""
    _common.live_header(
        "Dashboard",
        "Real-time civic issue monitoring, heatmaps & KPIs.",
        refresh_key="refresh_dashboard",
    )

    incidents = _common.load_incidents(
        "No data yet. Upload and analyze a drone snapshot to populate live "
        "KPIs and the heatmap.",
        icon="📊",
    )
    if incidents is None:
        return

    # --- KPI row ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Issues", len(incidents))
    m2.metric("High Severity", int((incidents["severity"] == "High").sum()))
    m3.metric("Open", int((incidents["status"] == "Open").sum()))
    m4.metric("Resolved", int((incidents["status"] == "Resolved").sum()))

    st.write("")
    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.container(border=True):
            styles.card_title("By Severity")
            st.bar_chart(incidents["severity"].value_counts())

        with st.container(border=True):
            styles.card_title("By Issue Type")
            st.bar_chart(incidents["type"].value_counts())

    with right:
        _common.map_card(
            incidents,
            "Issue Heatmap",
            caption="Marker density approximates issue hotspots across the patrol zone.",
        )
