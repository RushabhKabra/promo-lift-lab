"""Warehouse assertions. Skipped when Postgres is not loaded."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from quality.checks import parse_assertions, run_assertions
from warehouse.db import get_engine


def _engine():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"warehouse not reachable: {exc}")


def test_assertion_file_has_the_reconciliation_check():
    names = [name for name, _ in parse_assertions()]
    assert "sales_reconcile" in names
    assert "transaction_grain" in names
    assert "promotion_grain" in names


def test_sql_assertions_pass():
    engine = _engine()
    with engine.connect() as conn:
        staging = conn.execute(text("SELECT to_regclass('staging.transactions')")).scalar()
        facts = conn.execute(text("SELECT to_regclass('core.fct_transactions')")).scalar()
    if staging and not facts:
        pytest.fail("staging is loaded but the star schema is missing; run make build")
    if not facts:
        pytest.skip("star schema not built")
    failures = run_assertions(engine)
    assert failures == []


def test_full_build_has_a_campaign_that_does_not_pay():
    engine = _engine()
    with engine.connect() as conn:
        facts = conn.execute(text("SELECT to_regclass('marts.campaign_results')")).scalar()
        if not facts:
            pytest.skip("campaign mart not built")
        n_lines = conn.execute(text("SELECT COUNT(*) FROM core.fct_transactions")).scalar()
        if n_lines < 100_000:
            pytest.skip("fixture build is too small to require a losing campaign")
        negative = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM marts.campaign_results
                WHERE status = 'ok' AND incremental_sales < 0
                """
            )
        ).scalar()
    assert negative and negative > 0


def test_forecast_scores_exist_on_the_full_build():
    engine = _engine()
    with engine.connect() as conn:
        if not conn.execute(text("SELECT to_regclass('marts.forecast_scores')")).scalar():
            pytest.skip("forecast mart not built")
        n_lines = conn.execute(text("SELECT COUNT(*) FROM core.fct_transactions")).scalar()
        if n_lines < 100_000:
            pytest.skip("fixture build")
        models = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM marts.forecast_scores
                WHERE model IN ('naive_last_4', 'hist_gradient_boosting')
                  AND department = 'ALL' AND scope = 'all'
                """
            )
        ).scalar()
    assert models >= 2
