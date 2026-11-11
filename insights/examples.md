# Questions I actually asked the snapshot

## Which campaigns lost money after discounts?

Campaign 8 (Type A) is the one I would not run back. The difference-in-differences puts incremental net sales at -$9,002 against coupon and match discounts of $820. ROI proxy -10.98. 11 scored campaigns have incremental net sales below zero.

Sources:

- incremental_sales · campaign, household-week difference-in-differences · 2017-05-08 to 2017-06-25 · -9001.881025398
- promo_roi_proxy · campaign · 2017-05-08 to 2017-06-25 · -10.9819214657

## Where was the feature lift largest?

The largest incremental net sales on the matched panel are in GROCERY: $78,195, a 54.7% lift versus the non-feature run-rate. Across the whole matched panel, feature incremental net sales are $133,971, covering 39.1% of non-fuel feature-week sales. The rest of the feature sales sit on product-store pairs I would not give a baseline.

Sources:

- incremental_sales · department, matched product-store · 2017-01-01 to 2018-01-01 · 78195.0163265679

## Did the forecast beat the four-week mean?

The four-week mean beat the tree model. Sales-weighted MAPE was 8.7% for the mean and 13.1% for the tree, so the default stays the simpler forecast (naive_last_4). A year of weeks is not much history for a model to earn its place.

Sources:

- forecast_mape · department-week, sales-weighted · 2017-01-01 to 2018-01-01 · 0.0870359879
- forecast_mape_tree · department-week, sales-weighted · 2017-01-01 to 2018-01-01 · 0.1312350893

## Who is promo-sensitive?

26.4% of households (653) put at least 18.0% of their pre-discount ring on a recorded discount, with at least 8 baskets. That is my promo-sensitive share. The Champions segment is 20.1% of households and 44.8% of net sales.

Sources:

- promo_sensitive_household_share · household · 2017-01-01 to 2018-01-01 · 0.2644795464

## Which week looks unusual?

Week 16 in FLORAL sits away from its trailing eight-week median. Net sales were $1,040 against a trailing median of $375 (robust z 12.9, flagged by robust_z).

Sources:

- robust_z · department-week · week 16 · 12.9034956955

## What is the capital of France?

I only answer from the certified tables in this lab. Ask me about a campaign, a department, the forecast, or who responds to discounts.

