"""Store-SKU weekly demand from receipt lines.

Units are quantity on non-fuel products. A week with fewer than six distinct
dates is partial, the same rule as `core.dim_week`, and it drops out of the
panel. Silent weeks inside a series' first and last sale are filled with
zero. That zero mixes "nobody in the panel bought it" with "it may have been
out of stock". The span stops at the last sale, so I do not treat the weeks
after a delist as demand of zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HOLDOUT_WEEKS = 8
MIN_POSITIVE_WEEKS = 8
MIN_PRE_WEEKS = 8
PARTIAL_DATE_THRESHOLD = 6

PANEL_COLUMNS = [
    "product_id",
    "store_id",
    "week_no",
    "units",
    "on_feature",
    "department",
    "product_category",
]


def partial_week_numbers(transactions: pd.DataFrame) -> set[int]:
    """Weeks that cover fewer than six distinct dates. Week 1 is one of these."""
    if transactions.empty:
        return set()
    week_col = "week_no" if "week_no" in transactions.columns else "week"
    if week_col not in transactions.columns:
        return set()
    if "date_key" in transactions.columns:
        dates = pd.to_datetime(transactions["date_key"], errors="coerce").dt.floor("D")
    elif "transaction_timestamp" in transactions.columns:
        dates = pd.to_datetime(transactions["transaction_timestamp"], errors="coerce").dt.floor("D")
    else:
        return set()
    weeks = pd.to_numeric(transactions[week_col], errors="coerce")
    valid = dates.notna() & weeks.notna()
    if not valid.any():
        return set()
    counts = dates.loc[valid].groupby(weeks.loc[valid].astype(int)).nunique()
    return {int(week) for week, n_dates in counts.items() if int(n_dates) < PARTIAL_DATE_THRESHOLD}


def weekly_demand(transactions: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """One row per product, store, and week that appears on a non-fuel receipt."""
    if transactions.empty:
        return pd.DataFrame(columns=["product_id", "store_id", "week_no", "units", "department", "product_category"])
    week_col = "week_no" if "week_no" in transactions.columns else "week"
    work = transactions.copy()
    work["product_id"] = work["product_id"].map(_as_id)
    work["store_id"] = work["store_id"].map(_as_id)
    work["week_no"] = pd.to_numeric(work[week_col], errors="coerce")
    work["quantity"] = pd.to_numeric(work["quantity"], errors="coerce").fillna(0.0)
    work = work.dropna(subset=["product_id", "store_id", "week_no"])
    work = work.loc[work["product_id"].ne("") & work["store_id"].ne("")]
    work["week_no"] = work["week_no"].astype(int)

    product_meta = _product_meta(products)
    fuel_ids = set(product_meta.loc[product_meta["is_fuel"], "product_id"])
    work = work.loc[~work["product_id"].isin(fuel_ids)]
    grouped = (
        work.groupby(["product_id", "store_id", "week_no"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "units"})
    )
    grouped = grouped.merge(
        product_meta[["product_id", "department", "product_category"]],
        on="product_id",
        how="left",
    )
    grouped["department"] = grouped["department"].fillna("Unmapped")
    grouped["product_category"] = grouped["product_category"].fillna("Uncategorized")
    return grouped


def build_panel(
    weekly: pd.DataFrame,
    promotions: pd.DataFrame | None,
    partial_weeks: set[int] | None = None,
    holdout_weeks: int = HOLDOUT_WEEKS,
    min_positive_weeks: int = MIN_POSITIVE_WEEKS,
    min_pre_weeks: int = MIN_PRE_WEEKS,
) -> tuple[pd.DataFrame, dict]:
    """Dense product-store-week panel for series long enough to score.

    A series is kept when it has at least `min_positive_weeks` sale weeks
    before the holdout, at least `min_pre_weeks` calendar weeks of span
    before the holdout, and it is still selling in the holdout window.
    """
    partial = set(partial_weeks or [])
    meta = {
        "holdout_weeks": [],
        "calendar_weeks": [],
        "partial_weeks": sorted(partial),
        "n_series": 0,
        "grocery_units": 0.0,
        "eligible_units": 0.0,
        "coverage": np.nan,
        "note": "",
    }
    if weekly.empty:
        meta["note"] = "no weekly demand"
        return _empty_panel(), meta

    meta["grocery_units"] = float(weekly["units"].sum())
    observed = weekly.loc[~weekly["week_no"].isin(partial)].copy()
    calendar = sorted(int(w) for w in observed["week_no"].unique())
    meta["calendar_weeks"] = calendar
    if len(calendar) < holdout_weeks + min_pre_weeks:
        meta["note"] = (
            f"need at least {holdout_weeks + min_pre_weeks} non-partial weeks, found {len(calendar)}"
        )
        return _empty_panel(), meta

    holdout = calendar[-holdout_weeks:]
    meta["holdout_weeks"] = holdout
    first_holdout = holdout[0]
    pre_calendar = np.array([w for w in calendar if w < first_holdout], dtype=int)
    positive = observed.loc[observed["units"] > 0]
    if positive.empty:
        meta["note"] = "no positive weeks"
        return _empty_panel(), meta

    stats = positive.groupby(["product_id", "store_id"], as_index=False).agg(
        first_week=("week_no", "min"),
        last_week=("week_no", "max"),
        department=("department", "first"),
        product_category=("product_category", "first"),
    )
    pre_positive = positive.loc[positive["week_no"].isin(pre_calendar)]
    pre_counts = pre_positive.groupby(["product_id", "store_id"]).size().rename("n_positive_pre")
    stats = stats.merge(pre_counts, on=["product_id", "store_id"], how="left")
    stats["n_positive_pre"] = stats["n_positive_pre"].fillna(0).astype(int)
    first = stats["first_week"].to_numpy(dtype=int)
    stats["n_pre_weeks"] = np.searchsorted(pre_calendar, first, side="left")
    stats["n_pre_weeks"] = len(pre_calendar) - stats["n_pre_weeks"]
    stats = stats.loc[
        (stats["n_positive_pre"] >= min_positive_weeks)
        & (stats["n_pre_weeks"] >= min_pre_weeks)
        & (stats["last_week"] >= first_holdout)
    ].copy()
    if stats.empty:
        meta["note"] = "no store-SKU series met the history rule"
        return _empty_panel(), meta

    panel = _dense(stats, np.array(calendar, dtype=int))
    panel = panel.merge(
        observed[["product_id", "store_id", "week_no", "units"]],
        on=["product_id", "store_id", "week_no"],
        how="left",
    )
    panel["units"] = panel["units"].fillna(0.0)
    panel = _attach_feature(panel, promotions)
    meta["n_series"] = int(panel.groupby(["product_id", "store_id"]).ngroups)
    meta["eligible_units"] = float(panel["units"].sum())
    if meta["grocery_units"] > 0:
        # Coverage is eligible units over non-fuel units on non-partial weeks.
        # Partial-week units stay in grocery_units and out of this ratio.
        base = float(observed["units"].sum())
        meta["coverage"] = meta["eligible_units"] / base if base > 0 else np.nan
    return panel[PANEL_COLUMNS], meta


def _dense(stats: pd.DataFrame, calendar: np.ndarray) -> pd.DataFrame:
    product_ids = []
    store_ids = []
    weeks = []
    departments = []
    categories = []
    first = stats["first_week"].to_numpy(dtype=int)
    last = stats["last_week"].to_numpy(dtype=int)
    pid = stats["product_id"].to_numpy()
    sid = stats["store_id"].to_numpy()
    dept = stats["department"].to_numpy()
    cat = stats["product_category"].to_numpy()
    for i in range(len(stats)):
        chosen = calendar[(calendar >= first[i]) & (calendar <= last[i])]
        n = len(chosen)
        if n == 0:
            continue
        product_ids.append(np.full(n, pid[i], dtype=object))
        store_ids.append(np.full(n, sid[i], dtype=object))
        weeks.append(chosen)
        departments.append(np.full(n, dept[i], dtype=object))
        categories.append(np.full(n, cat[i], dtype=object))
    if not weeks:
        return _empty_panel()
    return pd.DataFrame(
        {
            "product_id": np.concatenate(product_ids),
            "store_id": np.concatenate(store_ids),
            "week_no": np.concatenate(weeks).astype(int),
            "department": np.concatenate(departments),
            "product_category": np.concatenate(categories),
        }
    )


def _attach_feature(panel: pd.DataFrame, promotions: pd.DataFrame | None) -> pd.DataFrame:
    out = panel.copy()
    if promotions is None or promotions.empty:
        out["on_feature"] = False
        return out
    keys = _promotion_keys(promotions)
    if keys.empty:
        out["on_feature"] = False
        return out
    keys = keys.drop_duplicates(["product_id", "store_id", "week_no"])
    marked = out.merge(keys, on=["product_id", "store_id", "week_no"], how="left")
    # A missing placement is not a feature. eq(True) keeps NaN off the flag.
    marked["on_feature"] = marked["on_feature"].eq(True)
    return marked


def _promotion_keys(promotions: pd.DataFrame) -> pd.DataFrame:
    week_col = "week_no" if "week_no" in promotions.columns else "week"
    if week_col not in promotions.columns:
        return pd.DataFrame(columns=["product_id", "store_id", "week_no", "on_feature"])
    work = promotions.copy()
    work["product_id"] = work["product_id"].map(_as_id)
    work["store_id"] = work["store_id"].map(_as_id)
    work["week_no"] = pd.to_numeric(work[week_col], errors="coerce")
    work = work.dropna(subset=["product_id", "store_id", "week_no"])
    work["week_no"] = work["week_no"].astype(int)
    if "on_display" in work.columns or "in_mailer" in work.columns:
        on_display = work["on_display"].fillna(False).astype(bool) if "on_display" in work.columns else False
        in_mailer = work["in_mailer"].fillna(False).astype(bool) if "in_mailer" in work.columns else False
        work = work.loc[on_display | in_mailer]
    elif "display_location" in work.columns or "mailer_location" in work.columns:
        display = work.get("display_location", pd.Series("0", index=work.index)).astype(str)
        mailer = work.get("mailer_location", pd.Series("0", index=work.index)).astype(str)
        work = work.loc[display.ne("0") | mailer.ne("0")]
    if work.empty:
        return pd.DataFrame(columns=["product_id", "store_id", "week_no", "on_feature"])
    keys = work[["product_id", "store_id", "week_no"]].drop_duplicates()
    keys["on_feature"] = True
    return keys


def _product_meta(products: pd.DataFrame) -> pd.DataFrame:
    if products is None or products.empty:
        return pd.DataFrame(columns=["product_id", "department", "product_category", "is_fuel"])
    work = products.copy()
    work["product_id"] = work["product_id"].map(_as_id)
    work = work.dropna(subset=["product_id"]).drop_duplicates("product_id", keep="first")
    if "department" not in work.columns:
        work["department"] = pd.NA
    if "product_category" not in work.columns:
        work["product_category"] = pd.NA
    if "is_fuel" not in work.columns:
        department = work["department"].astype(str).str.upper()
        product_type = (
            work["product_type"].astype(str).str.upper() if "product_type" in work.columns else pd.Series("", index=work.index)
        )
        work["is_fuel"] = department.eq("FUEL") | product_type.str.contains("GASOLINE", na=False)
    else:
        work["is_fuel"] = work["is_fuel"].fillna(False).astype(bool)
    work["department"] = work["department"].fillna("Unmapped").astype(str).replace({"nan": "Unmapped", "<NA>": "Unmapped"})
    work["product_category"] = (
        work["product_category"].fillna("Uncategorized").astype(str).replace({"nan": "Uncategorized", "<NA>": "Uncategorized"})
    )
    return work[["product_id", "department", "product_category", "is_fuel"]]


def _as_id(value) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    return text


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_COLUMNS)
