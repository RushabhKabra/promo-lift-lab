-- The Python ingest already lands typed columns. This view is the contract
-- the star schema reads, so the formula for gross sales lives in one place.

CREATE OR REPLACE VIEW staging.v_transactions AS
SELECT
    household_id,
    store_id,
    basket_id,
    product_id,
    quantity,
    sales_value,
    retail_disc AS retail_discount,
    coupon_disc AS coupon_discount,
    coupon_match_disc AS match_discount,
    retail_disc + coupon_disc + coupon_match_disc AS discount_cost,
    sales_value + retail_disc + coupon_disc + coupon_match_disc AS gross_sales,
    week_no,
    transaction_timestamp,
    date_key,
    is_return
FROM staging.transactions;
