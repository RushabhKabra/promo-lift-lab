# The warehouse

Local Postgres. Nothing here assumes a cloud account. `docker compose up -d` starts Postgres 16 with database `promo_lift`, user `promo`, password `promo`.

## Schemas

- `staging` — typed landing tables, a reject pile, and a per-table ingest run log. Ingest truncates and reloads these. It does not touch the star schema.
- `core` — dimensions and facts. `make build` drops and recreates this schema.
- `marts` — descriptive views and the analytical tables the app reads. Also recreated on build.
- `ops` — end-to-end run audit. `make pipeline` writes one row to `ops.pipeline_runs`, step timings and row counts, every quality assertion, and the lineage from a landed file to a mart. A failed quality gate marks the run failed and skips publish.

## Grains and keys

| Table | Grain | Key |
| --- | --- | --- |
| `core.dim_date` | calendar date | `date_key` |
| `core.dim_week` | study week | `week_no` |
| `core.dim_product` | product | `product_id`, plus a surrogate `product_sk` |
| `core.dim_store` | store | `store_id` |
| `core.dim_household` | household | `household_id` |
| `core.dim_campaign` | campaign | `campaign_id` |
| `core.fct_transactions` | receipt line | `basket_id`, `product_id` |
| `core.fct_promotions` | placement | `product_id`, `store_id`, `week_no` |
| `core.fct_campaign_households` | mailing | `campaign_id`, `household_id` |
| `core.fct_coupon_redemptions` | redemption event | no natural single key; do not pre-join to products |
| `core.bridge_coupon_product` | coupon UPC × product × campaign | the three columns |

Facts keep the natural keys so a query reads like the question. Surrogate keys are there for the product, store, household, and campaign dimensions because a BI model usually wants them. I did not hide the business keys.

`on_feature` on a receipt line is true when that product, store, and week has a promotion row. The update runs after the load, against the collapsed placement table, so a duplicate placement cannot multiply a line.

## Why the date dimension is a little odd

Study weeks are not ISO weeks, and the cutover is early morning, so one calendar date can sit in two study weeks. `dim_date.primary_week_no` is the majority week that day. Receipt facts keep the week number that came on the row. See `warehouse/seeds/date_dimension.sql` for the rule. The rows themselves are loaded by `scripts/build.py` from the receipts, not from a static calendar file, because the week numbering belongs to the study.

## Marts I will quote

- `marts.v_weekly_department`, `marts.v_weekly_total` — description, not lift.
- `marts.v_department_lift`, `marts.v_category_lift`, `marts.v_product_store_lift` — matched feature baseline.
- `marts.v_campaign_results` — difference-in-differences and the ROI proxy.
- `marts.v_forecast_weekly`, `marts.v_forecast_scores`.
- `marts.v_segment_summary`, `marts.v_basket_pairs`, `marts.v_halo_pairs`, `marts.v_anomalies`.
- `marts.v_headline` — one row, the figures the briefing repeats.

Household RFM rows live in `marts.household_rfm` and are not part of the snapshot sent to a model.

## Rebuild

`make build` is idempotent. It will refuse to finish if fact sales drift from staging by more than $1 or 0.01%, whichever is larger. That check is `quality/assertions.sql`.

`make pipeline` runs ingest, build, tests, and export under one `run_id`. Curated marts are written to `exports/curated/`, with weekly tables in `week_no=<n>/` folders.
