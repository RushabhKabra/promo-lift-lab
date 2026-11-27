"""Periodic-review order quantities from the pre-holdout history.

The order cycle is one week. Lead time is an argument, default one week,
because this panel has no distribution-centre file. Service level is the
probability of covering demand over the protection period under a normal
assumption. That assumption is rough on intermittent store-SKU demand. I
use it because it is the formula a replenishment meeting already knows,
and I say where it is thin.

    protection weeks = lead time + review interval
    safety stock     = z × σ_quiet × sqrt(protection)
    reorder point    = quiet weekly mean × lead time + z × σ_quiet × sqrt(lead time)
    order-up-to      = quiet weekly mean × protection + safety stock

σ_quiet is the sample standard deviation of quiet weeks before the holdout.
Promo spikes stay out of it. The feature order-up-to swaps in the feature
weekly mean and keeps the same safety stock, so the lift is planned in the
forecast instead of buried in the buffer.

Suggested order quantity equals the order-up-to level. On-hand and on-order
are not in the data, so this is the order I would place if the pipeline
were empty. It is not a store's true order.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

DEFAULT_LEAD_TIME_WEEKS = 1
DEFAULT_REVIEW_WEEKS = 1
DEFAULT_SERVICE_LEVEL = 0.95
MIN_FEATURE_WEEKS_FOR_RATE = 2
MIN_QUIET_WEEKS_FOR_SIGMA = 2

SUM_COLUMNS = [
    "holdout_units",
    "holdout_feature_units",
    "holdout_quiet_units",
    "holdout_feature_weeks",
    "holdout_feature_weeks_above_quiet_mean",
    "holdout_feature_weeks_above_cover",
    "holdout_quiet_weeks",
    "units_short_vs_quiet_mean",
    "units_short_vs_service_cover",
    "units_extra_if_feature_rate_on_quiet",
    "units_extra_week_after_feature",
    "suggested_order_qty",
    "safety_stock_units",
    "reorder_point_units",
    "order_up_to_units",
]


def service_z(service_level: float) -> float:
    if not 0.5 < float(service_level) < 1.0:
        raise ValueError(f"service level must be between 0.5 and 1, got {service_level}")
    return float(norm.ppf(service_level))


def build_policy(
    panel: pd.DataFrame,
    holdout_weeks: list[int],
    lead_time_weeks: int = DEFAULT_LEAD_TIME_WEEKS,
    review_weeks: int = DEFAULT_REVIEW_WEEKS,
    service_level: float = DEFAULT_SERVICE_LEVEL,
) -> pd.DataFrame:
    if lead_time_weeks <= 0 or review_weeks <= 0:
        raise ValueError("lead time and review interval are in weeks and must be positive")
    if panel.empty:
        return pd.DataFrame()

    z = service_z(service_level)
    protection = float(lead_time_weeks + review_weeks)
    holdout_set = set(int(w) for w in holdout_weeks)
    work = panel.sort_values(["product_id", "store_id", "week_no"]).copy()
    keys = ["product_id", "store_id"]
    grouped = work.groupby(keys, sort=False)
    work["prev_units"] = grouped["units"].shift(1)
    work["prev_feature"] = grouped["on_feature"].shift(1)

    pre = work.loc[~work["week_no"].isin(holdout_set)]
    stats = _history_stats(pre)
    measures = [column for column in stats.columns if column not in ("department", "product_category")]
    post = work.loc[work["week_no"].isin(holdout_set)].merge(stats[measures], on=keys, how="left")
    cover = post["mean_quiet_units"] + z * post["sigma_quiet_units"]
    on_feature = post["on_feature"].astype(bool)
    has_feature_rate = post["mean_feature_units"].notna()
    post["short_quiet"] = np.where(on_feature, np.maximum(post["units"] - post["mean_quiet_units"], 0.0), 0.0)
    post["short_cover"] = np.where(on_feature, np.maximum(post["units"] - cover, 0.0), 0.0)
    post["above_quiet"] = on_feature & (post["units"] > post["mean_quiet_units"])
    post["above_cover"] = on_feature & (post["units"] > cover)
    post["extra_rate"] = np.where(
        ~on_feature & has_feature_rate,
        np.maximum(post["mean_feature_units"] - post["units"], 0.0),
        0.0,
    )
    prev_feature = post["prev_feature"].eq(True)
    post["extra_after"] = np.where(
        ~on_feature & prev_feature,
        np.maximum(post["prev_units"].fillna(0.0) - post["units"], 0.0),
        0.0,
    )
    post["feature_units"] = np.where(on_feature, post["units"], 0.0)
    post["quiet_units"] = np.where(~on_feature, post["units"], 0.0)

    holdout_totals = post.groupby(keys, as_index=False).agg(
        holdout_units=("units", "sum"),
        holdout_feature_units=("feature_units", "sum"),
        holdout_quiet_units=("quiet_units", "sum"),
        holdout_feature_weeks=("on_feature", "sum"),
        holdout_feature_weeks_above_quiet_mean=("above_quiet", "sum"),
        holdout_feature_weeks_above_cover=("above_cover", "sum"),
        holdout_quiet_weeks=("on_feature", lambda s: int((~s.astype(bool)).sum())),
        units_short_vs_quiet_mean=("short_quiet", "sum"),
        units_short_vs_service_cover=("short_cover", "sum"),
        units_extra_if_feature_rate_on_quiet=("extra_rate", "sum"),
        units_extra_week_after_feature=("extra_after", "sum"),
    )
    policy = stats.merge(holdout_totals, on=keys, how="left")
    for column in (
        "holdout_units",
        "holdout_feature_units",
        "holdout_quiet_units",
        "holdout_feature_weeks",
        "holdout_feature_weeks_above_quiet_mean",
        "holdout_feature_weeks_above_cover",
        "holdout_quiet_weeks",
        "units_short_vs_quiet_mean",
        "units_short_vs_service_cover",
        "units_extra_if_feature_rate_on_quiet",
        "units_extra_week_after_feature",
    ):
        policy[column] = policy[column].fillna(0.0)

    sigma = policy["sigma_quiet_units"].to_numpy(dtype=float)
    mean_quiet = policy["mean_quiet_units"].to_numpy(dtype=float)
    mean_feature = policy["mean_feature_units"].to_numpy(dtype=float)
    safety = z * sigma * np.sqrt(protection)
    reorder = mean_quiet * float(lead_time_weeks) + z * sigma * np.sqrt(float(lead_time_weeks))
    order_up_to = mean_quiet * protection + safety
    feature_base = np.where(np.isfinite(mean_feature), mean_feature, mean_quiet)
    feature_order = feature_base * protection + safety

    policy["lead_time_weeks"] = int(lead_time_weeks)
    policy["review_weeks"] = int(review_weeks)
    policy["service_level"] = float(service_level)
    policy["service_z"] = z
    policy["safety_stock_units"] = np.maximum(safety, 0.0)
    policy["reorder_point_units"] = np.maximum(reorder, 0.0)
    policy["order_up_to_units"] = np.maximum(order_up_to, 0.0)
    policy["suggested_order_qty"] = policy["order_up_to_units"]
    policy["feature_order_up_to_units"] = np.maximum(feature_order, 0.0)
    policy["suggested_feature_order_qty"] = policy["feature_order_up_to_units"]

    one_week_cover = mean_quiet + z * sigma
    enough_feature = policy["n_pre_feature_weeks"].to_numpy(dtype=int) >= MIN_FEATURE_WEEKS_FOR_RATE
    policy["stockout_risk_if_base_order"] = enough_feature & np.isfinite(mean_feature) & (mean_feature > one_week_cover)
    policy["overstock_risk_if_promo_repeated"] = (
        enough_feature & np.isfinite(mean_feature) & ((mean_feature - mean_quiet) > policy["safety_stock_units"].to_numpy())
    )
    policy["stockout_risk_if_base_order"] = policy["stockout_risk_if_base_order"].astype(bool)
    policy["overstock_risk_if_promo_repeated"] = policy["overstock_risk_if_promo_repeated"].astype(bool)
    return policy


def rollup(policy: pd.DataFrame, group: list[str]) -> pd.DataFrame:
    if policy.empty:
        return pd.DataFrame()
    named = {column: (column, "sum") for column in SUM_COLUMNS if column in policy.columns}
    named["n_series"] = ("product_id", "size")
    named["n_stockout_risk"] = ("stockout_risk_if_base_order", "sum")
    named["n_overstock_risk"] = ("overstock_risk_if_promo_repeated", "sum")
    out = policy.groupby(group, as_index=False).agg(**named)
    out["n_series"] = out["n_series"].astype(int)
    out["n_stockout_risk"] = out["n_stockout_risk"].astype(int)
    out["n_overstock_risk"] = out["n_overstock_risk"].astype(int)
    feature_weeks = out["holdout_feature_weeks"].replace(0, np.nan)
    out["share_feature_weeks_above_quiet_mean"] = out["holdout_feature_weeks_above_quiet_mean"] / feature_weeks
    out["share_feature_weeks_above_cover"] = out["holdout_feature_weeks_above_cover"] / feature_weeks
    out["share_series_stockout_risk"] = out["n_stockout_risk"] / out["n_series"]
    out["share_series_overstock_risk"] = out["n_overstock_risk"] / out["n_series"]
    return out.sort_values("units_short_vs_quiet_mean", ascending=False).reset_index(drop=True)


def _history_stats(pre: pd.DataFrame) -> pd.DataFrame:
    keys = ["product_id", "store_id"]
    identity = pre.groupby(keys, as_index=False).agg(
        department=("department", "first"),
        product_category=("product_category", "first"),
        n_pre_weeks=("week_no", "size"),
        mean_weekly_units=("units", "mean"),
    )
    quiet = pre.loc[~pre["on_feature"].astype(bool)]
    feature = pre.loc[pre["on_feature"].astype(bool)]
    quiet_stats = quiet.groupby(keys).agg(
        n_pre_quiet_weeks=("units", "size"),
        mean_quiet_units=("units", "mean"),
        sigma_quiet_units=("units", lambda s: float(s.std(ddof=1)) if len(s) >= MIN_QUIET_WEEKS_FOR_SIGMA else np.nan),
    )
    all_sigma = (
        pre.groupby(keys)["units"]
        .agg(lambda s: float(s.std(ddof=1)) if len(s) >= MIN_QUIET_WEEKS_FOR_SIGMA else 0.0)
        .rename("sigma_all")
        .reset_index()
    )
    feature_stats = feature.groupby(keys).agg(
        n_pre_feature_weeks=("units", "size"),
        mean_feature_raw=("units", "mean"),
    )
    stats = identity.merge(quiet_stats, on=keys, how="left")
    stats = stats.merge(feature_stats, on=keys, how="left")
    stats = stats.merge(all_sigma, on=keys, how="left")
    stats["n_pre_quiet_weeks"] = stats["n_pre_quiet_weeks"].fillna(0).astype(int)
    stats["n_pre_feature_weeks"] = stats["n_pre_feature_weeks"].fillna(0).astype(int)
    stats["mean_quiet_units"] = stats["mean_quiet_units"].fillna(stats["mean_weekly_units"])
    stats["sigma_quiet_units"] = stats["sigma_quiet_units"].where(
        stats["n_pre_quiet_weeks"] >= MIN_QUIET_WEEKS_FOR_SIGMA,
        stats["sigma_all"],
    )
    stats["sigma_quiet_units"] = stats["sigma_quiet_units"].fillna(0.0).clip(lower=0.0)
    enough = stats["n_pre_feature_weeks"] >= MIN_FEATURE_WEEKS_FOR_RATE
    stats["mean_feature_units"] = stats["mean_feature_raw"].where(enough)
    return stats.drop(columns=["mean_feature_raw", "sigma_all"])
