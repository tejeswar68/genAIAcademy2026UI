"""Upload Snapshot screen.

Lets an operator upload a drone snapshot, tag it with geo-coordinates, and run
the (simulated) multi-agent AI analysis. Detected issues flow into the shared
incident store for the Reported Incidents and Dashboard screens.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from app import styles
from app.config import settings
from app.services import analysis_service, incident_store
from app.services.image_service import ImageLoadError, load_image


def _parse_coordinate(raw: str, fallback: float) -> float:
    """Parse a decimal-degree string, falling back on empty/invalid input."""
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return fallback


def _coordinate_inputs() -> tuple[float, float]:
    """Render the lat/lon inputs inside a card and return their values.

    Uses text inputs (not number_input) so there are no +/- steppers and the
    value shows as a plain decimal, e.g. ``17.496667``.
    """
    st.markdown('<div class="ce-card-title">Geo-tag</div>', unsafe_allow_html=True)
    lat_raw = st.text_input("Latitude", value="", placeholder="e.g. 17.496667")
    lon_raw = st.text_input("Longitude", value="", placeholder="e.g. 78.361389")
    latitude = _parse_coordinate(lat_raw, settings.default_latitude)
    longitude = _parse_coordinate(lon_raw, settings.default_longitude)
    return latitude, longitude


def _map_preview(latitude: float, longitude: float) -> None:
    """Show a small map centered on the tagged coordinates."""
    st.map(
        pd.DataFrame({"lat": [latitude], "lon": [longitude]}),
        zoom=12,
        width="stretch",
    )


def _run_analysis(image, image_bytes: bytes, latitude: float, longitude: float) -> None:
    """Simulate the orchestration/agent pipeline with visible progress."""
    with st.status("Running CivicEYEAI multi-agent analysis…", expanded=True) as status:
        st.write("🛰️  Ingesting geo-tagged snapshot…")
        time.sleep(0.5)
        for agent in analysis_service.AGENTS:
            st.write(f"{agent['icon']}  {agent['name']} scanning for {agent['label']}…")
            time.sleep(0.45)
        st.write("🧠  Issue Intelligence Layer scoring severity…")
        time.sleep(0.5)
        st.write("✨  Gemini generating recommendations…")
        time.sleep(0.5)
        status.update(label="Analysis complete", state="complete", expanded=False)

    result = analysis_service.analyze(image_bytes, latitude, longitude, thumbnail=image)
    incident_store.add_from_analysis(result)
    st.session_state["last_analysis"] = result


def _render_result() -> None:
    """Render the most recent analysis result, if any."""
    result: analysis_service.AnalysisResult | None = st.session_state.get("last_analysis")
    if result is None:
        return

    st.write("")
    with st.container(border=True):
        st.markdown('<div class="ce-card-title">Analysis Result</div>', unsafe_allow_html=True)

        top = result.top_severity
        c1, c2, c3 = st.columns(3)
        c1.metric("Issues Detected", len(result.detections))
        c2.markdown(
            f"**Top Severity**<br>{styles.severity_badge(top)}",
            unsafe_allow_html=True,
        )
        c3.metric("Agents Run", result.meta.get("agents_run", 0))

        st.write("")
        if result.detections:
            for det in result.detections:
                st.markdown(
                    f"""
                    <div class="ce-agent">
                        <div class="ce-agent-icon">🔎</div>
                        <div style="flex:1">
                            <div class="ce-agent-name">{det.agent} — {det.issue_type}</div>
                            <div class="ce-agent-sub">Confidence {det.confidence:.0%} · {det.recommendation}</div>
                        </div>
                        {styles.severity_badge(det.severity)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No civic issues detected in this snapshot.")

        st.write("")
        st.markdown("**✨ Gemini Recommendation**")
        st.info(result.summary)
        st.caption(f"Analyzed at {result.analyzed_at} · added to Reported Incidents")


def render() -> None:
    """Render the upload-snapshot screen."""
    styles.inject()
    styles.hero(settings.app_title, settings.app_subtitle, settings.app_icon)

    left, right = st.columns([1, 1], gap="large")

    # --- Left column: upload + coordinates ---
    with left:
        with st.container(border=True):
            st.markdown(
                '<div class="ce-card-title">Drone Snapshot</div>',
                unsafe_allow_html=True,
            )
            uploaded_file = st.file_uploader(
                "Upload Drone Snapshot",
                type=list(settings.allowed_image_types),
                label_visibility="collapsed",
            )

        with st.container(border=True):
            latitude, longitude = _coordinate_inputs()

    # --- Right column: preview ---
    image = None
    image_bytes = b""
    with right:
        with st.container(border=True):
            st.markdown('<div class="ce-card-title">Preview</div>', unsafe_allow_html=True)
            if uploaded_file is not None:
                try:
                    image = load_image(uploaded_file)
                except ImageLoadError as exc:
                    st.error(str(exc))
                else:
                    image_bytes = uploaded_file.getvalue()
                    st.image(image, caption="Uploaded Snapshot", width="stretch")
            else:
                st.info("Upload a snapshot to see the preview here.")

            _map_preview(latitude, longitude)

    # --- Geo-tag metrics ---
    st.write("")
    m1, m2, m3 = st.columns(3)
    m1.metric("Latitude", f"{latitude:.6f}")
    m2.metric("Longitude", f"{longitude:.6f}")
    m3.metric("Snapshot", "Ready" if image is not None else "Pending")

    # --- Action ---
    st.write("")
    if st.button("🔍 Analyze Snapshot"):
        if image is None:
            st.warning("Please upload a snapshot before analyzing.")
        else:
            _run_analysis(image, image_bytes, latitude, longitude)
            st.toast("Snapshot analyzed — incidents updated", icon="🛰️")

    _render_result()
