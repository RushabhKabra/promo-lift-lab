"""Land Complete Journey files in staging.

Default path: the public completejourney mirrors (no login). If those files
are already in data/raw, they are reused. Pass --source fixtures for the
committed slice, or --source kaggle-csv if you have the Kaggle extract.
If the mirrors cannot be fetched, the lab falls back to UCI Online Retail II
so the warehouse still has something honest to build.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pyreadr
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.frames import (  # noqa: E402
    collapse_promotions,
    prepare_products,
    prepare_transactions,
    price_off_promotions,
    rename_kaggle,
    text_id,
)
from quality.contracts import validate_transactions  # noqa: E402
from warehouse.db import ROOT as PROJECT_ROOT  # noqa: E402
from warehouse.db import get_engine, run_sql_file  # noqa: E402
from warehouse.load import copy_frame, execute  # noqa: E402

GITHUB = "https://raw.githubusercontent.com/bradleyboehmke/completejourney/master/data"
FILES = {
    "transactions.rds": f"{GITHUB}/transactions.rds",
    "promotions.rds": f"{GITHUB}/promotions.rds",
    "products.rda": f"{GITHUB}/products.rda",
    "campaigns.rda": f"{GITHUB}/campaigns.rda",
    "campaign_descriptions.rda": f"{GITHUB}/campaign_descriptions.rda",
    "coupons.rda": f"{GITHUB}/coupons.rda",
    "coupon_redemptions.rda": f"{GITHUB}/coupon_redemptions.rda",
    "demographics.rda": f"{GITHUB}/demographics.rda",
}
UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"

RAW = PROJECT_ROOT / "data" / "raw"
PROCESSED = PROJECT_ROOT / "data" / "processed"
FIXTURES = PROJECT_ROOT / "data" / "fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load source files into staging.")
    parser.add_argument("--source", choices=["github", "fixtures", "kaggle-csv", "uci"], default="github")
    parser.add_argument("--dir", type=Path, default=None, help="Folder of Kaggle CSVs or raw mirrors.")
    parser.add_argument("--refresh", action="store_true", help="Ignore the parquet cache and reread the source.")
    args = parser.parse_args()

    engine = get_engine()
    run_sql_file(engine, PROJECT_ROOT / "warehouse" / "ddl" / "001_schemas.sql")
    run_sql_file(engine, PROJECT_ROOT / "warehouse" / "ddl" / "002_staging.sql")

    if args.source == "fixtures":
        frames = _read_fixture_parquets()
        source_name = "fixtures"
    elif args.source == "kaggle-csv":
        folder = args.dir or (RAW / "kaggle")
        frames = _read_kaggle(folder)
        source_name = "kaggle-csv"
    elif args.source == "uci":
        frames = _read_uci()
        source_name = "uci-online-retail-ii"
    else:
        try:
            frames = _read_github(refresh=args.refresh)
            source_name = "completejourney-github"
        except Exception as exc:  # noqa: BLE001 — fallback is the documented path
            print(f"GitHub mirrors unavailable ({exc}). Falling back to UCI Online Retail II.")
            frames = _read_uci()
            source_name = "uci-online-retail-ii"

    _land(engine, frames, source_name)
    print(f"staging loaded from {source_name}")


def _read_github(refresh: bool) -> dict[str, pd.DataFrame]:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cache = PROCESSED / "transactions.parquet"
    if cache.exists() and not refresh and (PROCESSED / "promotions.parquet").exists():
        print("reading parquet cache in data/processed")
        frames = {name: pd.read_parquet(PROCESSED / f"{name}.parquet") for name in _frame_names()}
        frames["rejects"] = pd.DataFrame(columns=["source_table", "reason", "row_json"])
        return frames

    for name, url in FILES.items():
        dest = RAW / name
        if not dest.exists() or refresh:
            print(f"downloading {name}")
            _download(url, dest)
    print("reading R files")
    transactions, rejected = prepare_transactions(_read_r(RAW / "transactions.rds"))
    validate_transactions(transactions)
    products = prepare_products(_read_r(RAW / "products.rda"))
    promotions = collapse_promotions(_read_r(RAW / "promotions.rds"))
    if _full_build_disabled():
        keep = set(transactions["product_id"])
        before = len(promotions)
        promotions = promotions.loc[promotions["product_id"].isin(keep)].copy()
        print(f"FULL_BUILD=0 kept {len(promotions):,} of {before:,} promotion rows for products that sold")
    campaigns = _read_r(RAW / "campaigns.rda")
    descriptions = _read_r(RAW / "campaign_descriptions.rda")
    coupons = _read_r(RAW / "coupons.rda")
    redemptions = _read_r(RAW / "coupon_redemptions.rda")
    demographics = _read_r(RAW / "demographics.rda")
    frames = _pack(transactions, rejected, products, promotions, campaigns, descriptions, coupons, redemptions, demographics)
    _write_cache(frames)
    return frames


def _read_fixture_parquets() -> dict[str, pd.DataFrame]:
    frames = {}
    for name in _frame_names():
        path = FIXTURES / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        frames[name] = pd.read_parquet(path)
    if "rejects" not in frames:
        frames["rejects"] = pd.DataFrame(columns=["source_table", "reason", "row_json"])
    return frames


def _read_kaggle(folder: Path) -> dict[str, pd.DataFrame]:
    def _csv(stem: str) -> pd.DataFrame:
        matches = list(folder.glob(f"{stem}.csv")) + list(folder.glob(f"{stem}.CSV"))
        if not matches:
            raise FileNotFoundError(f"{stem}.csv not in {folder}")
        frame = pd.read_csv(matches[0])
        frame.columns = [c.lower() for c in frame.columns]
        return rename_kaggle(frame)

    transactions, rejected = prepare_transactions(_csv("transaction_data"))
    products = prepare_products(_csv("product"))
    promotions = collapse_promotions(_csv("causal_data").rename(columns={"week_no": "week"}))
    campaigns = _csv("campaign_table")
    descriptions = _csv("campaign_desc")
    if "start_day" in descriptions.columns:
        origin = pd.Timestamp("2017-01-01")
        descriptions["start_date"] = origin + pd.to_timedelta(pd.to_numeric(descriptions["start_day"]) - 1, unit="D")
        descriptions["end_date"] = origin + pd.to_timedelta(pd.to_numeric(descriptions["end_day"]) - 1, unit="D")
    coupons = _csv("coupon")
    redemptions = _csv("coupon_redempt")
    if "day" in redemptions.columns and "redemption_date" not in redemptions.columns:
        origin = pd.Timestamp("2017-01-01")
        redemptions["redemption_date"] = origin + pd.to_timedelta(pd.to_numeric(redemptions["day"]) - 1, unit="D")
    demographics = _csv("hh_demographic")
    return _pack(transactions, rejected, products, promotions, campaigns, descriptions, coupons, redemptions, demographics)


def _read_uci() -> dict[str, pd.DataFrame]:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "online_retail_ii.zip"
    if not dest.exists():
        print("downloading UCI Online Retail II")
        _download(UCI_URL, dest)
    frames = []
    with zipfile.ZipFile(dest) as archive:
        for name in archive.namelist():
            if name.lower().endswith((".xlsx", ".xls")):
                frames.append(pd.read_excel(io.BytesIO(archive.read(name))))
    if not frames:
        raise RuntimeError("UCI archive did not contain a spreadsheet")
    raw = pd.concat(frames, ignore_index=True)
    raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]
    raw = raw.rename(columns={"customer_id": "household_id", "invoice": "basket_id", "stockcode": "product_id", "price": "unit_price", "invoicedate": "transaction_timestamp"})
    raw = raw.dropna(subset=["household_id"])
    raw["household_id"] = text_id(raw["household_id"])
    raw["store_id"] = raw["country"].astype(str)
    raw["basket_id"] = raw["basket_id"].astype(str)
    raw["product_id"] = raw["product_id"].astype(str)
    raw["quantity"] = pd.to_numeric(raw["quantity"], errors="coerce")
    raw["unit_price"] = pd.to_numeric(raw["unit_price"], errors="coerce")
    raw["sales_value"] = raw["quantity"] * raw["unit_price"]
    raw["retail_disc"] = 0.0
    raw["coupon_disc"] = 0.0
    raw["coupon_match_disc"] = 0.0
    raw["transaction_timestamp"] = pd.to_datetime(raw["transaction_timestamp"])
    origin = raw["transaction_timestamp"].min().normalize()
    raw["week"] = ((raw["transaction_timestamp"].dt.normalize() - origin).dt.days // 7) + 1
    transactions, rejected = prepare_transactions(raw)
    products = prepare_products(
        raw.rename(columns={"description": "product_category"})[
            ["product_id", "product_category"]
        ].drop_duplicates("product_id")
    )
    products["department"] = products["product_category"].fillna("Uncategorized")
    products["is_fuel"] = False
    promotions = price_off_promotions(transactions)
    empty_campaigns = pd.DataFrame(columns=["campaign_id", "household_id"])
    empty_desc = pd.DataFrame(columns=["campaign_id", "campaign_type", "start_date", "end_date"])
    empty_coupons = pd.DataFrame(columns=["coupon_upc", "product_id", "campaign_id"])
    empty_redemptions = pd.DataFrame(columns=["household_id", "coupon_upc", "campaign_id", "redemption_date"])
    empty_demo = pd.DataFrame(columns=["household_id", "age", "income", "home_ownership", "marital_status", "household_size", "household_comp", "kids_count"])
    print("UCI fallback has no campaigns. Feature flags are price-off weeks, not a mailer.")
    return _pack(transactions, rejected, products, promotions, empty_campaigns, empty_desc, empty_coupons, empty_redemptions, empty_demo)


def _pack(transactions, rejected, products, promotions, campaigns, descriptions, coupons, redemptions, demographics) -> dict[str, pd.DataFrame]:
    from analysis.frames import rejects_to_records

    promotions = promotions.rename(columns={"week": "week_no"})
    campaigns = campaigns.copy()
    campaigns["campaign_id"] = text_id(campaigns["campaign_id"]) if len(campaigns) else campaigns.get("campaign_id", pd.Series(dtype="string"))
    if len(campaigns):
        campaigns["household_id"] = text_id(campaigns["household_id"])
        campaigns = campaigns[["campaign_id", "household_id"]].dropna().drop_duplicates()
    descriptions = descriptions.copy()
    if len(descriptions):
        descriptions["campaign_id"] = text_id(descriptions["campaign_id"])
        descriptions["campaign_type"] = descriptions["campaign_type"].astype(str)
        descriptions["start_date"] = pd.to_datetime(descriptions["start_date"]).dt.date
        descriptions["end_date"] = pd.to_datetime(descriptions["end_date"]).dt.date
    coupons = coupons.copy()
    if len(coupons):
        for col in ("coupon_upc", "product_id", "campaign_id"):
            coupons[col] = text_id(coupons[col])
        coupons = coupons.dropna(subset=["coupon_upc", "product_id", "campaign_id"])
    redemptions = redemptions.copy()
    if len(redemptions):
        for col in ("household_id", "coupon_upc", "campaign_id"):
            redemptions[col] = text_id(redemptions[col])
        redemptions["redemption_date"] = pd.to_datetime(redemptions["redemption_date"]).dt.date
    demographics = demographics.copy()
    if len(demographics):
        demographics["household_id"] = text_id(demographics["household_id"])
        for col in ("age", "income", "home_ownership", "marital_status", "household_size", "household_comp", "kids_count"):
            if col not in demographics.columns:
                demographics[col] = pd.NA
            demographics[col] = demographics[col].astype("string")
    return {
        "transactions": transactions,
        "rejects": rejects_to_records(rejected, "transactions"),
        "products": products,
        "promotions": promotions,
        "campaigns": campaigns,
        "campaign_descriptions": descriptions,
        "coupons": coupons,
        "coupon_redemptions": redemptions,
        "demographics": demographics,
    }


def _land(engine, frames: dict[str, pd.DataFrame], source_name: str) -> None:
    print("clearing staging tables")
    execute(
        engine,
        """
        TRUNCATE TABLE
            staging.transactions,
            staging.products,
            staging.promotions,
            staging.campaigns,
            staging.campaign_descriptions,
            staging.coupons,
            staging.coupon_redemptions,
            staging.demographics,
            staging.rejects
        RESTART IDENTITY
        """,
    )
    tx_cols = [
        "household_id", "store_id", "basket_id", "product_id", "quantity", "sales_value",
        "retail_disc", "coupon_disc", "coupon_match_disc", "discount_cost", "gross_sales",
        "week_no", "transaction_timestamp", "date_key", "is_return",
    ]
    transactions = frames["transactions"].rename(columns={"week": "week_no"})
    print(f"loading transactions {len(transactions):,}")
    copy_frame(engine, transactions, "staging.transactions", tx_cols)
    print(f"loading products {len(frames['products']):,}")
    copy_frame(
        engine,
        frames["products"],
        "staging.products",
        ["product_id", "manufacturer_id", "department", "brand", "product_category", "product_type", "package_size", "is_fuel"],
    )
    print(f"loading promotions {len(frames['promotions']):,}")
    copy_frame(
        engine,
        frames["promotions"],
        "staging.promotions",
        ["product_id", "store_id", "week_no", "display_location", "mailer_location", "on_display", "in_mailer"],
    )
    _copy_optional(engine, frames["campaigns"], "staging.campaigns", ["campaign_id", "household_id"])
    _copy_optional(
        engine,
        frames["campaign_descriptions"],
        "staging.campaign_descriptions",
        ["campaign_id", "campaign_type", "start_date", "end_date"],
    )
    _copy_optional(engine, frames["coupons"], "staging.coupons", ["coupon_upc", "product_id", "campaign_id"])
    _copy_optional(
        engine,
        frames["coupon_redemptions"],
        "staging.coupon_redemptions",
        ["household_id", "coupon_upc", "campaign_id", "redemption_date"],
    )
    _copy_optional(
        engine,
        frames["demographics"],
        "staging.demographics",
        ["household_id", "age", "income", "home_ownership", "marital_status", "household_size", "household_comp", "kids_count"],
    )
    if frames["rejects"] is not None and len(frames["rejects"]):
        copy_frame(engine, frames["rejects"], "staging.rejects", ["source_table", "reason", "row_json"])

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO staging.etl_run_log
                    (source, table_name, rows_in, rows_loaded, rows_rejected, status, finished_at, note)
                VALUES
                    (:source, 'transactions', :rows_in, :rows_loaded, :rejected, 'loaded', NOW(), :note)
                """
            ),
            {
                "source": source_name,
                "rows_in": int(len(transactions) + len(frames["rejects"])),
                "rows_loaded": int(len(transactions)),
                "rejected": int(len(frames["rejects"])),
                "note": "discounts stored as non-negative costs; sales_value is cash received",
            },
        )


def _copy_optional(engine, frame: pd.DataFrame, table: str, columns: list[str]) -> None:
    if frame is None or frame.empty:
        print(f"loading {table} 0")
        return
    print(f"loading {table} {len(frame):,}")
    copy_frame(engine, frame, table, columns)


def _write_cache(frames: dict[str, pd.DataFrame]) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        if name == "rejects":
            continue
        frame.to_parquet(PROCESSED / f"{name}.parquet", index=False)


def _frame_names() -> list[str]:
    return [
        "transactions",
        "products",
        "promotions",
        "campaigns",
        "campaign_descriptions",
        "coupons",
        "coupon_redemptions",
        "demographics",
    ]


def _read_r(path: Path) -> pd.DataFrame:
    loaded = pyreadr.read_r(str(path))
    if None in loaded:
        return loaded[None]
    return next(iter(loaded.values()))


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=180) as response, dest.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def _full_build_disabled() -> bool:
    import os

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    return os.environ.get("FULL_BUILD", "1") == "0"


if __name__ == "__main__":
    main()
