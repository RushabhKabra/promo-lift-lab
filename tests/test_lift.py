import numpy as np
import pandas as pd
import pytest

from analysis.lift import campaign_did, product_store_baseline, rollup_lift


def _weekly_panel():
    rows = []
    for week in range(1, 9):
        on_feature = week >= 7
        rows.append(
            {
                "product_id": "p",
                "store_id": "s",
                "week_no": week,
                "department": "MEAT",
                "product_category": "BEEF",
                "units": 16 if on_feature else 10,
                "net_sales": 28 if on_feature else 20,
                "discount_cost": 4 if on_feature else 1,
                "on_feature": on_feature,
            }
        )
    return pd.DataFrame(rows)


def test_product_store_lift_matches_a_hand_calculation():
    summary = product_store_baseline(_weekly_panel())
    row = summary.iloc[0]
    assert row["n_base_weeks"] == 6
    assert row["n_promo_weeks"] == 2
    assert row["baseline_sales"] == 20
    assert row["promo_sales"] == 28
    assert row["incremental_sales"] == 16  # (28 - 20) * 2 feature weeks
    assert row["discount_cost"] == 8
    assert row["roi"] == 2
    assert row["lift_pct"] == pytest.approx(0.4)


def test_rollup_weights_by_sales_not_by_pair():
    panel = pd.concat(
        [
            _weekly_panel(),
            _weekly_panel().assign(product_id="q", net_sales=lambda d: np.where(d["on_feature"], 10, 10), units=1),
        ],
        ignore_index=True,
    )
    summary = product_store_baseline(panel)
    rolled = rollup_lift(summary, ["department"])
    # Product q has no sales lift. The department lift uses dollars, so it is
    # below the 40% on product p alone.
    assert rolled.iloc[0]["lift_pct"] < 0.4
    assert rolled.iloc[0]["incremental_sales"] == 16


def test_campaign_did_known_gap():
    # Two treated households rise by 5 a week. Two control households stay flat.
    rows = []
    for hh, pre, post in [("1", 10, 15), ("2", 10, 15), ("3", 10, 10), ("4", 10, 10)]:
        for week, value in [(1, pre), (2, pre), (3, post), (4, post)]:
            rows.append({"household_id": hh, "week_no": week, "net_sales": value})
    exposure = pd.DataFrame({"campaign_id": ["7", "7"], "household_id": ["1", "2"]})
    windows = pd.DataFrame(
        [
            {
                "campaign_id": "7",
                "campaign_type": "Type A",
                "start_week": 3,
                "end_week": 4,
                "start_date": "2017-01-15",
                "end_date": "2017-01-28",
                "window_clipped": False,
            }
        ]
    )
    costs = pd.DataFrame(
        [
            {
                "campaign_id": "7",
                "coupon_cost": 20.0,
                "redemptions": 2,
                "mailed_households": 2,
                "distinct_upcs": 1,
            }
        ]
    )
    result = campaign_did(pd.DataFrame(rows), exposure, windows, costs, pre_weeks=2, min_treated=2)
    row = result.iloc[0]
    assert row["status"] == "ok"
    assert row["did_per_household_week"] == 5
    # 5 dollars per household per post week * 2 households * 2 post weeks.
    assert row["incremental_sales"] == 20
    assert row["roi"] == 1


def test_campaign_that_does_not_pay():
    rows = []
    for hh, pre, post in [("1", 20, 10), ("2", 20, 10), ("3", 10, 10), ("4", 10, 10)]:
        for week, value in [(1, pre), (2, pre), (3, post), (4, post)]:
            rows.append({"household_id": hh, "week_no": week, "net_sales": value})
    exposure = pd.DataFrame({"campaign_id": ["8", "8"], "household_id": ["1", "2"]})
    windows = pd.DataFrame(
        [
            {
                "campaign_id": "8",
                "campaign_type": "Type B",
                "start_week": 3,
                "end_week": 4,
                "start_date": "2017-02-01",
                "end_date": "2017-02-14",
                "window_clipped": False,
            }
        ]
    )
    costs = pd.DataFrame(
        [{"campaign_id": "8", "coupon_cost": 30.0, "redemptions": 1, "mailed_households": 2, "distinct_upcs": 1}]
    )
    result = campaign_did(pd.DataFrame(rows), exposure, windows, costs, pre_weeks=2, min_treated=2)
    assert result.iloc[0]["incremental_sales"] < 0
    assert result.iloc[0]["roi"] < 0
