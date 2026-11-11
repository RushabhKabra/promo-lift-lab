"""Run ingest, build, tests, and publish under one run_id.

A quality assertion that fails marks the run as failed and stops the remaining
steps. That is the point: a number does not get published if the totals drifted.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quality.checks import collect_assertion_results, quality_gate_failed  # noqa: E402
from warehouse.db import get_engine  # noqa: E402
from warehouse.ops import (  # noqa: E402
    count_relation,
    finish_run,
    finish_step,
    record_lineage,
    record_quality_results,
    start_run,
    start_step,
)

PIPELINE_ENV = "PROMO_PIPELINE_RUN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the lab from landing to publish under one run id.")
    parser.add_argument("--source", choices=["github", "fixtures", "kaggle-csv", "uci"], default="github")
    parser.add_argument("--dir", type=Path, default=None, help="Folder of Kaggle CSVs or raw mirrors.")
    parser.add_argument("--refresh", action="store_true", help="Ignore the parquet cache and reread the source.")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest. Quality assertions still run during build.",
    )
    args = parser.parse_args(argv)

    from scripts import build as build_mod  # local imports keep --help fast
    from scripts import export as export_mod
    from scripts.ingest import load_staging

    engine = get_engine()
    run_id = start_run(
        engine,
        source=args.source,
        triggered_by="scripts/run_pipeline.py",
        note="weekend rebuild: land, check, publish",
    )
    print(f"pipeline run {run_id}")
    source_name = args.source
    failed_note = None

    try:
        step_id = start_step(engine, run_id, "ingest")
        try:
            source_name = load_staging(source=args.source, data_dir=args.dir, refresh=args.refresh)
            rows = count_relation(engine, "staging.transactions") or 0
            finish_step(engine, step_id, "success", rows_in=rows, rows_out=rows, note=source_name)
            record_lineage(engine, run_id, source_name)
        except Exception as exc:
            finish_step(engine, step_id, "failed", note=str(exc))
            raise

        step_id = start_step(engine, run_id, "build")
        build_error: SystemExit | None = None
        try:
            build_mod.main()
        except SystemExit as exc:
            if _is_failure(exc):
                build_error = exc
            else:
                raise
        except Exception as exc:
            finish_step(engine, step_id, "failed", note=str(exc))
            raise
        results = collect_assertion_results(engine)
        record_quality_results(engine, run_id, results)
        rows_in = count_relation(engine, "staging.transactions")
        rows_out = count_relation(engine, "core.fct_transactions")
        if build_error or quality_gate_failed(results):
            finish_step(engine, step_id, "failed", rows_in=rows_in, rows_out=rows_out, note="quality gate failed")
            raise SystemExit("Quality checks failed.")
        passed = sum(1 for result in results if result["passed"])
        finish_step(
            engine,
            step_id,
            "success",
            rows_in=rows_in,
            rows_out=rows_out,
            note=f"{passed} assertions passed",
        )

        if args.skip_tests:
            step_id = start_step(engine, run_id, "test")
            finish_step(engine, step_id, "skipped", note="--skip-tests")
        else:
            step_id = start_step(engine, run_id, "test")
            code = _run_pytest()
            if code != 0:
                finish_step(engine, step_id, "failed", note=f"pytest exit {code}")
                raise SystemExit(code)
            finish_step(engine, step_id, "success")

        step_id = start_step(engine, run_id, "export")
        try:
            export_mod.main()
            from scripts.export import CURATED

            n_files = sum(1 for path in CURATED.rglob("*.parquet"))
            finish_step(
                engine,
                step_id,
                "success",
                rows_out=n_files,
                note=f"{n_files} curated parquet files",
            )
        except Exception as exc:
            finish_step(engine, step_id, "failed", note=str(exc))
            raise

        finish_run(engine, run_id, "success", note=source_name)
        print(f"pipeline run {run_id} succeeded")
        return 0
    except SystemExit as exc:
        failed_note = str(exc)
        finish_run(engine, run_id, "failed", note=failed_note)
        print(f"pipeline run {run_id} failed: {failed_note}", file=sys.stderr)
        code = exc.code if isinstance(exc.code, int) else 1
        return code or 1
    except Exception as exc:
        failed_note = str(exc)
        finish_run(engine, run_id, "failed", note=failed_note)
        print(f"pipeline run {run_id} failed: {failed_note}", file=sys.stderr)
        raise


def _is_failure(exc: SystemExit) -> bool:
    return exc.code not in (0, None)


def _run_pytest() -> int:
    env = os.environ.copy()
    env[PIPELINE_ENV] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return int(result.returncode)


if __name__ == "__main__":
    sys.exit(main())
