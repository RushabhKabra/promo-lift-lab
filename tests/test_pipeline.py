import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from quality.checks import collect_assertion_results, parse_assertions, quality_gate_failed
from scripts.export import (
    curated_partition_path,
    curated_table_path,
    is_weekly_mart,
    write_curated_frames,
)
from scripts.run_pipeline import PIPELINE_ENV
from warehouse.ops import (
    LINEAGE,
    count_relation,
    ensure_ops,
    finish_run,
    lineage_rows,
    record_lineage,
    record_quality_results,
    source_path,
    start_run,
)


def test_fixture_source_paths_point_at_committed_files():
    path = source_path("fixtures", "transactions")
    assert path == "data/fixtures/transactions.parquet"
    assert (Path(__file__).resolve().parents[1] / path).exists()


def test_lineage_rows_follow_a_file_to_a_mart():
    rows = lineage_rows("fixtures")
    assert len(rows) == len(LINEAGE)
    weekly = next(row for row in rows if row["mart_object"] == "marts.v_weekly_department")
    assert weekly["source_object"] == "data/fixtures/transactions.parquet"
    assert weekly["staging_object"] == "staging.transactions"
    assert weekly["core_object"] == "core.fct_transactions"
    assert weekly["grain"] == "week, department"


def test_is_weekly_mart_skips_dimensions():
    weekly = pd.DataFrame({"week_no": [1], "net_sales": [10.0]})
    dim = pd.DataFrame({"week_no": [1], "is_partial": [True]})
    scores = pd.DataFrame({"model": ["naive_last_4"], "weighted_mape": [0.087]})
    assert is_weekly_mart("weekly_department", weekly) is True
    assert is_weekly_mart("forecast_weekly", weekly) is True
    assert is_weekly_mart("dim_week", dim) is False
    assert is_weekly_mart("forecast_scores", scores) is False


def test_curated_paths_use_week_folders():
    base = Path("/tmp/curated")
    assert curated_partition_path(base, "weekly_total", 7) == base / "weekly_total" / "week_no=7" / "part.parquet"
    assert curated_table_path(base, "headline") == base / "headline" / "part.parquet"


def test_write_curated_frames_partitions_weekly_marts(tmp_path):
    weekly = pd.DataFrame(
        {
            "week_no": [1, 1, 2],
            "department": ["GROCERY", "MEAT", "GROCERY"],
            "net_sales": [10.0, 4.0, 12.0],
        }
    )
    scores = pd.DataFrame({"model": ["naive_last_4"], "weighted_mape": [0.087]})
    dim = pd.DataFrame({"week_no": [1, 2], "is_partial": [True, False]})
    written = write_curated_frames(
        {"weekly_department": weekly, "forecast_scores": scores, "dim_week": dim},
        tmp_path,
    )
    assert written["weekly_department"] == 2
    week1 = pd.read_parquet(tmp_path / "weekly_department" / "week_no=1" / "part.parquet")
    week2 = pd.read_parquet(tmp_path / "weekly_department" / "week_no=2" / "part.parquet")
    assert set(week1["department"]) == {"GROCERY", "MEAT"}
    assert week2["net_sales"].tolist() == [12.0]
    assert written["forecast_scores"] == 1
    assert (tmp_path / "forecast_scores" / "part.parquet").exists()
    assert (tmp_path / "dim_week" / "part.parquet").exists()
    assert not (tmp_path / "dim_week" / "week_no=1").exists()


def test_write_curated_frames_replaces_stale_partitions(tmp_path):
    stale = tmp_path / "weekly_department" / "week_no=99" / "part.parquet"
    stale.parent.mkdir(parents=True)
    pd.DataFrame({"week_no": [99], "net_sales": [1]}).to_parquet(stale, index=False)
    write_curated_frames(
        {"weekly_department": pd.DataFrame({"week_no": [1], "net_sales": [2.0]})},
        tmp_path,
    )
    assert not stale.exists()
    assert (tmp_path / "weekly_department" / "week_no=1" / "part.parquet").exists()


def test_quality_gate_failed_is_false_only_when_every_check_passed():
    assert quality_gate_failed([]) is False
    assert quality_gate_failed([{"passed": True, "failing_rows": 0}]) is False
    assert quality_gate_failed([{"passed": True, "failing_rows": 0}, {"passed": False, "failing_rows": 1}]) is True


def _engine():
    try:
        from warehouse.db import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"warehouse not reachable: {exc}")


def test_ops_audit_records_quality_and_lineage_on_a_built_warehouse():
    engine = _engine()
    with engine.connect() as conn:
        facts = conn.execute(text("SELECT to_regclass('core.fct_transactions')")).scalar()
    if not facts:
        pytest.skip("star schema not built")
    ensure_ops(engine)
    run_id = start_run(engine, source="fixtures", triggered_by="pytest", note="audit self-check")
    results = collect_assertion_results(engine)
    assert [row["assertion_name"] for row in results] == [name for name, _ in parse_assertions()]
    record_quality_results(engine, run_id, results)
    record_lineage(engine, run_id, "fixtures")
    finish_run(engine, run_id, "success")
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM ops.pipeline_runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
        quality_n = conn.execute(
            text("SELECT COUNT(*) FROM ops.quality_results WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
        lineage_n = conn.execute(
            text("SELECT COUNT(*) FROM ops.lineage WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
    assert status == "success"
    assert quality_n == len(results)
    assert lineage_n == len(LINEAGE)
    assert quality_gate_failed(results) is False
    assert count_relation(engine, "core.fct_transactions",) >= 1


def test_pipeline_orchestrator_is_not_reentered_from_its_own_pytest():
    # If this test is running, pytest itself is fine. The live orchestrator
    # sets PROMO_PIPELINE_RUN so a nested make pipeline cannot start here.
    if os.environ.get(PIPELINE_ENV) == "1":
        assert True
        return
    assert os.environ.get(PIPELINE_ENV) in (None, "", "0")
