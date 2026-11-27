"""Store-SKU replenishment. Every figure is written by `make replenishment`."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import load  # noqa: E402
from app.theme import AMBER, BASELINE, BRICK, GREEN, finish, inject, note, pct  # noqa: E402


def _share(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number:.1%}"


def _units(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number != number:
        return ""
    return f"{number:,.0f}"


st.set_page_config(page_title="Replenishment · promo-lift lab", layout="wide")
inject()
st.title("What I would have ordered")

summary = load("replenishment_summary")
accuracy = load("replenishment_accuracy")
weekly = load("replenishment_weekly")
department = load("replenishment_department")
if summary.empty:
    st.info("No replenishment export yet. From the repo root: `make replenishment`.")
    st.stop()

row = summary.iloc[0]
default = str(row.get("default_model") or "moving_average_4")
default_label = {
    "moving_average_4": "Four-week mean",
    "seasonal_naive": "Seasonal naive",
    "promo_adjusted": "Promo-adjusted",
}.get(default, default)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Default forecast", default_label)
c2.metric("Its WAPE", pct(row.get("wape_default")))
c3.metric("Series scored", f"{int(row.get('n_series') or 0):,}")
c4.metric("Feature weeks short", f"{float(row.get('units_short_vs_quiet_mean') or 0):,.0f}")
note(
    "WAPE is absolute error divided by actual units, on the last "
    f"{int(row.get('holdout_week_count') or 0)} non-partial weeks, one step ahead. "
    "The shortfall is holdout feature-week units above the quiet-week mean from before the holdout. "
    "These are panel units at a store, not the store's full movement. "
    f"Eligible series cover {pct(row.get('coverage'))} of non-fuel units on non-partial weeks."
)

left, right = st.columns(2)
with left:
    st.subheader("Did the flyer belong in the forecast?")
    labels = ["Four-week mean", "Promo-adjusted"]
    keys = ["wape_moving_average_4", "wape_promo_adjusted"]
    values = [row.get(key) for key in keys]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=[BASELINE, GREEN],
            text=[pct(value) if value == value else "—" for value in values],
            textposition="outside",
        )
    )
    fig.update_layout(yaxis_tickformat=".0%", yaxis_title="WAPE", showlegend=False)
    st.plotly_chart(finish(fig, "Holdout WAPE, all scored store-SKU weeks"), width="stretch")
    feature_note = ""
    feature_ma = row.get("wape_feature_ma4")
    feature_promo = row.get("wape_feature_promo")
    try:
        if float(feature_promo) > float(feature_ma):
            feature_note = (
                f" On feature weeks the four-week mean is the lower WAPE ({pct(feature_ma)} versus {pct(feature_promo)}). "
                "I would not order the promo week from the adjustment."
            )
    except (TypeError, ValueError):
        feature_note = ""
    note(
        "Seasonal naive is the same study week last year. One year of history leaves it blank. "
        "The promo adjustment is the mean of the last four quiet weeks, scaled on a feature week by this series' own past lift, shrunk toward 1."
        + feature_note
    )
with right:
    st.subheader("The order, if the pipeline is empty")
    st.markdown(
        f"""
        Lead time **{int(row.get('lead_time_weeks') or 1)} week**, review every **{int(row.get('review_weeks') or 1)} week**, service level **{pct(row.get('service_level'))}** (z = {float(row.get('service_z') or 0):.2f}).

        Safety stock is z times the quiet-week standard deviation times the square root of lead time plus the review interval. The suggested order equals the order-up-to level, because on-hand is not in this file.

        Median safety stock **{float(row.get('median_safety_stock') or 0):,.1f}** units. Median suggested order **{float(row.get('median_suggested_order') or 0):,.1f}** units.
        """
    )
    st.markdown(
        f"""
        - **{int(row.get('n_stockout_risk') or 0):,}** of {int(row.get('n_series') or 0):,} series have a feature-week mean above the quiet week plus one week of safety stock.
        - **{int(row.get('n_overstock_risk') or 0):,}** series would overshoot that buffer if the promo quantity was ordered again on a quiet week.
        - Quiet weeks ordered at the feature rate would have left **{float(row.get('units_extra_if_feature_rate_on_quiet') or 0):,.0f}** extra units in the holdout.
        """
    )

if not weekly.empty:
    st.subheader("Holdout, one department")
    departments = sorted(weekly["department"].dropna().unique())
    preferred = "MEAT" if "MEAT" in departments else departments[0]
    choice = st.selectbox("Department", departments, index=departments.index(preferred))
    part = weekly.loc[weekly["department"].eq(choice)].sort_values("week_no")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=part["week_no"],
            y=part["actual_units"],
            name="Actual",
            mode="lines",
            line=dict(color=GREEN, width=2.4),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=part["week_no"],
            y=part["moving_average_4"],
            name="Four-week mean",
            mode="lines",
            line=dict(color=BASELINE, width=2, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=part["week_no"],
            y=part["promo_adjusted"],
            name="Promo-adjusted",
            mode="lines",
            line=dict(color=AMBER, width=2),
        )
    )
    fig.update_layout(xaxis_title="Study week", yaxis_title="Panel units")
    st.plotly_chart(finish(fig, f"{choice}: eligible store-SKU series, summed"), width="stretch")
    note(
        "The lines are the sum of series that passed the history rule, not every unit in the department. "
        "Forecasts are blank until four quiet or calendar weeks exist. "
        "A feature week can still be a zero: the panel may not have bought it, or the store may have been out."
    )

if not department.empty:
    st.subheader("Where a quiet-week order misses the flyer")
    show = department.loc[department["n_series"] >= 100].copy()
    if show.empty:
        show = department.copy()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=show["department"],
            y=show["units_short_vs_quiet_mean"],
            name="Short if the order ignores the flyer",
            marker_color=BRICK,
        )
    )
    fig.add_trace(
        go.Bar(
            x=show["department"],
            y=show["units_extra_if_feature_rate_on_quiet"],
            name="Extra if the promo rate is ordered every quiet week",
            marker_color=AMBER,
        )
    )
    fig.update_layout(barmode="group", yaxis_title="Holdout units", xaxis_tickangle=-35)
    st.plotly_chart(finish(fig, "Promotion risk by department, holdout weeks"), width="stretch")
    table = pd.DataFrame(
        {
            "Department": show["department"],
            "Series": show["n_series"].map(lambda v: f"{int(v):,}"),
            "Short vs quiet mean": show["units_short_vs_quiet_mean"].map(_units),
            "Short after safety stock": show["units_short_vs_service_cover"].map(_units),
            "Extra at feature rate": show["units_extra_if_feature_rate_on_quiet"].map(_units),
            "Stock-out risk": show["share_series_stockout_risk"].map(_share),
            "Overstock risk": show["share_series_overstock_risk"].map(_share),
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")
    note(
        "Short vs quiet mean is the units a feature week sold above the pre-holdout quiet average. "
        "Short vs quiet + safety stock uses one week of the service buffer, not the two-week order-up-to. "
        "The store-SKU rows behind this table are in `exports/bi/replenishment_policy.csv`."
    )

overall = accuracy.loc[accuracy["department"].eq("ALL")] if not accuracy.empty and "department" in accuracy.columns else accuracy
if not overall.empty:
    st.subheader("Accuracy")
    view = overall.loc[overall["model"].isin(["moving_average_4", "seasonal_naive", "promo_adjusted"])].copy()
    labels = {
        "moving_average_4": "Four-week mean",
        "seasonal_naive": "Seasonal naive",
        "promo_adjusted": "Promo-adjusted",
    }
    shown = pd.DataFrame(
        {
            "Model": view["model"].map(lambda name: labels.get(name, name)),
            "Weeks": view["scope"].map(lambda scope: {"all": "All", "feature_weeks": "Feature", "quiet_weeks": "Quiet"}.get(scope, scope)),
            "MAPE": view["mape"].map(_share),
            "WAPE": view["wape"].map(_share),
            "Median APE": view["median_ape"].map(_share),
            "Bias (units)": view["bias"].map(lambda v: "—" if pd.isna(v) else f"{float(v):+.3f}"),
            "Points": view["n_points"].map(lambda v: f"{int(v):,}"),
        }
    )
    st.dataframe(shown, hide_index=True, width="stretch")
    note(
        "Bias is prediction minus actual. Positive means I would have ordered heavy. "
        "MAPE ignores silent weeks and is pulled around by weeks that sold a unit or two. I rank on WAPE. "
        "Seasonal naive is lag 52. One year of weeks usually leaves it with nothing to copy."
    )

st.subheader("What I will not pretend")
st.markdown(
    """
    There is no on-hand, no on-order, and no cost of goods. The suggested order is the order-up-to level
    under an empty pipeline, in panel units. A normal safety stock is a rough fit when many weeks are zero.
    The campaigns were not randomized, and a zero inside the span may be a stock-out I cannot see.
    Lead time is one week because I assumed a weekly grocery order, not because a DC file said so.
    """
)
