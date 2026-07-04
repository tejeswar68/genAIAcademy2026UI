"""Central place for custom CSS and small UI helpers.

Keeping presentation here means screens stay focused on layout and logic while
the look-and-feel can evolve in one spot.
"""
from __future__ import annotations

import streamlit as st

# Palette (brand-neutral, works in light & dark).
_PRIMARY = "#2563eb"
_PRIMARY_DARK = "#1d4ed8"
_ACCENT = "#0ea5e9"

_CSS = f"""
<style>
  /* Tighten the default top padding so the hero sits higher. Use the full
     wide-layout width (with comfortable side padding) so previews/maps are big. */
  .block-container {{
      padding-top: 2.2rem;
      max-width: 1600px;
      padding-left: 2.5rem;
      padding-right: 2.5rem;
  }}

  /* Hero banner */
  .ce-hero {{
      background: linear-gradient(120deg, {_PRIMARY} 0%, {_ACCENT} 100%);
      border-radius: 16px;
      padding: 1.6rem 1.8rem;
      color: #ffffff;
      box-shadow: 0 8px 24px rgba(37, 99, 235, 0.25);
      margin-bottom: 1.6rem;
  }}
  .ce-hero h1 {{
      margin: 0;
      font-size: 2.1rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #ffffff;
  }}
  .ce-hero p {{
      margin: 0.35rem 0 0;
      font-size: 1rem;
      opacity: 0.92;
  }}

  /* Section card */
  .ce-card {{
      border: 1px solid rgba(148, 163, 184, 0.25);
      border-radius: 14px;
      padding: 1.1rem 1.2rem;
      background: rgba(148, 163, 184, 0.06);
      margin-bottom: 1rem;
  }}
  .ce-card-title {{
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: {_PRIMARY};
      margin-bottom: 0.6rem;
  }}

  /* Primary button restyle */
  .stButton > button {{
      background: linear-gradient(120deg, {_PRIMARY} 0%, {_PRIMARY_DARK} 100%);
      color: #ffffff;
      border: none;
      border-radius: 10px;
      padding: 0.6rem 1.1rem;
      font-weight: 600;
      width: 100%;
      transition: transform 0.05s ease, box-shadow 0.15s ease;
  }}
  .stButton > button:hover {{
      box-shadow: 0 6px 16px rgba(37, 99, 235, 0.35);
      color: #ffffff;
  }}
  .stButton > button:active {{
      transform: translateY(1px);
  }}

  /* Uploaded image rounding */
  .stImage img {{
      border-radius: 12px;
  }}

  /* Directions link styled as a pill button */
  a.ce-directions {{
      display: inline-block;
      padding: 0.45rem 0.95rem;
      border-radius: 10px;
      background: rgba(37, 99, 235, 0.1);
      color: {_PRIMARY};
      font-weight: 600;
      text-decoration: none;
      border: 1px solid rgba(37, 99, 235, 0.3);
      transition: background 0.15s ease;
  }}
  a.ce-directions:hover {{
      background: rgba(37, 99, 235, 0.2);
      text-decoration: none;
  }}

  /* Severity / status badges */
  .ce-badge {{
      display: inline-block;
      padding: 0.15rem 0.7rem;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.3px;
  }}
  .ce-badge-high    {{ background: #fee2e2; color: #b91c1c; }}
  .ce-badge-medium  {{ background: #fef3c7; color: #b45309; }}
  .ce-badge-low     {{ background: #dcfce7; color: #15803d; }}

  /* Agent result row */
  .ce-agent {{
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 0.55rem 0.2rem;
      border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  }}
  .ce-agent:last-child {{ border-bottom: none; }}
  .ce-agent-icon {{ font-size: 1.4rem; }}
  .ce-agent-name {{ font-weight: 600; }}
  .ce-agent-sub  {{ font-size: 0.8rem; opacity: 0.7; }}
</style>
"""


def inject() -> None:
    """Inject the global stylesheet. Call once, early in a screen's render."""
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, icon: str = "") -> None:
    """Render the gradient hero banner."""
    prefix = f"{icon} " if icon else ""
    st.markdown(
        f"""
        <div class="ce-hero">
            <h1>{prefix}{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def card_title(text: str) -> None:
    """Render a section-card title (the uppercase label used inside cards)."""
    st.markdown(f'<div class="ce-card-title">{text}</div>', unsafe_allow_html=True)


def severity_badge(severity: str) -> str:
    """Return an HTML badge string for a severity level."""
    cls = f"ce-badge-{severity.lower()}"
    return f'<span class="ce-badge {cls}">{severity.upper()}</span>'


def directions_url(latitude: float, longitude: float) -> str:
    """Google Maps directions URL to the given coordinates (from the user)."""
    return f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"


def directions_link(latitude: float, longitude: float, label: str = "🧭 Get directions") -> None:
    """Render a link that opens turn-by-turn directions to the coordinates."""
    st.markdown(
        f'<a href="{directions_url(latitude, longitude)}" target="_blank" '
        f'rel="noopener" class="ce-directions">{label}</a>',
        unsafe_allow_html=True,
    )
