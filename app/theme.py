"""Colour and type for the lab. Actuals are green, the baseline is warm grey, discounts are brick."""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

INK = "#1F1A17"
MUTED = "#6B625A"
GREEN = "#1F6B4A"
GREEN_SOFT = "#7BA894"
AMBER = "#C47B2B"
BRICK = "#A33B32"
BASELINE = "#8D8378"
PAPER = "#FFFDF9"
RULE = "#E4DCD0"

pio.templates["liftlab"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Source Sans 3, Segoe UI, sans-serif", color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=PAPER,
        colorway=[GREEN, AMBER, BASELINE, BRICK, "#3D5A80", "#6B4C7A"],
        margin=dict(l=48, r=20, t=56, b=48),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=RULE, tickfont=dict(size=12)),
        yaxis=dict(gridcolor="#EFE8DC", zeroline=False, linecolor=RULE, tickfont=dict(size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12)),
        hoverlabel=dict(bgcolor=PAPER, font_size=13, font_family="Source Sans 3, Segoe UI, sans-serif"),
        title=dict(font=dict(family="Source Serif 4, Georgia, serif", size=18, color=INK), x=0, xanchor="left"),
    )
)
pio.templates.default = "liftlab"


def inject() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,560;8..60,650&display=swap');
          html, body, [class*="css"] { font-family: "Source Sans 3", "Segoe UI", sans-serif; }
          h1, h2, h3 { font-family: "Source Serif 4", Georgia, serif !important; letter-spacing: -0.02em; }
          .block-container { padding-top: 1.4rem; max-width: 1180px; }
          div[data-testid="stMetric"] {
            background: #fffdf9;
            border: 1px solid #e4dcd0;
            border-radius: 12px;
            padding: 0.6rem 0.8rem 0.4rem 0.8rem;
          }
          div[data-testid="stMetric"] label { color: #6b625a; }
          div[data-testid="stMetricValue"] { font-size: 1.35rem !important; overflow: visible; }
          [data-testid="stToolbar"] { display: none; }
          .caption-note { color: #6b625a; font-size: 0.95rem; margin-top: -0.4rem; margin-bottom: 1rem; }
          .source-line { color: #6b625a; font-size: 0.82rem; }
          .wordmark { font-family: "Source Serif 4", Georgia, serif; font-size: 1.7rem; color: #1f6b4a; margin-bottom: 0; }
          .tagline { color: #6b625a; margin-top: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def finish(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, template="liftlab")
    return fig


def note(text: str) -> None:
    import streamlit as st

    st.markdown(f'<p class="caption-note">{text}</p>', unsafe_allow_html=True)


def money(value) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.0f}"


def pct(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number:.1%}"
