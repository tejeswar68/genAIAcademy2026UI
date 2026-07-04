"""Shared scaffolding for the live (Cloud-Storage-backed) screens.

The Reported Incidents and Dashboard screens share the same shell: a hero
banner, a "Live from Cloud Storage" header with a Refresh button, an
empty-state guard, and a lat/lon map card. Those pieces live here so each
screen only describes what's unique to it (its metrics and body).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import styles
from app.config import settings
from app.services import incident_store


def live_header(title: str, subtitle: str, *, refresh_key: str) -> None:
    """Render the hero + "Live from Cloud Storage" row with a Refresh button.

    The Refresh button clears the incident cache and reruns, so the screen
    re-fetches the bucket. ``refresh_key`` keeps the button unique per screen.
    """
    styles.inject()
    styles.hero(title, subtitle, settings.app_icon)

    header, action = st.columns([4, 1])
    header.caption("Live from Cloud Storage")
    if action.button("🔄 Refresh", key=refresh_key, width="stretch"):
        incident_store.refresh()
        st.rerun()


def load_incidents(empty_message: str, *, icon: str) -> pd.DataFrame | None:
    """Return the live incidents, or ``None`` after showing an empty state.

    Screens call this right after :func:`live_header` and return early when it
    yields ``None`` — that keeps the "no data yet" guard identical everywhere.
    """
    incidents = incident_store.all_incidents()
    if incidents.empty:
        st.info(empty_message, icon=icon)
        return None
    return incidents


def map_card(incidents: pd.DataFrame, title: str, *, caption: str | None = None) -> None:
    """Render a bordered card with a lat/lon map of the incidents."""
    with st.container(border=True):
        styles.card_title(title)
        st.map(incidents[["lat", "lon"]], zoom=12, width="stretch")
        if caption:
            st.caption(caption)
