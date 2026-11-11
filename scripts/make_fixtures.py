"""Cut a relational slice of the processed cache for CI.

The slice is real rows. It is not large enough to re-estimate the findings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from warehouse.db import ROOT as PROJECT_ROOT  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
FIXTURES = PROJECT_ROOT / "data" / "fixtures"
WEEKS = set(range(10, 31))


def main() -> None:
    transactions = pd.read_parquet(PROCESSED / "transactions.parquet")
    week_col = "week_no" if "week_no" in transactions.columns else "week"
    counts = (
        transactions.loc[transactions[week_col].isin(WEEKS)]
        .groupby("store_id")
        .size()
        .sort_values(ascending=False)
    )
    stores = set(counts.head(2).index.astype(str))
    tx = transactions.loc[transactions["store_id"].astype(str).isin(stores) & transactions[week_col].isin(WEEKS)].copy()
    products = pd.read_parquet(PROCESSED / "products.parquet")
    products = products.loc[products["product_id"].isin(set(tx["product_id"]))]
    promotions = pd.read_parquet(PROCESSED / "promotions.parquet")
    promo_week = "week_no" if "week_no" in promotions.columns else "week"
    promotions = promotions.loc[
        promotions["store_id"].astype(str).isin(stores)
        & promotions["product_id"].isin(set(tx["product_id"]))
        & promotions[promo_week].isin(WEEKS)
    ]
    households = set(tx["household_id"].astype(str))
    campaigns = pd.read_parquet(PROCESSED / "campaigns.parquet")
    campaigns = campaigns.loc[campaigns["household_id"].astype(str).isin(households)]
    descriptions = pd.read_parquet(PROCESSED / "campaign_descriptions.parquet")
    # Keep descriptions that overlap the slice weeks via the campaign ids we kept,
    # plus any description whose dates might still be useful. Restrict to mailed campaigns.
    descriptions = descriptions.loc[descriptions["campaign_id"].isin(set(campaigns["campaign_id"]))]
    coupons = pd.read_parquet(PROCESSED / "coupons.parquet")
    coupons = coupons.loc[
        coupons["campaign_id"].isin(set(campaigns["campaign_id"]))
        & coupons["product_id"].isin(set(tx["product_id"]))
    ]
    redemptions = pd.read_parquet(PROCESSED / "coupon_redemptions.parquet")
    redemptions = redemptions.loc[
        redemptions["household_id"].astype(str).isin(households)
        & redemptions["campaign_id"].isin(set(descriptions["campaign_id"]))
    ]
    demographics = pd.read_parquet(PROCESSED / "demographics.parquet")
    demographics = demographics.loc[demographics["household_id"].astype(str).isin(households)]

    FIXTURES.mkdir(parents=True, exist_ok=True)
    frames = {
        "transactions": tx,
        "products": products,
        "promotions": promotions,
        "campaigns": campaigns,
        "campaign_descriptions": descriptions,
        "coupons": coupons,
        "coupon_redemptions": redemptions,
        "demographics": demographics,
    }
    for name, frame in frames.items():
        frame.to_parquet(FIXTURES / f"{name}.parquet", index=False)
        print(f"{name}: {len(frame):,}")


if __name__ == "__main__":
    main()
