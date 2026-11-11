from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import headline, load  # noqa: E402
from app.theme import AMBER, BASELINE, BRICK, GREEN, finish, inject, money, note, pct  # noqa: E402

st.set_page_config(page_title="Overview · promo-lift lab", layout="wide")
inject()
st.title("The year, before I start arguing with any one campaign")

numbers = headline()
weekly = load("weekly")
departments = load("departments")
anomalies = load("anomalies")
if not numbers or weekly.empty:
    st.info("Build the warehouse first (`make build`).")
    st.stop()

start = str(numbers.get("period_start") or "")[:10]
end = str(numbers.get("period_end") or "")[:10]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Net sales", money(numbers.get("net_sales")))
c2.metric("Discounts", money(numbers.get("discount_cost")))
c3.metric("Discount share of ring", pct(numbers.get("discount_share_of_gross")))
c4.metric("Off-feature discounts", pct(numbers.get("off_feature_discount_share")))
c5.metric("Households", f"{int(numbers.get('n_households') or 0):,}")
note(
    f"Source period {start} to {end}. Net sales are cash received. "
    f"Off-feature discounts are loyalty and coupon dollars on lines with no display and no mailer. "
    f"Fuel is {pct(numbers.get('fuel_sales_share'))} of net sales and is kept in the dollars, not in the unit counts."
)

weekly = weekly.sort_values("week_no")
partial = weekly.loc[weekly["is_partial"] == True, "week_no"].tolist() if "is_partial" in weekly.columns else []  # noqa: E712
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=weekly["week_no"],
        y=weekly["net_sales"],
        name="Net sales",
        mode="lines",
        line=dict(color=GREEN, width=2.4),
        hovertemplate="Week %{x}<br>Net sales $%{y:,.0f}<extra></extra>",
    )
)
if "discount_cost" in weekly.columns:
    fig.add_trace(
        go.Bar(
            x=weekly["week_no"],
            y=weekly["discount_cost"],
            name="Discounts",
            marker_color=BRICK,
            opacity=0.75,
            hovertemplate="Week %{x}<br>Discounts $%{y:,.0f}<extra></extra>",
        )
    )
fig.update_layout(barmode="overlay", yaxis_title="Dollars", xaxis_title="Study week")
st.plotly_chart(finish(fig, "Weekly cash received, with the discount bill behind it"), width="stretch")
partial_text = f" Weeks {partial} are partial and I keep them out of the forecast." if partial else ""
note(
    "The first week of this calendar is a stub, and the series steps around the holidays rather than exploding. "
    "I read the green line as demand and the brick bars as the price the panel gave up."
    + partial_text
)

if not departments.empty:
    top = departments.head(10).iloc[::-1]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=top["department"],
            x=top["incremental_sales"],
            orientation="h",
            marker_color=[GREEN if v >= 0 else BRICK for v in top["incremental_sales"]],
            hovertemplate="%{y}<br>Incremental net sales $%{x:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="Incremental net sales on feature weeks", yaxis_title="")
    st.plotly_chart(finish(fig, "Where a feature week actually added cash"), width="stretch")
    note(
        "Each bar is feature-week net sales minus the same product-store's non-feature run-rate, summed inside the department. "
        f"The matched panel covers {pct(numbers.get('feature_coverage'))} of non-fuel feature sales "
        f"({int(numbers.get('feature_pairs') or 0):,} product-store pairs). "
        "A negative bar means those featured items sold less than their own quiet weeks."
    )

st.subheader("Operations, from what this extract can see")
left, right = st.columns(2)
with left:
    st.markdown(
        f"""
        - **No return rate.** Quantity never goes negative in this mirror, so I will not invent one.
        - **Zero-quantity lines** are {pct(numbers.get('zero_quantity_share'))} of receipt lines. Some of them carry a coupon and no units.
        - **Grocery units**, fuel removed, total {float(numbers.get('grocery_units') or 0):,.0f}. Gasoline quantity is scaled (about a thousand units per gallon) and would swamp any unit total.
        """
    )
with right:
    if not anomalies.empty:
        show = anomalies.sort_values("robust_z", key=lambda s: s.abs(), ascending=False).head(6)
        st.dataframe(
            show[["week_no", "department", "net_sales", "trail_median", "robust_z", "reason"]],
            hide_index=True,
            width="stretch",
        )
        note("Robust z uses the previous eight weeks, so one spike does not set the bar for the next. Amber would be a forecast miss; these are level shifts.")
    else:
        st.write("No department-week cleared the anomaly bar.")

st.caption(f"Baseline colour in other pages is {BASELINE}. Discounts stay {BRICK}. Incremental, when I draw it, is {AMBER}.")
