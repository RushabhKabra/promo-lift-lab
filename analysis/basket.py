"""Which departments share a basket, and which ones move together across weeks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def department_affinity(basket_departments: pd.DataFrame, min_support: float = 0.03) -> pd.DataFrame:
    """Pair lift inside the basket.

    basket_departments: basket_id, department. A department is counted once per basket.
    Lift above 1 means the pair shows up together more than the two base rates imply.
    """
    pairs = basket_departments.drop_duplicates(["basket_id", "department"])
    if pairs.empty:
        return pd.DataFrame()
    n_baskets = pairs["basket_id"].nunique()
    support = pairs.groupby("department")["basket_id"].nunique() / n_baskets
    # Combinations within a basket.
    joined = pairs.merge(pairs, on="basket_id", suffixes=("_a", "_b"))
    joined = joined.loc[joined["department_a"] < joined["department_b"]]
    if joined.empty:
        return pd.DataFrame()
    counts = joined.groupby(["department_a", "department_b"], as_index=False)["basket_id"].nunique()
    counts = counts.rename(columns={"basket_id": "baskets"})
    counts["support"] = counts["baskets"] / n_baskets
    counts["support_a"] = counts["department_a"].map(support)
    counts["support_b"] = counts["department_b"].map(support)
    counts["confidence_a_to_b"] = counts["support"] / counts["support_a"]
    counts["lift"] = counts["support"] / (counts["support_a"] * counts["support_b"])
    counts = counts.loc[counts["support"] >= min_support].sort_values("lift", ascending=False)
    return counts.reset_index(drop=True)


def halo_associations(weekly: pd.DataFrame, departments: list[str] | None = None) -> pd.DataFrame:
    """Does department B's weekly sales move with department A's flyer intensity?

    Each pair is an ordinary regression of B's sales on A's placement intensity,
    B's own placement intensity, and a linear week trend. A positive coefficient
    on A is a halo in this panel; a negative one is the cannibalization direction.
    Fifty-odd weeks is a short panel, so I treat the sign as a clue, not a verdict.
    """
    frame = weekly.copy()
    if "is_partial" in frame.columns:
        frame = frame.loc[~frame["is_partial"].astype(bool)].copy()
    # Placement counts differ by orders of magnitude across departments.
    # Scale each department by its own average so the coefficient is the
    # change in target sales when the source moves by one typical flyer.
    means = frame.groupby("department")["promo_intensity"].transform("mean")
    frame["promo_intensity"] = (frame["promo_intensity"] / means.replace(0, np.nan)).fillna(0.0)
    if departments is None:
        totals = frame.groupby("department")["net_sales"].sum().sort_values(ascending=False)
        departments = [d for d in totals.head(8).index if d not in ("FUEL", "MISCELLANEOUS", "Unmapped")]
    wide_sales = frame.pivot_table(index="week_no", columns="department", values="net_sales", aggfunc="sum")
    wide_promo = frame.pivot_table(index="week_no", columns="department", values="promo_intensity", aggfunc="mean")
    rows = []
    for source in departments:
        if source not in wide_sales.columns or source not in wide_promo.columns:
            continue
        for target in departments:
            if target == source or target not in wide_sales.columns:
                continue
            design = pd.DataFrame(
                {
                    "source_promo": wide_promo[source],
                    "target_promo": wide_promo[target] if target in wide_promo.columns else 0.0,
                    "trend": np.arange(len(wide_sales)),
                },
                index=wide_sales.index,
            ).dropna()
            y = wide_sales[target].reindex(design.index)
            if design["source_promo"].std(ddof=0) < 1e-6 or y.std(ddof=0) < 1e-6:
                continue
            fitted = sm.OLS(y.to_numpy(), sm.add_constant(design.to_numpy())).fit()
            coef = float(fitted.params[1])
            se = float(fitted.bse[1])
            rows.append(
                {
                    "source_department": source,
                    "target_department": target,
                    "coef_sales_per_intensity": coef,
                    "std_error": se,
                    "t_stat": float(fitted.tvalues[1]),
                    "n_weeks": int(fitted.nobs),
                    "direction": "halo" if coef > 0 else "cannibalization",
                }
            )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["abs_t"] = out["t_stat"].abs()
    return out.sort_values("abs_t", ascending=False).reset_index(drop=True)
