"""Read the star schema, write the marts the app is allowed to quote."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.anomalies import anomaly_table  # noqa: E402
from analysis.basket import department_affinity, halo_associations  # noqa: E402
from analysis.forecast import fit_forecast  # noqa: E402
from analysis.lift import (  # noqa: E402
    campaign_did,
    discount_depth_bins,
    product_store_baseline,
    rollup_lift,
    scored_campaigns,
)
from analysis.metrics import (  # noqa: E402
    MIN_SALE_WEEKS,
    PROMO_SENSITIVE_GROSS_SHARE,
    redemption_rate,
)
from analysis.ops import operations_summary, weekly_discount_rate  # noqa: E402
from analysis.segments import rfm_table, segment_summary  # noqa: E402
from warehouse.db import get_engine  # noqa: E402
from warehouse.load import read_df  # noqa: E402

PANEL_SQL_SIMPLE = f"""
WITH sales AS (
    SELECT
        t.product_id,
        t.store_id,
        t.week_no,
        SUM(t.grocery_units) AS units,
        SUM(t.sales_value) AS net_sales,
        SUM(t.discount_cost) AS discount_cost,
        BOOL_OR(t.on_feature) AS on_feature
    FROM core.fct_transactions t
    JOIN core.dim_product p ON p.product_id = t.product_id
    WHERE NOT p.is_fuel
    GROUP BY t.product_id, t.store_id, t.week_no
),
spans AS (
    SELECT product_id, store_id, MIN(week_no) AS min_w, MAX(week_no) AS max_w
    FROM sales
    GROUP BY product_id, store_id
    HAVING COUNT(*) >= {int(MIN_SALE_WEEKS)}
)
SELECT
    spans.product_id,
    spans.store_id,
    w.week_no,
    dp.department,
    dp.product_category,
    COALESCE(sa.units, 0) AS units,
    COALESCE(sa.net_sales, 0) AS net_sales,
    COALESCE(sa.discount_cost, 0) AS discount_cost,
    (COALESCE(sa.on_feature, FALSE) OR promo.product_id IS NOT NULL) AS on_feature
FROM spans
JOIN core.dim_week w
    ON w.week_no BETWEEN spans.min_w AND spans.max_w
   AND NOT w.is_partial
JOIN core.dim_product dp ON dp.product_id = spans.product_id
LEFT JOIN sales sa
    ON sa.product_id = spans.product_id
   AND sa.store_id = spans.store_id
   AND sa.week_no = w.week_no
LEFT JOIN core.fct_promotions promo
    ON promo.product_id = spans.product_id
   AND promo.store_id = spans.store_id
   AND promo.week_no = w.week_no
"""


def main() -> None:
    engine = get_engine()
    print("product-store panel")
    panel = read_df(engine, PANEL_SQL_SIMPLE)
    print(f"  panel rows {len(panel):,}")
    product_store = product_store_baseline(panel)
    print(f"  pairs with a baseline {len(product_store):,}")
    by_department = rollup_lift(product_store, ["department"]) if len(product_store) else pd.DataFrame()
    by_category = (
        rollup_lift(product_store, ["department", "product_category"]) if len(product_store) else pd.DataFrame()
    )
    depth = discount_depth_bins(product_store) if len(product_store) else pd.DataFrame()

    print("campaigns")
    household_week = read_df(
        engine,
        """
        SELECT household_id, week_no, SUM(sales_value) AS net_sales
        FROM core.fct_transactions
        GROUP BY household_id, week_no
        """,
    )
    exposure = read_df(engine, "SELECT campaign_id, household_id FROM core.fct_campaign_households")
    windows = read_df(
        engine,
        """
        SELECT campaign_id, campaign_type, start_week, end_week, start_date, end_date, window_clipped
        FROM core.dim_campaign
        WHERE start_week IS NOT NULL AND end_week IS NOT NULL
        """,
    )
    costs = read_df(engine, _COST_SQL)
    campaigns = campaign_did(household_week, exposure, windows, costs if len(costs) else None)
    if len(campaigns):
        campaigns["redemption_rate"] = [
            redemption_rate(row.redemptions, row.mailed_households, row.distinct_upcs)
            for row in campaigns.itertuples(index=False)
        ]

    print("forecast")
    weekly = read_df(engine, _WEEKLY_SQL)
    predictions, scores = fit_forecast(weekly)

    print("households, baskets, anomalies")
    baskets = read_df(
        engine,
        """
        SELECT
            household_id,
            basket_id,
            MIN(date_key) AS transaction_timestamp,
            SUM(sales_value) AS sales_value,
            SUM(discount_cost) AS discount_cost,
            SUM(gross_sales) AS gross_sales
        FROM core.fct_transactions
        GROUP BY household_id, basket_id
        """,
    )
    households = rfm_table(baskets) if len(baskets) else pd.DataFrame()
    segments = segment_summary(households) if len(households) else pd.DataFrame()
    basket_pairs = department_affinity(
        read_df(
            engine,
            """
            SELECT DISTINCT t.basket_id, p.department
            FROM core.fct_transactions t
            JOIN core.dim_product p ON p.product_id = t.product_id
            WHERE NOT p.is_fuel
              AND p.department NOT IN ('MISCELLANEOUS', 'Unmapped', 'CHARITABLE CONT')
            """,
        )
    )
    halo = halo_associations(weekly) if len(weekly) else pd.DataFrame()
    anomalies = anomaly_table(weekly) if len(weekly) else pd.DataFrame()

    print("operations")
    lines = read_df(
        engine,
        """
        SELECT quantity, sales_value, discount_cost, gross_sales, on_feature, is_fuel, week_no
        FROM core.fct_transactions
        """,
    )
    ops = operations_summary(lines)
    discount_weeks = weekly_discount_rate(lines)

    coverage = _coverage(engine, product_store)
    conditional = _conditional_lift(panel)
    worked = _worked_example(by_category)
    headline = _headline(
        engine, ops, product_store, by_department, campaigns, scores, households, coverage, worked, conditional
    )

    print("writing marts")
    _write(engine, product_store, "product_store_lift")
    _write(engine, by_department, "department_lift")
    _write(engine, by_category, "category_lift")
    _write(engine, depth, "discount_depth")
    _write(engine, campaigns, "campaign_results")
    _write(engine, predictions, "forecast_weekly")
    _write(engine, scores, "forecast_scores")
    # Household rows stay in the warehouse. The ask page reads the summary only.
    _write(engine, households, "household_rfm")
    _write(engine, segments, "segment_summary")
    _write(engine, basket_pairs.head(40) if len(basket_pairs) else basket_pairs, "basket_pairs")
    _write(engine, halo.head(40) if len(halo) else halo, "halo_pairs")
    _write(engine, anomalies, "anomalies")
    _write(engine, discount_weeks, "weekly_discount")
    _write(engine, pd.DataFrame([ops]), "ops_summary")
    _write(engine, pd.DataFrame([headline]), "headline")
    _write(engine, pd.DataFrame([worked]) if worked else pd.DataFrame(), "worked_example")
    _publish_views(engine)
    _write_snapshot(engine, headline, campaigns, by_department, by_category, scores, segments, anomalies, halo, worked, ops)
    print("marts ready")


_COST_SQL = """
WITH mailed AS (
    SELECT campaign_id, COUNT(*) AS mailed_households
    FROM core.fct_campaign_households
    GROUP BY campaign_id
),
upcs AS (
    SELECT campaign_id, COUNT(DISTINCT coupon_upc) AS distinct_upcs
    FROM core.bridge_coupon_product
    GROUP BY campaign_id
),
redemptions AS (
    SELECT campaign_id, COUNT(*) AS redemptions
    FROM core.fct_coupon_redemptions
    GROUP BY campaign_id
),
coupon_cost AS (
    SELECT
        ch.campaign_id,
        SUM(t.coupon_discount + t.match_discount) AS coupon_cost
    FROM core.fct_campaign_households ch
    JOIN core.dim_campaign d ON d.campaign_id = ch.campaign_id
    JOIN core.fct_transactions t
        ON t.household_id = ch.household_id
       AND t.week_no BETWEEN d.start_week AND d.end_week
    JOIN (
        SELECT DISTINCT campaign_id, product_id FROM core.bridge_coupon_product
    ) cp
        ON cp.campaign_id = ch.campaign_id
       AND cp.product_id = t.product_id
    GROUP BY ch.campaign_id
)
SELECT
    d.campaign_id,
    COALESCE(c.coupon_cost, 0) AS coupon_cost,
    COALESCE(r.redemptions, 0) AS redemptions,
    COALESCE(m.mailed_households, 0) AS mailed_households,
    COALESCE(u.distinct_upcs, 0) AS distinct_upcs
FROM core.dim_campaign d
LEFT JOIN coupon_cost c ON c.campaign_id = d.campaign_id
LEFT JOIN redemptions r ON r.campaign_id = d.campaign_id
LEFT JOIN mailed m ON m.campaign_id = d.campaign_id
LEFT JOIN upcs u ON u.campaign_id = d.campaign_id
"""

_WEEKLY_SQL = """
WITH sales AS (
    SELECT t.week_no, p.department, SUM(t.sales_value) AS net_sales
    FROM core.fct_transactions t
    JOIN core.dim_product p ON p.product_id = t.product_id
    GROUP BY t.week_no, p.department
),
placements AS (
    SELECT pr.week_no, p.department, COUNT(*)::DOUBLE PRECISION AS placements
    FROM core.fct_promotions pr
    JOIN core.dim_product p ON p.product_id = pr.product_id
    GROUP BY pr.week_no, p.department
)
SELECT
    s.week_no,
    s.department,
    s.net_sales,
    COALESCE(pl.placements, 0) AS promo_intensity,
    w.is_partial
FROM sales s
JOIN core.dim_week w ON w.week_no = s.week_no
LEFT JOIN placements pl
    ON pl.week_no = s.week_no
   AND pl.department = s.department
"""


def _conditional_lift(panel: pd.DataFrame) -> dict:
    """Mean ring on weeks that actually sold, feature versus not.

    The zero-filled baseline counts silent weeks as zero. This companion
    ignores those weeks, so it answers a smaller question: when the item
    rang up, was the ring larger on a feature week?
    """
    if panel.empty:
        return {}
    observed = panel.loc[panel["net_sales"] > 0].copy()
    observed["on_feature"] = observed["on_feature"].astype(bool)
    base = observed.loc[~observed["on_feature"], "net_sales"]
    promo = observed.loc[observed["on_feature"], "net_sales"]
    if base.empty or promo.empty or float(base.mean()) <= 0:
        return {}
    base_mean = float(base.mean())
    promo_mean = float(promo.mean())
    return {
        "conditional_base_mean": base_mean,
        "conditional_promo_mean": promo_mean,
        "conditional_lift_pct": promo_mean / base_mean - 1,
        "conditional_base_weeks": int(len(base)),
        "conditional_promo_weeks": int(len(promo)),
    }


def _coverage(engine, product_store: pd.DataFrame) -> float:
    total = read_df(
        engine,
        """
        SELECT COALESCE(SUM(t.sales_value), 0) AS feature_sales
        FROM core.fct_transactions t
        JOIN core.dim_product p ON p.product_id = t.product_id
        WHERE t.on_feature AND NOT p.is_fuel
        """,
    )
    feature_sales = float(total["feature_sales"].iloc[0]) if len(total) else 0.0
    if feature_sales <= 0 or product_store.empty:
        return float("nan")
    return float(product_store["feature_sales"].sum()) / feature_sales


def _worked_example(by_category: pd.DataFrame) -> dict:
    if by_category.empty:
        return {}
    frame = by_category.copy()
    frame = frame.loc[
        ~frame["department"].isin(["FUEL", "MISCELLANEOUS", "Unmapped", "CHARITABLE CONT"])
        & (frame["n_product_stores"] >= 25)
        & (frame["counterfactual_sales"] >= 2000)
        & frame["lift_pct"].between(0.05, 1.2)
        & (frame["incremental_sales"] > 0)
    ]
    if frame.empty:
        return {}
    preferred = ["MEAT", "DELI", "PRODUCE", "SEAFOOD", "SEAFOOD-PCKGD", "NUTRITION", "PASTRY"]
    pick = frame.loc[frame["department"].isin(preferred)]
    if pick.empty:
        pick = frame
    row = pick.sort_values(["n_product_stores", "incremental_sales"], ascending=False).iloc[0]
    return {
        "department": row["department"],
        "product_category": row["product_category"],
        "n_product_stores": int(row["n_product_stores"]),
        "feature_sales": float(row["feature_sales"]),
        "counterfactual_sales": float(row["counterfactual_sales"]),
        "incremental_sales": float(row["incremental_sales"]),
        "discount_cost": float(row["discount_cost"]),
        "lift_pct": float(row["lift_pct"]),
        "roi": float(row["roi"]) if pd.notna(row["roi"]) else None,
    }


def _headline(engine, ops, product_store, by_department, campaigns, scores, households, coverage, worked, conditional) -> dict:
    counts = read_df(
        engine,
        """
        SELECT
            (SELECT COUNT(*) FROM core.fct_transactions) AS n_lines,
            (SELECT COUNT(DISTINCT household_id) FROM core.fct_transactions) AS n_households,
            (SELECT COUNT(DISTINCT basket_id) FROM core.fct_transactions) AS n_baskets,
            (SELECT COUNT(*) FROM core.dim_store) AS n_stores,
            (SELECT COUNT(*) FROM core.dim_product) AS n_products,
            (SELECT MIN(date_key)::text FROM core.dim_date) AS period_start,
            (SELECT MAX(date_key)::text FROM core.dim_date) AS period_end,
            (SELECT SUM(sales_value) FROM staging.transactions) AS staged_sales,
            (SELECT SUM(sales_value) FROM core.fct_transactions) AS fact_sales
        """,
    ).iloc[0]
    feature_incremental = float(product_store["incremental_sales"].sum()) if len(product_store) else float("nan")
    feature_discount = float(product_store["discount_cost"].sum()) if len(product_store) else float("nan")
    feature_sales = float(product_store["feature_sales"].sum()) if len(product_store) else float("nan")
    counterfactual = float(product_store["counterfactual_sales"].sum()) if len(product_store) else float("nan")
    lift_pct = feature_sales / counterfactual - 1 if counterfactual and counterfactual > 0 else float("nan")
    scored = scored_campaigns(campaigns) if len(campaigns) else pd.DataFrame()
    negative = scored.loc[scored["incremental_sales"] < 0] if len(scored) else pd.DataFrame()
    below_one = scored.loc[scored["roi"] < 1] if len(scored) else pd.DataFrame()
    worst = negative.sort_values("incremental_sales").head(1) if len(negative) else (
        scored.sort_values("roi").head(1) if len(scored) else pd.DataFrame()
    )
    best = scored.sort_values("incremental_sales", ascending=False).head(1) if len(scored) else pd.DataFrame()
    naive = _score_value(scores, "naive_last_4")
    tree = _score_value(scores, "hist_gradient_boosting")
    comparison = ""
    if len(scores):
        notes = scores.loc[scores["model"] == "comparison", "note"]
        comparison = notes.iloc[0] if len(notes) else ""
    default_model = "naive_last_4"
    if len(scores) and "default_model" not in scores.columns:
        default_model = "hist_gradient_boosting" if (np.isfinite(tree) and np.isfinite(naive) and tree < naive) else "naive_last_4"
    elif len(predictions_default(scores, tree, naive)):
        default_model = predictions_default(scores, tree, naive)
    return {
        "period_start": counts["period_start"],
        "period_end": counts["period_end"],
        "n_lines": int(counts["n_lines"]),
        "n_households": int(counts["n_households"]),
        "n_baskets": int(counts["n_baskets"]),
        "n_stores": int(counts["n_stores"]),
        "n_products": int(counts["n_products"]),
        "net_sales": ops["net_sales"],
        "gross_sales": ops["gross_sales"],
        "discount_cost": ops["discount_cost"],
        "discount_share_of_gross": ops["discount_share_of_gross"],
        "grocery_units": ops["grocery_units"],
        "fuel_sales_share": ops["fuel_sales_share"],
        "off_feature_discount_share": ops["off_feature_discount_share"],
        "zero_quantity_share": ops["zero_quantity_share"],
        "returns_observed": ops["returns_observed"],
        "feature_incremental_sales": feature_incremental,
        "feature_lift_pct": lift_pct,
        "feature_discount_cost": feature_discount,
        "feature_roi": (feature_incremental / feature_discount) if feature_discount and feature_discount > 0 else float("nan"),
        "feature_coverage": coverage,
        "feature_pairs": int(len(product_store)),
        "conditional_base_mean": conditional.get("conditional_base_mean"),
        "conditional_promo_mean": conditional.get("conditional_promo_mean"),
        "conditional_lift_pct": conditional.get("conditional_lift_pct"),
        "conditional_base_weeks": conditional.get("conditional_base_weeks"),
        "conditional_promo_weeks": conditional.get("conditional_promo_weeks"),
        "n_campaigns": int(len(campaigns)),
        "n_campaigns_scored": int(len(scored)),
        "n_campaigns_negative_incremental": int(len(negative)),
        "n_campaigns_roi_below_one": int(len(below_one)),
        "worst_campaign_id": _cell(worst, "campaign_id"),
        "worst_campaign_incremental": _cell(worst, "incremental_sales"),
        "worst_campaign_roi": _cell(worst, "roi"),
        "worst_campaign_cost": _cell(worst, "coupon_cost"),
        "worst_campaign_type": _cell(worst, "campaign_type"),
        "best_campaign_id": _cell(best, "campaign_id"),
        "best_campaign_incremental": _cell(best, "incremental_sales"),
        "best_campaign_roi": _cell(best, "roi"),
        "best_campaign_cost": _cell(best, "coupon_cost"),
        "forecast_default_model": default_model,
        "forecast_naive_wmape": naive,
        "forecast_ml_wmape": tree,
        "forecast_ml_beats_naive": bool(np.isfinite(tree) and np.isfinite(naive) and tree < naive),
        "forecast_note": comparison,
        "promo_sensitive_share": float(households["promo_sensitive"].mean()) if len(households) else float("nan"),
        "promo_sensitive_threshold": PROMO_SENSITIVE_GROSS_SHARE,
        "promo_sensitive_households": int(households["promo_sensitive"].sum()) if len(households) else 0,
        "worked_department": worked.get("department"),
        "worked_category": worked.get("product_category"),
        "worked_lift_pct": worked.get("lift_pct"),
        "worked_incremental": worked.get("incremental_sales"),
        "reconciliation_drift": float(counts["fact_sales"] - counts["staged_sales"]),
        "top_department": _cell(by_department, "department") if len(by_department) else None,
    }


def predictions_default(scores, tree, naive) -> str:
    if np.isfinite(tree) and np.isfinite(naive) and tree < naive:
        return "hist_gradient_boosting"
    if np.isfinite(naive):
        return "naive_last_4"
    return "unavailable"


def _score_value(scores: pd.DataFrame, model: str) -> float:
    if scores.empty:
        return float("nan")
    rows = scores.loc[(scores["model"] == model) & (scores["department"] == "ALL") & (scores["scope"] == "all")]
    if rows.empty:
        return float("nan")
    return float(rows["weighted_mape"].iloc[0])


def _cell(frame: pd.DataFrame, column: str):
    if frame is None or frame.empty or column not in frame.columns:
        return None
    value = frame.iloc[0][column]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return value
    return value


def _write(engine, frame: pd.DataFrame, name: str) -> None:
    if frame is None:
        frame = pd.DataFrame()
    with engine.begin() as conn:
        conn.execute(text(f"DROP VIEW IF EXISTS marts.v_{name} CASCADE"))
        conn.execute(text(f"DROP TABLE IF EXISTS marts.{name} CASCADE"))
    frame.to_sql(name, engine, schema="marts", if_exists="replace", index=False)


def _publish_views(engine) -> None:
    names = [
        "headline",
        "campaign_results",
        "department_lift",
        "category_lift",
        "discount_depth",
        "forecast_weekly",
        "forecast_scores",
        "segment_summary",
        "basket_pairs",
        "halo_pairs",
        "anomalies",
        "ops_summary",
        "worked_example",
        "weekly_discount",
        "product_store_lift",
    ]
    with engine.begin() as conn:
        for name in names:
            conn.execute(text(f"CREATE OR REPLACE VIEW marts.v_{name} AS SELECT * FROM marts.{name}"))


def _write_snapshot(engine, headline, campaigns, by_department, by_category, scores, segments, anomalies, halo, worked, ops) -> None:
    dest = ROOT / "exports" / "app"
    dest.mkdir(parents=True, exist_ok=True)

    def _records(frame: pd.DataFrame, limit: int = 40) -> list:
        if frame is None or frame.empty:
            return []
        clipped = frame.head(limit).copy()
        return json.loads(clipped.to_json(orient="records", date_format="iso"))

    payload = {
        "headline": json.loads(pd.DataFrame([headline]).to_json(orient="records"))[0],
        "campaigns": _records(campaigns.sort_values("incremental_sales") if len(campaigns) else campaigns, 30),
        "departments": _records(by_department, 20),
        "categories": _records(by_category, 15),
        "forecast_scores": _records(scores, 40),
        "segments": _records(segments, 20),
        "anomalies": _records(anomalies, 15),
        "halo": _records(halo, 15),
        "worked_example": worked,
        "ops": ops,
    }
    (dest / "certified_kpis.json").write_text(json.dumps(payload, indent=2, default=str))
    # Small frames the app can read if Postgres is down.
    for name, frame in {
        "headline": pd.DataFrame([headline]),
        "campaign_results": campaigns,
        "department_lift": by_department,
        "forecast_scores": scores,
        "segment_summary": segments,
        "anomalies": anomalies,
        "halo_pairs": halo,
        "ops_summary": pd.DataFrame([ops]),
        "worked_example": pd.DataFrame([worked]) if worked else pd.DataFrame(),
    }.items():
        if frame is not None and len(frame):
            frame.to_parquet(dest / f"{name}.parquet", index=False)


if __name__ == "__main__":
    main()
