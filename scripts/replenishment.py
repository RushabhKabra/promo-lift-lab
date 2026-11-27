"""Store-SKU replenishment exports.

Reads the public Complete Journey mirrors (the same files `make ingest` uses)
and writes the forecast-accuracy table, the order policy, and the promotion
risk rollups. Postgres is not required. Raw files are downloaded into
data/raw when they are not already there, and a parquet cache under
data/processed keeps the next run from rereading the R files.

    python scripts/replenishment.py
    python scripts/replenishment.py --refresh

The grocery-unit total is checked against exports/app/certified_kpis.json
when that file is present. A drift above one unit stops the run, because the
order math is only worth quoting if it is on the same units as the rest of
the lab.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.frames import collapse_promotions, prepare_products, prepare_transactions, text_id  # noqa: E402
from replenishment.run import run_replenishment  # noqa: E402

GITHUB = "https://raw.githubusercontent.com/bradleyboehmke/completejourney/master/data"
FILES = {
    "transactions.rds": f"{GITHUB}/transactions.rds",
    "promotions.rds": f"{GITHUB}/promotions.rds",
    "products.rda": f"{GITHUB}/products.rda",
}
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
BI = ROOT / "exports" / "bi"
APP = ROOT / "exports" / "app"
KPIS = APP / "certified_kpis.json"
UNIT_TOLERANCE = 1.0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forecast store-SKU demand and write the order policy.")
    parser.add_argument("--refresh", action="store_true", help="Ignore the parquet cache and reread the R files.")
    parser.add_argument("--lead-time", type=int, default=1, help="Lead time in weeks. Default 1.")
    parser.add_argument("--review", type=int, default=1, help="Review interval in weeks. Default 1.")
    parser.add_argument("--service-level", type=float, default=0.95, help="Cycle service level. Default 0.95.")
    args = parser.parse_args(argv)

    transactions, products, promotions = load_inputs(refresh=args.refresh)
    _check_units(transactions, products)
    print("scoring store-SKU series")
    result = run_replenishment(
        transactions,
        products,
        promotions,
        lead_time_weeks=args.lead_time,
        review_weeks=args.review,
        service_level=args.service_level,
    )
    paths = write_outputs(result)
    summary = result["summary"].iloc[0]
    print(
        f"series {int(summary['n_series']):,}  "
        f"default {summary['default_model']}  "
        f"WAPE ma4 {summary['wape_moving_average_4']}  "
        f"promo {summary['wape_promo_adjusted']}  "
        f"seasonal {summary['wape_seasonal_naive']}"
    )
    print(
        f"feature-week shortfall vs quiet mean {summary['units_short_vs_quiet_mean']:.1f} units  "
        f"extra if the feature rate is ordered on quiet weeks {summary['units_extra_if_feature_rate_on_quiet']:.1f}"
    )
    for path in paths:
        print(f"wrote {path}")


def load_inputs(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cache_tx = PROCESSED / "repl_transactions.parquet"
    cache_products = PROCESSED / "repl_products.parquet"
    cache_promo = PROCESSED / "repl_promotions.parquet"
    if not refresh and cache_tx.exists() and cache_products.exists() and cache_promo.exists():
        print("reading replenishment cache in data/processed", flush=True)
        return pd.read_parquet(cache_tx), pd.read_parquet(cache_products), pd.read_parquet(cache_promo)

    _ensure_raw()
    if refresh or not (cache_tx.exists() and cache_products.exists()):
        print("reading transactions", flush=True)
        transactions, _rejected = prepare_transactions(_read_r(RAW / "transactions.rds"))
        print(f"  {len(transactions):,} lines", flush=True)
        print("reading products", flush=True)
        products = prepare_products(_read_r(RAW / "products.rda"))
        print(f"  {len(products):,} products", flush=True)
        keep_tx = ["product_id", "store_id", "week", "quantity", "date_key", "transaction_timestamp"]
        transactions = transactions[keep_tx]
        transactions.to_parquet(cache_tx, index=False)
        products.to_parquet(cache_products, index=False)
    else:
        print("reading cached transactions and products", flush=True)
        transactions = pd.read_parquet(cache_tx)
        products = pd.read_parquet(cache_products)

    print("reading promotions", flush=True)
    promotions = _promotions_for_sold_pairs(_read_r(RAW / "promotions.rds"), transactions)
    promotions.to_parquet(cache_promo, index=False)
    return transactions, products, promotions


def _promotions_for_sold_pairs(raw_promo: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Keep placements for product-store pairs the panel actually bought.

    The promotions file is every featured store, including stores where this
    panel never bought the item. Those rows cannot change a series. Filtering
    them out before the collapse is what keeps the pass in memory.
    """
    sold = transactions.loc[pd.to_numeric(transactions["quantity"], errors="coerce").fillna(0) > 0, ["product_id", "store_id"]]
    sold = sold.drop_duplicates()
    sold["pair"] = sold["product_id"].astype(str) + "\t" + sold["store_id"].astype(str)
    sold_pairs = set(sold["pair"])
    print(f"  {len(sold_pairs):,} product-store pairs with a sale", flush=True)

    work = raw_promo
    work["product_id"] = text_id(work["product_id"])
    work["store_id"] = text_id(work["store_id"])
    pair = work["product_id"].astype(str) + "\t" + work["store_id"].astype(str)
    before = len(work)
    work = work.loc[pair.isin(sold_pairs)].copy()
    print(f"  {before:,} placements, {len(work):,} on pairs that sold", flush=True)
    promotions = collapse_promotions(work)
    print(f"  {len(promotions):,} product-store-weeks after collapsing duplicates", flush=True)
    return promotions


def write_outputs(result: dict) -> list[Path]:
    BI.mkdir(parents=True, exist_ok=True)
    APP.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    accuracy = result["accuracy"]
    policy = result["policy"]
    weekly = result["weekly"]
    department = result["department"]
    category = result["category"]

    files = {
        BI / "replenishment_summary.csv": summary,
        BI / "replenishment_accuracy.csv": accuracy,
        BI / "replenishment_policy.csv": policy,
        BI / "replenishment_weekly.csv": weekly,
        BI / "replenishment_department.csv": department,
        BI / "replenishment_category.csv": category,
    }
    for path, frame in files.items():
        frame.to_csv(path, index=False)

    summary.to_parquet(APP / "replenishment_summary.parquet", index=False)
    accuracy.to_parquet(APP / "replenishment_accuracy.parquet", index=False)
    weekly.to_parquet(APP / "replenishment_weekly.parquet", index=False)
    department.to_parquet(APP / "replenishment_department.parquet", index=False)

    payload = {
        "summary": _records(summary),
        "accuracy": _records(accuracy),
        "department": _records(department),
        "category_top_shortfall": _records(category.head(15) if len(category) else category),
    }
    destination = APP / "replenishment_summary.json"
    destination.write_text(json.dumps(payload, indent=2))
    return [*files.keys(), destination]


def _check_units(transactions: pd.DataFrame, products: pd.DataFrame) -> None:
    fuel = set(products.loc[products["is_fuel"].fillna(False).astype(bool), "product_id"])
    units = float(pd.to_numeric(transactions["quantity"], errors="coerce").fillna(0.0).loc[
        ~transactions["product_id"].isin(fuel)
    ].sum())
    print(f"non-fuel units {units:,.2f}")
    if not KPIS.exists():
        print("certified_kpis.json is not here, so I did not reconcile the unit total")
        return
    expected = float(json.loads(KPIS.read_text())["headline"]["grocery_units"])
    drift = units - expected
    print(f"certified grocery units {expected:,.2f}, drift {drift:,.4f}")
    if abs(drift) > UNIT_TOLERANCE:
        raise SystemExit(
            f"grocery units drifted by {drift:,.2f}, above {UNIT_TOLERANCE}. "
            "I will not write a replenishment number that is on a different unit total."
        )


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    rows = json.loads(frame.to_json(orient="records"))
    return rows


def _ensure_raw() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = RAW / name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        print(f"downloading {name}")
        with urllib.request.urlopen(url, timeout=180) as response, dest.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def _read_r(path: Path):
    import pyreadr

    loaded = pyreadr.read_r(str(path))
    if None in loaded:
        return loaded[None]
    return next(iter(loaded.values()))


if __name__ == "__main__":
    main()
