# Notes on the files

## What I loaded

The public Complete Journey mirrors maintained with the R package `completejourney` (Bradley Boehmke and Steven Mortimer), which repackage the 84.51° Customer Journey study. Historically this panel is also associated with dunnhumby. I did not scrape a retailer site, and none of these files come from a store I have worked in.

| File | Rows I actually read |
| --- | ---: |
| transactions | 1,469,307 receipt lines |
| promotions | 20,940,529 placements, collapsed to one row per product-store-week |
| products | 92,331 |
| campaigns | 6,589 household mailings across 27 campaigns |
| coupons | 116,204 coupon-product rows |
| coupon redemptions | 2,102 |
| demographics | 801 households |

The panel is 2,469 households, 457 stores in the receipts, 53 study weeks. The calendar runs from 1 January 2017 to 1 January 2018 because that is how the mirror dates the study. Those are not the original fieldwork dates.

Raw files are downloaded into `data/raw` and cached as parquet in `data/processed`. Neither directory is committed. `data/fixtures` is a real slice, small enough that the tests can run without the download.

## Grains

- A receipt line is unique on `basket_id` × `product_id`. I checked.
- A promotion row should be unique on `product_id` × `store_id` × `week`. A few hundred duplicates exist. Joining them raw onto receipts double-counts those lines, so ingest keeps one placement and ORs the display and mailer flags.
- The promotions file contains only featured placements. There is no row where both display and mailer are "not on". Absence of a row means not on feature.
- Campaigns are the households recorded as receiving that campaign. Type A, Type B, and Type C are the study's labels. I do not pretend the letter tells me the creative. Every type in this extract has a household list, including Type C, so I use that list as the mailed group rather than assuming Type C went to everyone.
- Coupon redemptions are events. The coupon file maps a UPC to many products. Those are different grains.

## Discount sign

In this mirror, `retail_disc`, `coupon_disc`, and `coupon_match_disc` are zero or positive. `sales_value` is "the amount of dollars the retailer receives from the sale." Gross, as I use the word, is cash received plus the three discounts. About 39,000 lines have discounts larger than cash received. That is a deep deal, and the identity `gross = net + discounts` still holds.

Kaggle's older CSV extract stores discounts as negatives. Ingest flips the sign when at least 90% of non-zero discounts are negative, so the warehouse always sees a cost.

## Fuel, zeros, and unmapped products

- Fuel and gasoline lines are about 8% of net sales. Their quantity scale is roughly gallons × 1000. Grocery unit totals exclude them.
- A few thousand lines have quantity 0. Some have a coupon amount and no units. I keep them. They affect discount totals and not units.
- A few thousand receipt products are missing from the product file. Their sales are about $173. They land in department `Unmapped` so the product key still holds.
- Demographics exist for 801 of 2,469 households. Age, income, and the rest are coarse bins. Home ownership and marital status are missing for some of those 801. I do not send household-level demographics to the optional model.

## Weeks

The study week cuts over in the early morning, around 4 or 5 a.m. Fifty-one calendar dates appear in two study weeks. `dim_date.primary_week_no` is the week with more receipts that day. Facts keep the week that was on the receipt. A campaign date is mapped through `primary_week_no`. Campaigns that start before 1 January 2017 or end after 1 January 2018 are clipped to the observed weeks and flagged `window_clipped`. If I cannot find two pre weeks inside the data, I do not score that campaign.

A week with fewer than 6 distinct dates is partial. Week 1 is partial. Partial weeks stay in the descriptive charts and drop out of the baseline panel and the forecast.

## What this cannot support

- It is not a randomized test. Someone chose the mailed households.
- It is frequent shoppers, not a census of the store.
- There is no cost of goods, no vendor funding, and no inventory, so I cannot talk about margin or waste except as a wish.
- There are no negative quantities, so a return rate would be fiction.
- The optional language model is constrained to the certified snapshot. It can still phrase a true number badly. The sources under the answer are the check.

## If the grocery files are missing

`scripts/ingest.py` falls back to the UCI Online Retail II extract and says so in the run log. That file has invoices, not campaigns. Feature flags then mean "unit price at least 15% under the product's own median," and the campaign pages will be empty. I would rather the lab run in that mode than pretend a mailer existed.

## Kaggle

If you already have `frtgnn/dunnhumby-the-complete-journey` as CSVs, `python scripts/ingest.py --source kaggle-csv --dir data/raw/kaggle` renames `household_key` to `household_id` and the other columns onto the same staging tables. I do not download Kaggle from here. The anonymous page wanted a captcha.
