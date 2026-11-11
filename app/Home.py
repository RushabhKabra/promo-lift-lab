"""Opening page. The question, then the numbers I would actually say out loud."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import headline  # noqa: E402
from app.theme import inject, money, pct  # noqa: E402

st.set_page_config(page_title="promo-lift lab", page_icon=":seedling:", layout="wide")
inject()

st.markdown('<p class="wordmark">promo-lift lab</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="tagline">A weekend lab for measuring whether grocery promotions actually earn their keep.</p>',
    unsafe_allow_html=True,
)

numbers = headline()
if not numbers:
    st.info("The warehouse is empty. From the repo root: `make ingest && make build`.")
    st.stop()

start = str(numbers.get("period_start") or "")[:10]
end = str(numbers.get("period_end") or "")[:10]
st.write(
    f"I wanted to know how much of a promoted week's volume would have happened anyway. "
    f"Grocery data has been part of my weeks for long enough that the question stopped being abstract, "
    f"so I built a small warehouse around a public household panel and made the metrics argue with me. "
    f"The window below is {start} to {end}."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Net sales", money(numbers.get("net_sales")))
c2.metric("Feature lift", pct(numbers.get("feature_lift_pct")))
c3.metric("Feature incremental", money(numbers.get("feature_incremental_sales")))
c4.metric("Campaigns below baseline", f"{int(numbers.get('n_campaigns_negative_incremental') or 0)}")

st.caption(
    "Feature lift is the matched product-store comparison, not a campaign test. "
    f"It covers {pct(numbers.get('feature_coverage'))} of non-fuel feature-week sales. "
    "The campaign count is difference-in-differences on mailed households."
)

left, right = st.columns(2)
with left:
    st.subheader("Where to look")
    st.markdown(
        """
        - **Overview** — the year, the discount bill, and weeks that do not look like their neighbours.
        - **Promotion lift** — campaigns that paid, campaigns that did not, and one category walked in full.
        - **Forecast** — a tree model against the mean of the previous four weeks.
        - **Customers** — RFM slices, who buys on discount, and which departments share a basket.
        - **Ask the data** — questions answered from the certified tables, with the metric and the period underneath.
        """
    )
with right:
    st.subheader("What I will not pretend")
    st.markdown(
        """
        These campaigns were not randomized. Households who were mailed may already have been different.
        The panel is frequent shoppers, not every household a store sees.
        `sales_value` is the cash the retailer received, and the three discount fields are costs on top of that.
        There is no wholesale cost here, so ROI is a proxy.
        """
    )
