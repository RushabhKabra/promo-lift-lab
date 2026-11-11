-- Rebuilt on every `make build`. Staging is left alone.

DROP SCHEMA IF EXISTS marts CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
CREATE SCHEMA core;
CREATE SCHEMA marts;

CREATE TABLE core.dim_week (
    week_no INTEGER PRIMARY KEY,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    n_dates INTEGER NOT NULL,
    is_partial BOOLEAN NOT NULL
);

CREATE TABLE core.dim_date (
    date_key DATE PRIMARY KEY,
    primary_week_no INTEGER NOT NULL REFERENCES core.dim_week (week_no),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    is_boundary BOOLEAN NOT NULL
);

CREATE TABLE core.dim_product (
    product_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    manufacturer_id TEXT,
    department TEXT NOT NULL,
    brand TEXT,
    product_category TEXT NOT NULL,
    product_type TEXT,
    package_size TEXT,
    is_fuel BOOLEAN NOT NULL
);

CREATE TABLE core.dim_store (
    store_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id TEXT NOT NULL UNIQUE
);

CREATE TABLE core.dim_household (
    household_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id TEXT NOT NULL UNIQUE,
    age TEXT,
    income TEXT,
    home_ownership TEXT,
    marital_status TEXT,
    household_size TEXT,
    household_comp TEXT,
    kids_count TEXT,
    has_demographics BOOLEAN NOT NULL
);

CREATE TABLE core.dim_campaign (
    campaign_sk INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id TEXT NOT NULL UNIQUE,
    campaign_type TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    start_week INTEGER,
    end_week INTEGER,
    window_clipped BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE core.fct_transactions (
    line_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    basket_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    household_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    date_key DATE NOT NULL,
    week_no INTEGER NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    sales_value DOUBLE PRECISION NOT NULL,
    retail_discount DOUBLE PRECISION NOT NULL,
    coupon_discount DOUBLE PRECISION NOT NULL,
    match_discount DOUBLE PRECISION NOT NULL,
    discount_cost DOUBLE PRECISION NOT NULL,
    gross_sales DOUBLE PRECISION NOT NULL,
    is_fuel BOOLEAN NOT NULL,
    grocery_units DOUBLE PRECISION NOT NULL,
    on_feature BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (basket_id, product_id)
);

CREATE TABLE core.fct_promotions (
    product_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    week_no INTEGER NOT NULL,
    display_location TEXT NOT NULL,
    mailer_location TEXT NOT NULL,
    on_display BOOLEAN NOT NULL,
    in_mailer BOOLEAN NOT NULL,
    PRIMARY KEY (product_id, store_id, week_no)
);

CREATE TABLE core.fct_campaign_households (
    campaign_id TEXT NOT NULL,
    household_id TEXT NOT NULL,
    PRIMARY KEY (campaign_id, household_id)
);

CREATE TABLE core.fct_coupon_redemptions (
    household_id TEXT NOT NULL,
    coupon_upc TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    redemption_date DATE NOT NULL
);

CREATE TABLE core.bridge_coupon_product (
    campaign_id TEXT NOT NULL,
    coupon_upc TEXT NOT NULL,
    product_id TEXT NOT NULL,
    PRIMARY KEY (campaign_id, coupon_upc, product_id)
);
