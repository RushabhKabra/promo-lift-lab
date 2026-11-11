"""Answer a question from the certified snapshot, with sources under the reply.

If OPENAI_API_KEY is set and the openai package imports, I also ask a model.
The model only receives the snapshot and the glossary. It does not receive
household-level rows. If the key is missing, or the call fails, the templated
answer is what I show.
"""

from __future__ import annotations

import os
import re

from insights.retrieve import load_glossary, load_kpis, question_is_in_scope

SYSTEM_PROMPT = (
    "You are the voice of a personal grocery-promotion lab. Speak in the first person, "
    "as someone who built the lab and is reading the certified numbers. Use only the JSON "
    "snapshot and the glossary in the user message. Cite the metric, the grain, and the "
    "period. If the question is outside that material, say you cannot answer it from this lab. "
    "Do not invent campaigns, departments, or figures. Do not discuss individual households."
)


def answer_question(question: str, kpis: dict | None = None, glossary: str | None = None) -> dict:
    kpis = kpis if kpis is not None else load_kpis()
    glossary = glossary if glossary is not None else load_glossary()
    if not question_is_in_scope(question):
        return {
            "answer": (
                "I only answer from the certified tables in this lab. "
                "Ask me about a campaign, a department, the forecast, or who responds to discounts."
            ),
            "sources": [],
            "used_llm": False,
            "refused": True,
        }
    templated = _template(question, kpis)
    model_text = _try_llm(question, kpis, glossary)
    if model_text:
        return {
            "answer": model_text,
            "sources": templated["sources"],
            "used_llm": True,
            "refused": False,
        }
    templated["used_llm"] = False
    templated["refused"] = False
    return templated


def insight_cards(kpis: dict | None = None) -> list[dict]:
    kpis = kpis if kpis is not None else load_kpis()
    cards = []
    for question in [
        "Which campaigns lost money after discounts?",
        "Where was the feature lift largest?",
        "Did the forecast beat the four-week mean?",
        "Which week looks unusual?",
    ]:
        cards.append({"question": question, **_template(question, kpis)})
    return cards


def _template(question: str, kpis: dict) -> dict:
    text = question.lower()
    headline = kpis.get("headline") or {}
    period = _period(headline)
    if any(word in text for word in ("forecast", "mape", "predict", "four-week", "naive")):
        return _forecast_answer(headline, kpis.get("forecast_scores") or [], period)
    if any(word in text for word in ("segment", "rfm", "sensitive", "household", "customer")):
        return _segment_answer(headline, kpis.get("segments") or [], period)
    if any(word in text for word in ("halo", "cannibal", "basket")):
        return _halo_answer(kpis.get("halo") or [], period)
    if "anomal" in text or "unusual" in text:
        return _anomaly_answer(kpis.get("anomalies") or [], period)
    if any(word in text for word in ("lost", "worst", "didn't pay", "did not pay", "negative", "lose")):
        return _worst_campaign(kpis.get("campaigns") or [], headline, period)
    campaign_id = _campaign_id(text)
    if campaign_id:
        return _one_campaign(campaign_id, kpis.get("campaigns") or [], period)
    department = _department_match(text, kpis.get("departments") or [])
    if department is not None and any(word in text for word in ("department", "category", "lift", "meat", "grocery", "produce", "deli")):
        return _department_answer(department, period)
    if any(word in text for word in ("best", "largest", "biggest lift", "where")):
        return _best_lift(kpis.get("departments") or [], headline, period)
    return _overview(headline, period)


def _forecast_answer(headline: dict, scores: list, period: str) -> dict:
    naive = headline.get("forecast_naive_wmape")
    tree = headline.get("forecast_ml_wmape")
    default = headline.get("forecast_default_model")
    beats = headline.get("forecast_ml_beats_naive")
    if naive is None or tree is None:
        answer = "I don't have a scored forecast in this snapshot yet."
    elif beats:
        answer = (
            f"On the holdout weeks, the tree model's sales-weighted MAPE was {_pct(tree)} "
            f"against {_pct(naive)} for the mean of the previous four weeks. "
            f"I keep the tree as the default ({default})."
        )
    else:
        answer = (
            f"The four-week mean beat the tree model. Sales-weighted MAPE was {_pct(naive)} "
            f"for the mean and {_pct(tree)} for the tree, so the default stays the simpler forecast "
            f"({default}). A year of weeks is not much history for a model to earn its place."
        )
    return {
        "answer": answer,
        "sources": [
            {"metric": "forecast_mape", "grain": "department-week, sales-weighted", "period": period, "value": naive},
            {"metric": "forecast_mape_tree", "grain": "department-week, sales-weighted", "period": period, "value": tree},
        ],
    }


def _segment_answer(headline: dict, segments: list, period: str) -> dict:
    share = headline.get("promo_sensitive_share")
    threshold = headline.get("promo_sensitive_threshold")
    n = headline.get("promo_sensitive_households")
    bits = []
    if share is not None:
        bits.append(
            f"{_pct(share)} of households ({n}) put at least {_pct(threshold)} of their pre-discount ring "
            "on a recorded discount, with at least 8 baskets. That is my promo-sensitive share."
        )
    if segments:
        top = max(segments, key=lambda row: row.get("sales_share") or 0)
        bits.append(
            f"The {top.get('segment')} segment is {_pct(top.get('household_share'))} of households and "
            f"{_pct(top.get('sales_share'))} of net sales."
        )
    return {
        "answer": " ".join(bits) or "I don't have segment results in this snapshot.",
        "sources": [
            {
                "metric": "promo_sensitive_household_share",
                "grain": "household",
                "period": period,
                "value": share,
            }
        ],
    }


def _halo_answer(halo: list, period: str) -> dict:
    if not halo:
        return {"answer": "I don't have basket or halo results in this snapshot.", "sources": []}
    top = halo[0]
    direction = top.get("direction")
    answer = (
        f"The strongest weekly association I fit was {top.get('source_department')} placement "
        f"with {top.get('target_department')} sales, and the sign points to {direction}. "
        f"The coefficient is { _money(top.get('coef_sales_per_intensity')) } of {top.get('target_department')} "
        f"sales per unit of {top.get('source_department')} placement intensity "
        f"(t = {top.get('t_stat'):.2f} on {top.get('n_weeks')} weeks). "
        "That is a short-panel regression with a week trend and each department's own flyer, not a causal halo."
    )
    return {
        "answer": answer,
        "sources": [
            {
                "metric": "halo_coefficient",
                "grain": "department-week",
                "period": period,
                "value": top.get("coef_sales_per_intensity"),
            }
        ],
    }


def _anomaly_answer(anomalies: list, period: str) -> dict:
    if not anomalies:
        return {
            "answer": "No department-week cleared the robust-z or isolation-forest bar in this snapshot.",
            "sources": [{"metric": "robust_z", "grain": "department-week", "period": period, "value": None}],
        }
    row = max(anomalies, key=lambda item: abs(item.get("robust_z") or 0))
    answer = (
        f"Week {row.get('week_no')} in {row.get('department')} sits away from its trailing eight-week median. "
        f"Net sales were {_money(row.get('net_sales'))} against a trailing median of {_money(row.get('trail_median'))} "
        f"(robust z {row.get('robust_z'):.1f}, flagged by {row.get('reason')})."
    )
    return {
        "answer": answer,
        "sources": [
            {"metric": "robust_z", "grain": "department-week", "period": f"week {row.get('week_no')}", "value": row.get("robust_z")}
        ],
    }


def _worst_campaign(campaigns: list, headline: dict, period: str) -> dict:
    scored = [row for row in campaigns if row.get("status") == "ok" and row.get("incremental_sales") is not None]
    if not scored:
        return {"answer": "No campaign has a scored incrementality result in this snapshot.", "sources": []}
    worst = min(scored, key=lambda row: row.get("incremental_sales"))
    n_negative = headline.get("n_campaigns_negative_incremental")
    answer = (
        f"Campaign {worst.get('campaign_id')} ({worst.get('campaign_type')}) is the one I would not run back. "
        f"The difference-in-differences puts incremental net sales at {_money(worst.get('incremental_sales'))} "
        f"against coupon and match discounts of {_money(worst.get('coupon_cost'))}. "
        f"ROI proxy {_num(worst.get('roi'))}. "
        f"{n_negative} scored campaigns have incremental net sales below zero."
    )
    return {
        "answer": answer,
        "sources": [
            {
                "metric": "incremental_sales",
                "grain": "campaign, household-week difference-in-differences",
                "period": _campaign_period(worst, period),
                "value": worst.get("incremental_sales"),
            },
            {
                "metric": "promo_roi_proxy",
                "grain": "campaign",
                "period": _campaign_period(worst, period),
                "value": worst.get("roi"),
            },
        ],
    }


def _one_campaign(campaign_id: str, campaigns: list, period: str) -> dict:
    matches = [row for row in campaigns if str(row.get("campaign_id")) == str(campaign_id)]
    if not matches:
        return {"answer": f"I don't have campaign {campaign_id} in the certified campaign table.", "sources": []}
    row = matches[0]
    answer = (
        f"Campaign {row.get('campaign_id')} ({row.get('campaign_type')}, status {row.get('status')}) "
        f"shows incremental net sales of {_money(row.get('incremental_sales'))} "
        f"and a coupon-cost ROI proxy of {_num(row.get('roi'))}. "
        f"Mailed households in the scored panel: {row.get('n_treated')}. "
        f"Redemption rate {_pct(row.get('redemption_rate'))}."
    )
    return {
        "answer": answer,
        "sources": [
            {
                "metric": "incremental_sales",
                "grain": "campaign",
                "period": _campaign_period(row, period),
                "value": row.get("incremental_sales"),
            }
        ],
    }


def _department_answer(row: dict, period: str) -> dict:
    answer = (
        f"In {row.get('department')}, the matched product-store baseline says feature weeks sold "
        f"{_pct(row.get('lift_pct'))} versus the non-feature run-rate, on {row.get('n_product_stores')} "
        f"product-store pairs. Incremental net sales {_money(row.get('incremental_sales'))}, "
        f"discounts on those feature weeks {_money(row.get('discount_cost'))}, ROI proxy {_num(row.get('roi'))}."
    )
    return {
        "answer": answer,
        "sources": [
            {
                "metric": "feature_lift",
                "grain": "product-store, rolled to department",
                "period": period,
                "value": row.get("lift_pct"),
            }
        ],
    }


def _best_lift(departments: list, headline: dict, period: str) -> dict:
    if not departments:
        return {"answer": "I don't have a department lift table in this snapshot.", "sources": []}
    best = max(departments, key=lambda row: row.get("incremental_sales") or float("-inf"))
    answer = (
        f"The largest incremental net sales on the matched panel are in {best.get('department')}: "
        f"{_money(best.get('incremental_sales'))}, a {_pct(best.get('lift_pct'))} lift versus the non-feature "
        f"run-rate. Across the whole matched panel, feature incremental net sales are "
        f"{_money(headline.get('feature_incremental_sales'))}, covering {_pct(headline.get('feature_coverage'))} "
        "of non-fuel feature-week sales. The rest of the feature sales sit on product-store pairs I would not give a baseline."
    )
    return {
        "answer": answer,
        "sources": [
            {
                "metric": "incremental_sales",
                "grain": "department, matched product-store",
                "period": period,
                "value": best.get("incremental_sales"),
            }
        ],
    }


def _overview(headline: dict, period: str) -> dict:
    answer = (
        f"From {period}, the retailer received {_money(headline.get('net_sales'))}. "
        f"Recorded discounts were {_money(headline.get('discount_cost'))}, "
        f"{_pct(headline.get('discount_share_of_gross'))} of the pre-discount ring. "
        f"On product-store pairs with a real baseline, feature weeks added "
        f"{_money(headline.get('feature_incremental_sales'))} of net sales "
        f"({_pct(headline.get('feature_lift_pct'))} versus their own non-feature weeks). "
        f"{headline.get('n_campaigns_negative_incremental')} scored campaigns came in below their baseline."
    )
    return {
        "answer": answer,
        "sources": [
            {"metric": "net_sales", "grain": "study", "period": period, "value": headline.get("net_sales")},
            {
                "metric": "incremental_sales",
                "grain": "matched product-store",
                "period": period,
                "value": headline.get("feature_incremental_sales"),
            },
        ],
    }


def _campaign_id(text: str) -> str | None:
    match = re.search(r"campaign\s+(\d+)", text)
    return match.group(1) if match else None


def _department_match(text: str, departments: list) -> dict | None:
    aliases = {
        "packaged meat": "MEAT-PCKGD",
        "meat-pckgd": "MEAT-PCKGD",
    }
    by_name = {str(row.get("department") or "").upper(): row for row in departments}
    for phrase, canonical in aliases.items():
        if phrase in text and canonical in by_name:
            return by_name[canonical]
    # Longest name first so a specific department wins when its full name is in the question.
    ordered = sorted(departments, key=lambda row: len(str(row.get("department") or "")), reverse=True)
    for row in ordered:
        name = str(row.get("department") or "")
        if not name:
            continue
        if name.upper() == "MEAT" and "packaged" in text:
            continue
        if name.lower() in text:
            return row
    return None


def _period(headline: dict) -> str:
    start = headline.get("period_start") or "the study"
    end = headline.get("period_end") or ""
    if end:
        return f"{str(start)[:10]} to {str(end)[:10]}"
    return str(start)


def _campaign_period(row: dict, fallback: str) -> str:
    start = row.get("start_date")
    end = row.get("end_date")
    if start and end:
        return f"{str(start)[:10]} to {str(end)[:10]}"
    return fallback


def _money(value) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number < 0:
        return f"-${abs(number):,.0f}"
    return f"${number:,.0f}"


def _pct(value) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.1%}"


def _num(value) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number != number:  # NaN
        return "n/a"
    return f"{number:.2f}"


def _try_llm(question: str, kpis: dict, glossary: str) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    import json

    user = (
        "Glossary:\n"
        + glossary[:8000]
        + "\n\nCertified KPI snapshot (aggregates only):\n"
        + json.dumps(kpis)[:24000]
        + f"\n\nQuestion: {question}"
    )
    try:
        client = OpenAI(api_key=key)
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        )
    except Exception:
        return None
    text = response.choices[0].message.content if response.choices else None
    return text.strip() if text else None


def main() -> None:
    import sys

    question = " ".join(sys.argv[1:]).strip() or "Which campaigns lost money after discounts?"
    result = answer_question(question)
    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for source in result["sources"]:
            print(f"- {source['metric']} · {source['grain']} · {source['period']} · {source['value']}")


if __name__ == "__main__":
    main()
