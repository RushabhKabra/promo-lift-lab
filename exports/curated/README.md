# Curated week folders

This folder is the published side of a pipeline run. I wanted the files to sit the way a weekly sales planner sits: one folder per study week, so I can pick up a week without opening the whole year.

`make pipeline` or `make export` rebuilds the contents. The parquet files are not committed.

## Layout

Weekly marts (`weekly_department`, `weekly_total`, `forecast_weekly`) are written as:

```
exports/curated/<table>/week_no=<n>/part.parquet
```

Everything else in the extract set is a single file:

```
exports/curated/<table>/part.parquet
```

The study week is the week printed on the receipt, not an ISO week. Use `dim_week` if you need the calendar dates that week covers.

These extracts come from the public Complete Journey panel after the quality assertions have passed. They are not store data from work.
