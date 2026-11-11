INSERT INTO core.dim_week (week_no, week_start, week_end, n_dates, is_partial)
SELECT
    week_no,
    MIN(date_key) AS week_start,
    MAX(date_key) AS week_end,
    COUNT(DISTINCT date_key) AS n_dates,
    COUNT(DISTINCT date_key) < 6 AS is_partial
FROM staging.transactions
GROUP BY week_no;

INSERT INTO core.dim_date (
    date_key, primary_week_no, year, month, month_name, day_of_week, day_name, is_boundary
)
WITH counts AS (
    SELECT date_key, week_no, COUNT(*) AS n
    FROM staging.transactions
    GROUP BY date_key, week_no
),
ranked AS (
    SELECT
        date_key,
        week_no,
        n,
        ROW_NUMBER() OVER (PARTITION BY date_key ORDER BY n DESC, week_no) AS rn,
        COUNT(*) OVER (PARTITION BY date_key) AS n_weeks
    FROM counts
)
SELECT
    date_key,
    week_no,
    EXTRACT(YEAR FROM date_key)::INTEGER,
    EXTRACT(MONTH FROM date_key)::INTEGER,
    TO_CHAR(date_key, 'FMMonth'),
    EXTRACT(ISODOW FROM date_key)::INTEGER,
    TO_CHAR(date_key, 'FMDay'),
    n_weeks > 1
FROM ranked
WHERE rn = 1;

INSERT INTO core.dim_product (
    product_id, manufacturer_id, department, brand, product_category, product_type, package_size, is_fuel
)
SELECT
    product_id, manufacturer_id, department, brand, product_category, product_type, package_size, is_fuel
FROM staging.products;

INSERT INTO core.dim_product (product_id, department, product_category, brand, product_type, is_fuel)
SELECT DISTINCT t.product_id, 'Unmapped', 'Uncategorized', 'Unknown', 'Unspecified', FALSE
FROM staging.transactions t
WHERE NOT EXISTS (
    SELECT 1 FROM core.dim_product p WHERE p.product_id = t.product_id
);

INSERT INTO core.dim_store (store_id)
SELECT DISTINCT store_id FROM staging.transactions
UNION
SELECT DISTINCT store_id FROM staging.promotions;

INSERT INTO core.dim_household (
    household_id, age, income, home_ownership, marital_status,
    household_size, household_comp, kids_count, has_demographics
)
SELECT
    h.household_id,
    d.age,
    d.income,
    d.home_ownership,
    d.marital_status,
    d.household_size,
    d.household_comp,
    d.kids_count,
    d.household_id IS NOT NULL
FROM (
    SELECT household_id FROM staging.transactions
    UNION
    SELECT household_id FROM staging.campaigns
    UNION
    SELECT household_id FROM staging.coupon_redemptions
    UNION
    SELECT household_id FROM staging.demographics
) h
LEFT JOIN staging.demographics d ON d.household_id = h.household_id;

INSERT INTO core.dim_campaign (
    campaign_id, campaign_type, start_date, end_date, start_week, end_week, window_clipped
)
SELECT
    c.campaign_id,
    c.campaign_type,
    c.start_date,
    c.end_date,
    COALESCE(sw.primary_week_no, (SELECT MIN(week_no) FROM core.dim_week WHERE NOT is_partial)),
    COALESCE(ew.primary_week_no, (SELECT MAX(week_no) FROM core.dim_week WHERE NOT is_partial)),
    sw.date_key IS NULL
        OR ew.date_key IS NULL
        OR c.start_date < (SELECT MIN(date_key) FROM core.dim_date)
        OR c.end_date > (SELECT MAX(date_key) FROM core.dim_date)
FROM staging.campaign_descriptions c
LEFT JOIN core.dim_date sw ON sw.date_key = c.start_date
LEFT JOIN core.dim_date ew ON ew.date_key = c.end_date;

INSERT INTO core.fct_transactions (
    basket_id, product_id, household_id, store_id, date_key, week_no,
    quantity, sales_value, retail_discount, coupon_discount, match_discount,
    discount_cost, gross_sales, is_fuel, grocery_units, on_feature
)
SELECT
    t.basket_id,
    t.product_id,
    t.household_id,
    t.store_id,
    t.date_key,
    t.week_no,
    t.quantity,
    t.sales_value,
    t.retail_disc,
    t.coupon_disc,
    t.coupon_match_disc,
    t.discount_cost,
    t.gross_sales,
    COALESCE(p.is_fuel, FALSE),
    CASE WHEN COALESCE(p.is_fuel, FALSE) THEN 0 ELSE t.quantity END,
    FALSE
FROM staging.transactions t
LEFT JOIN core.dim_product p ON p.product_id = t.product_id;

INSERT INTO core.fct_promotions (
    product_id, store_id, week_no, display_location, mailer_location, on_display, in_mailer
)
SELECT product_id, store_id, week_no, display_location, mailer_location, on_display, in_mailer
FROM staging.promotions;

INSERT INTO core.fct_campaign_households (campaign_id, household_id)
SELECT campaign_id, household_id FROM staging.campaigns;

INSERT INTO core.fct_coupon_redemptions (household_id, coupon_upc, campaign_id, redemption_date)
SELECT household_id, coupon_upc, campaign_id, redemption_date
FROM staging.coupon_redemptions;

INSERT INTO core.bridge_coupon_product (campaign_id, coupon_upc, product_id)
SELECT DISTINCT campaign_id, coupon_upc, product_id
FROM staging.coupons;

CREATE INDEX fct_tx_product_store_week ON core.fct_transactions (product_id, store_id, week_no);
CREATE INDEX fct_tx_household_week ON core.fct_transactions (household_id, week_no);
CREATE INDEX fct_tx_week ON core.fct_transactions (week_no);
CREATE INDEX fct_tx_product ON core.fct_transactions (product_id);
CREATE INDEX dim_product_department ON core.dim_product (department);
