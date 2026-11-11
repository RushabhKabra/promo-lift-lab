-- The study week is not an ISO week. It is the week number on each receipt,
-- and the cutover falls in the early morning, so one calendar date can sit
-- in two study weeks. dim_date.primary_week_no is the week with more receipts
-- that day. Facts keep the receipt's own week_no.
--
-- A week is partial when it covers fewer than 6 distinct calendar dates.
-- Week 1 of this mirror is 1-2 January 2017 and is partial.
--
-- Rows are loaded by scripts/build.py from staging.transactions. This file
-- documents the rule; it is not executed as a seed insert.

SELECT
    week_no,
    MIN(date_key) AS week_start,
    MAX(date_key) AS week_end,
    COUNT(DISTINCT date_key) AS n_dates,
    COUNT(DISTINCT date_key) < 6 AS is_partial
FROM staging.transactions
GROUP BY week_no
ORDER BY week_no;
