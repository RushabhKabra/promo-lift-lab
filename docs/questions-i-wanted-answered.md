# Questions I wanted answered

Each one is something I actually wanted to know, with the check that tells me the lab answered it. No imaginary audience.

| Question | Where the answer lives | How I check it |
| --- | --- | --- |
| When a product is on display or in the mailer, how do those weeks compare with its own quiet weeks? | `marts.v_department_lift`, `marts.v_category_lift`, Promotion lift page | `tests/test_lift.py` recomputes a hand-built panel. The page reads the view, not a number typed into the script. |
| How much of feature-week sales even has a baseline? | `headline.feature_coverage` | Printed under the overview chart. Pairs need 6 sale weeks, 4 quiet weeks, and 1 feature week. |
| Which campaigns came in below the comparison group? | `marts.v_campaign_results` where incremental sales are negative | `tests/test_lift.py` builds a campaign that loses. On the full build, `quality/test_sql.py` requires at least one negative scored campaign. |
| What did the coupon cost, without double-counting products on the same UPC? | `campaign_results.coupon_cost`, `redemption_rate` | `tests/test_metrics.py` locks the redemption denominator to households × UPCs. |
| Did a tree model beat the last four weeks? | `marts.v_forecast_scores`, Forecast page | `tests/test_forecast_segments.py`. The default model is whichever won. |
| Who buys on discount as a habit? | `marts.v_segment_summary`, Customers page | Threshold 18% of the pre-discount ring and 8 baskets, asserted in the segment test. |
| Which departments share a basket, and which weekly series move together? | `marts.v_basket_pairs`, `marts.v_halo_pairs` | Basket lift test uses a pair that always travels together. The halo note on the page says the regression is a clue. |
| Which weeks do not look like their neighbours? | `marts.v_anomalies` | A planted spike is flagged even when the recent history is perfectly flat. |
| Can I ask, in a sentence, which campaigns lost money, and see the source? | Ask page, `python -m insights.answer` | `tests/test_insights.py`. An off-topic question is refused. No API key required. |
| Do the receipt totals in the star schema match staging? | Quality exceptions sheet, build log | `quality/assertions.sql` fails the build if sales drift by more than $1 or 0.01%. |
| Can I hand the same numbers to a spreadsheet or a BI tool? | `exports/excel/promo_weekly_brief.xlsx`, `exports/bi/` | `make export`. The dictionary sheet names the columns. |

If a question is not on this list, the app should not invent a metric for it.
