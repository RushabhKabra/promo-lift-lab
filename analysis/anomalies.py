"""Quiet checks for weeks that do not look like their recent neighbours."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def robust_z_flags(weekly: pd.DataFrame, window: int = 8, z_cut: float = 3.5) -> pd.DataFrame:
    """Flag department-weeks whose sales sit far from the trailing 8-week median.

    The scale is a trailing MAD, so one wild week does not set the bar for the next.
    """
    frame = weekly.sort_values(["department", "week_no"]).copy()
    if "is_partial" in frame.columns:
        frame = frame.loc[~frame["is_partial"].astype(bool)].copy()
    pieces = []
    for department, part in frame.groupby("department", sort=False):
        part = part.sort_values("week_no").copy()
        sales = part["net_sales"].astype(float)
        median = sales.shift(1).rolling(window).median()
        mad = sales.shift(1).rolling(window).apply(_mad, raw=True)
        scale = 1.4826 * mad
        z = (sales - median) / scale.replace(0, np.nan)
        # A flat history has MAD 0. A large relative jump is still an exception.
        relative = (sales - median) / median.replace(0, np.nan)
        z = z.where(~(z.isna() & median.notna() & relative.abs().ge(0.5)), np.sign(relative) * 10)
        part["trail_median"] = median
        part["robust_z"] = z
        part["robust_flag"] = z.abs() >= z_cut
        part["department"] = department
        pieces.append(part)
    if not pieces:
        return pd.DataFrame()
    out = pd.concat(pieces, ignore_index=True)
    return out


def isolation_flags(flagged: pd.DataFrame) -> pd.DataFrame:
    """Second opinion from an isolation forest on sales, the lag, and placement."""
    if flagged.empty or len(flagged) < 30:
        out = flagged.copy()
        out["isolation_flag"] = False
        return out
    work = flagged.copy()
    work["lag_sales"] = work.groupby("department")["net_sales"].shift(1)
    cols = ["net_sales", "lag_sales", "promo_intensity"]
    matrix = work[cols].fillna(work[cols].median(numeric_only=True))
    forest = IsolationForest(n_estimators=200, contamination=0.03, random_state=7)
    pred = forest.fit_predict(matrix)
    work["isolation_flag"] = pred == -1
    return work


def anomaly_table(weekly: pd.DataFrame) -> pd.DataFrame:
    flagged = isolation_flags(robust_z_flags(weekly))
    if flagged.empty:
        return flagged
    # The first weeks have no trailing median. An isolation flag there is just
    # "the series has not started yet", so I wait until the trailing window exists.
    keep = flagged.loc[flagged["trail_median"].notna()].copy()
    keep = keep.loc[keep["robust_flag"].fillna(False) | keep["isolation_flag"].fillna(False)].copy()
    keep["reason"] = np.where(
        keep["robust_flag"].fillna(False) & keep["isolation_flag"].fillna(False),
        "both",
        np.where(keep["robust_flag"].fillna(False), "robust_z", "isolation_forest"),
    )
    columns = [
        "week_no",
        "department",
        "net_sales",
        "trail_median",
        "robust_z",
        "robust_flag",
        "isolation_flag",
        "promo_intensity",
        "reason",
    ]
    columns = [c for c in columns if c in keep.columns]
    return keep[columns].sort_values(["week_no", "department"]).reset_index(drop=True)


def _mad(values: np.ndarray) -> float:
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return np.nan
    med = np.median(values)
    return float(np.median(np.abs(values - med)))
