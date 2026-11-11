from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import headline, load  # noqa: E402
from app.theme import AMBER, BRICK, GREEN, finish, inject, money, note, pct  # noqa: E402

st.set_page_config(page_title="Customers · promo-lift lab", layout="wide")
inject()
st.title("Who shops, and who actually moves when the tag changes")

numbers = headline()
segments = load("segments")
baskets = load("baskets")
halo = load("halo")
if segments.empty:
    st.info("No segment mart yet.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Promo-sensitive households", pct(numbers.get("promo_sensitive_share")))
c2.metric("Threshold", pct(numbers.get("promo_sensitive_threshold")))
c3.metric("Households over the line", f"{int(numbers.get('promo_sensitive_households') or 0):,}")
note(
    "Promo-sensitive means discounts are at least 18% of the pre-discount ring, and the household has at least 8 baskets. "
    "It is a habit of buying on offer, not a response to one mailing. "
    "Demographics exist for only part of the panel, and I do not put household-level bins on this page."
)

order = segments.copy()
fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=order["segment"].astype(str),
        y=order["sales_share"],
        name="Share of net sales",
        marker_color=GREEN,
        hovertemplate="%{x}<br>Sales share %{y:.1%}<extra></extra>",
    )
)
fig.add_trace(
    go.Bar(
        x=order["segment"].astype(str),
        y=order["household_share"],
        name="Share of households",
        marker_color=AMBER,
        hovertemplate="%{x}<br>Household share %{y:.1%}<extra></extra>",
    )
)
fig.update_layout(barmode="group", yaxis_tickformat=".0%", yaxis_title="Share")
st.plotly_chart(finish(fig, "A small group of households carries a large share of the cash"), width="stretch")
note("Quintile 5 is most recent, most frequent, or highest spend. Champions are high on all three. Hibernating is the opposite corner.")

st.dataframe(
    order,
    hide_index=True,
    width="stretch",
    column_config={
        "household_share": st.column_config.NumberColumn("Households", format="%.1%"),
        "sales_share": st.column_config.NumberColumn("Net sales", format="%.1%"),
        "promo_sensitive_share": st.column_config.NumberColumn("Promo-sensitive", format="%.1%"),
        "net_sales": st.column_config.NumberColumn("Net sales $", format="$%,.0f"),
        "avg_monetary": st.column_config.NumberColumn("Average spend", format="$%,.0f"),
    },
)

if not baskets.empty:
    st.subheader("Departments that share a basket")
    top = baskets.head(12).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            y=top["department_a"].astype(str) + " + " + top["department_b"].astype(str),
            x=top["lift"],
            orientation="h",
            marker_color=GREEN,
            hovertemplate="%{y}<br>Lift %{x:.2f}<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="Basket lift (1 = no more often than chance)")
    st.plotly_chart(finish(fig, "Pairs that show up together more often than their base rates"), width="stretch")
    note("Lift above 1 is affinity inside the same trip. It is not evidence that promoting one causes the other. Fuel and miscellaneous lines are left out.")

if not halo.empty:
    st.subheader("Across weeks, not inside the basket")
    show = halo.head(12).copy()
    show["read"] = show["direction"]
    st.dataframe(
        show[
            [
                "source_department",
                "target_department",
                "direction",
                "coef_sales_per_intensity",
                "t_stat",
                "n_weeks",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "coef_sales_per_intensity": st.column_config.NumberColumn("Sales per intensity point", format="$%,.0f"),
            "t_stat": st.column_config.NumberColumn("t", format="%.2f"),
        },
    )
    note(
        "Each row is a regression of the target department's weekly sales on the source department's flyer intensity, "
        "controlling for the target's own flyer and a linear week trend. "
        f"A positive sign is the halo direction; a negative sign is cannibalization. "
        f"I coloured nothing as a verdict — {BRICK} would overclaim a t-statistic from fifty weeks."
    )
    note(f"The largest associations are clues for a category conversation, not a media plan. Average segment spend context: {money(order['avg_monetary'].mean()) if 'avg_monetary' in order.columns else '—'}.")
