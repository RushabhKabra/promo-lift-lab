"""Baseline versus feature lift, and campaign incrementality.

The feature comparison is observational: the same product in the same store,
on weeks it was on display or in the mailer versus weeks it was not. Campaign
incrementality is a difference-in-differences against households that were
not mailed the campaign. Neither is a randomized test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.metrics import (
    CAMPAIGN_MIN_TREATED,
    CAMPAIGN_PRE_WEEKS,
    MIN_BASE_WEEKS,
    MIN_PROMO_WEEKS,
    roi,
)


def product_store_baseline(
    weekly: pd.DataFrame,
    min_base_weeks: int = MIN_BASE_WEEKS,
    min_promo_weeks: int = MIN_PROMO_WEEKS,
) -> pd.DataFrame:
    """Compare feature weeks with other weeks inside each product-store span.

    `weekly` is already zero-filled across the weeks between a pair's first
    and last observed sale. `on_feature` marks a display or mailer placement.
    Means on the two kinds of week are the baseline and the feature run-rate.
    Incremental totals multiply the per-week gap by the number of feature weeks.
    """
    required = {"product_id", "store_id", "week_no", "units", "net_sales", "discount_cost", "on_feature"}
    missing = required - set(weekly.columns)
    if missing:
        raise ValueError(f"weekly panel missing {sorted(missing)}")
    if weekly.empty:
        return pd.DataFrame()

    frame = weekly.copy()
    frame["on_feature"] = frame["on_feature"].astype(bool)
    frame["base_units"] = np.where(~frame["on_feature"], frame["units"], np.nan)
    frame["promo_units_obs"] = np.where(frame["on_feature"], frame["units"], np.nan)
    frame["base_sales"] = np.where(~frame["on_feature"], frame["net_sales"], np.nan)
    frame["promo_sales_obs"] = np.where(frame["on_feature"], frame["net_sales"], np.nan)
    frame["base_discount"] = np.where(~frame["on_feature"], frame["discount_cost"], np.nan)
    frame["promo_discount"] = np.where(frame["on_feature"], frame["discount_cost"], np.nan)
    frame["base_flag"] = ~frame["on_feature"]
    grouped = frame.groupby(["product_id", "store_id"], sort=False)
    summary = pd.DataFrame(
        {
            "n_base_weeks": grouped["base_flag"].sum().astype(int),
            "n_promo_weeks": grouped["on_feature"].sum().astype(int),
        }
    )
    summary["baseline_units"] = grouped["base_units"].mean()
    summary["promo_units"] = grouped["promo_units_obs"].mean()
    summary["baseline_sales"] = grouped["base_sales"].mean()
    summary["promo_sales"] = grouped["promo_sales_obs"].mean()
    summary["baseline_discount_per_week"] = grouped["base_discount"].mean()
    summary["promo_discount_per_week"] = grouped["promo_discount"].mean()
    if "department" in frame.columns:
        summary["department"] = grouped["department"].first()
    if "product_category" in frame.columns:
        summary["product_category"] = grouped["product_category"].first()
    summary = summary.reset_index()
    summary = summary.loc[
        (summary["n_base_weeks"] >= min_base_weeks) & (summary["n_promo_weeks"] >= min_promo_weeks)
    ].copy()
    if summary.empty:
        return summary

    summary["incremental_units_per_week"] = summary["promo_units"] - summary["baseline_units"]
    summary["incremental_sales_per_week"] = summary["promo_sales"] - summary["baseline_sales"]
    summary["incremental_units"] = summary["incremental_units_per_week"] * summary["n_promo_weeks"]
    summary["incremental_sales"] = summary["incremental_sales_per_week"] * summary["n_promo_weeks"]
    summary["discount_cost"] = summary["promo_discount_per_week"] * summary["n_promo_weeks"]
    summary["baseline_discount"] = summary["baseline_discount_per_week"] * summary["n_promo_weeks"]
    summary["incremental_discount"] = summary["discount_cost"] - summary["baseline_discount"]
    summary["counterfactual_sales"] = summary["baseline_sales"] * summary["n_promo_weeks"]
    summary["feature_sales"] = summary["promo_sales"] * summary["n_promo_weeks"]
    summary["lift_pct"] = np.where(
        summary["baseline_sales"] > 0,
        summary["promo_sales"] / summary["baseline_sales"] - 1,
        np.nan,
    )
    summary["roi"] = [
        roi(inc, cost) for inc, cost in zip(summary["incremental_sales"], summary["discount_cost"], strict=True)
    ]
    return summary.reset_index(drop=True)


def rollup_lift(product_store: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Sales-weighted rollup. Percentages are not averaged."""
    if product_store.empty:
        return product_store
    rows = []
    for key, part in product_store.groupby(group_cols, dropna=False, sort=False, observed=True):
        if not isinstance(key, tuple):
            key = (key,)
        feature_sales = float(part["feature_sales"].sum())
        counterfactual = float(part["counterfactual_sales"].sum())
        incremental = float(part["incremental_sales"].sum())
        discount = float(part["discount_cost"].sum())
        record = dict(zip(group_cols, key, strict=True))
        record.update(
            {
                "n_product_stores": int(len(part)),
                "feature_sales": feature_sales,
                "counterfactual_sales": counterfactual,
                "incremental_sales": incremental,
                "incremental_units": float(part["incremental_units"].sum()),
                "discount_cost": discount,
                "incremental_discount": float(part["incremental_discount"].sum()),
                "lift_pct": (feature_sales / counterfactual - 1) if counterfactual > 0 else np.nan,
                "roi": roi(incremental, discount),
            }
        )
        rows.append(record)
    out = pd.DataFrame(rows)
    return out.sort_values("incremental_sales", ascending=False).reset_index(drop=True)


def discount_depth_bins(product_store: pd.DataFrame) -> pd.DataFrame:
    """Terciles of discount depth against sales-weighted lift.

    Depth is feature-week discount divided by the pre-discount ring on those
    same weeks. It is a description of how lift lines up with price cuts, not
    a structural elasticity.
    """
    if product_store.empty:
        return pd.DataFrame()
    frame = product_store.copy()
    gross = frame["feature_sales"] + frame["discount_cost"]
    frame["depth"] = np.where(gross > 0, frame["discount_cost"] / gross, np.nan)
    frame = frame.loc[frame["depth"].notna() & np.isfinite(frame["lift_pct"])].copy()
    if frame.empty:
        return frame
    try:
        frame["depth_bin"] = pd.qcut(frame["depth"], 3, labels=["shallow", "middling", "deep"])
    except ValueError:
        frame["depth_bin"] = "all"
    rolled = rollup_lift(frame, ["depth_bin"])
    rolled["median_depth"] = frame.groupby("depth_bin", observed=True)["depth"].median().reindex(rolled["depth_bin"]).to_numpy()
    return rolled


def campaign_did(
    household_week: pd.DataFrame,
    exposure: pd.DataFrame,
    windows: pd.DataFrame,
    costs: pd.DataFrame | None = None,
    pre_weeks: int = CAMPAIGN_PRE_WEEKS,
    min_treated: int = CAMPAIGN_MIN_TREATED,
) -> pd.DataFrame:
    """Difference-in-differences on household weekly net sales.

    household_week: household_id, week_no, net_sales (weeks with no trip omitted).
    exposure: campaign_id, household_id for households who were mailed.
    windows: campaign_id, campaign_type, start_week, end_week, start_date, end_date,
             and optional window_clipped.
    costs: campaign_id, coupon_cost, redemptions, targeted_households, distinct_upcs.

    Control households are people who shopped during the year and were not
    mailed any campaign that overlaps the pre window or the campaign window.
    """
    if household_week.empty or windows.empty:
        return pd.DataFrame()

    spend = household_week.pivot_table(
        index="household_id", columns="week_no", values="net_sales", aggfunc="sum", fill_value=0.0
    )
    all_weeks = set(int(w) for w in spend.columns)
    households = set(spend.index.astype(str))
    exposure = exposure.copy()
    exposure["household_id"] = exposure["household_id"].astype(str)
    exposure["campaign_id"] = exposure["campaign_id"].astype(str)
    windows = windows.copy()
    windows["campaign_id"] = windows["campaign_id"].astype(str)

    # Which weeks each household is "busy" being in some campaign.
    campaign_weeks: dict[str, set[int]] = {}
    for row in windows.itertuples(index=False):
        start = int(row.start_week)
        end = int(row.end_week)
        campaign_weeks[str(row.campaign_id)] = set(range(start, end + 1)) & all_weeks

    treated_lookup = {
        cid: set(part["household_id"]) & households
        for cid, part in exposure.groupby("campaign_id")
    }

    occupied: dict[str, set[int]] = {hh: set() for hh in households}
    for cid, weeks in campaign_weeks.items():
        for hh in treated_lookup.get(cid, ()):
            occupied[hh].update(weeks)

    cost_lookup = {}
    if costs is not None and not costs.empty:
        for row in costs.itertuples(index=False):
            cost_lookup[str(row.campaign_id)] = row

    results = []
    for row in windows.itertuples(index=False):
        cid = str(row.campaign_id)
        post = [w for w in range(int(row.start_week), int(row.end_week) + 1) if w in all_weeks]
        if not post:
            results.append(_empty_campaign(row, "no_observed_weeks"))
            continue
        pre_candidates = [w for w in range(int(row.start_week) - pre_weeks, int(row.start_week)) if w in all_weeks]
        if len(pre_candidates) < 2:
            results.append(_empty_campaign(row, "insufficient_pre_period"))
            continue
        focus = set(pre_candidates) | set(post)
        treated = sorted(treated_lookup.get(cid, set()))
        control = sorted(
            hh for hh in households if hh not in treated_lookup.get(cid, set()) and occupied.get(hh, set()).isdisjoint(focus)
        )
        status = "ok"
        if len(treated) < min_treated:
            status = "small_treated_group"
        if len(control) < min_treated:
            status = "small_control_group"
        did_stats = _did_means(spend, treated, control, pre_candidates, post)
        coupon_cost = np.nan
        redemptions = np.nan
        targeted = float(len(treated_lookup.get(cid, set())))
        distinct_upcs = np.nan
        mailed = targeted
        if cid in cost_lookup:
            coupon_cost = float(getattr(cost_lookup[cid], "coupon_cost"))
            redemptions = float(getattr(cost_lookup[cid], "redemptions"))
            distinct_upcs = float(getattr(cost_lookup[cid], "distinct_upcs"))
            mailed = float(getattr(cost_lookup[cid], "mailed_households", targeted))
        incremental = did_stats["did_per_household_week"] * len(treated) * len(post)
        results.append(
            {
                "campaign_id": cid,
                "campaign_type": getattr(row, "campaign_type", pd.NA),
                "start_date": getattr(row, "start_date", pd.NA),
                "end_date": getattr(row, "end_date", pd.NA),
                "start_week": int(row.start_week),
                "end_week": int(row.end_week),
                "n_pre_weeks": len(pre_candidates),
                "n_post_weeks": len(post),
                "n_treated": len(treated),
                "n_control": len(control),
                "targeted_households": targeted,
                "mailed_households": mailed,
                "status": status,
                "window_clipped": bool(getattr(row, "window_clipped", False)),
                **did_stats,
                "incremental_sales": incremental,
                "coupon_cost": coupon_cost,
                "redemptions": redemptions,
                "distinct_upcs": distinct_upcs,
                "roi": roi(incremental, coupon_cost),
                "method": "difference_in_differences_household_week",
            }
        )
    out = pd.DataFrame(results)
    return out


def _did_means(spend: pd.DataFrame, treated: list[str], control: list[str], pre: list[int], post: list[int]) -> dict:
    def _change(ids: list[str]) -> pd.Series:
        if not ids:
            return pd.Series(dtype=float)
        block = spend.reindex(ids).fillna(0.0)
        return block[post].mean(axis=1) - block[pre].mean(axis=1)

    treated_change = _change(treated)
    control_change = _change(control)
    t_pre = t_post = c_pre = c_post = np.nan
    if treated:
        block = spend.reindex(treated).fillna(0.0)
        t_pre = float(block[pre].mean(axis=1).mean())
        t_post = float(block[post].mean(axis=1).mean())
    if control:
        block = spend.reindex(control).fillna(0.0)
        c_pre = float(block[pre].mean(axis=1).mean())
        c_post = float(block[post].mean(axis=1).mean())
    control_delta = float(control_change.mean()) if len(control_change) else np.nan
    did_hh = treated_change - control_delta if len(treated_change) else pd.Series(dtype=float)
    did = float(did_hh.mean()) if len(did_hh) else np.nan
    if len(did_hh) >= 2:
        se = float(did_hh.std(ddof=1) / np.sqrt(len(did_hh)))
    else:
        se = np.nan
    return {
        "treated_pre_per_week": t_pre,
        "treated_post_per_week": t_post,
        "control_pre_per_week": c_pre,
        "control_post_per_week": c_post,
        "did_per_household_week": did,
        "did_se_per_household_week": se,
        "did_low": did - 1.96 * se if np.isfinite(se) else np.nan,
        "did_high": did + 1.96 * se if np.isfinite(se) else np.nan,
    }


def _empty_campaign(row, status: str) -> dict:
    return {
        "campaign_id": str(row.campaign_id),
        "campaign_type": getattr(row, "campaign_type", pd.NA),
        "start_date": getattr(row, "start_date", pd.NA),
        "end_date": getattr(row, "end_date", pd.NA),
        "start_week": getattr(row, "start_week", pd.NA),
        "end_week": getattr(row, "end_week", pd.NA),
        "n_pre_weeks": 0,
        "n_post_weeks": 0,
        "n_treated": 0,
        "n_control": 0,
        "targeted_households": 0,
        "mailed_households": 0,
        "status": status,
        "window_clipped": bool(getattr(row, "window_clipped", False)),
        "treated_pre_per_week": np.nan,
        "treated_post_per_week": np.nan,
        "control_pre_per_week": np.nan,
        "control_post_per_week": np.nan,
        "did_per_household_week": np.nan,
        "did_se_per_household_week": np.nan,
        "did_low": np.nan,
        "did_high": np.nan,
        "incremental_sales": np.nan,
        "coupon_cost": np.nan,
        "redemptions": np.nan,
        "distinct_upcs": np.nan,
        "roi": np.nan,
        "method": "difference_in_differences_household_week",
    }


def scored_campaigns(results: pd.DataFrame) -> pd.DataFrame:
    """Campaigns with a usable pre period and a large enough mailed group.

    ROI is missing when no coupon discount was recorded. Those rows still
    belong in the incremental ranking; they just do not get a return figure.
    """
    if results.empty:
        return results
    return results.loc[results["status"].eq("ok")].copy()
