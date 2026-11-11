"""Build the star schema from staging, then the analytical marts."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.run_all import main as run_analyses  # noqa: E402
from quality.checks import assert_clean  # noqa: E402
from warehouse.db import get_engine, run_sql_file  # noqa: E402


def main() -> None:
    engine = get_engine()
    print("star schema")
    run_sql_file(engine, ROOT / "warehouse" / "ddl" / "003_star.sql")
    run_sql_file(engine, ROOT / "warehouse" / "models" / "marts" / "020_load_star.sql")
    run_sql_file(engine, ROOT / "warehouse" / "models" / "staging" / "010_documented_columns.sql")
    print("marking feature placements on receipt lines")
    with engine.begin() as conn:
        conn.execute(text("SET work_mem = '256MB'"))
        conn.execute(text("ANALYZE core.fct_transactions"))
        conn.execute(text("ANALYZE core.fct_promotions"))
        conn.execute(
            text(
                """
                UPDATE core.fct_transactions AS t
                SET on_feature = TRUE
                FROM core.fct_promotions AS p
                WHERE t.product_id = p.product_id
                  AND t.store_id = p.store_id
                  AND t.week_no = p.week_no
                """
            )
        )
    run_sql_file(engine, ROOT / "warehouse" / "models" / "marts" / "010_weekly.sql")
    print("quality assertions")
    assert_clean(engine)
    print("analyses")
    run_analyses()


if __name__ == "__main__":
    main()
