"""Excel briefing pack and Power BI / Tableau extracts."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from warehouse.db import get_engine  # noqa: E402
from warehouse.load import read_df  # noqa: E402

BI = ROOT / "exports" / "bi"
EXCEL = ROOT / "exports" / "excel"
CURATED = ROOT / "exports" / "curated"

INK = "1F1A17"
GREEN = "1F6B4A"
PAPER = "F4F0E8"
AMBER = "C47B2B"
BRICK = "A33B32"
LINE = "E4DCD0"

DICTIONARY = [
    ("dim_date", "date_key", "Calendar date", "One row per calendar date in the study."),
    ("dim_date", "primary_week_no", "Study week", "Week with the most receipts that day. The cutover is early morning, so a date can touch two weeks."),
    ("dim_week", "week_no", "Study week number", "The week printed on the receipt, 1 to 53. Not an ISO week."),
    ("dim_week", "is_partial", "Partial week", "True when the week covers fewer than 6 dates. Week 1 is partial."),
    ("dim_product", "department", "Department", "Top of the product hierarchy."),
    ("dim_product", "product_category", "Category", "Commodity. The worked example lives at this grain."),
    ("dim_product", "is_fuel", "Fuel flag", "Gasoline quantity is scaled and is excluded from grocery unit totals."),
    ("dim_household", "has_demographics", "Demographics present", "Only a subset of households have age and income bins."),
    ("dim_campaign", "campaign_type", "Campaign type", "Type A, B, or C as labeled by the study. I treat the household list as the mailed group for every type."),
    ("fct_transactions", "sales_value", "Net sales", "Cash the retailer received. Already net of the three discounts."),
    ("fct_transactions", "gross_sales", "Gross sales proxy", "sales_value + retail_discount + coupon_discount + match_discount."),
    ("fct_transactions", "discount_cost", "Discount cost", "Sum of the three discount fields, stored as positive costs."),
    ("fct_transactions", "grocery_units", "Grocery units", "Quantity, with fuel lines set to 0."),
    ("fct_transactions", "on_feature", "On feature", "The product-store-week appears in the promotions file (display or mailer)."),
    ("campaign_results", "incremental_sales", "Incremental net sales", "Difference-in-differences on household weekly net sales, times treated households, times campaign weeks."),
    ("campaign_results", "roi", "Promo ROI proxy", "incremental_sales / coupon and match discounts on couponed products for mailed households."),
    ("campaign_results", "redemption_rate", "Redemption rate", "Redemptions / (mailed households × distinct coupon UPCs)."),
    ("department_lift", "lift_pct", "Feature lift", "Feature-week sales / baseline-week sales − 1, weighted by dollars, on pairs with enough history."),
    ("forecast_scores", "weighted_mape", "Forecast MAPE", "Sum of absolute errors / sum of actual net sales on the holdout."),
    ("segment_summary", "promo_sensitive_share", "Promo-sensitive share", "Households whose discount share of the pre-discount ring is at least 18%, with 8 or more baskets."),
]


def main() -> None:
    engine = get_engine()
    BI.mkdir(parents=True, exist_ok=True)
    EXCEL.mkdir(parents=True, exist_ok=True)
    extracts = {
        "dim_date": "SELECT * FROM core.dim_date ORDER BY date_key",
        "dim_week": "SELECT * FROM core.dim_week ORDER BY week_no",
        "dim_product": "SELECT product_sk, product_id, department, brand, product_category, product_type, is_fuel FROM core.dim_product",
        "dim_campaign": "SELECT * FROM core.dim_campaign ORDER BY campaign_id",
        "weekly_department": "SELECT * FROM marts.v_weekly_department ORDER BY week_no, department",
        "campaign_results": "SELECT * FROM marts.v_campaign_results",
        "department_lift": "SELECT * FROM marts.v_department_lift",
        "category_lift": "SELECT * FROM marts.v_category_lift",
        "forecast_weekly": "SELECT * FROM marts.v_forecast_weekly",
        "forecast_scores": "SELECT * FROM marts.v_forecast_scores",
        "segment_summary": "SELECT * FROM marts.v_segment_summary",
        "household_segments": "SELECT household_id, segment, recency_days, frequency, monetary, promo_sensitive, discount_share_of_gross, r_quintile, f_quintile, m_quintile FROM marts.household_rfm",
        "headline": "SELECT * FROM marts.v_headline",
    }
    frames = {}
    for name, query in extracts.items():
        frame = read_df(engine, query)
        frames[name] = frame
        frame.to_parquet(BI / f"{name}.parquet", index=False)
        # Line-level product dimension is wide but still a dimension, not the fact.
        if name != "dim_product":
            frame.to_csv(BI / f"{name}.csv", index=False)
        else:
            frame.to_csv(BI / f"{name}.csv", index=False)
    dictionary = pd.DataFrame(DICTIONARY, columns=["table", "column", "name", "definition"])
    dictionary.to_csv(BI / "data_dictionary.csv", index=False)
    curated_frames = dict(frames)
    curated_frames["weekly_total"] = read_df(engine, "SELECT * FROM marts.v_weekly_total ORDER BY week_no")
    curated_files = write_curated_frames(curated_frames, CURATED)
    _excel(frames, dictionary)
    _bi_readme()
    print(f"wrote {EXCEL / 'promo_weekly_brief.xlsx'}")
    print(f"wrote {sum(curated_files.values())} curated parquet files under {CURATED}")




def is_weekly_mart(name: str, frame: pd.DataFrame) -> bool:
    """Partition study-week marts, not dimensions that merely have a week key."""
    return "week_no" in frame.columns and not name.startswith("dim_")


def curated_partition_path(base: Path, name: str, week_no: int) -> Path:
    return base / name / f"week_no={int(week_no)}" / "part.parquet"


def curated_table_path(base: Path, name: str) -> Path:
    return base / name / "part.parquet"


def write_curated_frames(frames: dict[str, pd.DataFrame], dest: Path | None = None) -> dict[str, int]:
    """Publish marts as parquet. Weekly marts go in week_no= folders, like a dated planner."""
    dest = dest or CURATED
    dest.mkdir(parents=True, exist_ok=True)
    for child in dest.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
    written: dict[str, int] = {}
    for name, frame in frames.items():
        if frame is None:
            written[name] = 0
            continue
        if is_weekly_mart(name, frame) and len(frame):
            files = 0
            for week_no, part in frame.groupby("week_no", sort=True):
                path = curated_partition_path(dest, name, int(week_no))
                path.parent.mkdir(parents=True, exist_ok=True)
                part.to_parquet(path, index=False)
                files += 1
            written[name] = files
        else:
            path = curated_table_path(dest, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
            written[name] = 1
    return written

def _excel(frames: dict[str, pd.DataFrame], dictionary: pd.DataFrame) -> None:
    book = Workbook()
    headline = frames["headline"].iloc[0].to_dict() if len(frames["headline"]) else {}
    _cover(book.active, headline)
    _sheet(book, "KPI dictionary", dictionary, freeze=True)
    _sheet(
        book,
        "Campaign ranking",
        _sort_campaigns(frames["campaign_results"]),
        money_cols={"incremental_sales", "coupon_cost", "treated_pre_per_week", "treated_post_per_week"},
        pct_cols={"redemption_rate", "roi"},
        freeze=True,
    )
    _sheet(
        book,
        "Category lift",
        frames["category_lift"].head(200) if len(frames["category_lift"]) else frames["category_lift"],
        money_cols={"feature_sales", "counterfactual_sales", "incremental_sales", "discount_cost"},
        pct_cols={"lift_pct", "roi"},
        freeze=True,
    )
    _sheet(
        book,
        "Forecast accuracy",
        frames["forecast_scores"],
        pct_cols={"mape", "smape", "weighted_mape"},
        freeze=True,
    )
    _sheet(book, "Segments", frames["segment_summary"], pct_cols={"household_share", "sales_share", "promo_sensitive_share", "avg_discount_share_of_gross"}, money_cols={"net_sales", "avg_monetary"}, freeze=True)
    exceptions = _exceptions(frames)
    _sheet(book, "Quality exceptions", exceptions, freeze=True)
    book.save(EXCEL / "promo_weekly_brief.xlsx")


def _cover(sheet, headline: dict) -> None:
    sheet.title = "Cover"
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet["A1"] = "promo-lift lab"
    sheet["A1"].font = Font(name="Calibri", size=22, color=GREEN, bold=True)
    sheet["A2"] = "Weekly briefing on whether the promotions earned their keep"
    sheet["A2"].font = Font(name="Calibri", size=12, italic=True, color="6B625A")
    start = str(headline.get("period_start") or "")[:10]
    end = str(headline.get("period_end") or "")[:10]
    sheet["A3"] = f"Study window {start} to {end}. Figures come from the certified marts, not from a slide I typed by hand."
    sheet["A3"].font = Font(name="Calibri", size=10, color=INK)
    sheet.merge_cells("A3:F3")

    cards = [
        ("Net sales", headline.get("net_sales"), "$#,##0"),
        ("Discounts", headline.get("discount_cost"), "$#,##0"),
        ("Feature incremental sales", headline.get("feature_incremental_sales"), "$#,##0"),
        ("Feature lift", headline.get("feature_lift_pct"), "0.0%"),
        ("Campaigns below baseline", headline.get("n_campaigns_negative_incremental"), "#,##0"),
        ("Forecast default", headline.get("forecast_default_model"), None),
    ]
    for index, (label, value, fmt) in enumerate(cards):
        column = index + 1
        label_cell = sheet.cell(5, column, label)
        label_cell.font = Font(name="Calibri", size=9, color="FFFFFF", bold=True)
        label_cell.fill = PatternFill("solid", fgColor=GREEN)
        label_cell.alignment = Alignment(wrap_text=True, vertical="center")
        value_cell = sheet.cell(6, column, value if value is not None else "—")
        value_cell.font = Font(name="Calibri", size=16, color=INK, bold=True)
        value_cell.fill = PatternFill("solid", fgColor=PAPER)
        if fmt and isinstance(value, (int, float)):
            value_cell.number_format = fmt
        sheet.column_dimensions[get_column_letter(column)].width = 24
    sheet.row_dimensions[5].height = 30
    sheet.row_dimensions[6].height = 28

    sheet["A8"] = "How I read this"
    sheet["A8"].font = Font(name="Calibri", size=14, color=GREEN, bold=True)
    note = (
        "Feature lift compares the same product in the same store, on weeks it was on display or in the mailer, "
        "with the other weeks in its active span. It only covers pairs with enough history, so the coverage figure "
        "in the warehouse matters. Campaign ROI is a difference-in-differences against households that were not mailed, "
        "divided by coupon and match discounts. A negative incremental number means the mailed households handed over "
        "less money than that comparison, after discounts already reduced the net. This is observational. I would not "
        "call it a test."
    )
    sheet["A9"] = note
    sheet["A9"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet["A9"].font = Font(name="Calibri", size=11, color=INK)
    sheet.merge_cells("A9:F12")
    sheet.row_dimensions[9].height = 30
    sheet.oddFooter.left.text = "promo-lift lab"
    sheet.oddFooter.right.text = "Certified marts"


def _sheet(book, title, frame: pd.DataFrame, money_cols=None, pct_cols=None, freeze=False) -> None:
    money_cols = money_cols or set()
    pct_cols = pct_cols or set()
    sheet = book.create_sheet(title)
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.oddHeader.left.text = title
    thin = Border(
        left=Side(style="thin", color=LINE),
        right=Side(style="thin", color=LINE),
        top=Side(style="thin", color=LINE),
        bottom=Side(style="thin", color=LINE),
    )
    if frame is None or frame.empty:
        sheet["A1"] = "No rows in this build."
        return
    safe = frame.copy()
    for column in safe.columns:
        if str(safe[column].dtype).startswith("datetime"):
            safe[column] = safe[column].dt.strftime("%Y-%m-%d")
    for row_index, row in enumerate(dataframe_to_rows(safe, index=False, header=True), start=1):
        for col_index, value in enumerate(row, start=1):
            cell = sheet.cell(row_index, col_index, _cell_value(value))
            cell.font = Font(name="Calibri", size=10, color="FFFFFF" if row_index == 1 else INK, bold=row_index == 1)
            cell.border = thin
            cell.alignment = Alignment(vertical="center")
            if row_index == 1:
                cell.fill = PatternFill("solid", fgColor=GREEN)
            elif row_index % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="FBF8F3")
            header = safe.columns[col_index - 1]
            if row_index > 1 and isinstance(cell.value, (int, float)):
                if header in money_cols:
                    cell.number_format = '$#,##0.00'
                elif header in pct_cols or header.endswith("_pct") or header.endswith("_share"):
                    cell.number_format = "0.0%"
                elif header == "roi":
                    cell.number_format = "0.00"
                    if cell.value < 0:
                        cell.font = Font(name="Calibri", size=10, color=BRICK, bold=True)
                elif header == "incremental_sales" and cell.value < 0:
                    cell.font = Font(name="Calibri", size=10, color=BRICK)
    for col_index, column in enumerate(safe.columns, start=1):
        width = min(36, max(12, len(str(column)) + 2))
        sheet.column_dimensions[get_column_letter(col_index)].width = width
    sheet.auto_filter.ref = sheet.dimensions
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(safe.columns))}{len(safe) + 1}"
    if freeze:
        sheet.freeze_panes = "A2"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_TABLOID
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:1"
    if title == "Campaign ranking" and len(safe):
        _campaign_chart(sheet, safe)


def _campaign_chart(sheet, frame: pd.DataFrame) -> None:
    if "incremental_sales" not in frame.columns or "campaign_id" not in frame.columns:
        return
    chart = BarChart()
    chart.type = "col"
    chart.title = "Incremental net sales by campaign"
    chart.y_axis.title = "Dollars"
    chart.style = 10
    data = Reference(sheet, min_col=frame.columns.get_loc("incremental_sales") + 1, min_row=1, max_row=min(len(frame), 27) + 1)
    cats = Reference(sheet, min_col=frame.columns.get_loc("campaign_id") + 1, min_row=2, max_row=min(len(frame), 27) + 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.shape = 4
    chart.legend = None
    chart.dataLabels = DataLabelList()
    chart.y_axis.majorGridlines = None
    chart.width = 18
    chart.height = 8
    sheet.add_chart(chart, "A20")


def _exceptions(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    headline = frames["headline"].iloc[0].to_dict() if len(frames["headline"]) else {}
    rows = [
        {
            "check": "Fact sales versus staging",
            "value": headline.get("reconciliation_drift"),
            "note": "Must stay within $1 or 0.01%, whichever is larger. The build refuses to continue past that.",
        },
        {
            "check": "Returns observed",
            "value": headline.get("returns_observed"),
            "note": "This mirror has no negative quantities, so I do not report a return rate.",
        },
        {
            "check": "Off-feature discount share",
            "value": headline.get("off_feature_discount_share"),
            "note": "Share of discount dollars on lines with no display and no mailer.",
        },
        {
            "check": "Feature-baseline coverage",
            "value": headline.get("feature_coverage"),
            "note": "Share of non-fuel feature-week sales that sit on a product-store pair with a baseline.",
        },
        {
            "check": "Zero-quantity lines",
            "value": headline.get("zero_quantity_share"),
            "note": "Receipt lines with quantity 0. Some carry a coupon amount and no units.",
        },
    ]
    return pd.DataFrame(rows)


def _sort_campaigns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "incremental_sales" not in frame.columns:
        return frame
    return frame.sort_values("incremental_sales")


def _cell_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item") and not isinstance(value, (bytes, str)):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return value
    return value


def _bi_readme() -> None:
    text = """# Loading the extracts

These files are the star-schema-shaped extracts from the lab. I did not build a `.pbix` or a `.twbx`. Point the tool at this folder after `make export`.

## Relationships

- `weekly_department.week_no` → `dim_week.week_no`
- `weekly_department.department` is a degenerate key. If you want a department list, take the distinct values.
- `forecast_weekly.week_no` → `dim_week.week_no`, and `forecast_weekly.department` matches `weekly_department.department`
- `campaign_results.campaign_id` → `dim_campaign.campaign_id`
- `household_segments` is one row per household. It is a segment extract, not a receipt fact. Leave demographics off the model unless you have a reason; the bins live on `dim_household` inside Postgres, and I kept them out of this folder so a casual load does not drag household attributes onto a canvas.

`dim_product` is large. Load it when you need category drill-through. The briefing itself does not require the receipt lines.

## Measures worth defining

- Net sales = SUM(weekly_department[net_sales])
- Discount cost = SUM(weekly_department[discount_cost])
- Incremental sales = SUM(department_lift[incremental_sales])
- Promo ROI proxy = DIVIDE(SUM(campaign_results[incremental_sales]), SUM(campaign_results[coupon_cost]))

ROI at a campaign is already on `campaign_results.roi`. Prefer that column when you are looking at one campaign. A summed ratio is a different number.

## Tableau

Same relationships, same measures. Use `dim_week.week_start` as the date. Do not rebuild the study week from the calendar date: the week cuts over in the early morning, and one date can belong to two study weeks.

## What not to do

Do not join `bridge` coupon products onto redemptions before you count redemptions. One coupon UPC maps to many products, and the count will multiply. The redemption rate on `campaign_results` is already the one I use.
"""
    (BI / "README.md").write_text(text)


if __name__ == "__main__":
    main()
