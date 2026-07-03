"""Dashboard screen.

The "Presentation & Action Layer" from the architecture diagram: KPIs, a
severity breakdown, an issue-type breakdown, and a location heatmap-style map.
Reads from the shared incident store, falling back to sample data for demos.
"""
from __future__ import annotations

import streamlit as st

from app import styles
from app.config import settings
from app.screens.reported_incidents import _sample_incidents
from app.services import incident_store


def render() -> None:
    """Render the dashboard screen."""
    styles.inject()
    styles.hero(
        "Dashboard",
        "Real-time civic issue monitoring, heatmaps & KPIs.",
        settings.app_icon,
    )

    incidents = incident_store.all_incidents()
    if incidents.empty:
        incidents = _sample_incidents()
        st.caption("Showing sample data — analyze a snapshot to populate live KPIs.")

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
            st.markdown('<div class="ce-card-title">By Severity</div>', unsafe_allow_html=True)
            st.bar_chart(incidents["severity"].value_counts())

        with st.container(border=True):
            st.markdown('<div class="ce-card-title">By Issue Type</div>', unsafe_allow_html=True)
            st.bar_chart(incidents["type"].value_counts())

    with right:
        with st.container(border=True):
            st.markdown('<div class="ce-card-title">Issue Heatmap</div>', unsafe_allow_html=True)
            st.map(incidents[["lat", "lon"]], zoom=12, width="stretch")
            st.caption("Marker density approximates issue hotspots across the patrol zone.")
