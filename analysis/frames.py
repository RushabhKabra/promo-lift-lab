"""Column cleanup shared by the GitHub mirrors, the Kaggle CSVs, and fixtures."""

from __future__ import annotations

import json

import pandas as pd

from analysis.metrics import gross_sales, normalize_discount_signs

KAGGLE_RENAMES = {
    "household_key": "household_id",
    "product_id": "product_id",
    "store_id": "store_id",
    "basket_id": "basket_id",
    "day": "day",
    "week_no": "week",
    "trans_time": "trans_time",
    "quantity": "quantity",
    "sales_value": "sales_value",
    "retail_disc": "retail_disc",
    "coupon_disc": "coupon_disc",
    "coupon_match_disc": "coupon_match_disc",
    "commodity_desc": "product_category",
    "sub_commodity_desc": "product_type",
    "curr_size_of_product": "package_size",
    "manufacturer": "manufacturer_id",
    "department": "department",
    "brand": "brand",
    "display": "display_location",
    "mailer": "mailer_location",
    "campaign": "campaign_id",
    "description": "campaign_type",
    "start_day": "start_day",
    "end_day": "end_day",
    "coupon_upc": "coupon_upc",
    "age_desc": "age",
    "income_desc": "income",
    "homeowner_desc": "home_ownership",
    "hh_comp_desc": "household_comp",
    "household_size_desc": "household_size",
    "kid_category_desc": "kids_count",
    "marital_status_code": "marital_status",
}


def _stringify(series: pd.Series) -> pd.Series:
    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype("object")
    out = series.astype("string").str.strip()
    return out.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "<NA>": pd.NA, "NaN": pd.NA})


def text_id(series: pd.Series) -> pd.Series:
    """IDs arrive as strings or as floats after a CSV round-trip. Keep them stable."""
    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype("object")
    numeric = pd.to_numeric(series, errors="coerce")
    as_text = _stringify(series)
    whole = numeric.notna() & np_is_whole(numeric)
    as_text = as_text.copy()
    as_text.loc[whole] = numeric.loc[whole].astype("int64").astype("string")
    return as_text


def np_is_whole(numeric: pd.Series) -> pd.Series:
    return numeric.notna() & (numeric % 1 == 0) & numeric.abs().lt(10**15)


def rename_kaggle(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {c.lower(): c for c in df.columns}
    mapping = {}
    for src, dest in KAGGLE_RENAMES.items():
        if src in lookup:
            mapping[lookup[src]] = dest
    out = df.rename(columns=mapping)
    out.columns = [c.lower() for c in out.columns]
    return out


def collapse_promotions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per product, store, and week.

    A handful of placements are duplicated. Joining them straight onto
    transactions double-counts those lines, so I collapse first and keep a
    non-zero location code when one of the duplicates has one.
    """
    work = df.copy()
    work["product_id"] = text_id(work["product_id"])
    work["store_id"] = text_id(work["store_id"])
    work["week"] = pd.to_numeric(work["week"], errors="coerce").astype("int64")
    work["display_location"] = _stringify(work["display_location"]).fillna("0")
    work["mailer_location"] = _stringify(work["mailer_location"]).fillna("0")
    work["on_display"] = work["display_location"] != "0"
    work["in_mailer"] = work["mailer_location"] != "0"
    # Prefer a featured code over "0" via sort, then take the first row.
    work = work.sort_values(["on_display", "in_mailer"], ascending=False)
    grouped = (
        work.groupby(["product_id", "store_id", "week"], sort=False)
        .agg(
            display_location=("display_location", _first_nonzero),
            mailer_location=("mailer_location", _first_nonzero),
            on_display=("on_display", "max"),
            in_mailer=("in_mailer", "max"),
        )
        .reset_index()
    )
    return grouped


def _first_nonzero(values: pd.Series) -> str:
    for value in values:
        if value not in ("0", "", None) and not pd.isna(value):
            return str(value)
    return "0"


def prepare_transactions(df: pd.DataFrame, study_start: str = "2017-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize a transaction extract and quarantine rows I will not defend."""
    work = normalize_discount_signs(df)
    work["household_id"] = text_id(work["household_id"])
    work["store_id"] = text_id(work["store_id"])
    work["basket_id"] = text_id(work["basket_id"])
    work["product_id"] = text_id(work["product_id"])
    for col in ("quantity", "sales_value", "retail_disc", "coupon_disc", "coupon_match_disc"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    if "week" not in work.columns and "week_no" in work.columns:
        work["week"] = work["week_no"]
    work["week"] = pd.to_numeric(work["week"], errors="coerce")

    if "transaction_timestamp" in work.columns:
        work["transaction_timestamp"] = pd.to_datetime(work["transaction_timestamp"], errors="coerce")
    elif "day" in work.columns:
        day = pd.to_numeric(work["day"], errors="coerce")
        work["transaction_timestamp"] = pd.to_datetime(study_start) + pd.to_timedelta(day - 1, unit="D")
    else:
        work["transaction_timestamp"] = pd.NaT

    reasons = pd.Series("", index=work.index)
    reasons = _mark(reasons, work["household_id"].isna(), "missing_household")
    reasons = _mark(reasons, work["store_id"].isna(), "missing_store")
    reasons = _mark(reasons, work["basket_id"].isna(), "missing_basket")
    reasons = _mark(reasons, work["product_id"].isna(), "missing_product")
    reasons = _mark(reasons, work["sales_value"].isna(), "missing_sales")
    reasons = _mark(reasons, work["quantity"].isna(), "missing_quantity")
    reasons = _mark(reasons, work["week"].isna(), "missing_week")
    reasons = _mark(reasons, work["sales_value"] < -0.001, "negative_sales")
    # Returns would be negative quantity. This mirror has none. If a future
    # extract does, I keep them (is_return) rather than dropping the reversal.
    work["is_return"] = work["quantity"] < -0.001

    dup = work.duplicated(["basket_id", "product_id"], keep="first") & work["basket_id"].notna()
    reasons = _mark(reasons, dup, "duplicate_basket_product")

    rejected_mask = reasons.ne("")
    rejected = work.loc[rejected_mask].copy()
    rejected["reject_reason"] = reasons.loc[rejected_mask].to_numpy()
    good = work.loc[~rejected_mask].copy()
    good["week"] = good["week"].astype(int)
    for col in ("retail_disc", "coupon_disc", "coupon_match_disc"):
        good[col] = good[col].fillna(0.0).clip(lower=0.0)
    good["discount_cost"] = good["retail_disc"] + good["coupon_disc"] + good["coupon_match_disc"]
    good["gross_sales"] = gross_sales(
        good["sales_value"], good["retail_disc"], good["coupon_disc"], good["coupon_match_disc"]
    )
    good["date_key"] = good["transaction_timestamp"].dt.floor("D")
    return good, rejected


def rejects_to_records(rejected: pd.DataFrame, source_table: str) -> pd.DataFrame:
    if rejected.empty:
        return pd.DataFrame(columns=["source_table", "reason", "row_json"])
    keep_cols = [c for c in rejected.columns if c != "reject_reason"]
    records = []
    for _, row in rejected.iterrows():
        payload = {col: _jsonable(row[col]) for col in keep_cols}
        records.append(
            {
                "source_table": source_table,
                "reason": row["reject_reason"],
                "row_json": json.dumps(payload, default=str),
            }
        )
    return pd.DataFrame.from_records(records)


def _jsonable(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _mark(reasons: pd.Series, mask: pd.Series, reason: str) -> pd.Series:
    hit = mask.fillna(False) & reasons.eq("")
    reasons = reasons.copy()
    reasons.loc[hit] = reason
    return reasons


def prepare_products(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["product_id"] = text_id(work["product_id"])
    work = work.dropna(subset=["product_id"]).drop_duplicates("product_id", keep="first")
    for col in ("manufacturer_id", "department", "brand", "product_category", "product_type", "package_size"):
        if col not in work.columns:
            work[col] = pd.NA
        work[col] = _stringify(work[col])
    work["department"] = work["department"].fillna("Unmapped")
    work["product_category"] = work["product_category"].fillna("Uncategorized")
    work["product_type"] = work["product_type"].fillna("Unspecified")
    work["brand"] = work["brand"].fillna("Unknown")
    work["is_fuel"] = work["department"].str.upper().eq("FUEL") | work["product_type"].str.upper().str.contains(
        "GASOLINE", na=False
    )
    return work


def price_off_promotions(transactions: pd.DataFrame, depth: float = 0.15) -> pd.DataFrame:
    """Fallback feature flag when a file has prices but no mailer or display.

    A product-week is treated as on offer when its median unit price sits at
    least `depth` below that product's own median. This is a discount-depth
    stand-in, not a flyer.
    """
    work = transactions.copy()
    work = work.loc[work["quantity"] > 0]
    work["unit_price"] = work["sales_value"] / work["quantity"]
    if "week" not in work.columns:
        work["week"] = work["transaction_timestamp"].dt.isocalendar().week.astype(int)
    product_median = work.groupby("product_id")["unit_price"].median().rename("median_price")
    week_price = work.groupby(["product_id", "store_id", "week"], as_index=False)["unit_price"].median()
    week_price = week_price.merge(product_median, on="product_id", how="left")
    week_price = week_price.loc[week_price["unit_price"] <= week_price["median_price"] * (1 - depth)]
    week_price["display_location"] = "PRICE_OFF"
    week_price["mailer_location"] = "0"
    week_price["on_display"] = True
    week_price["in_mailer"] = False
    return week_price[
        ["product_id", "store_id", "week", "display_location", "mailer_location", "on_display", "in_mailer"]
    ]
