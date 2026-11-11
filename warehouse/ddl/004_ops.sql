-- End-to-end run audit. staging.etl_run_log still records per-table ingest.
-- This schema ties ingest, build, quality checks, and publish to one run_id.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    source TEXT,
    triggered_by TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS ops.pipeline_run_steps (
    step_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES ops.pipeline_runs (run_id),
    step_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms BIGINT,
    status TEXT NOT NULL,
    rows_in BIGINT,
    rows_out BIGINT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS ops.quality_results (
    result_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES ops.pipeline_runs (run_id),
    assertion_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    failing_rows BIGINT NOT NULL DEFAULT 0,
    detail TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops.lineage (
    lineage_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES ops.pipeline_runs (run_id),
    source_name TEXT NOT NULL,
    source_object TEXT NOT NULL,
    staging_object TEXT,
    core_object TEXT,
    mart_object TEXT,
    grain TEXT
);
