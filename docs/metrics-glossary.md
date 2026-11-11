# How I define the numbers

Owner of every definition below: Rushabh. If a dashboard figure does not appear here, or in a tested function that implements one of these, I do not quote it.

The study window is the calendar the `completejourney` mirror reconstructed, roughly 1 January 2017 through 1 January 2018. Study weeks are the week numbers on the receipts (1–53), not ISO weeks. Week 1 covers only 1–2 January and is partial.

## Gross sales

- **Grain:** whatever I am summing — line, week, department, campaign.
- **Formula:** `sales_value + retail_discount + coupon_discount + match_discount`.
- **What it is:** a pre-discount ring. `sales_value` in this mirror is the cash the retailer received. The three discount fields are non-negative costs (the original study files stored them as negatives; ingest flips that sign once and only once).
- **Caveat:** this is not a shelf price from a price book. It is the ring implied by the receipt. On a few lines the discount is larger than the cash received, which is a deep deal, not a broken identity. The identity I test is `gross = net + discounts`, within two cents.

## Units

- **Grain:** line, or any rollup.
- **Formula:** `grocery_units`, which is `quantity` on non-fuel lines and 0 on fuel.
- **Returns:** this mirror has no negative quantities, so there is nothing to net off. If a later extract has returns (negative quantity and negative sales together), I keep the reversal rather than dropping it.
- **Caveat:** gasoline quantity looks like thousandths of a gallon. Adding it to grocery units produces a nonsense total (on the order of 150 million). I report fuel in dollars only.

## Retail discount, coupon discount, match discount

- **Grain:** line, then summed.
- **Formula:** the three fields, as positive costs. Retail discount is the loyalty-card discount in the study's own words, not specifically the cost of a display. Coupon discount is the manufacturer coupon. Match discount is the retailer match of that coupon.
- **Caveat:** a line can carry a loyalty discount with no display and no mailer. I do not treat every retail discount dollar as the cost of a feature.

## Net sales

- **Grain:** line, then summed.
- **Formula:** `sales_value`.
- **What it is:** cash the retailer received. It is already net of the three discounts. I checked this against the field definition in the Complete Journey documentation and against the identity above.
- **Caveat:** calling `sales_value` "gross" will double-count discounts. I did that wrong in an early scratch and the reconciliation caught it.

## Baseline units and baseline sales

- **Grain:** product × store, then rolled to category or department by summing dollars (never by averaging percentages).
- **Default method:** for a product-store that sold in at least 6 distinct weeks, I fill zeros from its first observed week to its last, skipping partial weeks. Baseline is the mean of weeks with no display and no mailer. The feature run-rate is the mean of weeks that had either. I keep the pair only when there are at least 4 quiet weeks and 1 feature week.
- **Caveat:** pairs that sell rarely never get a baseline. Coverage — the share of non-fuel feature-week sales that sit on a kept pair — is part of the number. A second, stricter read of campaigns uses difference-in-differences and does not use this baseline.
- **Companion, not the default:** conditional lift keeps only weeks with a sale and compares the average ring. It answers "was the ring larger?" The default answers "including the weeks nothing sold, did the feature week add cash?" Silent weeks may be true zeros or weeks the item was not stocked. I publish both.

## Incremental sales

- **Grain:** the baseline's grain, or the campaign grain below.
- **Formula (feature):** `(feature weekly net sales − baseline weekly net sales) × number of feature weeks`.
- **Formula (campaign):** difference-in-differences on household weekly net sales. Pre window is up to 4 study weeks before the campaign, inside the observed calendar. Post window is the campaign's study weeks. Control households shopped during the year and were not mailed any campaign that overlaps the pre or post window. Incremental dollars = per-household weekly gap × treated households × post weeks.
- **Caveat:** never quoted without the method. The feature version has no control group. The campaign version is still observational: mailed households were chosen by someone.

## Promo ROI proxy

- **Grain:** campaign, or a feature rollup.
- **Formula (campaign):** incremental net sales ÷ (coupon discount + match discount) on the campaign's couponed products, for mailed households, during the campaign weeks.
- **Formula (feature rollup):** incremental net sales ÷ all three discounts on the feature weeks of the matched pairs.
- **Caveat:** there is no wholesale cost and no vendor funding split. A value below 0 means incremental cash was negative. A value between 0 and 1 means extra cash came in, but less than the discount in the denominator. Above 1, extra cash exceeded that discount. Retail loyalty discounts are not in the campaign denominator, because they are not the coupon.

## Redemption rate

- **Grain:** campaign.
- **Formula:** redemption rows ÷ (mailed households × distinct coupon UPCs on the campaign).
- **Caveat:** the coupon file is a product list, not a mail log. I do not know how many coupons were actually put in each mailbox. Joining redemptions to that product list before counting multiplies one redemption by every product on the UPC. I count redemption rows on their own.

## Forecast MAPE and bias

- **Grain:** department × week, scored on the last 12 non-partial weeks, one step ahead.
- **MAPE:** mean of `|actual − predicted| / |actual|` where actual is not zero.
- **Sales-weighted MAPE (the one I quote):** sum of absolute errors ÷ sum of actual net sales.
- **Bias:** mean of `predicted − actual`. Positive means the forecast ran hot.
- **Models:** the naive forecast is the mean of the previous four weeks. The tree is a histogram gradient booster on lags, week-of-year, department, and same-week placement intensity (known when the flyer is locked). A second tree omits the flyer.
- **Default:** whichever of the naive and the tree has the lower sales-weighted MAPE on the holdout. If the tree does not win, I say so and keep the four-week mean.
- **Caveat:** the score is one-step, with actual lags, not a recursive 12-week path. Partial weeks are dropped before scoring.

## Promo-sensitive household share

- **Grain:** household, then a share of households.
- **Formula:** discount cost ÷ gross sales ≥ 0.18, and at least 8 distinct baskets.
- **Caveat:** this is a habit of buying on offer across the year, not a lift during one campaign. The 0.18 cut is a round threshold I can defend, not a quantile I refit every run.

## A few companions I also publish

- **Off-feature discount share:** discount dollars on lines with no display and no mailer, divided by all discount dollars. This is the loyalty and coupon money that is not sitting on a feature.
- **Feature coverage:** non-fuel feature-week sales on pairs that received a baseline, divided by all non-fuel feature-week sales.
- **Basket lift:** pair support ÷ (support of A × support of B) inside a trip.
- **Halo coefficient:** weekly regression of department B's sales on department A's placement intensity, with B's own intensity and a linear week trend. Sign only. Fifty weeks is a short panel.
