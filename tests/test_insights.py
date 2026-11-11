from insights.answer import answer_question, insight_cards


def _kpis():
    return {
        "headline": {
            "period_start": "2017-01-01",
            "period_end": "2018-01-01",
            "net_sales": 1000,
            "gross_sales": 1200,
            "discount_cost": 200,
            "discount_share_of_gross": 200 / 1200,
            "feature_incremental_sales": 80,
            "feature_lift_pct": 0.12,
            "feature_coverage": 0.4,
            "n_campaigns_negative_incremental": 3,
            "forecast_naive_wmape": 0.08,
            "forecast_ml_wmape": 0.11,
            "forecast_ml_beats_naive": False,
            "forecast_default_model": "naive_last_4",
            "promo_sensitive_share": 0.22,
            "promo_sensitive_threshold": 0.18,
            "promo_sensitive_households": 500,
        },
        "campaigns": [
            {
                "campaign_id": "18",
                "campaign_type": "Type A",
                "status": "ok",
                "incremental_sales": -400,
                "coupon_cost": 150,
                "roi": -2.67,
                "n_treated": 100,
                "redemption_rate": 0.01,
                "start_date": "2017-10-30",
                "end_date": "2017-12-24",
            },
            {
                "campaign_id": "8",
                "campaign_type": "Type A",
                "status": "ok",
                "incremental_sales": 900,
                "coupon_cost": 200,
                "roi": 4.5,
                "n_treated": 80,
                "redemption_rate": 0.02,
                "start_date": "2017-05-08",
                "end_date": "2017-06-25",
            },
        ],
        "departments": [
            {
                "department": "MEAT",
                "incremental_sales": 300,
                "lift_pct": 0.2,
                "discount_cost": 100,
                "roi": 3,
                "n_product_stores": 40,
            },
            {
                "department": "MEAT-PCKGD",
                "incremental_sales": 50,
                "lift_pct": 0.05,
                "discount_cost": 40,
                "roi": 1.25,
                "n_product_stores": 10,
            },
        ],
        "segments": [
            {"segment": "Champions", "household_share": 0.1, "sales_share": 0.4},
        ],
        "forecast_scores": [],
        "anomalies": [
            {"week_no": 27, "department": "PRODUCE", "net_sales": 9000, "trail_median": 5000, "robust_z": 4.2, "reason": "robust_z"}
        ],
        "halo": [
            {
                "source_department": "MEAT",
                "target_department": "DELI",
                "coef_sales_per_intensity": 1200,
                "t_stat": 2.4,
                "n_weeks": 51,
                "direction": "halo",
            }
        ],
    }


def test_worst_campaign_is_the_negative_one():
    result = answer_question("Which campaigns lost money after discounts?", _kpis(), glossary="")
    assert "18" in result["answer"]
    assert result["refused"] is False
    assert result["sources"][0]["metric"] == "incremental_sales"
    assert any(source["metric"] == "promo_roi_proxy" for source in result["sources"])


def test_meat_does_not_match_packaged_by_accident():
    result = answer_question("How did packaged meat do on lift?", _kpis(), glossary="")
    assert "MEAT-PCKGD" in result["answer"]


def test_forecast_admits_when_the_mean_wins():
    result = answer_question("Did the forecast beat the four-week mean?", _kpis(), glossary="")
    assert "four-week" in result["answer"].lower() or "mean" in result["answer"].lower()
    assert "default stays" in result["answer"]


def test_out_of_scope_is_refused():
    result = answer_question("What is the capital of France?", _kpis(), glossary="")
    assert result["refused"] is True
    assert result["sources"] == []


def test_cards_are_never_empty():
    cards = insight_cards(_kpis())
    assert len(cards) >= 4
    assert all(card["answer"] for card in cards)
