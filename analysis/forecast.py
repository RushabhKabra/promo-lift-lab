"""One-step weekly department forecast: a seasonal-naive baseline and a tree model.

The naive forecast is the mean of the previous four weeks. The tree model sees
the same lags plus the week of year and how heavily the department was placed
on display or in the mailer. Placement is known when the flyer is locked, so
it is not a peek at the week's sales.

With about a year of weeks, a fancy model can lose to the four-week mean.
When it does, the four-week mean stays the default.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from analysis.metrics import bias, mape, smape, weighted_mape

HOLDOUT_WEEKS = 12
MIN_HISTORY_WEEKS = 24
NAIVE_WINDOW = 4


def naive_one_step(values: np.ndarray, window: int = NAIVE_WINDOW) -> np.ndarray:
    """Prediction at t is the mean of the previous `window` observations."""
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan)
    for i in range(window, len(values)):
        out[i] = np.mean(values[i - window : i])
    return out


def build_feature_frame(weekly: pd.DataFrame) -> pd.DataFrame:
    """weekly columns: week_no, department, net_sales, promo_intensity, and optional is_partial."""
    frame = weekly.sort_values(["department", "week_no"]).copy()
    if "is_partial" in frame.columns:
        frame = frame.loc[~frame["is_partial"].astype(bool)].copy()
    pieces = []
    for department, part in frame.groupby("department", sort=False):
        part = part.sort_values("week_no").copy()
        sales = part["net_sales"].astype(float)
        part["lag_1"] = sales.shift(1)
        part["lag_2"] = sales.shift(2)
        part["lag_4"] = sales.shift(4)
        part["lag_8"] = sales.shift(8)
        part["roll_4"] = sales.shift(1).rolling(4).mean()
        part["naive"] = part["roll_4"]
        week = part["week_no"].astype(float)
        part["sin_week"] = np.sin(2 * np.pi * week / 52)
        part["cos_week"] = np.cos(2 * np.pi * week / 52)
        part["department"] = department
        pieces.append(part)
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)


def fit_forecast(weekly: pd.DataFrame, holdout_weeks: int = HOLDOUT_WEEKS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (weekly predictions, score summary).

    Scores cover the last `holdout_weeks` study weeks, one step at a time,
    using actual lags. Both models see the same weeks.
    """
    features = build_feature_frame(weekly)
    if features.empty:
        return pd.DataFrame(), pd.DataFrame()
    usable_weeks = sorted(features["week_no"].unique())
    if len(usable_weeks) < MIN_HISTORY_WEEKS:
        note = pd.DataFrame(
            [
                {
                    "model": "unavailable",
                    "scope": "all",
                    "department": "ALL",
                    "mape": np.nan,
                    "smape": np.nan,
                    "weighted_mape": np.nan,
                    "bias": np.nan,
                    "n_points": 0,
                    "holdout_weeks": holdout_weeks,
                    "note": f"need at least {MIN_HISTORY_WEEKS} weeks, found {len(usable_weeks)}",
                }
            ]
        )
        return pd.DataFrame(), note

    test_weeks = set(usable_weeks[-holdout_weeks:])
    train_weeks = set(usable_weeks[:-holdout_weeks])
    feature_cols = ["lag_1", "lag_2", "lag_4", "lag_8", "roll_4", "sin_week", "cos_week", "promo_intensity", "dept_code"]
    model_frame = features.dropna(subset=["lag_1", "lag_2", "lag_4", "lag_8", "roll_4", "net_sales"]).copy()
    codes = {name: i for i, name in enumerate(sorted(model_frame["department"].unique()))}
    model_frame["dept_code"] = model_frame["department"].map(codes).astype(float)
    model_frame["promo_intensity"] = model_frame["promo_intensity"].fillna(0.0).astype(float)

    train_mask = model_frame["week_no"].isin(train_weeks)
    train_mean = model_frame.loc[train_mask].groupby("department")["promo_intensity"].mean()
    scaled = model_frame["department"].map(train_mean).replace(0, np.nan)
    model_frame["promo_intensity"] = (model_frame["promo_intensity"] / scaled).fillna(0.0)
    train = model_frame.loc[train_mask]
    test = model_frame.loc[model_frame["week_no"].isin(test_weeks)].copy()
    if train.empty or test.empty:
        return pd.DataFrame(), pd.DataFrame()

    model = HistGradientBoostingRegressor(
        max_depth=3,
        learning_rate=0.08,
        max_iter=250,
        min_samples_leaf=15,
        l2_regularization=0.1,
        random_state=7,
    )
    model.fit(train[feature_cols], train["net_sales"].to_numpy())
    test["predicted_ml"] = model.predict(test[feature_cols])
    test["predicted_naive"] = test["naive"]

    # A second fit without the flyer, so I can see whether placement actually helps.
    no_flyer_cols = [c for c in feature_cols if c != "promo_intensity"]
    bare = HistGradientBoostingRegressor(
        max_depth=3,
        learning_rate=0.08,
        max_iter=250,
        min_samples_leaf=15,
        l2_regularization=0.1,
        random_state=7,
    )
    bare.fit(train[no_flyer_cols], train["net_sales"].to_numpy())
    test["predicted_ml_no_flyer"] = bare.predict(test[no_flyer_cols])

    ml_mape = weighted_mape(test["net_sales"], test["predicted_ml"])
    naive_mape = weighted_mape(test["net_sales"], test["predicted_naive"])
    bare_mape = weighted_mape(test["net_sales"], test["predicted_ml_no_flyer"])
    default = "naive_last_4"
    if np.isfinite(ml_mape) and ml_mape < naive_mape:
        default = "hist_gradient_boosting"
    test["predicted_default"] = test["predicted_ml"] if default == "hist_gradient_boosting" else test["predicted_naive"]
    test["default_model"] = default

    scores = [_score_block(test, "ALL", "naive_last_4", "predicted_naive")]
    scores.append(_score_block(test, "ALL", "hist_gradient_boosting", "predicted_ml"))
    scores.append(_score_block(test, "ALL", "hist_gradient_boosting_no_flyer", "predicted_ml_no_flyer"))
    scores.append(
        {
            "model": "comparison",
            "scope": "all",
            "department": "ALL",
            "mape": np.nan,
            "smape": np.nan,
            "weighted_mape": np.nan,
            "bias": np.nan,
            "n_points": int(len(test)),
            "holdout_weeks": holdout_weeks,
            "note": (
                f"default={default}; weighted MAPE naive={naive_mape:.4f}, "
                f"tree={ml_mape:.4f}, tree_without_flyer={bare_mape:.4f}"
            ),
        }
    )
    median_intensity = float(test["promo_intensity"].median())
    for label, mask in (
        ("promo_weeks", test["promo_intensity"] >= median_intensity),
        ("quieter_weeks", test["promo_intensity"] < median_intensity),
    ):
        part = test.loc[mask]
        if part.empty:
            continue
        for model_name, col in (
            ("naive_last_4", "predicted_naive"),
            ("hist_gradient_boosting", "predicted_ml"),
        ):
            row = _score_block(part, "ALL", model_name, col)
            row["scope"] = label
            scores.append(row)

    for department, part in test.groupby("department"):
        for model_name, col in (
            ("naive_last_4", "predicted_naive"),
            ("hist_gradient_boosting", "predicted_ml"),
        ):
            row = _score_block(part, department, model_name, col)
            row["scope"] = "department"
            scores.append(row)

    keep = [
        "week_no",
        "department",
        "net_sales",
        "promo_intensity",
        "predicted_naive",
        "predicted_ml",
        "predicted_ml_no_flyer",
        "predicted_default",
        "default_model",
    ]
    return test[keep].reset_index(drop=True), pd.DataFrame(scores)


def _score_block(part: pd.DataFrame, department: str, model_name: str, column: str) -> dict:
    actual = part["net_sales"]
    pred = part[column]
    return {
        "model": model_name,
        "scope": "all",
        "department": department,
        "mape": mape(actual, pred),
        "smape": smape(actual, pred),
        "weighted_mape": weighted_mape(actual, pred),
        "bias": bias(actual, pred),
        "n_points": int(len(part)),
        "holdout_weeks": HOLDOUT_WEEKS,
        "note": "",
    }
