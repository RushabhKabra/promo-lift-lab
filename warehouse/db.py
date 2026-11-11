"""Database connection for the local warehouse."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql+psycopg2://promo:promo@127.0.0.1:5432/promo_lift"

# Fact totals may drift from staging by at most this much before the build fails.
RECONCILE_ABS_TOLERANCE = 1.0
RECONCILE_REL_TOLERANCE = 0.0001  # 0.01%


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def get_url() -> str:
    load_env()
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def get_engine() -> Engine:
    return create_engine(get_url(), future=True)


def run_sql_file(engine: Engine, path: Path) -> None:
    sql = path.read_text()
    # Strip full-line comments so a file of notes still executes cleanly,
    # but keep the statements themselves intact.
    statements = _split_sql(sql)
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _split_sql(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buf).strip().rstrip(";").strip()
            buf = []
            if statement:
                parts.append(statement)
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        parts.append(tail)
    return parts
