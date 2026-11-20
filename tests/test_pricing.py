import numpy as np
import pandas as pd

from analysis.pricing import (
    depth_band,
    depth_bands,
    depth_by_category,
    money_losing_campaigns,
    money_losing_categories,
)


def _categories():
    return pd.DataFrame(
        {
            "department": ["A", "A", "B", "B"],
            "product_category": ["shallow", "deep", "none", "thin"],
            "n_product_stores": [50, 50, 30, 2],
            "feature_sales": [95.0, 60.0, 10.0, 5.0],
            "counterfactual_sales": [80.0, 50.0, 9.0, 1.0],
            "incremental_sales": [15.0, 10.0, 1.0, 4.0],
            "discount_cost": [5.0, 40.0, 0.0, 5.0],
        }
    )


def test_depth_band_edges():
    assert depth_band(0.0, 0.0) == "0% (no discount)"
    assert depth_band(0.05, 1.0) == "0-10%"
    assert depth_band(0.10, 1.0) == "10-20%"
    assert depth_band(0.399, 1.0) == "30-40%"
    assert depth_band(0.40, 1.0) == "40%+"


def test_depth_and_payback_per_category():
    by_category = depth_by_category(_categories()).set_index("product_category")
    assert by_category.loc["shallow", "discount_depth"] == 0.05
    assert by_category.loc["deep", "discount_depth"] == 0.40
    assert by_category.loc["deep", "payback"] == 0.25
    assert np.isnan(by_category.loc["none", "payback"])


def test_bands_keep_every_dollar_and_use_ratio_of_sums():
    by_category = depth_by_category(_categories())
    bands = depth_bands(by_category)
    assert bands["incremental_sales"].sum() == by_category["incremental_sales"].sum()
    assert bands["discount_cost"].sum() == by_category["discount_cost"].sum()
    deep = bands.set_index("depth_band").loc["40%+"]
    assert deep["payback"] == (10.0 + 4.0) / (40.0 + 5.0)


def test_money_losing_lists():
    losers = money_losing_categories(depth_by_category(_categories()), min_pairs=20)
    assert list(losers["product_category"]) == ["deep"]
    campaigns = pd.DataFrame(
        {
            "campaign_id": ["1", "2", "3"],
            "campaign_type": ["A", "B", "B"],
            "start_date": ["2017-01-01"] * 3,
            "end_date": ["2017-02-01"] * 3,
            "n_treated": [100, 100, 5],
            "status": ["ok", "ok", "small_treated_group"],
            "incremental_sales": [-50.0, 20.0, -90.0],
            "coupon_cost": [10.0, 10.0, 1.0],
            "roi": [-5.0, 2.0, -90.0],
            "did_low": [-2.0, -1.0, -9.0],
            "did_high": [0.5, 3.0, -1.0],
        }
    )
    out = money_losing_campaigns(campaigns)
    assert list(out["campaign_id"]) == ["1"]
    assert not out.loc[0, "interval_excludes_zero"]
