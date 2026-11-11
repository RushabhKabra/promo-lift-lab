"""COPY helpers. to_sql is too slow once promotions land."""

from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def copy_frame(engine: Engine, frame: pd.DataFrame, table: str, columns: list[str]) -> int:
    if frame.empty:
        return 0
    payload = frame.loc[:, columns]
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        step = 250_000
        for start in range(0, len(payload), step):
            chunk = payload.iloc[start : start + step]
            buffer = io.StringIO()
            chunk.to_csv(buffer, index=False, header=False, na_rep="\\N")
            buffer.seek(0)
            column_list = ", ".join(columns)
            cursor.copy_expert(
                f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                buffer,
            )
        raw.commit()
    finally:
        raw.close()
    return len(payload)


def execute(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def read_df(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)
