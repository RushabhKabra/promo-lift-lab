"""Discount depth, payback, and the promotions that did not earn their discount.

Everything here reads the certified lift and campaign extracts. Nothing goes back
to receipt lines, so the totals tie to the feature headline by construction.

Discount depth on a category is the share of the pre-discount ring given away in
its feature weeks: discount_cost / (feature_sales + discount_cost). It is an
average across the category's product-store pairs, not a shelf price cut.

Payback is the lab's ROI proxy: incremental net sales per discount dollar. It is
a sales measure. There is no cost of goods in the panel, so a payback below 1
means the extra sales did not even cover the discount, before any margin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEPTH_EDGES = (0.10, 0.20, 0.30, 0.40)
DEPTH_LABELS = ("0% (no discount)", "0-10%", "10-20%", "20-30%", "30-40%", "40%+")


def depth_band(depth: float, discount: float) -> str:
    """Name the band for one category's feature-week discount depth."""
    if discount <= 0 or not np.isfinite(depth) or depth <= 0:
        return DEPTH_LABELS[0]
    for edge, label in zip(DEPTH_EDGES, DEPTH_LABELS[1:]):
        if depth < edge:
            return label
    return DEPTH_LABELS[-1]


def depth_by_category(category_lift: pd.DataFrame) -> pd.DataFrame:
    """One row per category with its depth, band, payback and shortfall."""
    out = category_lift.copy()
    gross = out["feature_sales"] + out["discount_cost"]
    out["discount_depth"] = np.where(gross > 0, out["discount_cost"] / gross, 0.0)
    out["depth_band"] = [
        depth_band(d, c) for d, c in zip(out["discount_depth"], out["discount_cost"])
    ]
    out["payback"] = np.where(
        out["discount_cost"] > 0, out["incremental_sales"] / out["discount_cost"], np.nan
    )
    out["incremental_less_discount"] = out["incremental_sales"] - out["discount_cost"]
    keep = [
        "department",
        "product_category",
        "n_product_stores",
        "depth_band",
        "discount_depth",
        "feature_sales",
        "counterfactual_sales",
        "incremental_sales",
        "discount_cost",
        "payback",
        "incremental_less_discount",
    ]
    return out[keep].sort_values(["discount_depth", "product_category"]).reset_index(drop=True)


def depth_bands(by_category: pd.DataFrame) -> pd.DataFrame:
    """Roll categories up to depth bands; payback is a ratio of sums, not a mean of ratios."""
    grouped = (
        by_category.groupby("depth_band", sort=False)
        .agg(
            categories=("product_category", "count"),
            product_store_pairs=("n_product_stores", "sum"),
            feature_sales=("feature_sales", "sum"),
            counterfactual_sales=("counterfactual_sales", "sum"),
            incremental_sales=("incremental_sales", "sum"),
            discount_cost=("discount_cost", "sum"),
        )
        .reindex(list(DEPTH_LABELS))
        .dropna(how="all")
        .reset_index()
    )
    grouped["lift_pct"] = grouped["feature_sales"] / grouped["counterfactual_sales"] - 1
    grouped["payback"] = np.where(
        grouped["discount_cost"] > 0,
        grouped["incremental_sales"] / grouped["discount_cost"],
        np.nan,
    )
    grouped["incremental_less_discount"] = grouped["incremental_sales"] - grouped["discount_cost"]
    return grouped


def money_losing_campaigns(campaign_results: pd.DataFrame) -> pd.DataFrame:
    """Scored campaigns whose incremental net sales came out below zero, worst first."""
    scored = campaign_results[campaign_results["status"] == "ok"].copy()
    losing = scored[scored["incremental_sales"] < 0].copy()
    losing["interval_excludes_zero"] = losing["did_high"] < 0
    keep = [
        "campaign_id",
        "campaign_type",
        "start_date",
        "end_date",
        "n_treated",
        "incremental_sales",
        "coupon_cost",
        "roi",
        "did_low",
        "did_high",
        "interval_excludes_zero",
    ]
    return losing[keep].sort_values("incremental_sales").reset_index(drop=True)


def money_losing_categories(by_category: pd.DataFrame, min_pairs: int = 20) -> pd.DataFrame:
    """Discounted categories whose feature-week extra sales fell short of the discount.

    Categories with fewer than ``min_pairs`` product-store pairs are left out of the
    list (they stay in the band totals) because one pair can swing the ratio.
    """
    mask = (
        (by_category["discount_cost"] > 0)
        & (by_category["incremental_less_discount"] < 0)
        & (by_category["n_product_stores"] >= min_pairs)
    )
    return (
        by_category[mask]
        .sort_values("incremental_less_discount")
        .reset_index(drop=True)
    )
