"""Add the pricing view to the Excel briefing: discount depth vs payback, and the
promotions that did not earn their discount.

Reads only the certified extracts in exports/bi, so it runs without Postgres:

    python scripts/pricing_view.py

It writes four CSVs next to the other BI extracts and adds three tabs to
exports/excel/promo_weekly_brief.xlsx: "Depth data" (an Excel Table, one row per
category), "Depth pivot" (a native PivotTable on that table, rows = depth band),
and "Money-losing promos". Rerunning replaces those tabs; the rest of the
workbook is left as scripts/export.py wrote it. The run stops if the band totals
drift from the certified feature headline by more than $1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.pivot.cache import (
    CacheDefinition,
    CacheField,
    CacheSource,
    SharedItems,
    WorksheetSource,
)
from openpyxl.pivot.fields import Index, Missing, Number, Text
from openpyxl.pivot.record import Record, RecordList
from openpyxl.pivot.table import (
    DataField,
    FieldItem,
    Location,
    PivotField,
    PivotTableStyle,
    RowColField,
    RowColItem,
    TableDefinition,
)
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.pricing import (  # noqa: E402
    DEPTH_LABELS,
    depth_bands,
    depth_by_category,
    money_losing_campaigns,
    money_losing_categories,
)

BI = ROOT / "exports" / "bi"
BOOK = ROOT / "exports" / "excel" / "promo_weekly_brief.xlsx"
KPIS = ROOT / "exports" / "app" / "certified_kpis.json"
TABS = ("Depth data", "Depth pivot", "Money-losing promos")

INK = "1F1A17"
GREEN = "1F6B4A"
BRICK = "A33B32"
LINE = "E4DCD0"
MONEY = "$#,##0.00"
PCT = "0.0%"
RATIO = "0.00"
THIN = Border(*(Side(style="thin", color=LINE),) * 4)


def build_frames() -> dict[str, pd.DataFrame]:
    category_lift = pd.read_csv(BI / "category_lift.csv")
    campaigns = pd.read_csv(BI / "campaign_results.csv", dtype={"campaign_id": str})
    by_category = depth_by_category(category_lift)
    return {
        "by_category": by_category,
        "bands": depth_bands(by_category),
        "campaigns": money_losing_campaigns(campaigns),
        "categories": money_losing_categories(by_category),
    }


def reconcile(bands: pd.DataFrame) -> None:
    headline = json.loads(KPIS.read_text())["headline"]
    checks = {
        "incremental_sales": headline["feature_incremental_sales"],
        "discount_cost": headline["feature_discount_cost"],
    }
    for column, certified in checks.items():
        drift = abs(float(bands[column].sum()) - float(certified))
        if drift > 1.0:
            raise SystemExit(f"{column} drifts {drift:.2f} from the certified headline")


def _header(cell) -> None:
    cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor=GREEN)
    cell.border = THIN
    cell.alignment = Alignment(vertical="center", wrap_text=True)


def _write_table(sheet, frame: pd.DataFrame, top: int, formats: dict[str, str]) -> int:
    for j, column in enumerate(frame.columns, start=1):
        _header(sheet.cell(top, j, column))
        sheet.column_dimensions[get_column_letter(j)].width = max(14, min(32, len(column) + 4))
    for i, row in enumerate(frame.itertuples(index=False), start=top + 1):
        for j, (column, value) in enumerate(zip(frame.columns, row), start=1):
            if isinstance(value, float) and pd.isna(value):
                value = None
            elif hasattr(value, "item"):
                value = value.item()
            cell = sheet.cell(i, j, value)
            cell.font = Font(name="Calibri", size=10, color=INK)
            cell.border = THIN
            if column in formats:
                cell.number_format = formats[column]
    return top + len(frame)


def _title(sheet, text: str, note: str) -> None:
    sheet.sheet_view.showGridLines = False
    sheet["A1"] = text
    sheet["A1"].font = Font(name="Calibri", size=16, bold=True, color=GREEN)
    sheet["A2"] = note
    sheet["A2"].font = Font(name="Calibri", size=10, italic=True, color="6B625A")


FORMATS = {
    "discount_depth": PCT,
    "lift_pct": PCT,
    "feature_sales": MONEY,
    "counterfactual_sales": MONEY,
    "incremental_sales": MONEY,
    "discount_cost": MONEY,
    "coupon_cost": MONEY,
    "incremental_less_discount": MONEY,
    "payback": RATIO,
    "roi": RATIO,
    "did_low": MONEY,
    "did_high": MONEY,
}


def _data_tab(book, by_category: pd.DataFrame) -> tuple[str, int, int]:
    sheet = book.create_sheet("Depth data")
    last = _write_table(sheet, by_category, 1, FORMATS)
    ref = f"A1:{get_column_letter(len(by_category.columns))}{last}"
    table = Table(displayName="tbl_depth_by_category", ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    sheet.add_table(table)
    sheet.freeze_panes = "C2"
    return ref, last, len(by_category.columns)


def _pivot(by_category: pd.DataFrame, ref: str) -> TableDefinition:
    """A PivotTable on tbl_depth_by_category: rows = depth band, values = sums."""
    columns = list(by_category.columns)
    sum_fields = ["incremental_sales", "discount_cost", "feature_sales", "counterfactual_sales"]
    bands = [b for b in DEPTH_LABELS if b in set(by_category["depth_band"])]

    # Text columns use shared items (records point at them by index); numbers go inline.
    shared: dict[str, list[str]] = {"depth_band": bands}
    for column in columns:
        if column != "depth_band" and not pd.api.types.is_numeric_dtype(by_category[column]):
            shared[column] = sorted(by_category[column].astype(str).unique())

    fields = []
    for column in columns:
        if column in shared:
            items = SharedItems(_fields=[Text(v=v) for v in shared[column]])
            fields.append(CacheField(name=column, sharedItems=items))
        else:
            numeric = pd.to_numeric(by_category[column], errors="coerce")
            integer = bool(numeric.dropna().eq(numeric.dropna().round()).all())
            fields.append(
                CacheField(
                    name=column,
                    sharedItems=SharedItems(
                        containsSemiMixedTypes=False,
                        containsString=False,
                        containsNumber=True,
                        containsInteger=integer or None,
                        containsBlank=True if numeric.isna().any() else None,
                        minValue=float(numeric.min()),
                        maxValue=float(numeric.max()),
                    ),
                )
            )

    records = []
    for row in by_category.itertuples(index=False):
        values = []
        for column, value in zip(columns, row):
            if column in shared:
                values.append(Index(v=shared[column].index(str(value))))
            elif value is None or pd.isna(value):
                values.append(Missing())
            else:
                values.append(Number(v=float(value)))
        records.append(Record(_fields=values))

    cache = CacheDefinition(
        refreshOnLoad=True,
        recordCount=len(records),
        cacheSource=CacheSource(type="worksheet", worksheetSource=WorksheetSource(name="tbl_depth_by_category")),
        cacheFields=fields,
    )
    cache.records = RecordList(count=len(records), r=records)

    pivot_fields = []
    for column in columns:
        if column == "depth_band":
            items = [FieldItem(x=i) for i in range(len(bands))] + [FieldItem(t="default")]
            pivot_fields.append(PivotField(axis="axisRow", showAll=False, items=items))
        elif column in sum_fields:
            pivot_fields.append(PivotField(dataField=True, showAll=False))
        else:
            pivot_fields.append(PivotField(showAll=False))

    band_col = columns.index("depth_band")
    n_rows = len(bands) + 2  # header + bands + grand total
    pivot = TableDefinition(
        name="pvt_depth_payback",
        cacheId=1,
        dataCaption="Values",
        applyNumberFormats=False,
        applyBorderFormats=False,
        applyFontFormats=False,
        applyPatternFormats=False,
        applyAlignmentFormats=False,
        applyWidthHeightFormats=True,
        updatedVersion=6,
        minRefreshableVersion=3,
        createdVersion=6,
        useAutoFormatting=True,
        itemPrintTitles=True,
        indent=0,
        outline=True,
        outlineData=True,
        rowHeaderCaption="Discount depth band",
        location=Location(
            ref=f"A4:{get_column_letter(1 + len(sum_fields))}{3 + n_rows}",
            firstHeaderRow=0,
            firstDataRow=1,
            firstDataCol=1,
        ),
        pivotFields=pivot_fields,
        rowFields=[RowColField(x=band_col)],
        rowItems=[RowColItem(x=[i]) for i in range(len(bands))] + [RowColItem(t="grand", x=[0])],
        colFields=[RowColField(x=-2)],
        colItems=[RowColItem(i=i, x=[i]) for i in range(len(sum_fields))],
        dataFields=[
            DataField(name=f"Sum of {f}", fld=columns.index(f), baseField=0, baseItem=0, numFmtId=4)
            for f in sum_fields
        ],
        pivotTableStyleInfo=PivotTableStyle(
            name="PivotStyleLight16", showRowHeaders=True, showColHeaders=True, showRowStripes=False
        ),
    )
    pivot.cache = cache
    return pivot


def _pivot_tab(book, frames: dict[str, pd.DataFrame], ref: str) -> None:
    sheet = book.create_sheet("Depth pivot")
    _title(
        sheet,
        "Discount depth vs payback",
        "PivotTable on tbl_depth_by_category (Depth data tab). Payback = incremental net sales per "
        "discount dollar, a sales measure before cost of goods.",
    )
    bands = frames["bands"]
    sum_fields = ["incremental_sales", "discount_cost", "feature_sales", "counterfactual_sales"]
    # Rendered cells, so the tab reads correctly before Excel refreshes the pivot.
    sheet.cell(4, 1, "Discount depth band")
    for j, f in enumerate(sum_fields, start=2):
        sheet.cell(4, j, f"Sum of {f}")
    for i, row in enumerate(bands.itertuples(index=False), start=5):
        sheet.cell(i, 1, row.depth_band)
        for j, f in enumerate(sum_fields, start=2):
            sheet.cell(i, j, float(getattr(row, f))).number_format = MONEY
    total_row = 5 + len(bands)
    sheet.cell(total_row, 1, "Grand Total")
    for j, f in enumerate(sum_fields, start=2):
        sheet.cell(total_row, j, float(bands[f].sum())).number_format = MONEY

    # Payback and lift beside the pivot, read from it with GETPIVOTDATA.
    for col, label in ((7, "payback"), (8, "lift_pct"), (9, "incremental_less_discount")):
        _header(sheet.cell(4, col, label))
        sheet.column_dimensions[get_column_letter(col)].width = 22
    for i, row in enumerate(list(bands["depth_band"]) + [None], start=5):
        def gp(field: str, band=row) -> str:
            if band is None:
                return f'GETPIVOTDATA("Sum of {field}",$A$4)'
            return f'GETPIVOTDATA("Sum of {field}",$A$4,"depth_band","{band}")'

        sheet.cell(i, 7, f'=IFERROR({gp("incremental_sales")}/{gp("discount_cost")},"")').number_format = RATIO
        sheet.cell(i, 8, f'=IFERROR({gp("feature_sales")}/{gp("counterfactual_sales")}-1,"")').number_format = PCT
        sheet.cell(i, 9, f'={gp("incremental_sales")}-{gp("discount_cost")}').number_format = MONEY
    for col in range(1, 6):
        sheet.column_dimensions[get_column_letter(col)].width = 24
    note_row = total_row + 2
    sheet.cell(note_row, 1, "How I read this").font = Font(name="Calibri", size=12, bold=True, color=GREEN)
    sheet.cell(
        note_row + 1,
        1,
        "Shallow discounts paid back; deep ones did not. Below 20% depth each discount dollar returned "
        "more than a dollar of extra sales. From 20% up it returned less than a dollar, before any cost of goods.",
    ).alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells(start_row=note_row + 1, start_column=1, end_row=note_row + 1, end_column=9)
    sheet.row_dimensions[note_row + 1].height = 32
    sheet.add_pivot(_pivot(frames["by_category"], ref))


def _losers_tab(book, frames: dict[str, pd.DataFrame]) -> None:
    sheet = book.create_sheet("Money-losing promos")
    _title(
        sheet,
        "Promotions that did not earn their discount",
        "Campaigns: scored mailers with incremental net sales below zero (difference-in-differences). "
        "Categories: feature weeks where extra sales fell short of the discount, 20+ product-store pairs.",
    )
    sheet["A4"] = "Campaigns with negative incremental sales"
    sheet["A4"].font = Font(name="Calibri", size=12, bold=True, color=BRICK)
    end = _write_table(sheet, frames["campaigns"], 5, FORMATS)
    top = end + 3
    sheet.cell(top - 1, 1, "Categories where feature-week extra sales did not cover the discount").font = Font(
        name="Calibri", size=12, bold=True, color=BRICK
    )
    _write_table(sheet, frames["categories"], top, FORMATS)
    sheet.freeze_panes = "B6"


def write_book(frames: dict[str, pd.DataFrame], path: Path = BOOK) -> None:
    book = load_workbook(path)
    for name in TABS:
        if name in book.sheetnames:
            del book[name]
    ref, _, _ = _data_tab(book, frames["by_category"])
    _pivot_tab(book, frames, ref)
    _losers_tab(book, frames)
    book.save(path)


def main() -> None:
    frames = build_frames()
    if frames["by_category"].empty:
        print("category_lift is empty in this build; pricing view skipped")
        return
    reconcile(frames["bands"])
    frames["by_category"].to_csv(BI / "discount_depth_by_category.csv", index=False)
    frames["bands"].to_csv(BI / "discount_depth_bands.csv", index=False)
    frames["campaigns"].to_csv(BI / "money_losing_campaigns.csv", index=False)
    frames["categories"].to_csv(BI / "money_losing_categories.csv", index=False)
    write_book(frames)
    print(frames["bands"].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
