"""Upload Snapshot screen.

Lets an operator upload a drone snapshot, tag it with geo-coordinates, and run
the multi-agent AI analysis. Detected issues flow into the shared incident
store for the Reported Incidents and Dashboard screens.

State model
-----------
A single session ``nonce`` keys the input widgets. "Upload another image"
increments the nonce, which gives the uploader and coordinate fields fresh keys
so Streamlit renders them empty — a clean reset without stale values.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from app import styles
from app.config import settings
from app.services import analysis_service, incident_store, upload_service
from app.services.image_service import ImageLoadError, load_image

# Session-state keys.
_NONCE = "upload_nonce"          # int — bumped to reset input widgets
_RESULT = "last_analysis"        # AnalysisResult | None


def _nonce() -> int:
    """Current form nonce (used to key/reset the input widgets)."""
    if _NONCE not in st.session_state:
        st.session_state[_NONCE] = 0
    return st.session_state[_NONCE]


def _reset_for_new_upload() -> None:
    """Clear the last result and bump the nonce so inputs render empty."""
    st.session_state[_RESULT] = None
    st.session_state[_NONCE] = _nonce() + 1


def _parse_coordinate(raw: str) -> float | None:
    """Parse a decimal-degree string; return None if empty or invalid."""
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


def _coordinate_inputs(nonce: int) -> tuple[float | None, float | None]:
    """Render the lat/lon inputs and return their parsed values (or None).

    Text inputs (not number_input) so there are no +/- steppers and the value
    shows as a plain decimal, e.g. ``17.496667``. No default is applied —
    coordinates must be entered by the operator.
    """
    styles.card_title("Geo-tag")
    lat_raw = st.text_input(
        "Latitude", value="", placeholder="e.g. 17.496667", key=f"lat_{nonce}"
    )
    lon_raw = st.text_input(
        "Longitude", value="", placeholder="e.g. 78.361389", key=f"lon_{nonce}"
    )
    return _parse_coordinate(lat_raw), _parse_coordinate(lon_raw)


def _map_preview(latitude: float, longitude: float) -> None:
    """Show a small map centered on the tagged coordinates."""
    st.map(
        pd.DataFrame({"lat": [latitude], "lon": [longitude]}),
        zoom=12,
        width="stretch",
    )


def _upload_to_backend(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    latitude: float,
    longitude: float,
    analysis: dict,
) -> tuple[str | None, str]:
    """Store the snapshot (with its analysis) via the backend Cloud Function.

    Returns ``(gs_uri, status)`` where ``status`` is one of
    ``"skipped" | "success" | "failed"`` for explicit UI reporting. The analysis
    is persisted as object metadata so the read screens can rebuild incidents.
    """
    if not upload_service.is_enabled():
        return None, "skipped"
    try:
        upload = upload_service.upload_snapshot(
            image_bytes,
            filename=filename,
            content_type=content_type,
            latitude=latitude,
            longitude=longitude,
            analysis=analysis,
        )
        return upload.gs_uri, "success"
    except upload_service.UploadError as exc:
        st.session_state["_upload_error"] = str(exc)
        return None, "failed"


def _run_analysis(
    image,
    image_bytes: bytes,
    filename: str,
    content_type: str,
    latitude: float,
    longitude: float,
) -> None:
    """Run the orchestration/agent pipeline with a visible, stateful status."""
    with st.status(
        "Running CivicEYEAI multi-agent analysis…", expanded=True
    ) as status:
        st.write("🛰️  Ingesting geo-tagged snapshot…")
        time.sleep(0.4)

        for agent in analysis_service.AGENTS:
            st.write(f"{agent['icon']}  {agent['name']} scanning for {agent['label']}…")
            time.sleep(0.4)
        st.write("🧠  Issue Intelligence Layer scoring severity…")
        time.sleep(0.4)
        st.write("✨  Gemini generating recommendations…")
        time.sleep(0.4)

        # Run the analysis first so its result can be persisted with the image.
        result = analysis_service.analyze(
            image_bytes, latitude, longitude, thumbnail=image
        )

        st.write("☁️  Storing snapshot + analysis in Cloud Storage…")
        gs_uri, upload_status = _upload_to_backend(
            image_bytes,
            filename,
            content_type,
            latitude,
            longitude,
            analysis=result.to_metadata(),
        )
        if upload_status == "success":
            st.write(f"✅  Stored in Cloud Storage → `{gs_uri}`")
        elif upload_status == "skipped":
            st.write("⏭️  Backend not configured — result not persisted.")
        else:
            err = st.session_state.get("_upload_error", "unknown error")
            st.write(f"❌  Cloud Storage upload failed: {err}")

        if upload_status == "failed":
            status.update(
                label="Analysis complete (backend upload failed)",
                state="error",
                expanded=False,
            )
        else:
            status.update(label="Analysis complete", state="complete", expanded=False)

    result.meta["gs_uri"] = gs_uri
    result.meta["upload_status"] = upload_status
    # New snapshot persisted — drop the cached list so the read screens refetch.
    if upload_status == "success":
        incident_store.refresh()
    st.session_state[_RESULT] = result


def _render_backend_status(result: "analysis_service.AnalysisResult") -> None:
    """Show the backend/Cloud Storage call state explicitly as a status chip."""
    status = result.meta.get("upload_status", "skipped")
    gs_uri = result.meta.get("gs_uri")
    if status == "success":
        st.success(f"☁️ Cloud Storage: **stored** · `{gs_uri}`", icon="✅")
    elif status == "failed":
        err = st.session_state.get("_upload_error", "upload failed")
        st.error(f"☁️ Cloud Storage: **failed** — {err}", icon="❌")
    else:
        st.warning("☁️ Cloud Storage: **skipped** — backend not configured.", icon="⏭️")


def _render_result() -> None:
    """Render the most recent analysis result, if any."""
    result: analysis_service.AnalysisResult | None = st.session_state.get(_RESULT)
    if result is None:
        return

    st.write("")
    with st.container(border=True):
        styles.card_title("Analysis Result")

        _render_backend_status(result)

        st.write("")
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
        caption = f"Analyzed at {result.analyzed_at}"
        if result.meta.get("upload_status") == "success":
            caption += " · added to Reported Incidents & Dashboard"
        st.caption(caption)

    # --- Reset: analyze another snapshot ---
    st.write("")
    st.button(
        "⬆️ Upload Another Image",
        on_click=_reset_for_new_upload,
        width="stretch",
    )


def render() -> None:
    """Render the upload-snapshot screen."""
    styles.inject()
    styles.hero(settings.app_title, settings.app_subtitle, settings.app_icon)

    # Once an analysis exists, show only the result + reset button.
    if st.session_state.get(_RESULT) is not None:
        _render_result()
        return

    nonce = _nonce()
    left, right = st.columns([1, 1], gap="large")

    # --- Left column: upload + coordinates ---
    with left:
        with st.container(border=True):
            styles.card_title("Drone Snapshot")
            uploaded_file = st.file_uploader(
                "Upload Drone Snapshot",
                type=list(settings.allowed_image_types),
                label_visibility="collapsed",
                key=f"uploader_{nonce}",
            )

        with st.container(border=True):
            latitude, longitude = _coordinate_inputs(nonce)

    # --- Right column: preview ---
    image = None
    image_bytes = b""
    with right:
        with st.container(border=True):
            styles.card_title("Preview")
            # Image preview and location preview side by side (not stacked).
            img_col, map_col = st.columns([1, 1], gap="medium")

            with img_col:
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

            with map_col:
                if latitude is not None and longitude is not None:
                    _map_preview(latitude, longitude)
                else:
                    st.caption("Enter latitude & longitude to preview the location.")

    # --- Geo-tag metrics ---
    st.write("")
    m1, m2, m3 = st.columns(3)
    m1.metric("Latitude", f"{latitude:.6f}" if latitude is not None else "—")
    m2.metric("Longitude", f"{longitude:.6f}" if longitude is not None else "—")
    m3.metric("Snapshot", "Ready" if image is not None else "Pending")

    # --- Action ---
    st.write("")
    if st.button("🔍 Analyze Snapshot", width="stretch"):
        if image is None:
            st.warning("Please upload a snapshot before analyzing.")
        elif latitude is None or longitude is None:
            st.warning("Please enter both latitude and longitude before analyzing.")
        else:
            _run_analysis(
                image,
                image_bytes,
                filename=uploaded_file.name,
                content_type=uploaded_file.type or "image/jpeg",
                latitude=latitude,
                longitude=longitude,
            )
            st.rerun()
