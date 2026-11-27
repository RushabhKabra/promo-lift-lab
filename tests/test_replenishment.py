import numpy as np
import pandas as pd
import pytest

from analysis.metrics import mape, wape
from replenishment.forecast import add_forecasts
from replenishment.policy import service_z
from replenishment.run import run_replenishment


def _products(rows):
    return pd.DataFrame(rows)


def _series(product, store, weeks, units, department="MEAT", category="BEEF"):
    if np.isscalar(units):
        units = [units] * len(weeks)
    return pd.DataFrame(
        {
            "product_id": product,
            "store_id": store,
            "week": list(weeks),
            "quantity": units,
            "department_hint": department,
        }
    )


def _frame(weeks, units, product="sku", store="store", department="MEAT", category="BEEF"):
    transactions = pd.DataFrame(
        {
            "product_id": product,
            "store_id": store,
            "week": list(weeks),
            "quantity": units,
        }
    )
    products = _products(
        [{"product_id": product, "department": department, "product_category": category, "is_fuel": False}]
    )
    return transactions, products


def test_wape_charges_a_forecast_on_a_silent_week():
    actual = [0.0, 10.0]
    predicted = [5.0, 10.0]
    assert wape(actual, predicted) == pytest.approx(0.5)
    assert mape(actual, predicted) == pytest.approx(0.0)


def test_service_z_is_the_normal_quantile():
    assert service_z(0.95) == pytest.approx(1.64485362695, rel=1e-6)


def test_moving_average_and_seasonal_naive_are_the_lags_i_claim():
    units = [1, 2, 3, 4, 5, 10]
    rows = []
    for week, unit in enumerate(units, start=1):
        rows.append(
            {
                "product_id": "sku",
                "store_id": "s",
                "week_no": week,
                "units": unit,
                "on_feature": False,
                "department": "MEAT",
                "product_category": "BEEF",
            }
        )
    # A second series long enough for lag 52.
    for week in range(1, 54):
        rows.append(
            {
                "product_id": "seasonal",
                "store_id": "s",
                "week_no": week,
                "units": ((week - 1) % 52) + 1,
                "on_feature": False,
                "department": "MEAT",
                "product_category": "BEEF",
            }
        )
    panel = add_forecasts(pd.DataFrame(rows))
    sku = panel.loc[panel["product_id"].eq("sku")].set_index("week_no")
    assert sku.loc[5, "predicted_ma4"] == pytest.approx(2.5)
    assert sku.loc[6, "predicted_ma4"] == pytest.approx(3.5)
    assert np.isnan(sku.loc[4, "predicted_ma4"])
    seasonal = panel.loc[panel["product_id"].eq("seasonal")].set_index("week_no")
    assert seasonal.loc[53, "predicted_seasonal_naive"] == seasonal.loc[1, "units"]


def test_flat_demand_orders_the_mean_and_keeps_the_simple_forecast():
    weeks = list(range(1, 31))
    transactions, products = _frame(weeks, [10.0] * 30)
    # A short series must not get an order.
    extra = pd.DataFrame(
        {
            "product_id": "short",
            "store_id": "store",
            "week": [1, 2, 3],
            "quantity": [10.0, 10.0, 10.0],
        }
    )
    products = pd.concat(
        [
            products,
            pd.DataFrame(
                [{"product_id": "short", "department": "MEAT", "product_category": "BEEF", "is_fuel": False}]
            ),
        ],
        ignore_index=True,
    )
    result = run_replenishment(pd.concat([transactions, extra], ignore_index=True), products, None)
    policy = result["policy"]
    assert list(policy["product_id"]) == ["sku"]
    row = policy.iloc[0]
    assert row["sigma_quiet_units"] == pytest.approx(0.0)
    assert row["safety_stock_units"] == pytest.approx(0.0)
    assert row["reorder_point_units"] == pytest.approx(10.0)
    assert row["order_up_to_units"] == pytest.approx(20.0)
    assert row["suggested_order_qty"] == pytest.approx(row["order_up_to_units"])
    assert row["feature_order_up_to_units"] == pytest.approx(20.0)
    assert not row["stockout_risk_if_base_order"]
    assert not row["overstock_risk_if_promo_repeated"]
    summary = result["summary"].iloc[0]
    assert summary["default_model"] == "moving_average_4"
    assert summary["wape_moving_average_4"] == pytest.approx(0.0)
    assert summary["wape_promo_adjusted"] == pytest.approx(0.0)
    assert summary["grocery_units"] == pytest.approx(330.0)


def test_promo_forecast_and_the_order_risk_on_a_known_series():
    units = []
    feature_weeks = {10, 11, 20, 21, 25, 26}
    for week in range(1, 31):
        units.append(20.0 if week in feature_weeks else 10.0)
    transactions, products = _frame(list(range(1, 31)), units)
    promotions = pd.DataFrame(
        {
            "product_id": "sku",
            "store_id": "store",
            "week": sorted(feature_weeks),
            "on_display": True,
            "in_mailer": False,
        }
    )
    result = run_replenishment(transactions, products, promotions)
    panel = result["panel"].set_index("week_no")
    assert not bool(panel.loc[15, "on_feature"])
    assert bool(panel.loc[25, "on_feature"])
    assert panel.loc[25, "predicted_ma4"] == pytest.approx(12.5)
    assert panel.loc[25, "predicted_promo"] == pytest.approx(15.0)
    assert panel.loc[23, "predicted_promo"] == pytest.approx(10.0)
    assert panel.loc[26, "predicted_promo"] == pytest.approx(140.0 / 9.0)
    row = result["policy"].iloc[0]
    assert row["mean_quiet_units"] == pytest.approx(10.0)
    assert row["mean_feature_units"] == pytest.approx(20.0)
    assert row["safety_stock_units"] == pytest.approx(0.0)
    assert row["reorder_point_units"] == pytest.approx(10.0)
    assert row["order_up_to_units"] == pytest.approx(20.0)
    assert row["feature_order_up_to_units"] == pytest.approx(40.0)
    assert row["suggested_order_qty"] == pytest.approx(20.0)
    assert row["suggested_feature_order_qty"] == pytest.approx(40.0)
    assert row["stockout_risk_if_base_order"]
    assert row["overstock_risk_if_promo_repeated"]
    assert row["units_short_vs_quiet_mean"] == pytest.approx(20.0)
    assert row["units_short_vs_service_cover"] == pytest.approx(20.0)
    assert row["units_extra_if_feature_rate_on_quiet"] == pytest.approx(60.0)
    assert row["units_extra_week_after_feature"] == pytest.approx(10.0)
    summary = result["summary"].iloc[0]
    assert summary["default_model"] == "promo_adjusted"
    assert summary["wape_promo_adjusted"] < summary["wape_moving_average_4"]
    assert summary["n_points_paired"] == 8
    assert summary["wape_promo_paired"] < summary["wape_ma4_paired"]
    assert summary["units_short_vs_quiet_mean"] == pytest.approx(20.0)


def test_a_zero_sale_feature_week_inside_the_span_stays_on_feature():
    transactions, products = _frame(list(range(1, 31)), [10.0] * 30)
    transactions.loc[transactions["week"].eq(15), "quantity"] = 0.0
    promotions = pd.DataFrame(
        {
            "product_id": "sku",
            "store_id": "store",
            "week": [15],
            "display_location": "3",
            "mailer_location": "0",
        }
    )
    result = run_replenishment(transactions, products, promotions)
    week = result["panel"].loc[result["panel"]["week_no"].eq(15)].iloc[0]
    assert week["units"] == pytest.approx(0.0)
    assert bool(week["on_feature"])


def test_partial_weeks_and_fuel_do_not_enter_the_order():
    rows = []
    # Week 1 has two dates and a spike. It is partial.
    for day in range(2):
        rows.append(
            {
                "product_id": "sku",
                "store_id": "store",
                "week": 1,
                "quantity": 9999.0 if day == 0 else 0.0,
                "date_key": pd.Timestamp("2017-01-01") + pd.Timedelta(days=day),
            }
        )
    for week in range(2, 32):
        for day in range(7):
            rows.append(
                {
                    "product_id": "sku",
                    "store_id": "store",
                    "week": week,
                    "quantity": 10.0 if day == 0 else 0.0,
                    "date_key": pd.Timestamp("2017-01-01") + pd.Timedelta(days=(week - 1) * 7 + day),
                }
            )
    for week in range(2, 32):
        for day in range(7):
            rows.append(
                {
                    "product_id": "gas",
                    "store_id": "store",
                    "week": week,
                    "quantity": 5000.0 if day == 0 else 0.0,
                    "date_key": pd.Timestamp("2017-01-01") + pd.Timedelta(days=(week - 1) * 7 + day),
                }
            )
    products = pd.DataFrame(
        [
            {"product_id": "sku", "department": "MEAT", "product_category": "BEEF", "is_fuel": False},
            {"product_id": "gas", "department": "FUEL", "product_category": "GASOLINE", "is_fuel": True},
        ]
    )
    result = run_replenishment(pd.DataFrame(rows), products, None)
    panel = result["panel"]
    assert 1 not in set(panel["week_no"])
    assert "gas" not in set(panel["product_id"])
    assert panel["units"].max() == pytest.approx(10.0)
    # Partial-week units still count in the grocery total, fuel does not.
    assert result["summary"].iloc[0]["grocery_units"] == pytest.approx(9999.0 + 30 * 10.0)


def test_higher_service_level_and_longer_lead_time_raise_the_buffer():
    units = [10.0 + (week % 3) for week in range(1, 31)]
    transactions, products = _frame(list(range(1, 31)), units, department="GROCERY", category="MILK")
    base = run_replenishment(transactions, products, None, service_level=0.95, lead_time_weeks=1)
    higher = run_replenishment(transactions, products, None, service_level=0.99, lead_time_weeks=1)
    longer = run_replenishment(transactions, products, None, service_level=0.95, lead_time_weeks=2)
    base_row = base["policy"].iloc[0]
    assert base_row["safety_stock_units"] > 0
    assert higher["policy"].iloc[0]["safety_stock_units"] > base_row["safety_stock_units"]
    assert longer["policy"].iloc[0]["reorder_point_units"] > base_row["reorder_point_units"]
    assert longer["policy"].iloc[0]["order_up_to_units"] > base_row["order_up_to_units"]
    z = base_row["service_z"]
    sigma = base_row["sigma_quiet_units"]
    mean = base_row["mean_quiet_units"]
    assert base_row["safety_stock_units"] == pytest.approx(z * sigma * np.sqrt(2))
    assert base_row["reorder_point_units"] == pytest.approx(mean * 1 + z * sigma)
    assert base_row["order_up_to_units"] == pytest.approx(mean * 2 + z * sigma * np.sqrt(2))
    assert longer["policy"].iloc[0]["order_up_to_units"] == pytest.approx(
        mean * 3 + z * sigma * np.sqrt(3)
    )


def test_seasonal_naive_wins_when_the_year_repeats_and_it_has_history():
    weeks = list(range(1, 71))
    units = [((week - 1) % 52) + 1 for week in weeks]
    transactions, products = _frame(weeks, units)
    result = run_replenishment(transactions, products, None)
    summary = result["summary"].iloc[0]
    assert summary["default_model"] == "seasonal_naive"
    assert summary["wape_seasonal_naive"] == pytest.approx(0.0)
    assert summary["wape_moving_average_4"] > 0
    assert summary["n_points_seasonal_naive"] >= 0.5 * summary["n_points_moving_average_4"]


def test_short_history_does_not_invent_an_order():
    transactions, products = _frame([1, 2, 3, 4], [1, 2, 3, 4])
    result = run_replenishment(transactions, products, None)
    assert result["policy"].empty
    assert result["summary"].iloc[0]["n_series"] == 0
    assert "weeks" in result["summary"].iloc[0]["note"]
