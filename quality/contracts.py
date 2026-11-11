"""Pandera checks on the frames I am about to load.

These run on the cleaned frames, after quarantine. A failure here means the
cleaning step let something through that the warehouse should not accept.
"""

from __future__ import annotations

import pandera.pandas as pa

transactions_schema = pa.DataFrameSchema(
    {
        "household_id": pa.Column(pa.String, nullable=False),
        "store_id": pa.Column(pa.String, nullable=False),
        "basket_id": pa.Column(pa.String, nullable=False),
        "product_id": pa.Column(pa.String, nullable=False),
        "quantity": pa.Column(float, pa.Check.ge(-0.001), nullable=False),
        "sales_value": pa.Column(float, pa.Check.ge(-0.001), nullable=False),
        "retail_disc": pa.Column(float, pa.Check.ge(-0.001), nullable=False),
        "coupon_disc": pa.Column(float, pa.Check.ge(-0.001), nullable=False),
        "coupon_match_disc": pa.Column(float, pa.Check.ge(-0.001), nullable=False),
        "week": pa.Column(int, pa.Check.in_range(1, 60), nullable=False),
    },
    strict=False,
    coerce=True,
)


def validate_transactions(df):
    if df.empty:
        return df
    return transactions_schema.validate(df, lazy=False)
