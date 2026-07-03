"""In-memory incident store backed by Streamlit session state.

Acts as the demo stand-in for the "Issue Database / Geo-Spatial Store" in the
architecture diagram. Analyzed snapshots are appended here and read back by the
Reported Incidents and Dashboard screens within a session.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services.analysis_service import AnalysisResult

_KEY = "incidents"
_COUNTER = "incident_counter"


def _ensure() -> None:
    if _KEY not in st.session_state:
        st.session_state[_KEY] = []            # list[dict]
    if _COUNTER not in st.session_state:
        st.session_state[_COUNTER] = 1040


def add_from_analysis(result: AnalysisResult) -> list[dict]:
    """Persist each detection from an analysis as an incident row."""
    _ensure()
    added: list[dict] = []
    for det in result.detections:
        st.session_state[_COUNTER] += 1
        row = {
            "id": f"INC-{st.session_state[_COUNTER]}",
            "type": det.issue_type,
            "agent": det.agent,
            "severity": det.severity,
            "confidence": det.confidence,
            "status": "Open",
            "lat": result.latitude,
            "lon": result.longitude,
            "reported": result.analyzed_at,
        }
        st.session_state[_KEY].append(row)
        added.append(row)
    return added


def all_incidents() -> pd.DataFrame:
    """Return every stored incident as a DataFrame."""
    _ensure()
    columns = [
        "id", "type", "agent", "severity", "confidence",
        "status", "lat", "lon", "reported",
    ]
    rows = st.session_state[_KEY]
    return pd.DataFrame(rows, columns=columns)


def clear() -> None:
    """Remove all incidents (useful for resetting a recording)."""
    st.session_state[_KEY] = []
