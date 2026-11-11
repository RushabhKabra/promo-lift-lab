"""Store-panel proxies I can actually see in this extract.

The Complete Journey mirror I am using has no negative quantities, so a return
rate is not something I can report without inventing one. What I can see is
discount that lands on lines with no display and no mailer, zero-quantity
coupon lines, and the fuel quantity scale that would wreck a unit total.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def operations_summary(transactions: pd.DataFrame) -> dict:
    work = transactions.copy()
    discount = work["discount_cost"]
    on_feature = work["on_feature"].astype(bool) if "on_feature" in work.columns else pd.Series(False, index=work.index)
    total_discount = float(discount.sum())
    off_feature = float(discount.loc[~on_feature].sum())
    fuel = work["is_fuel"].astype(bool) if "is_fuel" in work.columns else pd.Series(False, index=work.index)
    zero_qty = work["quantity"] == 0
    gross = float(work["gross_sales"].sum()) if "gross_sales" in work.columns else float(work["sales_value"].sum() + discount.sum())
    return {
        "lines": int(len(work)),
        "net_sales": float(work["sales_value"].sum()),
        "gross_sales": gross,
        "discount_cost": total_discount,
        "discount_share_of_gross": (total_discount / gross) if gross else np.nan,
        "off_feature_discount": off_feature,
        "off_feature_discount_share": (off_feature / total_discount) if total_discount else np.nan,
        "feature_discount": float(discount.loc[on_feature].sum()),
        "zero_quantity_lines": int(zero_qty.sum()),
        "zero_quantity_share": float(zero_qty.mean()) if len(work) else np.nan,
        "fuel_sales": float(work.loc[fuel, "sales_value"].sum()),
        "fuel_sales_share": float(work.loc[fuel, "sales_value"].sum() / work["sales_value"].sum()) if work["sales_value"].sum() else np.nan,
        "grocery_units": float(work.loc[~fuel, "quantity"].sum()),
        "returns_observed": bool((work["quantity"] < 0).any()),
    }


def weekly_discount_rate(transactions: pd.DataFrame) -> pd.DataFrame:
    work = transactions.copy()
    grouped = work.groupby("week_no", as_index=False).agg(
        net_sales=("sales_value", "sum"),
        discount_cost=("discount_cost", "sum"),
        gross_sales=("gross_sales", "sum"),
    )
    grouped["discount_rate"] = np.where(grouped["gross_sales"] > 0, grouped["discount_cost"] / grouped["gross_sales"], np.nan)
    return grouped
