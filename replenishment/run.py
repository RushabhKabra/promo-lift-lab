"""Run the replenishment pass from receipt lines, products, and placements."""

from __future__ import annotations

import numpy as np
import pandas as pd

from replenishment.accuracy import choose_default, paired_scores, score_panel
from replenishment.demand import (
    HOLDOUT_WEEKS,
    MIN_POSITIVE_WEEKS,
    MIN_PRE_WEEKS,
    build_panel,
    partial_week_numbers,
    weekly_demand,
)
from replenishment.forecast import PREDICTION_COLUMNS, add_forecasts
from replenishment.policy import (
    DEFAULT_LEAD_TIME_WEEKS,
    DEFAULT_REVIEW_WEEKS,
    DEFAULT_SERVICE_LEVEL,
    build_policy,
    rollup,
)


def run_replenishment(
    transactions: pd.DataFrame,
    products: pd.DataFrame,
    promotions: pd.DataFrame | None = None,
    *,
    lead_time_weeks: int = DEFAULT_LEAD_TIME_WEEKS,
    review_weeks: int = DEFAULT_REVIEW_WEEKS,
    service_level: float = DEFAULT_SERVICE_LEVEL,
    holdout_weeks: int = HOLDOUT_WEEKS,
    min_positive_weeks: int = MIN_POSITIVE_WEEKS,
    min_pre_weeks: int = MIN_PRE_WEEKS,
) -> dict[str, pd.DataFrame | dict]:
    partial = partial_week_numbers(transactions)
    weekly = weekly_demand(transactions, products)
    panel, meta = build_panel(
        weekly,
        promotions,
        partial_weeks=partial,
        holdout_weeks=holdout_weeks,
        min_positive_weeks=min_positive_weeks,
        min_pre_weeks=min_pre_weeks,
    )
    meta["partial_weeks"] = partial_week_numbers(transactions) if not meta["partial_weeks"] else meta["partial_weeks"]
    if panel.empty:
        accuracy = score_panel(panel, meta["holdout_weeks"])
        if meta["note"] and len(accuracy):
            accuracy.loc[accuracy.index[0], "note"] = meta["note"]
        summary = _summary(accuracy, pd.DataFrame(), pd.DataFrame(), meta, "moving_average_4", lead_time_weeks, review_weeks, service_level)
        return {
            "panel": panel,
            "accuracy": accuracy,
            "policy": pd.DataFrame(),
            "weekly": pd.DataFrame(),
            "department": pd.DataFrame(),
            "category": pd.DataFrame(),
            "summary": summary,
            "meta": meta,
        }

    panel = add_forecasts(panel)
    accuracy = score_panel(panel, meta["holdout_weeks"])
    default_model = choose_default(accuracy)
    policy = build_policy(
        panel,
        meta["holdout_weeks"],
        lead_time_weeks=lead_time_weeks,
        review_weeks=review_weeks,
        service_level=service_level,
    )
    weekly_out = department_weekly(panel)
    department = rollup(policy, ["department"])
    category = rollup(policy, ["department", "product_category"])
    summary = _summary(
        accuracy,
        policy,
        department,
        meta,
        default_model,
        lead_time_weeks,
        review_weeks,
        service_level,
        paired_scores(panel, meta["holdout_weeks"]),
    )
    return {
        "panel": panel,
        "accuracy": accuracy,
        "policy": policy,
        "weekly": weekly_out,
        "department": department,
        "category": category,
        "summary": summary,
        "meta": meta,
    }


def department_weekly(panel: pd.DataFrame) -> pd.DataFrame:
    """Eligible series, summed to department and week. Not the whole department."""
    if panel.empty:
        return pd.DataFrame()
    base = (
        panel.groupby(["department", "week_no"], as_index=False)["units"]
        .sum()
        .rename(columns={"units": "actual_units"})
    )
    feature = (
        panel.loc[panel["on_feature"]]
        .groupby(["department", "week_no"], as_index=False)["units"]
        .sum()
        .rename(columns={"units": "feature_units"})
    )
    base = base.merge(feature, on=["department", "week_no"], how="left")
    base["feature_units"] = base["feature_units"].fillna(0.0)
    base["quiet_units"] = base["actual_units"] - base["feature_units"]
    for name, column in PREDICTION_COLUMNS.items():
        summed = (
            panel.groupby(["department", "week_no"])[column]
            .sum(min_count=1)
            .rename(name)
            .reset_index()
        )
        base = base.merge(summed, on=["department", "week_no"], how="left")
    return base.sort_values(["department", "week_no"]).reset_index(drop=True)


def _summary(
    accuracy: pd.DataFrame,
    policy: pd.DataFrame,
    department: pd.DataFrame,
    meta: dict,
    default_model: str,
    lead_time_weeks: int,
    review_weeks: int,
    service_level: float,
    paired: dict | None = None,
) -> pd.DataFrame:
    row = {
        "default_model": default_model,
        "n_series": int(meta.get("n_series") or 0),
        "holdout_week_count": len(meta.get("holdout_weeks") or []),
        "holdout_first_week": (meta.get("holdout_weeks") or [None])[0],
        "holdout_last_week": (meta.get("holdout_weeks") or [None])[-1] if meta.get("holdout_weeks") else None,
        "partial_weeks": ",".join(str(w) for w in meta.get("partial_weeks") or []),
        "grocery_units": float(meta.get("grocery_units") or 0.0),
        "eligible_units": float(meta.get("eligible_units") or 0.0),
        "coverage": meta.get("coverage"),
        "lead_time_weeks": int(lead_time_weeks),
        "review_weeks": int(review_weeks),
        "service_level": float(service_level),
        "note": meta.get("note") or "",
    }
    overall = accuracy.loc[accuracy["department"].eq("ALL") & accuracy["scope"].eq("all")] if len(accuracy) else accuracy
    for model in ("moving_average_4", "seasonal_naive", "promo_adjusted"):
        match = overall.loc[overall["model"].eq(model)] if len(overall) else overall
        prefix = model
        if len(match):
            item = match.iloc[0]
            row[f"wape_{prefix}"] = item["wape"]
            row[f"mape_{prefix}"] = item["mape"]
            row[f"median_ape_{prefix}"] = item["median_ape"]
            row[f"bias_{prefix}"] = item["bias"]
            row[f"n_points_{prefix}"] = int(item["n_points"])
            row[f"actual_units_{prefix}"] = float(item["actual_units"])
        else:
            row[f"wape_{prefix}"] = np.nan
            row[f"mape_{prefix}"] = np.nan
            row[f"median_ape_{prefix}"] = np.nan
            row[f"bias_{prefix}"] = np.nan
            row[f"n_points_{prefix}"] = 0
            row[f"actual_units_{prefix}"] = 0.0
    chosen = overall.loc[overall["model"].eq(default_model)] if len(overall) else overall
    if len(chosen):
        row["wape_default"] = chosen.iloc[0]["wape"]
        row["mape_default"] = chosen.iloc[0]["mape"]
        row["bias_default"] = chosen.iloc[0]["bias"]
    else:
        row["wape_default"] = np.nan
        row["mape_default"] = np.nan
        row["bias_default"] = np.nan

    for scope, label in (("feature_weeks", "feature"), ("quiet_weeks", "quiet")):
        for model, short in (("moving_average_4", "ma4"), ("promo_adjusted", "promo")):
            match = accuracy.loc[
                accuracy["department"].eq("ALL") & accuracy["scope"].eq(scope) & accuracy["model"].eq(model)
            ] if len(accuracy) else accuracy
            key = f"wape_{label}_{short}"
            row[key] = float(match.iloc[0]["wape"]) if len(match) else np.nan

    if policy.empty:
        row.update(
            {
                "service_z": np.nan,
                "units_short_vs_quiet_mean": 0.0,
                "units_short_vs_service_cover": 0.0,
                "units_extra_if_feature_rate_on_quiet": 0.0,
                "units_extra_week_after_feature": 0.0,
                "holdout_feature_weeks": 0,
                "holdout_feature_weeks_above_quiet_mean": 0,
                "share_feature_weeks_above_quiet_mean": np.nan,
                "n_stockout_risk": 0,
                "n_overstock_risk": 0,
                "median_safety_stock": np.nan,
                "median_suggested_order": np.nan,
                "total_suggested_order_if_pipeline_empty": 0.0,
            }
        )
    else:
        feature_weeks = float(policy["holdout_feature_weeks"].sum())
        above = float(policy["holdout_feature_weeks_above_quiet_mean"].sum())
        row.update(
            {
                "service_z": float(policy["service_z"].iloc[0]),
                "units_short_vs_quiet_mean": float(policy["units_short_vs_quiet_mean"].sum()),
                "units_short_vs_service_cover": float(policy["units_short_vs_service_cover"].sum()),
                "units_extra_if_feature_rate_on_quiet": float(policy["units_extra_if_feature_rate_on_quiet"].sum()),
                "units_extra_week_after_feature": float(policy["units_extra_week_after_feature"].sum()),
                "holdout_feature_weeks": int(feature_weeks),
                "holdout_feature_weeks_above_quiet_mean": int(above),
                "share_feature_weeks_above_quiet_mean": above / feature_weeks if feature_weeks else np.nan,
                "n_stockout_risk": int(policy["stockout_risk_if_base_order"].sum()),
                "n_overstock_risk": int(policy["overstock_risk_if_promo_repeated"].sum()),
                "median_safety_stock": float(policy["safety_stock_units"].median()),
                "median_suggested_order": float(policy["suggested_order_qty"].median()),
                "total_suggested_order_if_pipeline_empty": float(policy["suggested_order_qty"].sum()),
            }
        )
    for key, value in (paired or {}).items():
        row[key] = value
    if len(department):
        top = department.iloc[0]
        row["largest_shortfall_department"] = top["department"]
        row["largest_shortfall_units"] = float(top["units_short_vs_quiet_mean"])
    else:
        row["largest_shortfall_department"] = ""
        row["largest_shortfall_units"] = 0.0
    return pd.DataFrame([row])
