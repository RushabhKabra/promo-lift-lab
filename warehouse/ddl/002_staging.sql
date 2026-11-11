CREATE TABLE IF NOT EXISTS staging.etl_run_log (
    run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    source TEXT NOT NULL,
    table_name TEXT NOT NULL,
    rows_in BIGINT,
    rows_loaded BIGINT,
    rows_rejected BIGINT,
    status TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS staging.rejects (
    reject_id BIGSERIAL PRIMARY KEY,
    source_table TEXT NOT NULL,
    reason TEXT NOT NULL,
    row_json TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.transactions (
    household_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    basket_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    sales_value DOUBLE PRECISION NOT NULL,
    retail_disc DOUBLE PRECISION NOT NULL,
    coupon_disc DOUBLE PRECISION NOT NULL,
    coupon_match_disc DOUBLE PRECISION NOT NULL,
    discount_cost DOUBLE PRECISION NOT NULL,
    gross_sales DOUBLE PRECISION NOT NULL,
    week_no INTEGER NOT NULL,
    transaction_timestamp TIMESTAMP NOT NULL,
    date_key DATE NOT NULL,
    is_return BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS staging.products (
    product_id TEXT PRIMARY KEY,
    manufacturer_id TEXT,
    department TEXT NOT NULL,
    brand TEXT,
    product_category TEXT NOT NULL,
    product_type TEXT,
    package_size TEXT,
    is_fuel BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS staging.promotions (
    product_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    week_no INTEGER NOT NULL,
    display_location TEXT NOT NULL,
    mailer_location TEXT NOT NULL,
    on_display BOOLEAN NOT NULL,
    in_mailer BOOLEAN NOT NULL,
    PRIMARY KEY (product_id, store_id, week_no)
);

CREATE TABLE IF NOT EXISTS staging.campaigns (
    campaign_id TEXT NOT NULL,
    household_id TEXT NOT NULL,
    PRIMARY KEY (campaign_id, household_id)
);

CREATE TABLE IF NOT EXISTS staging.campaign_descriptions (
    campaign_id TEXT PRIMARY KEY,
    campaign_type TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.coupons (
    coupon_upc TEXT NOT NULL,
    product_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.coupon_redemptions (
    household_id TEXT NOT NULL,
    coupon_upc TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    redemption_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.demographics (
    household_id TEXT PRIMARY KEY,
    age TEXT,
    income TEXT,
    home_ownership TEXT,
    marital_status TEXT,
    household_size TEXT,
    household_comp TEXT,
    kids_count TEXT
);
