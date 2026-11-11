from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import headline, load  # noqa: E402
from app.theme import AMBER, BASELINE, GREEN, finish, inject, money, note, pct  # noqa: E402

st.set_page_config(page_title="Forecast · promo-lift lab", layout="wide")
inject()
st.title("What I would have forecast, and whether the model earned it")

numbers = headline()
forecast = load("forecast")
scores = load("scores")
if forecast.empty:
    st.info("No forecast mart. A short fixture build skips the model on purpose when there are fewer than 24 weeks.")
    if not scores.empty:
        st.dataframe(scores, hide_index=True, width="stretch")
    st.stop()

default = numbers.get("forecast_default_model") or "naive_last_4"
beats = bool(numbers.get("forecast_ml_beats_naive"))
c1, c2, c3 = st.columns(3)
c1.metric("Four-week mean MAPE", pct(numbers.get("forecast_naive_wmape")))
c2.metric("Tree model MAPE", pct(numbers.get("forecast_ml_wmape")))
c3.metric("Default I would ship", "Tree" if default == "hist_gradient_boosting" else "Four-week mean")
if beats:
    note("The tree won on sales-weighted MAPE over the holdout, one step at a time, using actual lags. I still show the four-week mean beside it.")
else:
    note(
        "The four-week mean won, or tied in spirit. I keep it as the default. "
        "A year of department weeks is a short history, and a model that cannot beat the recent average does not get to be the number I quote."
    )

departments = sorted(forecast["department"].unique())
preferred = "GROCERY" if "GROCERY" in departments else departments[0]
choice = st.selectbox("Department", departments, index=departments.index(preferred))
part = forecast.loc[forecast["department"].eq(choice)].sort_values("week_no")
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=part["week_no"],
        y=part["net_sales"],
        name="Actual",
        mode="lines+markers",
        line=dict(color=GREEN, width=2.4),
        hovertemplate="Week %{x}<br>Actual $%{y:,.0f}<extra></extra>",
    )
)
fig.add_trace(
    go.Scatter(
        x=part["week_no"],
        y=part["predicted_naive"],
        name="Four-week mean",
        mode="lines",
        line=dict(color=BASELINE, width=2, dash="dash"),
        hovertemplate="Week %{x}<br>Naive $%{y:,.0f}<extra></extra>",
    )
)
fig.add_trace(
    go.Scatter(
        x=part["week_no"],
        y=part["predicted_ml"],
        name="Tree, with the flyer",
        mode="lines",
        line=dict(color=AMBER, width=2),
        hovertemplate="Week %{x}<br>Tree $%{y:,.0f}<extra></extra>",
    )
)
fig.update_layout(xaxis_title="Holdout week", yaxis_title="Net sales")
st.plotly_chart(finish(fig, f"{choice}: holdout weeks, one step ahead"), width="stretch")
note(
    "Both forecasts see the actual recent weeks (one-step, not a recursive 12-week path). "
    "The tree also sees how heavily the department was placed on display or in the mailer that week, which a planner knows when the flyer locks. "
    "There is a second tree without the flyer in the score table, so I can tell whether the flyer was doing any work."
)

overall = scores.loc[(scores["department"] == "ALL") & (scores["scope"].isin(["all", "promo_weeks", "quieter_weeks"]))]
if not overall.empty:
    pivot = overall.pivot_table(index="scope", columns="model", values="weighted_mape", aggfunc="first")
    keep = [c for c in ["naive_last_4", "hist_gradient_boosting", "hist_gradient_boosting_no_flyer"] if c in pivot.columns]
    if keep:
        melted = pivot[keep].reset_index().melt(id_vars="scope", var_name="model", value_name="weighted_mape")
        fig = go.Figure()
        colors = {"naive_last_4": BASELINE, "hist_gradient_boosting": GREEN, "hist_gradient_boosting_no_flyer": AMBER}
        for model, part_m in melted.groupby("model"):
            fig.add_trace(
                go.Bar(
                    x=part_m["scope"],
                    y=part_m["weighted_mape"],
                    name=model.replace("_", " "),
                    marker_color=colors.get(model, GREEN),
                    hovertemplate="%{x}<br>%{y:.1%}<extra>" + model + "</extra>",
                )
            )
        fig.update_layout(barmode="group", yaxis_tickformat=".0%", yaxis_title="Sales-weighted MAPE")
        st.plotly_chart(finish(fig, "Holdout error, including the noisier promotional weeks"), width="stretch")
        note(
            "Promo weeks are holdout department-weeks whose placement intensity is at or above the median. "
            "If the tree only wins on quiet weeks, it is not helping the decision the lab is about."
        )

dept_scores = scores.loc[(scores["scope"] == "department") & (scores["model"].isin(["naive_last_4", "hist_gradient_boosting"]))]
if not dept_scores.empty:
    st.subheader("By department")
    wide = dept_scores.pivot_table(index="department", columns="model", values="weighted_mape", aggfunc="first").reset_index()
    wide["tree_minus_naive"] = wide.get("hist_gradient_boosting", 0) - wide.get("naive_last_4", 0)
    st.dataframe(
        wide.sort_values("naive_last_4") if "naive_last_4" in wide.columns else wide,
        hide_index=True,
        width="stretch",
        column_config={
            "naive_last_4": st.column_config.NumberColumn("Four-week MAPE", format="%.1%"),
            "hist_gradient_boosting": st.column_config.NumberColumn("Tree MAPE", format="%.1%"),
            "tree_minus_naive": st.column_config.NumberColumn("Tree − naive", format="+.1%"),
        },
    )
    bias_rows = dept_scores.loc[dept_scores["department"].eq(choice)]
    if not bias_rows.empty and "bias" in bias_rows.columns:
        naive_bias = bias_rows.loc[bias_rows["model"].eq("naive_last_4"), "bias"]
        if len(naive_bias):
            note(
                f"Bias is prediction minus actual. For {choice}, the four-week mean bias on the holdout is {money(naive_bias.iloc[0])} per week. "
                "Positive means I would have ordered heavy."
            )
