"""Reported Incidents screen.

Lists civic incidents produced by the analysis pipeline (via the shared
incident store). If nothing has been analyzed yet this session, it seeds a few
sample rows so the screen is never empty during a demo.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import styles
from app.config import settings
from app.services import incident_store


def _sample_incidents() -> pd.DataFrame:
    """Fallback rows so the screen looks populated before any analysis."""
    return pd.DataFrame(
        [
            {"id": "INC-1039", "type": "Waste / Garbage", "agent": "Waste Agent",
             "severity": "High", "confidence": 0.94, "status": "Open",
             "lat": 17.4980, "lon": 78.3625, "reported": "2026-07-02 09:14 UTC"},
            {"id": "INC-1038", "type": "Drainage / Flooding", "agent": "Drainage AI Agent",
             "severity": "Medium", "confidence": 0.83, "status": "In Review",
             "lat": 17.4951, "lon": 78.3602, "reported": "2026-07-01 16:40 UTC"},
            {"id": "INC-1037", "type": "Open Manhole / Hazard", "agent": "Safety Agent",
             "severity": "High", "confidence": 0.91, "status": "Resolved",
             "lat": 17.4967, "lon": 78.3640, "reported": "2026-06-29 11:05 UTC"},
        ]
    )


def render() -> None:
    """Render the reported-incidents screen."""
    styles.inject()
    styles.hero(
        "Reported Incidents",
        "Civic issues detected from analyzed drone snapshots.",
        settings.app_icon,
    )

    incidents = incident_store.all_incidents()
    if incidents.empty:
        incidents = _sample_incidents()
        st.caption("Showing sample incidents — analyze a snapshot to add live data.")

    # --- Summary metrics ---
    m1, m2, m3 = st.columns(3)
    m1.metric("Total", len(incidents))
    m2.metric("Open", int((incidents["status"] == "Open").sum()))
    m3.metric("High Severity", int((incidents["severity"] == "High").sum()))

    st.write("")
    left, right = st.columns([3, 2], gap="large")

    with left:
        with st.container(border=True):
            st.markdown('<div class="ce-card-title">Incidents</div>', unsafe_allow_html=True)
            st.dataframe(
                incidents.drop(columns=["lat", "lon"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "confidence": st.column_config.ProgressColumn(
                        "Confidence", min_value=0.0, max_value=1.0, format="%.0f%%"
                    ),
                },
            )

    with right:
        with st.container(border=True):
            st.markdown('<div class="ce-card-title">Locations</div>', unsafe_allow_html=True)
            st.map(incidents[["lat", "lon"]], zoom=12, width="stretch")
