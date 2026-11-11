"""Load the certified KPI snapshot. Household-level rows are not included."""

from __future__ import annotations

import json

from warehouse.db import ROOT

SNAPSHOT = ROOT / "exports" / "app" / "certified_kpis.json"
GLOSSARY = ROOT / "docs" / "metrics-glossary.md"


def load_kpis() -> dict:
    if SNAPSHOT.exists():
        return json.loads(SNAPSHOT.read_text())
    from warehouse.db import get_engine
    from warehouse.load import read_df

    engine = get_engine()
    headline = read_df(engine, "SELECT * FROM marts.v_headline")
    campaigns = read_df(engine, "SELECT * FROM marts.v_campaign_results")
    departments = read_df(engine, "SELECT * FROM marts.v_department_lift")
    return {
        "headline": json.loads(headline.to_json(orient="records"))[0],
        "campaigns": json.loads(campaigns.to_json(orient="records", date_format="iso")),
        "departments": json.loads(departments.to_json(orient="records")),
        "categories": [],
        "forecast_scores": [],
        "segments": [],
        "anomalies": [],
        "halo": [],
        "worked_example": {},
        "ops": {},
    }


def load_glossary() -> str:
    if GLOSSARY.exists():
        return GLOSSARY.read_text()
    return ""


def question_is_in_scope(question: str) -> bool:
    text = question.lower()
    tokens = [
        "campaign",
        "promo",
        "promotion",
        "lift",
        "roi",
        "discount",
        "forecast",
        "mape",
        "predict",
        "segment",
        "rfm",
        "household",
        "customer",
        "basket",
        "halo",
        "cannibal",
        "anomal",
        "coupon",
        "redeem",
        "department",
        "category",
        "meat",
        "grocery",
        "produce",
        "deli",
        "fuel",
        "baseline",
        "incremental",
        "sales",
        "week",
        "feature",
        "mailer",
        "display",
        "sensitive",
        "pay",
        "lost",
        "money",
        "worst",
        "best",
        "how did",
        "what moved",
    ]
    return any(token in text for token in tokens)
