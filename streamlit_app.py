"""CivicEYEAI — Streamlit entrypoint.

Run from the ``ui`` directory with:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

from app.config import settings
from app.screens import dashboard, reported_incidents, upload_image

# Sidebar navigation: label -> screen module exposing render().
PAGES = {
    "📤 Upload Snapshot": upload_image,
    "📋 Reported Incidents": reported_incidents,
    "📊 Dashboard": dashboard,
}


def _sidebar() -> str:
    """Render the left navigation bar and return the selected page label."""
    with st.sidebar:
        st.markdown(f"## {settings.app_icon} {settings.app_title}")
        st.caption(settings.app_subtitle)
        st.divider()
        selection = st.radio(
            "Navigation",
            list(PAGES.keys()),
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("© 2026 CivicEYEAI")
    return selection


def main() -> None:
    """Configure the page and render the active screen."""
    st.set_page_config(
        page_title=settings.app_title,
        page_icon=settings.app_icon,
        layout="wide",
    )
    selection = _sidebar()
    PAGES[selection].render()


if __name__ == "__main__":
    main()
