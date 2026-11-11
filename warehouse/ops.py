"""End-to-end run audit: one run_id for ingest, build, checks, and publish."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from warehouse.db import ROOT, run_sql_file

OPS_DDL = ROOT / "warehouse" / "ddl" / "004_ops.sql"

# Paths a number travels from a landed file to a mart I would quote.
# source_object is the logical file name; source_path() fills in the folder.
LINEAGE = [
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_weekly_department", "week, department"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_weekly_total", "week"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_department_lift", "department"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_category_lift", "department, category"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_campaign_results", "campaign"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_forecast_weekly", "week, department"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_forecast_scores", "model, department"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_segment_summary", "segment"),
    ("transactions", "staging.transactions", "core.fct_transactions", "marts.v_headline", "one row"),
    ("promotions", "staging.promotions", "core.fct_promotions", "marts.v_department_lift", "department"),
    ("promotions", "staging.promotions", "core.fct_promotions", "marts.v_category_lift", "department, category"),
    ("products", "staging.products", "core.dim_product", "marts.v_weekly_department", "week, department"),
    ("campaigns", "staging.campaigns", "core.fct_campaign_households", "marts.v_campaign_results", "campaign"),
    ("campaign_descriptions", "staging.campaign_descriptions", "core.dim_campaign", "marts.v_campaign_results", "campaign"),
    ("coupons", "staging.coupons", "core.bridge_coupon_product", "marts.v_campaign_results", "campaign"),
    ("coupon_redemptions", "staging.coupon_redemptions", "core.fct_coupon_redemptions", "marts.v_campaign_results", "campaign"),
    ("demographics", "staging.demographics", "core.dim_household", "marts.v_segment_summary", "segment"),
]

SOURCE_FOLDERS = {
    "fixtures": "data/fixtures",
    "completejourney-github": "data/raw",
    "kaggle-csv": "data/raw/kaggle",
    "uci-online-retail-ii": "data/raw",
}

SOURCE_SUFFIX = {
    "fixtures": ".parquet",
    "completejourney-github": ".rds",
    "kaggle-csv": ".csv",
    "uci-online-retail-ii": ".xlsx",
}


def source_path(source_name: str, logical_name: str) -> str:
    folder = SOURCE_FOLDERS.get(source_name, "data/raw")
    suffix = SOURCE_SUFFIX.get(source_name, "")
    return f"{folder}/{logical_name}{suffix}"


def lineage_rows(source_name: str) -> list[dict[str, str]]:
    rows = []
    for logical, staging, core, mart, grain in LINEAGE:
        rows.append(
            {
                "source_name": source_name,
                "source_object": source_path(source_name, logical),
                "staging_object": staging,
                "core_object": core,
                "mart_object": mart,
                "grain": grain,
            }
        )
    return rows


def ensure_ops(engine: Engine) -> None:
    run_sql_file(engine, OPS_DDL)


def start_run(engine: Engine, source: str | None, triggered_by: str, note: str | None = None) -> int:
    ensure_ops(engine)
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                """
                INSERT INTO ops.pipeline_runs (status, source, triggered_by, note)
                VALUES ('running', :source, :triggered_by, :note)
                RETURNING run_id
                """
            ),
            {"source": source, "triggered_by": triggered_by, "note": note},
        ).scalar_one()
    return int(run_id)


def finish_run(engine: Engine, run_id: int, status: str, note: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ops.pipeline_runs
                SET finished_at = NOW(),
                    status = :status,
                    note = COALESCE(:note, note)
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id, "status": status, "note": note},
        )


def start_step(engine: Engine, run_id: int, step_name: str) -> int:
    with engine.begin() as conn:
        step_id = conn.execute(
            text(
                """
                INSERT INTO ops.pipeline_run_steps (run_id, step_name, status)
                VALUES (:run_id, :step_name, 'running')
                RETURNING step_id
                """
            ),
            {"run_id": run_id, "step_name": step_name},
        ).scalar_one()
    return int(step_id)


def finish_step(
    engine: Engine,
    step_id: int,
    status: str,
    rows_in: int | None = None,
    rows_out: int | None = None,
    note: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ops.pipeline_run_steps
                SET finished_at = NOW(),
                    duration_ms = CAST(EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000 AS BIGINT),
                    status = :status,
                    rows_in = :rows_in,
                    rows_out = :rows_out,
                    note = :note
                WHERE step_id = :step_id
                """
            ),
            {
                "step_id": step_id,
                "status": status,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "note": note,
            },
        )


def record_quality_results(engine: Engine, run_id: int, results: list[dict]) -> None:
    if not results:
        return
    with engine.begin() as conn:
        for result in results:
            conn.execute(
                text(
                    """
                    INSERT INTO ops.quality_results
                        (run_id, assertion_name, passed, failing_rows, detail)
                    VALUES
                        (:run_id, :assertion_name, :passed, :failing_rows, :detail)
                    """
                ),
                {
                    "run_id": run_id,
                    "assertion_name": result["assertion_name"],
                    "passed": bool(result["passed"]),
                    "failing_rows": int(result["failing_rows"]),
                    "detail": result.get("detail"),
                },
            )


def record_lineage(engine: Engine, run_id: int, source_name: str) -> None:
    rows = lineage_rows(source_name)
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO ops.lineage
                        (run_id, source_name, source_object, staging_object, core_object, mart_object, grain)
                    VALUES
                        (:run_id, :source_name, :source_object, :staging_object, :core_object, :mart_object, :grain)
                    """
                ),
                {"run_id": run_id, **row},
            )


def count_relation(engine: Engine, qualified_name: str) -> int | None:
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass(:name)"), {"name": qualified_name}).scalar()
        if not exists:
            return None
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {qualified_name}")).scalar() or 0)
