"""One-step store-SKU forecasts.

The baseline is the mean of the previous four weeks in the series, partial
weeks already removed. Seasonal naive is the same study week a year earlier
(lag 52). This panel is one year long, so that lag usually has nothing to
point at. I still score it, and I do not let it become the default unless it
actually has the history.

The challenger is a quiet-week mean. On a week the flyer already marks, I
scale that mean by this series' own past feature-to-quiet ratio, shrunk
toward 1. The shrinkage weight is n / (n + 4), fixed before I look at the
holdout. Two feature weeks only get a third of their raw ratio. I would
rather under-call a lift than order a one-week spike forever.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MA_WINDOW = 4
SEASONAL_PERIOD = 52
MIN_FEATURE_HISTORY = 2
LIFT_PRIOR_WEEKS = 4

MODEL_MA = "moving_average_4"
MODEL_SEASONAL = "seasonal_naive"
MODEL_PROMO = "promo_adjusted"
PREDICTION_COLUMNS = {
    MODEL_MA: "predicted_ma4",
    MODEL_SEASONAL: "predicted_seasonal_naive",
    MODEL_PROMO: "predicted_promo",
}
# Simpler model wins a tie. Seasonal naive only enters the tie when it has history.
SIMPLICITY = (MODEL_MA, MODEL_SEASONAL, MODEL_PROMO)


def add_forecasts(panel: pd.DataFrame) -> pd.DataFrame:
    """Return the panel with one-step predictions. Current week is not an input."""
    work = panel.sort_values(["product_id", "store_id", "week_no"]).reset_index(drop=True)
    n = len(work)
    for column in PREDICTION_COLUMNS.values():
        work[column] = np.nan
    if n == 0:
        return work

    units = work["units"].to_numpy(dtype=float)
    feature = work["on_feature"].to_numpy(dtype=bool)
    weeks = work["week_no"].to_numpy(dtype=int)
    product = work["product_id"].astype(str).to_numpy()
    store = work["store_id"].astype(str).to_numpy()
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = (product[1:] != product[:-1]) | (store[1:] != store[:-1])
    starts = np.flatnonzero(change)
    ends = np.empty_like(starts)
    ends[:-1] = starts[1:]
    ends[-1] = n

    ma = np.full(n, np.nan)
    seasonal = np.full(n, np.nan)
    promo = np.full(n, np.nan)
    for start, end in zip(starts, ends, strict=True):
        _one_series(units, feature, weeks, ma, seasonal, promo, int(start), int(end))
    work["predicted_ma4"] = ma
    work["predicted_seasonal_naive"] = seasonal
    work["predicted_promo"] = promo
    return work


def _one_series(
    units: np.ndarray,
    feature: np.ndarray,
    weeks: np.ndarray,
    ma: np.ndarray,
    seasonal: np.ndarray,
    promo: np.ndarray,
    start: int,
    end: int,
) -> None:
    index_by_week = {int(weeks[i]): i for i in range(start, end)}
    quiet_window: list[float] = []
    quiet_window_sum = 0.0
    quiet_sum = 0.0
    quiet_n = 0
    feat_sum = 0.0
    feat_n = 0
    for i in range(start, end):
        if i - start >= MA_WINDOW:
            ma[i] = float(units[i - MA_WINDOW : i].mean())
        previous = index_by_week.get(int(weeks[i]) - SEASONAL_PERIOD)
        if previous is not None:
            seasonal[i] = units[previous]
        if len(quiet_window) >= MA_WINDOW:
            base = quiet_window_sum / MA_WINDOW
            if feature[i] and feat_n >= MIN_FEATURE_HISTORY and quiet_n > 0 and quiet_sum > 0:
                raw = (feat_sum / feat_n) / (quiet_sum / quiet_n)
                weight = feat_n / (feat_n + LIFT_PRIOR_WEEKS)
                promo[i] = max(0.0, base * (1.0 + weight * (raw - 1.0)))
            else:
                promo[i] = max(0.0, base)
        value = float(units[i])
        if feature[i]:
            feat_sum += value
            feat_n += 1
        else:
            quiet_window.append(value)
            quiet_window_sum += value
            quiet_sum += value
            quiet_n += 1
            if len(quiet_window) > MA_WINDOW:
                quiet_window_sum -= quiet_window.pop(0)
