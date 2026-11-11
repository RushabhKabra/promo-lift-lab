"""Every number on a page comes from a certified view, or from the snapshot those views were written to."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from warehouse.db import get_engine  # noqa: E402

QUERIES = {
    "headline": "SELECT * FROM marts.v_headline",
    "weekly": "SELECT * FROM marts.v_weekly_total ORDER BY week_no",
    "weekly_department": "SELECT * FROM marts.v_weekly_department ORDER BY week_no, department",
    "campaigns": "SELECT * FROM marts.v_campaign_results",
    "departments": "SELECT * FROM marts.v_department_lift",
    "categories": "SELECT * FROM marts.v_category_lift",
    "depth": "SELECT * FROM marts.v_discount_depth",
    "forecast": "SELECT * FROM marts.v_forecast_weekly",
    "scores": "SELECT * FROM marts.v_forecast_scores",
    "segments": "SELECT * FROM marts.v_segment_summary",
    "baskets": "SELECT * FROM marts.v_basket_pairs",
    "halo": "SELECT * FROM marts.v_halo_pairs",
    "anomalies": "SELECT * FROM marts.v_anomalies",
    "ops": "SELECT * FROM marts.v_ops_summary",
    "worked": "SELECT * FROM marts.v_worked_example",
    "discount_weeks": "SELECT * FROM marts.v_weekly_discount ORDER BY week_no",
}


def load(name: str) -> pd.DataFrame:
    import streamlit as st

    @st.cache_data(ttl=300, show_spinner=False)
    def _load(query_name: str) -> pd.DataFrame:
        try:
            engine = get_engine()
            frame = pd.read_sql(QUERIES[query_name], engine)
            if len(frame):
                return frame
        except Exception:
            pass
        parquet = ROOT / "exports" / "app" / f"{_parquet_name(query_name)}.parquet"
        if parquet.exists():
            return pd.read_parquet(parquet)
        return pd.DataFrame()

    return _load(name)


def _parquet_name(query_name: str) -> str:
    return {
        "headline": "headline",
        "campaigns": "campaign_results",
        "departments": "department_lift",
        "scores": "forecast_scores",
        "segments": "segment_summary",
        "halo": "halo_pairs",
        "anomalies": "anomalies",
        "ops": "ops_summary",
        "worked": "worked_example",
    }.get(query_name, query_name)


def headline() -> dict:
    frame = load("headline")
    if frame.empty:
        return {}
    return frame.iloc[0].to_dict()
