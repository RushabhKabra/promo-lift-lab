"""Run the named statements in assertions.sql. Any returned row fails the build."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

ASSERTIONS = Path(__file__).with_name("assertions.sql")


def parse_assertions(sql: str | None = None) -> list[tuple[str, str]]:
    body = sql if sql is not None else ASSERTIONS.read_text()
    checks: list[tuple[str, str]] = []
    name: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("-- NAME:"):
            if name and "".join(buf).strip():
                checks.append((name, "\n".join(buf).strip().rstrip(";")))
            name = line.split(":", 1)[1].strip()
            buf = []
            continue
        buf.append(line)
    if name and "".join(buf).strip():
        checks.append((name, "\n".join(buf).strip().rstrip(";")))
    return checks


def run_assertions(engine: Engine) -> list[tuple[str, pd.DataFrame]]:
    failures: list[tuple[str, pd.DataFrame]] = []
    with engine.connect() as conn:
        for name, statement in parse_assertions():
            frame = pd.read_sql(text(statement), conn)
            if len(frame):
                failures.append((name, frame))
    return failures


def assert_clean(engine: Engine) -> None:
    failures = run_assertions(engine)
    if not failures:
        return
    lines = []
    for name, frame in failures:
        lines.append(f"{name}: {len(frame)} failing row(s)")
        lines.append(frame.head(5).to_string(index=False))
    raise SystemExit("Quality checks failed.\n" + "\n".join(lines))

def collect_assertion_results(engine: Engine) -> list[dict]:
    """Run every named assertion and return passes as well as failures."""
    results: list[dict] = []
    with engine.connect() as conn:
        for name, statement in parse_assertions():
            try:
                frame = pd.read_sql(text(statement), conn)
                failing = int(len(frame))
                detail = frame.head(5).to_json(orient="records") if failing else None
                results.append(
                    {
                        "assertion_name": name,
                        "passed": failing == 0,
                        "failing_rows": failing,
                        "detail": detail,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — record a broken check, do not hide it
                results.append(
                    {
                        "assertion_name": name,
                        "passed": False,
                        "failing_rows": -1,
                        "detail": str(exc),
                    }
                )
    return results


def quality_gate_failed(results: list[dict]) -> bool:
    return any(not result["passed"] for result in results)
