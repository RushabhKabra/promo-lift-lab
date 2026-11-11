import numpy as np
import pandas as pd

from analysis.anomalies import anomaly_table
from analysis.basket import department_affinity
from analysis.forecast import build_feature_frame, fit_forecast, naive_one_step
from analysis.metrics import PROMO_SENSITIVE_GROSS_SHARE
from analysis.segments import rfm_table, segment_summary


def test_naive_is_the_trailing_mean():
    values = np.array([10, 10, 10, 10, 20], dtype=float)
    pred = naive_one_step(values, window=4)
    assert np.isnan(pred[3])
    assert pred[4] == 10


def test_flat_series_forecast_is_accurate():
    rows = []
    for week in range(1, 40):
        for department, level in [("GROCERY", 1000.0), ("MEAT", 400.0)]:
            rows.append(
                {
                    "week_no": week,
                    "department": department,
                    "net_sales": level,
                    "promo_intensity": 10 + (week % 3),
                    "is_partial": False,
                }
            )
    predictions, scores = fit_forecast(pd.DataFrame(rows), holdout_weeks=8)
    assert not predictions.empty
    naive = scores.loc[
        (scores["model"] == "naive_last_4") & (scores["department"] == "ALL") & (scores["scope"] == "all"),
        "weighted_mape",
    ].iloc[0]
    assert naive < 0.01
    features = build_feature_frame(pd.DataFrame(rows))
    assert features["naive"].dropna().iloc[-1] == 1000 or features.loc[features["department"] == "GROCERY", "naive"].dropna().iloc[-1] == 1000


def test_short_history_does_not_invent_a_model():
    weekly = pd.DataFrame(
        {
            "week_no": [1, 2, 3],
            "department": ["GROCERY"] * 3,
            "net_sales": [10, 11, 12],
            "promo_intensity": [1, 1, 1],
            "is_partial": [False, False, False],
        }
    )
    predictions, scores = fit_forecast(weekly)
    assert predictions.empty
    assert scores.iloc[0]["model"] == "unavailable"


def test_rfm_labels_and_promo_sensitivity():
    rows = []
    # Household A shops often and recently, mostly on discount.
    for i in range(12):
        rows.append(
            {
                "household_id": "A",
                "basket_id": f"a{i}",
                "transaction_timestamp": pd.Timestamp("2017-12-01") - pd.Timedelta(days=i),
                "sales_value": 8.0,
                "discount_cost": 4.0,
                "gross_sales": 12.0,
            }
        )
    # Household B bought once, a long time ago, full price.
    rows.append(
        {
            "household_id": "B",
            "basket_id": "b1",
            "transaction_timestamp": pd.Timestamp("2017-01-15"),
            "sales_value": 5.0,
            "discount_cost": 0.0,
            "gross_sales": 5.0,
        }
    )
    households = rfm_table(pd.DataFrame(rows), as_of=pd.Timestamp("2017-12-20"))
    summary = segment_summary(households)
    sensitive = households.loc[households["household_id"] == "A"].iloc[0]
    quiet = households.loc[households["household_id"] == "B"].iloc[0]
    assert sensitive["promo_sensitive"]
    assert sensitive["discount_share_of_gross"] >= PROMO_SENSITIVE_GROSS_SHARE
    assert not quiet["promo_sensitive"]
    assert quiet["recency_days"] > sensitive["recency_days"]
    assert summary["households"].sum() == 2


def test_basket_lift_above_one_for_a_tied_pair():
    # A and B always travel together. C is common on its own.
    rows = []
    for i in range(20):
        rows.append({"basket_id": f"t{i}", "department": "MEAT"})
        rows.append({"basket_id": f"t{i}", "department": "DELI"})
    for i in range(20):
        rows.append({"basket_id": f"c{i}", "department": "GROCERY"})
    affinity = department_affinity(pd.DataFrame(rows), min_support=0.01)
    pair = affinity.loc[
        affinity["department_a"].isin(["DELI", "MEAT"]) & affinity["department_b"].isin(["DELI", "MEAT"])
    ]
    assert len(pair) == 1
    assert pair.iloc[0]["lift"] > 1


def test_anomaly_flags_a_spike():
    rows = []
    for week in range(1, 20):
        sales = 100.0 if week != 15 else 1000.0
        rows.append(
            {
                "week_no": week,
                "department": "GROCERY",
                "net_sales": sales,
                "promo_intensity": 1.0,
                "is_partial": False,
            }
        )
    flagged = anomaly_table(pd.DataFrame(rows))
    assert (flagged["week_no"] == 15).any()
