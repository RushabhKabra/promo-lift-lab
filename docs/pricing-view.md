# Reading the lab as a pricing analyst

I built the lab to ask whether a promotion pays for itself. A pricing analyst asks a sharper version of that question: how deep can a discount go before it stops paying back, and which deals should not be run again? This page answers both from figures the lab already certifies. It adds a discount-depth view of the existing category lift. It does not go back to the receipt lines, and its totals tie to the feature headline in [`exports/app/certified_kpis.json`](../exports/app/certified_kpis.json): $133,971.26 of incremental net sales on $172,181.45 of feature-week discounts. `scripts/pricing_view.py` stops if they drift by more than $1.

## Two definitions

- **Discount depth** for a category is the share of the pre-discount ring given away in its feature weeks: discount ÷ (net feature sales + discount). It is an average across the category's product-store pairs, not a shelf price cut.
- **Payback** is the lab's ROI proxy: incremental net sales per discount dollar. It is a sales measure. The panel has no cost of goods, so a payback below 1 means the extra sales did not even cover the discount, before any margin.

## Depth against payback

| Discount depth | Categories | Product-store pairs | Incremental net sales | Discount | Payback | Incremental less discount |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% (no discount) | 28 | 301 | $347.52 | $0.00 | n/a | $347.52 |
| 0–10% | 14 | 559 | $1,612.35 | $395.43 | 4.08 | $1,216.92 |
| 10–20% | 40 | 3,052 | $7,192.34 | $5,376.02 | 1.34 | $1,816.32 |
| 20–30% | 68 | 11,820 | $21,847.59 | $35,890.30 | 0.61 | −$14,042.71 |
| 30–40% | 37 | 9,138 | $81,984.70 | $91,500.44 | 0.90 | −$9,515.74 |
| 40%+ | 21 | 2,685 | $20,986.77 | $39,019.26 | 0.54 | −$18,032.49 |
| **All** | **208** | **27,555** | **$133,971.26** | **$172,181.45** | **0.78** | **−$38,210.19** |

Band payback is a ratio of sums, not an average of category ratios.

What I take from it:

1. **Below 20% depth, discounts paid back. From 20% up, they did not.** Each discount dollar returned $4.08 of extra sales in the 0–10% band and $1.34 in the 10–20% band. In every band from 20% up, it returned less than a dollar.
2. **Almost all the money sits where payback is below 1.** 96.65% of feature-week discount dollars ($166,410.00) were spent at 20% depth or deeper. Only 3.35% went on the shallow deals that paid back.
3. **The curve is not perfectly smooth, and I would not pretend it is.** The 30–40% band reads better than 20–30% because of a few large categories. Beef sits in it at 1.31. Soft drinks (0.83) and fluid milk (0.87) are $54,337.85 of the band's $91,500.44 of discount. A pricing decision would be made category by category, and the Depth data tab has that grain.

## Promotions that did not earn their discount

**Categories.** 119 of the 180 discounted categories had a payback below 1. Leaving out categories with fewer than 20 product-store pairs, where one pair can swing the ratio, 83 remain. Their extra sales fell $49,511.43 short of $141,763.59 of discount. The five biggest shortfalls:

| Category | Pairs | Depth | Incremental net sales | Discount | Payback | Shortfall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Meat: chicken | 334 | 53.8% | $8,908.46 | $18,515.89 | 0.48 | −$9,607.43 |
| Grocery: soft drinks | 1,866 | 39.9% | $25,522.11 | $30,897.11 | 0.83 | −$5,375.00 |
| Grocery: baked bread, buns and rolls | 1,167 | 28.6% | $2,266.40 | $6,440.07 | 0.35 | −$4,173.67 |
| Grocery: fluid milk products | 1,016 | 33.4% | $20,317.12 | $23,440.74 | 0.87 | −$3,123.62 |
| Packaged meat: misc | 177 | 29.3% | $292.29 | $3,015.81 | 0.10 | −$2,723.52 |

Chicken is the clearest case: the deepest discount on the list, and the largest shortfall. Soft drinks and milk do bring in a lot of extra sales, but not enough to cover a discount of that size. That is a case for a shallower deal, not for no deal.

**Campaigns.** 11 of the 21 scored mailer campaigns had incremental net sales below zero (difference-in-differences against unmailed households). Campaign 8 is the largest miss at −$9,001.88. Campaign 13 is next at −$5,841.32. To be fair to the data, only campaign 9 has an interval that sits wholly below zero. For the rest, the result is "no evidence it helped", not proof it hurt. I rank on incremental dollars, not on a ratio with a tiny coupon cost underneath it.

## Where to find it

- The Excel briefing [`exports/excel/promo_weekly_brief.xlsx`](../exports/excel/promo_weekly_brief.xlsx) has three new tabs:
  - **Depth data:** one row per category, as the Excel Table `tbl_depth_by_category`.
  - **Depth pivot:** a native PivotTable on that table, with rows by depth band and sums of incremental sales, discount, feature sales and counterfactual sales. Payback, lift and shortfall sit beside it as `GETPIVOTDATA` formulas, so they follow the pivot when it is filtered.
  - **Money-losing promos:** both lists above, in full.
- The same data is in CSV form: [`exports/bi/discount_depth_by_category.csv`](../exports/bi/discount_depth_by_category.csv), [`discount_depth_bands.csv`](../exports/bi/discount_depth_bands.csv), [`money_losing_campaigns.csv`](../exports/bi/money_losing_campaigns.csv) and [`money_losing_categories.csv`](../exports/bi/money_losing_categories.csv).
- Rebuild with `make pricing-view`. It reads only `exports/bi`, so it does not need Postgres. `make export` runs it too.
- I checked the PivotTable by opening the workbook in LibreOffice Calc. It loads as a pivot, refreshes to the same totals, and the `GETPIVOTDATA` cells return 0.78 payback and 60.97% lift on the grand total. I have not opened it in Microsoft Excel yet.

## What a real pricing desk would add

- Cost of goods by item, so payback becomes a margin return and the break-even depth can be found per category.
- Regular shelf price history, so depth is measured against the everyday price rather than inferred from the receipt.
- Vendor funding by deal, so the retailer's share of the discount is separated from the supplier's.
- Customer or contract price lists for B2B pricing, where the same depth question applies to account-level discounts.
