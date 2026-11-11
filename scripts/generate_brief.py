"""Write the executive brief from the certified snapshot, after the build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights.retrieve import SNAPSHOT  # noqa: E402


def main() -> None:
    if not SNAPSHOT.exists():
        raise SystemExit("No certified snapshot. Run make build first.")
    payload = json.loads(SNAPSHOT.read_text())
    text = render(payload)
    path = ROOT / "docs" / "executive-brief.md"
    path.write_text(text)
    examples = ROOT / "insights" / "examples.md"
    examples.write_text(_examples(payload))
    print(f"wrote {path}")


def render(payload: dict) -> str:
    h = payload["headline"]
    start = str(h.get("period_start") or "")[:10]
    end = str(h.get("period_end") or "")[:10]
    worked = payload.get("worked_example") or {}
    campaigns = payload.get("campaigns") or []
    scored = [row for row in campaigns if row.get("status") == "ok"]
    losers = sorted(
        [row for row in scored if (row.get("incremental_sales") or 0) < 0],
        key=lambda row: row.get("incremental_sales"),
    )
    winners = sorted(scored, key=lambda row: row.get("incremental_sales") or 0, reverse=True)
    departments = payload.get("departments") or []
    segments = payload.get("segments") or []
    forecast_line = _forecast_sentence(h)
    loser_line = _loser_sentence(losers, h)
    winner_line = _winner_sentence(winners)
    worked_line = _worked_sentence(worked)
    segment_line = _segment_sentence(h, segments)
    dept_lines = _dept_lines(departments[:5])

    return f"""# What I would tell myself after this pass

Study window {start} to {end}. Household panel from the public Complete Journey mirrors: {int(h.get('n_households') or 0):,} households, {int(h.get('n_lines') or 0):,} receipt lines, {int(h.get('n_baskets') or 0):,} baskets. Every figure below is in `exports/app/certified_kpis.json`, which is written from the marts.

## What moved

The retailer received **{_money(h.get('net_sales'))}** in net sales. Recorded discounts were **{_money(h.get('discount_cost'))}**, which is **{_pct(h.get('discount_share_of_gross'))}** of the pre-discount ring. About **{_pct(h.get('off_feature_discount_share'))}** of those discount dollars sat on lines with no display and no mailer. A feature is not where most of the discount bill lives.

On product-store pairs with a real baseline ({int(h.get('feature_pairs') or 0):,} pairs, covering **{_pct(h.get('feature_coverage'))}** of non-fuel feature-week sales), counting silent weeks as zero, feature weeks added **{_money(h.get('feature_incremental_sales'))}** of net sales versus those pairs' own quiet weeks. That is a **{_pct(h.get('feature_lift_pct'))}** lift. The ROI proxy on that matched panel, incremental net sales divided by the discounts recorded on the feature weeks, is **{_num(h.get('feature_roi'))}**. The extra cash did not cover the discount bill on those weeks.

That lift is mostly "a sale happened." On weeks that actually rang up, the average feature-week ring was **${float(h.get('conditional_promo_mean') or 0):,.2f}** against **${float(h.get('conditional_base_mean') or 0):,.2f}** on a quiet week, a lift of **{_pct(h.get('conditional_lift_pct'))}** ({int(h.get('conditional_promo_weeks') or 0):,} feature weeks, {int(h.get('conditional_base_weeks') or 0):,} quiet weeks). I cannot see which silent weeks were out of stock, so I quote both numbers and I do not lead with the larger one alone.

{dept_lines}

{worked_line}

## What did not

{loser_line}

{winner_line}

I scored **{int(h.get('n_campaigns_scored') or 0)}** of **{int(h.get('n_campaigns') or 0)}** campaigns. The ones I skipped had too few mailed households or no pre-period inside the calendar. **{int(h.get('n_campaigns_negative_incremental') or 0)}** scored campaigns have incremental net sales below zero, and **{int(h.get('n_campaigns_roi_below_one') or 0)}** have an ROI proxy under 1. A few of those ratios look absurd because the coupon bill is a few dollars. I rank on the incremental dollars, not on a ratio with a tiny denominator.

## The forecast

{forecast_line}

## Who responded

{segment_line}

## What I would try next weekend

1. Take the worst scored campaign and read the pre-period by hand, household by household, before I believe the dollar. The sign is the part I trust first.
2. Spend the feature slots on the category in the worked example only if a quick week-level chart still shows the gap. Busy weeks can impersonate a lift.
3. Stop treating the loyalty discount as the cost of the mailer. Most of the discount bill is off feature. The campaign ROI I quote uses coupon and match discounts on the couponed products, and leaves the loyalty field beside it.
4. Keep the forecast default on whichever method won. If that is the four-week mean, I will not add model complexity until I have a second year.

## What I will not say

This was not a randomized test. The panel is frequent shoppers. There is no cost of goods, so none of these ROI figures are a margin. The language page, if I use it, is only allowed to repeat these tables.
"""


def _forecast_sentence(h: dict) -> str:
    naive = h.get("forecast_naive_wmape")
    tree = h.get("forecast_ml_wmape")
    if naive is None or tree is None:
        return "The forecast did not score on this build."
    if h.get("forecast_ml_beats_naive"):
        return (
            f"On the holdout, the tree model's sales-weighted MAPE was **{_pct(tree)}**, "
            f"against **{_pct(naive)}** for the mean of the previous four weeks. "
            "The tree is the default, and I still plot the four-week mean next to it. "
            "The score is one step ahead with actual lags, not a 12-week path I walked blind."
        )
    return (
        f"The four-week mean beat the tree. Sales-weighted MAPE was **{_pct(naive)}** for the mean "
        f"and **{_pct(tree)}** for the tree, so the default stays the mean. "
        "I would rather keep a forecast I can explain than one that loses to the recent average."
    )


def _loser_sentence(losers: list, h: dict) -> str:
    if not losers:
        return (
            "No scored campaign came in below its comparison group in this snapshot. "
            "I would still read the smallest incremental result before calling the set a success."
        )
    worst = losers[0]
    return (
        f"Campaign **{worst.get('campaign_id')}** ({worst.get('campaign_type')}, "
        f"{_short(worst.get('start_date'))} to {_short(worst.get('end_date'))}) is the one that does not pay. "
        f"Incremental net sales **{_money(worst.get('incremental_sales'))}** against coupon and match discounts of "
        f"**{_money(worst.get('coupon_cost'))}** (ROI proxy **{_num(worst.get('roi'))}**). "
        "The mailed households handed over less cash than the comparison group. I trust the sign before I trust the dollar."
    )


def _winner_sentence(winners: list) -> str:
    if not winners:
        return ""
    best = winners[0]
    if (best.get("incremental_sales") or 0) <= 0:
        return "The least-bad campaign was still not positive. I would not lead with it."
    return (
        f"The largest positive gap was campaign **{best.get('campaign_id')}** ({best.get('campaign_type')}), "
        f"incremental net sales **{_money(best.get('incremental_sales'))}**, ROI proxy **{_num(best.get('roi'))}**. "
        "I would still want the spread across households in front of me before I treated that dollar as settled."
    )


def _worked_sentence(worked: dict) -> str:
    if not worked or not worked.get("department"):
        return "I did not find a category that met the bar for a worked example on this build (enough pairs, a lift between 5% and 120%, not fuel)."
    return (
        f"The category I would walk through is **{worked.get('department')} / {worked.get('product_category')}**. "
        f"{int(worked.get('n_product_stores') or 0)} product-store pairs, feature-week sales **{_money(worked.get('feature_sales'))}**, "
        f"quiet-week run-rate stretched over those weeks **{_money(worked.get('counterfactual_sales'))}**, "
        f"gap **{_money(worked.get('incremental_sales'))}** (**{_pct(worked.get('lift_pct'))}**), "
        f"discounts on those feature weeks **{_money(worked.get('discount_cost'))}**."
    )


def _segment_sentence(h: dict, segments: list) -> str:
    share = h.get("promo_sensitive_share")
    line = (
        f"**{_pct(share)}** of households ({int(h.get('promo_sensitive_households') or 0):,}) "
        f"put at least {_pct(h.get('promo_sensitive_threshold'))} of their pre-discount ring on a recorded discount, "
        "with at least 8 baskets."
    )
    if not segments:
        return line
    top = max(segments, key=lambda row: row.get("sales_share") or 0)
    return (
        line
        + f" The **{top.get('segment')}** segment is {_pct(top.get('household_share'))} of households and "
        + f"{_pct(top.get('sales_share'))} of net sales."
    )


def _dept_lines(departments: list) -> str:
    if not departments:
        return ""
    bits = []
    for row in departments:
        bits.append(
            f"- **{row.get('department')}**: incremental {_money(row.get('incremental_sales'))}, "
            f"lift {_pct(row.get('lift_pct'))}, ROI proxy {_num(row.get('roi'))}, "
            f"{int(row.get('n_product_stores') or 0)} pairs."
        )
    return "Largest department gaps on the matched panel:\n\n" + "\n".join(bits)


def _examples(payload: dict) -> str:
    from insights.answer import answer_question

    questions = [
        "Which campaigns lost money after discounts?",
        "Where was the feature lift largest?",
        "Did the forecast beat the four-week mean?",
        "Who is promo-sensitive?",
        "Which week looks unusual?",
        "What is the capital of France?",
    ]
    lines = ["# Questions I actually asked the snapshot", ""]
    for question in questions:
        result = answer_question(question, payload, glossary="")
        lines.append(f"## {question}")
        lines.append("")
        lines.append(result["answer"])
        lines.append("")
        if result.get("sources"):
            lines.append("Sources:")
            lines.append("")
            for source in result["sources"]:
                lines.append(
                    f"- {source.get('metric')} · {source.get('grain')} · {source.get('period')} · {source.get('value')}"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def _money(value) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number != number:
        return "n/a"
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.2f}"


def _pct(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number != number:
        return "n/a"
    return f"{number:.1%}"


def _num(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number != number:
        return "n/a"
    return f"{number:.2f}"


def _short(value) -> str:
    if not value:
        return "?"
    return str(value)[:10]


if __name__ == "__main__":
    main()
