"""Holdout accuracy for the store-SKU forecasts.

MAPE is the unweighted mean of absolute percent errors on weeks that sold.
WAPE is the volume-weighted error, and it keeps silent weeks in the
numerator. Bias is mean prediction minus actual, in units. Positive means
the forecast ran hot and the order would have been heavy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.metrics import bias, mape, median_ape, wape
from replenishment.forecast import MODEL_MA, PREDICTION_COLUMNS, SIMPLICITY

# A model with almost no scored weeks does not get to win. Half the moving
# average's holdout points is the bar, so a lag-52 forecast on a one-year
# panel stays a note instead of the default.
MIN_POINT_SHARE = 0.5


def score_panel(panel: pd.DataFrame, holdout_weeks: list[int]) -> pd.DataFrame:
    columns = [
        "model",
        "scope",
        "department",
        "mape",
        "wape",
        "median_ape",
        "bias",
        "n_points",
        "n_series",
        "actual_units",
        "holdout_weeks",
        "note",
    ]
    if panel.empty or not holdout_weeks:
        return pd.DataFrame(
            [
                {
                    "model": "unavailable",
                    "scope": "all",
                    "department": "ALL",
                    "mape": np.nan,
                    "wape": np.nan,
                    "median_ape": np.nan,
                    "bias": np.nan,
                    "n_points": 0,
                    "n_series": 0,
                    "actual_units": 0.0,
                    "holdout_weeks": len(holdout_weeks),
                    "note": "nothing to score",
                }
            ]
        )

    holdout = panel.loc[panel["week_no"].isin(holdout_weeks)].copy()
    rows: list[dict] = []
    departments = ["ALL", *sorted(holdout["department"].dropna().unique())]
    for model, column in PREDICTION_COLUMNS.items():
        for department in departments:
            part = holdout if department == "ALL" else holdout.loc[holdout["department"].eq(department)]
            for scope, scoped in _scopes(part):
                scored = scoped.loc[scoped[column].notna()]
                if scored.empty:
                    if department == "ALL" and scope == "all":
                        rows.append(_empty_row(model, scope, department, len(holdout_weeks), _empty_note(model)))
                    continue
                rows.append(_score_row(scored, model, column, scope, department, len(holdout_weeks)))
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def paired_scores(panel: pd.DataFrame, holdout_weeks: list[int]) -> dict:
    """WAPE, MAPE, and bias on weeks where both forecasts exist.

    The promo-adjusted forecast is blank until four quiet weeks have passed,
    so its own WAPE can drop a few hard weeks. The paired numbers score the
    same rows.
    """
    empty = {
        "n_points_paired": 0,
        "actual_units_paired": 0.0,
        "wape_ma4_paired": np.nan,
        "wape_promo_paired": np.nan,
        "mape_ma4_paired": np.nan,
        "mape_promo_paired": np.nan,
        "bias_ma4_paired": np.nan,
        "bias_promo_paired": np.nan,
        "n_points_feature_paired": 0,
        "wape_feature_ma4_paired": np.nan,
        "wape_feature_promo_paired": np.nan,
        "n_points_quiet_paired": 0,
        "wape_quiet_ma4_paired": np.nan,
        "wape_quiet_promo_paired": np.nan,
    }
    if panel.empty or "predicted_ma4" not in panel.columns or not holdout_weeks:
        return empty
    holdout = panel.loc[panel["week_no"].isin(holdout_weeks)]
    both = holdout.loc[holdout["predicted_ma4"].notna() & holdout["predicted_promo"].notna()]
    if both.empty:
        return empty
    empty.update(_paired_block(both))
    feature = both.loc[both["on_feature"].astype(bool)]
    quiet = both.loc[~both["on_feature"].astype(bool)]
    if len(feature):
        empty["n_points_feature_paired"] = int(len(feature))
        empty["wape_feature_ma4_paired"] = wape(feature["units"], feature["predicted_ma4"])
        empty["wape_feature_promo_paired"] = wape(feature["units"], feature["predicted_promo"])
    if len(quiet):
        empty["n_points_quiet_paired"] = int(len(quiet))
        empty["wape_quiet_ma4_paired"] = wape(quiet["units"], quiet["predicted_ma4"])
        empty["wape_quiet_promo_paired"] = wape(quiet["units"], quiet["predicted_promo"])
    return empty


def _paired_block(frame: pd.DataFrame) -> dict:
    actual = frame["units"]
    return {
        "n_points_paired": int(len(frame)),
        "actual_units_paired": float(actual.sum()),
        "wape_ma4_paired": wape(actual, frame["predicted_ma4"]),
        "wape_promo_paired": wape(actual, frame["predicted_promo"]),
        "mape_ma4_paired": mape(actual, frame["predicted_ma4"]),
        "mape_promo_paired": mape(actual, frame["predicted_promo"]),
        "bias_ma4_paired": bias(actual, frame["predicted_ma4"]),
        "bias_promo_paired": bias(actual, frame["predicted_promo"]),
    }


def choose_default(scores: pd.DataFrame) -> str:
    """Lowest WAPE on all holdout points. A tie keeps the simpler model."""
    if scores.empty or "model" not in scores.columns:
        return MODEL_MA
    overall = scores.loc[
        scores["department"].eq("ALL") & scores["scope"].eq("all") & scores["model"].isin(SIMPLICITY)
    ]
    anchor = overall.loc[overall["model"].eq(MODEL_MA)]
    anchor_n = int(anchor["n_points"].iloc[0]) if len(anchor) else 0
    eligible = []
    for row in overall.itertuples(index=False):
        if anchor_n <= 0:
            break
        if int(row.n_points) >= MIN_POINT_SHARE * anchor_n and np.isfinite(row.wape):
            eligible.append(row)
    if not eligible:
        return MODEL_MA
    eligible.sort(key=lambda row: (float(row.wape), SIMPLICITY.index(row.model)))
    return str(eligible[0].model)


def _scopes(frame: pd.DataFrame):
    yield "all", frame
    if frame.empty:
        return
    yield "feature_weeks", frame.loc[frame["on_feature"].astype(bool)]
    yield "quiet_weeks", frame.loc[~frame["on_feature"].astype(bool)]


def _score_row(part: pd.DataFrame, model: str, column: str, scope: str, department: str, holdout_weeks: int) -> dict:
    actual = part["units"]
    predicted = part[column]
    return {
        "model": model,
        "scope": scope,
        "department": department,
        "mape": mape(actual, predicted),
        "wape": wape(actual, predicted),
        "median_ape": median_ape(actual, predicted),
        "bias": bias(actual, predicted),
        "n_points": int(len(part)),
        "n_series": int(part.groupby(["product_id", "store_id"]).ngroups),
        "actual_units": float(actual.sum()),
        "holdout_weeks": holdout_weeks,
        "note": "",
    }


def _empty_row(model: str, scope: str, department: str, holdout_weeks: int, note: str) -> dict:
    return {
        "model": model,
        "scope": scope,
        "department": department,
        "mape": np.nan,
        "wape": np.nan,
        "median_ape": np.nan,
        "bias": np.nan,
        "n_points": 0,
        "n_series": 0,
        "actual_units": 0.0,
        "holdout_weeks": holdout_weeks,
        "note": note,
    }


def _empty_note(model: str) -> str:
    if model == "seasonal_naive":
        return "lag 52 falls outside this series. One year of weeks is not a seasonal history."
    return "no scored weeks"
