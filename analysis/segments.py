"""RFM slices plus a simple read of who spends under a discount."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.metrics import PROMO_SENSITIVE_GROSS_SHARE, PROMO_SENSITIVE_MIN_BASKETS


def rfm_table(transactions: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per household.

    Recency is days since the last trip. Frequency is distinct baskets.
    Monetary value is net sales, the cash the retailer received.
    Quintile 5 is the most recent, the most frequent, or the highest spend.
    """
    work = transactions.copy()
    work["transaction_timestamp"] = pd.to_datetime(work["transaction_timestamp"])
    if as_of is None:
        as_of = work["transaction_timestamp"].max()
    grouped = work.groupby("household_id", as_index=False).agg(
        last_purchase=("transaction_timestamp", "max"),
        frequency=("basket_id", "nunique"),
        monetary=("sales_value", "sum"),
        discount_cost=("discount_cost", "sum"),
        gross_sales=("gross_sales", "sum"),
    )
    discounted = (
        work.loc[work["discount_cost"] > 0].groupby("household_id")["basket_id"].nunique().rename("discounted_baskets")
    )
    grouped = grouped.merge(discounted, on="household_id", how="left")
    grouped["discounted_baskets"] = grouped["discounted_baskets"].fillna(0)
    grouped["recency_days"] = (as_of.normalize() - grouped["last_purchase"].dt.normalize()).dt.days
    grouped["discount_share_of_gross"] = np.where(
        grouped["gross_sales"] > 0, grouped["discount_cost"] / grouped["gross_sales"], np.nan
    )
    grouped["r_quintile"] = _quintile(grouped["recency_days"], higher_is_better=False)
    grouped["f_quintile"] = _quintile(grouped["frequency"], higher_is_better=True)
    grouped["m_quintile"] = _quintile(grouped["monetary"], higher_is_better=True)
    grouped["segment"] = [
        _label(r, f, m)
        for r, f, m in zip(grouped["r_quintile"], grouped["f_quintile"], grouped["m_quintile"], strict=True)
    ]
    grouped["promo_sensitive"] = (grouped["discount_share_of_gross"] >= PROMO_SENSITIVE_GROSS_SHARE) & (
        grouped["frequency"] >= PROMO_SENSITIVE_MIN_BASKETS
    )
    grouped["as_of_date"] = as_of.normalize()
    return grouped


def _quintile(values: pd.Series, higher_is_better: bool) -> pd.Series:
    # rank first so ties don't collapse a bin into nothing on a small fixture.
    ranks = values.rank(method="average", ascending=higher_is_better)
    try:
        bins = pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
    except ValueError:
        bins = pd.Series(3, index=values.index)
    return bins.astype(int)


def _label(r: int, f: int, m: int) -> str:
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"
    if f >= 4 and m >= 3:
        return "Loyal"
    if m >= 4:
        return "Big spenders"
    if r >= 4 and f <= 2:
        return "Promising"
    if r <= 2 and f >= 3 and m >= 3:
        return "At risk"
    if r <= 2 and f <= 2:
        return "Hibernating"
    return "Regulars"


def segment_summary(households: pd.DataFrame) -> pd.DataFrame:
    if households.empty:
        return households
    total_sales = households["monetary"].sum()
    total_hh = len(households)
    rows = []
    for segment, part in households.groupby("segment"):
        rows.append(
            {
                "segment": segment,
                "households": int(len(part)),
                "household_share": len(part) / total_hh,
                "net_sales": float(part["monetary"].sum()),
                "sales_share": float(part["monetary"].sum() / total_sales) if total_sales else np.nan,
                "avg_recency_days": float(part["recency_days"].mean()),
                "avg_frequency": float(part["frequency"].mean()),
                "avg_monetary": float(part["monetary"].mean()),
                "promo_sensitive_share": float(part["promo_sensitive"].mean()),
                "avg_discount_share_of_gross": float(part["discount_share_of_gross"].mean()),
            }
        )
    order = ["Champions", "Loyal", "Big spenders", "Regulars", "Promising", "At risk", "Hibernating"]
    out = pd.DataFrame(rows)
    out["segment"] = pd.Categorical(out["segment"], categories=order, ordered=True)
    return out.sort_values("segment").reset_index(drop=True)
