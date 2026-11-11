import numpy as np
import pandas as pd

from analysis.frames import collapse_promotions, prepare_transactions
from analysis.metrics import (
    discount_cost,
    gross_sales,
    mape,
    normalize_discount_signs,
    redemption_rate,
    roi,
    weighted_mape,
)


def test_gross_sales_adds_positive_discounts_back():
    net = pd.Series([0.99])
    assert gross_sales(net, pd.Series([1.25]), pd.Series([0.75]), pd.Series([0.25])).iloc[0] == 3.24
    assert discount_cost(pd.Series([1.25]), pd.Series([0.75]), pd.Series([0.25])).iloc[0] == 2.25


def test_negative_discounts_are_flipped_once():
    frame = pd.DataFrame(
        {
            "retail_disc": [-1.0, -0.5, 0.0],
            "coupon_disc": [0.0, -0.2, 0.0],
            "coupon_match_disc": [0.0, 0.0, 0.0],
        }
    )
    flipped = normalize_discount_signs(frame)
    assert flipped["retail_disc"].tolist() == [1.0, 0.5, 0.0]
    assert flipped["coupon_disc"].tolist() == [0.0, 0.2, 0.0]
    # Already-positive costs must not be flipped again.
    again = normalize_discount_signs(flipped)
    assert again["retail_disc"].tolist() == [1.0, 0.5, 0.0]


def test_roi_is_undefined_without_a_cost():
    assert np.isnan(roi(10, 0))
    assert roi(10, 4) == 2.5
    assert roi(-6, 3) == -2


def test_redemption_rate_does_not_explode_with_product_fanout():
    # 2 redemptions, 10 households, 4 UPCs. The product list under those UPCs
    # must not enter the denominator.
    assert redemption_rate(2, 10, 4) == 2 / 40


def test_mape_ignores_zero_actuals():
    assert mape([0, 10], [5, 12]) == 0.2
    assert abs(weighted_mape([10, 30], [12, 24]) - (2 + 6) / 40) < 1e-9


def test_duplicate_promotions_collapse_to_one_placement():
    raw = pd.DataFrame(
        {
            "product_id": ["1", "1", "1"],
            "store_id": ["9", "9", "9"],
            "week": [3, 3, 4],
            "display_location": ["0", "5", "0"],
            "mailer_location": ["A", "0", "0"],
        }
    )
    collapsed = collapse_promotions(raw)
    assert len(collapsed) == 2
    week3 = collapsed.loc[collapsed["week"] == 3].iloc[0]
    assert bool(week3["on_display"]) is True
    assert bool(week3["in_mailer"]) is True
    assert week3["display_location"] == "5"
    assert week3["mailer_location"] == "A"


def test_quarantine_keeps_a_clean_grain():
    raw = pd.DataFrame(
        {
            "household_id": ["1", "1", None],
            "store_id": ["2", "2", "2"],
            "basket_id": ["b", "b", "c"],
            "product_id": ["p", "p", "p"],
            "quantity": [1, 1, 1],
            "sales_value": [2.0, 2.0, 2.0],
            "retail_disc": [0.1, 0.1, 0.0],
            "coupon_disc": [0.0, 0.0, 0.0],
            "coupon_match_disc": [0.0, 0.0, 0.0],
            "week": [1, 1, 1],
            "transaction_timestamp": pd.to_datetime(["2017-01-02", "2017-01-02", "2017-01-02"]),
        }
    )
    good, rejected = prepare_transactions(raw)
    assert len(good) == 1
    assert set(rejected["reject_reason"]) == {"duplicate_basket_product", "missing_household"}
    assert good.iloc[0]["gross_sales"] == 2.1
