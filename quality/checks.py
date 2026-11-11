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
