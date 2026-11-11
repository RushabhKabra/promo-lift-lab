# Loading the extracts

These files are the star-schema-shaped extracts from the lab. I did not build a `.pbix` or a `.twbx`. Point the tool at this folder after `make export`.

## Relationships

- `weekly_department.week_no` → `dim_week.week_no`
- `weekly_department.department` is a degenerate key. If you want a department list, take the distinct values.
- `forecast_weekly.week_no` → `dim_week.week_no`, and `forecast_weekly.department` matches `weekly_department.department`
- `campaign_results.campaign_id` → `dim_campaign.campaign_id`
- `household_segments` is one row per household. It is a segment extract, not a receipt fact. Leave demographics off the model unless you have a reason; the bins live on `dim_household` inside Postgres, and I kept them out of this folder so a casual load does not drag household attributes onto a canvas.

`dim_product` is large. Load it when you need category drill-through. The briefing itself does not require the receipt lines.

## Measures worth defining

- Net sales = SUM(weekly_department[net_sales])
- Discount cost = SUM(weekly_department[discount_cost])
- Incremental sales = SUM(department_lift[incremental_sales])
- Promo ROI proxy = DIVIDE(SUM(campaign_results[incremental_sales]), SUM(campaign_results[coupon_cost]))

ROI at a campaign is already on `campaign_results.roi`. Prefer that column when you are looking at one campaign. A summed ratio is a different number.

## Tableau

Same relationships, same measures. Use `dim_week.week_start` as the date. Do not rebuild the study week from the calendar date: the week cuts over in the early morning, and one date can belong to two study weeks.

## What not to do

Do not join `bridge` coupon products onto redemptions before you count redemptions. One coupon UPC maps to many products, and the count will multiply. The redemption rate on `campaign_results` is already the one I use.
