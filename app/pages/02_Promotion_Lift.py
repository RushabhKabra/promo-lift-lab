from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import headline, load  # noqa: E402
from app.theme import AMBER, BRICK, GREEN, finish, inject, money, note, pct  # noqa: E402

st.set_page_config(page_title="Promotion lift · promo-lift lab", layout="wide")
inject()
st.title("Did the promotion earn its keep?")

numbers = headline()
campaigns = load("campaigns")
categories = load("categories")
depth = load("depth")
worked = load("worked")
if campaigns.empty:
    st.info("No campaign mart yet. Run `make build`.")
    st.stop()

scored = campaigns.loc[campaigns["status"].eq("ok")].copy() if "status" in campaigns.columns else campaigns.copy()
scored = scored.sort_values("incremental_sales")
negative = int((scored["incremental_sales"] < 0).sum()) if len(scored) else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Scored campaigns", f"{len(scored)}")
c2.metric("Below their baseline", f"{negative}")
c3.metric("Worst incremental", money(numbers.get("worst_campaign_incremental")))
c4.metric("Matched feature lift", pct(numbers.get("feature_lift_pct")))
note(
    f"On the matched panel the zero-filled baseline (silent weeks count as zero) says feature weeks lifted net sales by {pct(numbers.get('feature_lift_pct'))}, "
    f"{money(numbers.get('feature_incremental_sales'))} in total, ROI proxy {numbers.get('feature_roi'):.2f}. "
    f"If I ignore the silent weeks and only compare weeks that rang up, the average ring is ${float(numbers.get('conditional_promo_mean') or 0):,.2f} on a feature week "
    f"versus ${float(numbers.get('conditional_base_mean') or 0):,.2f} on a quiet week, a lift of {pct(numbers.get('conditional_lift_pct'))}. "
    "Most of the bigger number is 'a sale happened at all,' and I cannot see which silent weeks were simply out of stock."
)
note(
    "A scored campaign has at least two pre weeks inside the data and a mailed group large enough to compare. "
    "Incremental net sales is a difference-in-differences: the change for mailed households, minus the change "
    "for households who were not in any overlapping mailing. ROI divides that by coupon and match discounts "
    "on the campaign's couponed products. Retail loyalty discounts are not in that denominator."
)

fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=scored["campaign_id"].astype(str),
        y=scored["incremental_sales"],
        name="Incremental net sales",
        marker_color=[GREEN if v >= 0 else BRICK for v in scored["incremental_sales"]],
        hovertemplate="Campaign %{x}<br>Incremental $%{y:,.0f}<extra></extra>",
    )
)
if "coupon_cost" in scored.columns:
    fig.add_trace(
        go.Scatter(
            x=scored["campaign_id"].astype(str),
            y=scored["coupon_cost"],
            name="Coupon + match cost",
            mode="markers",
            marker=dict(size=9, color=AMBER, symbol="diamond"),
            hovertemplate="Campaign %{x}<br>Coupon cost $%{y:,.0f}<extra></extra>",
        )
    )
fig.update_layout(xaxis_title="Campaign", yaxis_title="Dollars")
st.plotly_chart(finish(fig, "Campaigns, from the ones that gave cash back to the ones that added it"), width="stretch")
if negative:
    worst = scored.iloc[0]
    roi_value = worst.get("roi")
    roi_text = f"{float(roi_value):.2f}" if roi_value == roi_value and roi_value is not None else "n/a"
    note(
        f"Campaign {worst['campaign_id']} ({worst.get('campaign_type')}) is the clearest miss: "
        f"incremental net sales {money(worst['incremental_sales'])} on coupon cost {money(worst.get('coupon_cost'))} "
        f"(ROI {roi_text}). "
        "The spread across households is wide, so I treat the sign as the finding and the dollar as an estimate."
    )
else:
    note("None of the scored campaigns came in below baseline in this build. I would still read the smallest one before calling the set a success.")

show_cols = [
    c
    for c in [
        "campaign_id",
        "campaign_type",
        "start_date",
        "end_date",
        "n_treated",
        "n_control",
        "incremental_sales",
        "coupon_cost",
        "roi",
        "redemption_rate",
        "status",
        "window_clipped",
    ]
    if c in campaigns.columns
]
display = campaigns.sort_values("incremental_sales")[show_cols].copy()
if "redemption_rate" in display.columns:
    display["redemption_rate"] = display["redemption_rate"].map(lambda v: None if pd.isna(v) else float(v))
st.dataframe(
    display,
    hide_index=True,
    width="stretch",
    column_config={
        "incremental_sales": st.column_config.NumberColumn("Incremental net sales", format="$%,.0f"),
        "coupon_cost": st.column_config.NumberColumn("Coupon + match", format="$%,.0f"),
        "roi": st.column_config.NumberColumn("ROI proxy", format="%.2f"),
        "redemption_rate": st.column_config.NumberColumn("Redemption rate", format="%.2%"),
    },
)
note("Redemption rate is redemptions divided by mailed households times distinct coupon UPCs. It is a thin rate because most mailed households never redeem. I do not join the product list before counting, or the same redemption would be counted once per product on the coupon.")

if not categories.empty:
    departments = sorted(categories["department"].dropna().unique())
    choice = st.selectbox("Department", departments, index=departments.index("MEAT") if "MEAT" in departments else 0)
    part = categories.loc[categories["department"].eq(choice)].sort_values("incremental_sales", ascending=False).head(12)
    part = part.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            y=part["product_category"],
            x=part["lift_pct"],
            orientation="h",
            marker_color=[GREEN if v >= 0 else BRICK for v in part["lift_pct"]],
            hovertemplate="%{y}<br>Lift %{x:.1%}<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="Feature lift versus the pair's own quiet weeks", xaxis_tickformat=".0%")
    st.plotly_chart(finish(fig, f"{choice}: category lift on the matched panel"), width="stretch")
    note(
        "This is not the campaign test. It is the same item in the same store, featured versus not, "
        "zero-filled between its first and last observed week, and only kept when I have at least four quiet weeks."
    )

if not depth.empty and "depth_bin" in depth.columns:
    st.subheader("Discount depth, described rather than modelled")
    st.dataframe(depth, hide_index=True, width="stretch")
    note("Terciles of feature-week discount depth against sales-weighted lift. A deeper cut is not automatically a better lift. I am not calling this an elasticity.")

if not worked.empty:
    row = worked.iloc[0].to_dict()
    if row.get("department"):
        st.subheader(f"One category I would walk someone through: {row.get('department')} / {row.get('product_category')}")
        st.write(
            f"I kept {int(row.get('n_product_stores') or 0)} product-store pairs. "
            f"On their feature weeks they took in {money(row.get('feature_sales'))}. "
            f"Their own quiet-week run-rate, stretched across those same weeks, says {money(row.get('counterfactual_sales'))}. "
            f"The gap is {money(row.get('incremental_sales'))}, a lift of {pct(row.get('lift_pct'))}, "
            f"against {money(row.get('discount_cost'))} of recorded discounts (ROI proxy {row.get('roi')})."
        )
        st.write(
            "If I were choosing a feature for next weekend I would start here only if the lift survives a look at the weeks themselves. "
            "A category can look good because the feature weeks happened to be the busy ones. The campaign page is the stricter test, because it has a control group."
        )
