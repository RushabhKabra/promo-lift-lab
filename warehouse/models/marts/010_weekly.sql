-- Descriptive marts. Analytical marts (lift, forecast, segments) are written
-- by analysis/run_all.py after these exist.

CREATE OR REPLACE VIEW marts.v_weekly_department AS
SELECT
    t.week_no,
    w.week_start,
    w.week_end,
    w.is_partial,
    p.department,
    SUM(t.sales_value) AS net_sales,
    SUM(t.gross_sales) AS gross_sales,
    SUM(t.grocery_units) AS grocery_units,
    SUM(t.discount_cost) AS discount_cost,
    SUM(t.sales_value) FILTER (WHERE t.on_feature) AS feature_net_sales,
    COUNT(*) AS lines,
    COUNT(DISTINCT t.basket_id) AS baskets
FROM core.fct_transactions t
JOIN core.dim_product p ON p.product_id = t.product_id
JOIN core.dim_week w ON w.week_no = t.week_no
GROUP BY t.week_no, w.week_start, w.week_end, w.is_partial, p.department;

CREATE OR REPLACE VIEW marts.v_weekly_total AS
SELECT
    week_no,
    week_start,
    week_end,
    is_partial,
    SUM(net_sales) AS net_sales,
    SUM(gross_sales) AS gross_sales,
    SUM(grocery_units) AS grocery_units,
    SUM(discount_cost) AS discount_cost,
    SUM(feature_net_sales) AS feature_net_sales
FROM marts.v_weekly_department
GROUP BY week_no, week_start, week_end, is_partial;
