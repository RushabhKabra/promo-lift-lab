"""Metric formulas shared by the analyses, the tests, and the glossary.

sales_value in the Complete Journey mirror is the cash the retailer received.
Discount columns in that mirror are non-negative amounts. The original study
files stored discounts as negatives; ingest flips that sign so every later
formula can assume a positive cost.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DISCOUNT_COLUMNS = ("retail_disc", "coupon_disc", "coupon_match_disc")

# A household is promo-sensitive when discounts are at least this share of the
# pre-discount ring, and the household has enough trips to make the share stable.
PROMO_SENSITIVE_GROSS_SHARE = 0.18
PROMO_SENSITIVE_MIN_BASKETS = 8

# Product-store pairs need this many observed sale weeks before I trust a baseline.
MIN_SALE_WEEKS = 6
MIN_BASE_WEEKS = 4
MIN_PROMO_WEEKS = 1
CAMPAIGN_PRE_WEEKS = 4
CAMPAIGN_MIN_TREATED = 25


def normalize_discount_signs(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy where discount columns are costs (non-negative).

    If most non-zero discounts are negative, they are signed reductions and
    get multiplied by -1. Magnitudes that are already positive are left alone.
    """
    out = df.copy()
    present = [c for c in DISCOUNT_COLUMNS if c in out.columns]
    if not present:
        return out
    stacked = out[present].apply(pd.to_numeric, errors="coerce")
    nonzero = stacked.to_numpy().ravel()
    nonzero = nonzero[np.isfinite(nonzero) & (nonzero != 0)]
    if len(nonzero) and np.mean(nonzero < 0) > 0.9:
        for col in present:
            out[col] = pd.to_numeric(out[col], errors="coerce") * -1
    else:
        for col in present:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def discount_cost(retail, coupon, match) -> pd.Series:
    retail = pd.to_numeric(retail, errors="coerce").fillna(0.0)
    coupon = pd.to_numeric(coupon, errors="coerce").fillna(0.0)
    match = pd.to_numeric(match, errors="coerce").fillna(0.0)
    return retail + coupon + match


def gross_sales(sales_value, retail, coupon, match) -> pd.Series:
    """Pre-discount ring proxy: cash received plus the three recorded discounts."""
    net = pd.to_numeric(sales_value, errors="coerce").fillna(0.0)
    return net + discount_cost(retail, coupon, match)


def roi(incremental_sales, discount) -> float:
    """Promo ROI proxy. Undefined when there is no positive discount cost."""
    if discount is None or not np.isfinite(discount) or discount <= 0:
        return np.nan
    if incremental_sales is None or not np.isfinite(incremental_sales):
        return np.nan
    return float(incremental_sales) / float(discount)


def redemption_rate(redemptions: float, targeted_households: float, distinct_upcs: float) -> float:
    """Redemptions divided by targeted households times distinct coupon UPCs.

    The coupon file is a product list, not a mail log. Multiplying households
    by UPCs is a stand-in for coupons issued, and it is easy to overstate
    the denominator. I still use it because the study does not record how
    many coupons were actually placed in each mailbox.
    """
    issued = float(targeted_households) * float(distinct_upcs)
    if issued <= 0:
        return np.nan
    return float(redemptions) / issued


def mape(actual, predicted) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(predicted) & (np.abs(actual) > 0)
    if not mask.any():
        return np.nan
    return float(np.mean(np.abs(actual[mask] - predicted[mask]) / np.abs(actual[mask])))


def smape(actual, predicted) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denom = np.abs(actual) + np.abs(predicted)
    mask = np.isfinite(actual) & np.isfinite(predicted) & (denom > 0)
    if not mask.any():
        return np.nan
    return float(np.mean(2.0 * np.abs(actual[mask] - predicted[mask]) / denom[mask]))


def bias(actual, predicted) -> float:
    """Mean prediction minus actual. Positive means the forecast ran hot."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(predicted)
    if not mask.any():
        return np.nan
    return float(np.mean(predicted[mask] - actual[mask]))


def weighted_mape(actual, predicted) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0)
    if not mask.any():
        return np.nan
    return float(np.sum(np.abs(actual[mask] - predicted[mask])) / np.sum(actual[mask]))
