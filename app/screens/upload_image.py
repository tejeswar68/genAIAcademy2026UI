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

import threading

import pandas as pd
import streamlit as st

from app import styles
from app.config import settings
from app.services import analysis_service, incident_store, upload_service
from app.services.image_service import ImageLoadError, annotate_detections, load_image

# Backend pipeline steps, shown one at a time (~2s each) while the real cloud
# call runs. These mirror what the backend actually does per snapshot; the
# status advances dynamically and loops on the last steps until the call
# returns, so it always tracks in-flight work rather than a fixed delay.
_PIPELINE_STEPS = (
    "🛰️ Ingesting geo-tagged snapshot…",
    "☁️ Uploading to Google Cloud Storage…",
    "🧠 Vertex AI · loading Gemini 2.5 vision model…",
    "🗑️ Waste Agent · scanning for garbage & litter…",
    "🌊 Drainage Agent · checking drains & flooding…",
    "🕳️ Safety Agent · detecting manholes & road hazards…",
    "📐 Localizing issues & drawing detection boxes…",
    "✨ Gemini · generating recommendations & severity…",
    "🗄️ Writing incidents to BigQuery…",
)
_STEP_SECONDS = 2.0

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
) -> tuple[upload_service.UploadResult | None, str, str]:
    """Store the snapshot (with its analysis) via the backend Cloud Function.

    Returns ``(upload, status, error)`` where ``status`` is one of
    ``"skipped" | "success" | "failed"`` for explicit UI reporting and ``error``
    carries the failure message (empty unless ``status == "failed"``). Pure with
    respect to Streamlit state so it is safe to call from a worker thread — the
    caller writes any ``st.session_state`` on the main thread.
    """
    if not upload_service.is_enabled():
        return None, "skipped", ""
    try:
        upload = upload_service.upload_snapshot(
            image_bytes,
            filename=filename,
            content_type=content_type,
            latitude=latitude,
            longitude=longitude,
            analysis=analysis,
        )
        return upload, "success", ""
    except upload_service.UploadError as exc:
        return None, "failed", str(exc)


def _run_analysis(
    image,
    image_bytes: bytes,
    filename: str,
    content_type: str,
    latitude: float,
    longitude: float,
) -> None:
    """Run the analysis pipeline behind a live status that tracks real work.

    Each ``status.update`` reflects an actual stage that is about to run (upload
    + backend Gemini analysis), so the animated spinner label always matches
    what the system is really doing — no fabricated per-agent delays.
    """
    # Local analysis: the fallback display + the payload sent to a backend that
    # isn't running its own AI. When Gemini is enabled the backend returns the
    # authoritative result and we display that instead.
    result = analysis_service.analyze(
        image_bytes, latitude, longitude, thumbnail=image
    )

    # Run the (blocking) backend call in a worker thread so the status can step
    # through the real pipeline stages (~2s each) while the cloud work is in
    # flight. The thread only does the network I/O and hands its outcome back
    # via ``out`` — all st.session_state writes stay on the main thread.
    out: dict = {}

    def _worker() -> None:
        out["upload"], out["status"], out["error"] = _upload_to_backend(
            image_bytes, filename, content_type, latitude, longitude,
            analysis=result.to_metadata(),
        )

    worker = threading.Thread(target=_worker, daemon=True)

    with st.status("Analyzing snapshot…", expanded=True) as status:
        worker.start()
        # Advance one step every ~2s; hold on the last step until the call ends
        # so the label always reflects work still in progress.
        step = 0
        while worker.is_alive():
            status.update(label=_PIPELINE_STEPS[min(step, len(_PIPELINE_STEPS) - 1)])
            step += 1
            worker.join(timeout=_STEP_SECONDS)
        worker.join()

        upload, upload_status = out.get("upload"), out.get("status", "failed")
        upload_error = out.get("error", "")
        # Surface the error on the main thread (never from the worker).
        if upload_error:
            st.session_state["_upload_error"] = upload_error

        # Prefer the backend's Gemini analysis over the local mock when present.
        if upload and upload.analysis_source == "gemini" and upload.analysis:
            result = analysis_service.from_metadata(
                upload.analysis, latitude, longitude, thumbnail=image
            )

        # Backend skips storage when no civic issue is found — reflect that.
        not_stored = bool(upload) and not getattr(upload, "stored", True)
        n = len(result.detections)

        if upload_status == "success" and not_stored:
            status.update(
                label="✅ Analysis complete — no civic issue to report",
                state="complete",
                expanded=False,
            )
        elif upload_status == "success":
            src = upload.analysis_source if upload else "none"
            status.update(
                label=(
                    f"✅ Analysis complete — {n} issue(s) detected"
                    if src == "gemini"
                    else "✅ Analysis complete"
                ),
                state="complete",
                expanded=False,
            )
        elif upload_status == "skipped":
            status.update(
                label="✅ Analysis complete (local only — backend not configured)",
                state="complete",
                expanded=False,
            )
        else:
            err = st.session_state.get("_upload_error", "unknown error")
            status.update(
                label=f"❌ Cloud upload failed — {err}",
                state="error",
                expanded=False,
            )

    result.meta["upload_status"] = upload_status
    result.meta["analysis_source"] = upload.analysis_source if upload else "none"
    result.meta["stored"] = (not not_stored) if upload_status == "success" else False
    # A new incident was persisted only when the backend actually stored it.
    if upload_status == "success" and not not_stored:
        incident_store.refresh()
    st.session_state[_RESULT] = result


def _render_backend_status(result: "analysis_service.AnalysisResult") -> None:
    """Show the backend/Cloud Storage call state explicitly as a status chip.

    Deliberately does not expose the internal ``gs://`` object path.
    """
    status = result.meta.get("upload_status", "skipped")
    if status == "success":
        engine = "Gemini AI" if result.meta.get("analysis_source") == "gemini" else "local analysis"
        if result.meta.get("stored", True):
            st.success(f"☁️ Snapshot stored & analyzed with {engine}.", icon="✅")
        else:
            # Analyzed but intentionally not persisted (no civic issue found).
            st.info(f"🔍 Analyzed with {engine} · not added to incidents.", icon="ℹ️")
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

        # Nothing-to-report gate. Two cases, neither persisted as an incident:
        #   1. Off-topic upload (selfie, document, indoor photo…) — not a scene.
        #   2. A valid civic scene that happens to be clean (no issues found).
        # Either way, show a clear message instead of a fake "0 issues" result.
        if not result.relevant or not result.detections:
            st.write("")
            if not result.relevant:
                note = result.relevance_note or "the image does not appear to be a civic scene"
                st.warning(
                    f"⚠️ **This image isn't ideal for civic analysis.** "
                    f"CivicEye AI expects a drone snapshot of a street, road, drain, "
                    f"or public area — but {note}. Please upload a relevant snapshot.",
                    icon="🚫",
                )
            else:
                st.success(
                    "✅ **No civic issues detected.** This area looks clear, so "
                    "nothing was added to Reported Incidents.",
                    icon="🌿",
                )
            if result.thumbnail is not None:
                st.write("")
                st.image(result.thumbnail, caption="Uploaded image · CivicEye AI", width="stretch")
            st.write("")
            st.button(
                "⬆️ Upload Another Image",
                on_click=_reset_for_new_upload,
                width="stretch",
            )
            return

        st.write("")
        top = result.top_severity
        c1, c2, c3 = st.columns(3)
        c1.metric("Issues Detected", len(result.detections))
        c2.markdown(
            f"**Top Severity**<br>{styles.severity_badge(top)}",
            unsafe_allow_html=True,
        )
        c3.metric("Agents Run", result.meta.get("agents_run", 0))

        # Annotated snapshot: draw the AI-detected regions on the image so the
        # operator sees exactly *where* each issue is, not just that one exists.
        if result.thumbnail is not None:
            st.write("")
            located = [d for d in result.detections if getattr(d, "box", None)]
            annotated = annotate_detections(result.thumbnail, result.detections)
            caption = (
                "AI-highlighted issue regions · CivicEye AI"
                if located
                else "Analyzed snapshot · CivicEye AI"
            )
            st.image(annotated, caption=caption, width="stretch")

        st.write("")
        if result.detections:
            for det in result.detections:
                sub = f" · {det.sub_type}" if det.sub_type else ""
                st.markdown(
                    f"""
                    <div class="ce-agent">
                        <div class="ce-agent-icon">🔎</div>
                        <div style="flex:1">
                            <div class="ce-agent-name">{det.agent} — {det.issue_type}{sub}</div>
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

        # Location + one-tap directions so a crew can navigate to the site.
        st.write("")
        loc_col, dir_col = st.columns([2, 1])
        with loc_col:
            st.markdown(
                f"📍 **Location:** {result.latitude:.6f}, {result.longitude:.6f}"
            )
        with dir_col:
            styles.directions_link(result.latitude, result.longitude)

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
