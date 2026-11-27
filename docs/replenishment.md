# What I would have ordered

Study weeks 46 to 53 are the holdout, eight weeks, one step ahead. Lead time is 1 week, the order cycle is 1 week, and the service level is 95% (z = 1.6449). Every figure below is in `exports/bi/replenishment_summary.csv` and `exports/bi/replenishment_accuracy.csv`, written by `make replenishment`. Non-fuel units in that run were 1,902,528.00, the same total as `exports/app/certified_kpis.json`. Drift was 0.

The demand is panel households at a store, not the store's full movement. A suggested order is the method on that panel. It is not a case quantity.

## Who got an order

A series needs 8 sale weeks before the holdout and 8 calendar weeks of span before it, and it has to still be selling in the holdout. Week 1 is partial (two dates) and is dropped, the same rule as the rest of the lab.

**12,604** store-SKU series qualified. They account for **399,166** units, which is **21.03%** of non-fuel units on non-partial weeks (1,897,735). The other series were too intermittent for a weekly mean I would defend. That coverage number is part of the result.

Holdout demand on the scored weeks was **59,445** units across **74,466** product-store-weeks. That is about 0.8 units a week. The median safety stock is **1.55** units and the median suggested order is **2.37** units, because the panel is small at this grain. The ratios are what I would take into a real order file. The levels are not.

## The forecast

Three forecasts, all explainable, all one step ahead:

- **Four-week mean.** The previous four weeks in the series, zeros included.
- **Seasonal naive.** The same study week 52 weeks earlier. This panel is one year. Lag 52 falls on week 1, which is partial, or outside the series. Scored points: **0**. It cannot be the default.
- **Promo-adjusted.** The mean of the previous four quiet weeks. On a week the flyer already marks, that mean is scaled by the series' own past feature-to-quiet ratio, shrunk by `n / (n + 4)`. Two feature weeks are required before any lift is applied. The shrinkage was fixed before the holdout.

The promo forecast is blank until four quiet weeks exist, so it misses **911** holdout points (74,466 − 73,555). The paired rows score the **73,555** weeks both models can see.

| Model | Weeks | MAPE | WAPE | Median APE | Bias (units) | Points | Actual units |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Four-week mean | all of its own | 66.89% | 100.85% | 75% | −0.177 | 74,466 | 59,445 |
| Promo-adjusted | all of its own | 68.15% | 100.11% | 75% | −0.178 | 73,555 | 58,688 |
| Four-week mean | paired | 66.93% | 100.86% |  | −0.178 | 73,555 | 58,688 |
| Promo-adjusted | paired | 68.15% | 100.11% |  | −0.178 | 73,555 | 58,688 |
| Four-week mean | paired, feature weeks |  | 90.62% |  |  | 14,617 |  |
| Promo-adjusted | paired, feature weeks |  | 95.39% |  |  | 14,617 |  |
| Four-week mean | paired, quiet weeks |  | 105.01% |  |  | 58,938 |  |
| Promo-adjusted | paired, quiet weeks |  | 102.03% |  |  | 58,938 |  |

WAPE is absolute error divided by actual units, and a silent week stays in the numerator. That is why WAPE can exceed 100% when the forecast still writes down a recent average in a week nothing sold. MAPE ignores those silent weeks. Median APE on weeks that did sell is 75% for both models. Bias is prediction minus actual. Both forecasts ran about 0.18 units cold.

The pre-committed rule picks the lower WAPE, so the default name is the promo-adjusted forecast. I would not order from that name. On the paired weeks WAPE moves from 100.86% to 100.11%. MAPE moves the other way, 66.93% to 68.15%. On the feature weeks, the week the adjustment exists for, the four-week mean is better: **90.62%** versus **95.39%**. The adjustment helps a little on quiet weeks (102.03% versus 105.01%), because it refuses to let a promo spike into the trailing mean. The lift it applies on the feature week is too noisy to earn the week.

Department sales were a different result, and I am not mixing them. There the four-week mean beat a tree, sales-weighted MAPE 8.70% versus 13.12%. The error shows up when the grain gets down to the store and the SKU.

## The order

Quiet weeks set the everyday rate. Their standard deviation sets the buffer. Promo spikes stay out of the sigma, and the feature week gets its own rate instead of a fatter buffer.

For a weekly order with a one-week lead time, the protection period is two weeks.

- Safety stock = `1.6449 × σ_quiet × sqrt(2)`
- Reorder point = quiet weekly mean × 1 + `1.6449 × σ_quiet × sqrt(1)`
- Order-up-to = quiet weekly mean × 2 + safety stock
- Suggested order = the order-up-to level

There is no on-hand and no on-order in this file. The suggested order is what I would place if the pipeline were empty. Summed across the 12,604 series that total is **38,637.2** units. It is a stack of empty-pipeline orders, not one week's chain demand.

A feature order-up-to swaps in the feature-week mean when the series had at least two feature weeks before the holdout, and it keeps the same safety stock.

## What the flyer does to that order

The risk numbers use the pre-holdout quiet mean as a standing order, then look at the holdout. They are not the one-step forecast errors above.

| | Units or weeks |
| --- | ---: |
| Feature weeks in the holdout | 15,394 |
| Of those, above the quiet mean | 7,728 (50.20%) |
| Units short if the order is the quiet mean | 12,610.5 |
| Units still short after one week of safety stock | 5,488.8 |
| Units left over if the feature rate is ordered on quiet weeks | 29,538.8 |
| Units left over the week after a feature, if last week's actual is ordered again | 4,532 |

Safety stock absorbs part of a promo spike and not most of it. 12,610.5 units of feature demand sat above the quiet mean, and 5,488.8 of those units still sat above the quiet mean plus one week of the 95% buffer.

**1,442** series (11.44%) have a typical feature week above that one-week buffer. **891** series (7.07%) would overshoot the safety stock if the promo quantity was ordered again on a quiet week. Grocery is where the units are: **9,868.4** of the 12,610.5 short units, 78.26%.

Meat is the department I order, and the rate is sharper there even though the units are smaller. 601 series. **488 of 793** feature weeks (61.54%) beat the quiet mean, a shortfall of **965.5** units out of 1,165 feature units. One week of safety stock still leaves **493.8** units short. **163** of the 601 series (27.12%) are flagged that way, against 11.44% overall, and **109** (18.14%) are flagged for repeating the promo. Ordering the meat feature rate onto quiet weeks would have left **2,299.5** units against 1,330 units those quiet weeks actually sold. Repeating the prior feature week's actual onto the next quiet week would have left **579** units.

The meat forecast has the same shape as the total. Four-week-mean WAPE is 115.70%, promo-adjusted is 106.13%, and that gain is on the quiet weeks. On meat feature weeks the four-week mean is still the lower WAPE, 88.48% versus 90.39%.

## What I would tell a replenishment manager

I would keep the everyday order on the recent quiet average, and I would size safety stock off the quiet weeks. I would not bury the flyer inside the buffer, and I would not let the flyer set next week's order. On this panel, repeating the feature rate onto quiet weeks leaves more than twice the units that ordering the quiet mean misses on feature weeks (29,538.8 against 12,610.5). The miss is real: half of feature weeks beat the quiet mean, and in meat it is closer to two thirds. The fix is a separate promo order for the week the flyer is already locked, not a more complicated forecast. The forecast I tried, which does exactly that scaling, did not beat the four-week mean on those feature weeks.

I would also refuse a weekly order policy for the 79% of units that did not have eight sale weeks. Those series need a different rule, and this file does not pretend to give them one.

## Limits

- The panel is frequent shoppers, recorded at a store. It is not store POS, and the order quantities are panel units.
- On-hand and on-order are absent, so suggested order equals the order-up-to level.
- A zero inside the first-to-last sale can be a true zero or a stock-out. I cannot tell them apart. Weeks outside that span are treated as not ranged.
- A normal z on intermittent weekly demand is a rough buffer. The median safety stock of 1.55 units is the formula being honest about how small and spiky the series are.
- Lead time is an assumption. Nothing in the files says how many days the DC takes.
- There is no cost of goods, so none of this is a margin.
- The promotions were not randomized. Someone chose the display and the mailer.
- One year of weeks cannot support a seasonal naive. I scored it and it had nothing to copy.
- The shrinkage on the promo lift was not tuned. Tuning it on the holdout would have been a second look at the same weeks.
