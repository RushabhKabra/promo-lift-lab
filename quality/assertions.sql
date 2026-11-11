-- Each statement returns the failing rows. An empty result passes.
-- Tolerances: absolute $1 or 0.01% of staging sales, whichever is larger.

-- NAME: sales_reconcile
WITH staged AS (
    SELECT COALESCE(SUM(sales_value), 0) AS v FROM staging.transactions
),
facts AS (
    SELECT COALESCE(SUM(sales_value), 0) AS v FROM core.fct_transactions
)
SELECT s.v AS staged_sales, f.v AS fact_sales, ABS(s.v - f.v) AS drift
FROM staged s CROSS JOIN facts f
WHERE ABS(s.v - f.v) > GREATEST(1.0, 0.0001 * ABS(s.v));

-- NAME: discount_reconcile
WITH staged AS (
    SELECT COALESCE(SUM(discount_cost), 0) AS v FROM staging.transactions
),
facts AS (
    SELECT COALESCE(SUM(discount_cost), 0) AS v FROM core.fct_transactions
)
SELECT s.v AS staged_discount, f.v AS fact_discount, ABS(s.v - f.v) AS drift
FROM staged s CROSS JOIN facts f
WHERE ABS(s.v - f.v) > GREATEST(1.0, 0.0001 * ABS(s.v));

-- NAME: gross_identity
SELECT COUNT(*) AS broken_lines
FROM core.fct_transactions
WHERE ABS(gross_sales - (sales_value + retail_discount + coupon_discount + match_discount)) > 0.02
HAVING COUNT(*) > 0;

-- NAME: transaction_grain
SELECT basket_id, product_id, COUNT(*) AS n
FROM core.fct_transactions
GROUP BY basket_id, product_id
HAVING COUNT(*) > 1;

-- NAME: promotion_grain
SELECT product_id, store_id, week_no, COUNT(*) AS n
FROM core.fct_promotions
GROUP BY product_id, store_id, week_no
HAVING COUNT(*) > 1;

-- NAME: negative_sales
SELECT COUNT(*) AS n
FROM core.fct_transactions
WHERE sales_value < -0.001
HAVING COUNT(*) > 0;

-- NAME: negative_discounts
SELECT COUNT(*) AS n
FROM core.fct_transactions
WHERE retail_discount < -0.001 OR coupon_discount < -0.001 OR match_discount < -0.001
HAVING COUNT(*) > 0;

-- NAME: orphan_products
SELECT COUNT(*) AS n
FROM core.fct_transactions t
LEFT JOIN core.dim_product p ON p.product_id = t.product_id
WHERE p.product_id IS NULL
HAVING COUNT(*) > 0;

-- NAME: orphan_households
SELECT COUNT(*) AS n
FROM core.fct_transactions t
LEFT JOIN core.dim_household h ON h.household_id = t.household_id
WHERE h.household_id IS NULL
HAVING COUNT(*) > 0;

-- NAME: orphan_stores
SELECT COUNT(*) AS n
FROM core.fct_transactions t
LEFT JOIN core.dim_store s ON s.store_id = t.store_id
WHERE s.store_id IS NULL
HAVING COUNT(*) > 0;

-- NAME: campaign_household_grain
SELECT campaign_id, household_id, COUNT(*) AS n
FROM core.fct_campaign_households
GROUP BY campaign_id, household_id
HAVING COUNT(*) > 1;

-- NAME: week_on_facts
SELECT COUNT(*) AS n
FROM core.fct_transactions t
LEFT JOIN core.dim_week w ON w.week_no = t.week_no
WHERE w.week_no IS NULL
HAVING COUNT(*) > 0;
