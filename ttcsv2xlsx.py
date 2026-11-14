#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.workbook.properties import CalcProperties
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from lapsrv import RaceConfig


def parse_clock_to_days(value: str) -> Optional[float]:
    raw = (value or "").strip()
    if not raw:
        return None
    sign = -1 if raw.startswith("-") else 1
    clean = raw[1:] if sign < 0 else raw
    parts = clean.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    else:
        raise ValueError(f"unsupported time format: {value!r}")
    total_seconds = sign * (hours * 3600 + minutes * 60 + seconds)
    return total_seconds / 86400.0


def set_time_cell(ws, ref: str, value: str) -> None:
    parsed = parse_clock_to_days(value) if (value or "").strip() else None
    cell = ws[ref]
    cell.value = parsed
    if parsed is not None:
        cell.number_format = "[h]:mm:ss.00"


def infer_source_xlsx(csv_path: Path) -> Optional[Path]:
    stem = csv_path.stem
    if stem.endswith("-tt-results"):
        candidate = csv_path.with_name(stem[: -len("-tt-results")] + ".xlsx")
        if candidate.exists():
            return candidate
        alt = csv_path.with_name(stem[: -len("-tt-results")] + "-orig.xlsx")
        if alt.exists():
            return alt
    return None


def load_rider_meta(source_xlsx: Optional[Path]) -> dict[str, dict[str, str]]:
    if not source_xlsx or not source_xlsx.exists():
        return {}
    cfg = RaceConfig.load(source_xlsx)
    wb = load_workbook(source_xlsx, data_only=True, read_only=True)
    category_by_bib: dict[str, str] = {}
    if "--CrossMgr-Categories" in wb.sheetnames:
        ws = wb["--CrossMgr-Categories"]
        headers = [str(v).strip() if v is not None else "" for v in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            rec = dict(zip(headers, row))
            name = str(rec.get("Name") or "").strip()
            if not name:
                continue
            gender = str(rec.get("Gender") or "").strip().lower()
            display = f"{name} (Women)" if gender == "women" else name
            numbers = str(rec.get("Numbers") or "").strip()
            if not numbers:
                continue
            for bib in numbers.split(","):
                bib_s = bib.strip()
                if bib_s:
                    category_by_bib[bib_s] = display

    return {
        bib: {
            "category": category_by_bib.get(bib, rider.category or ""),
            "team": rider.team or "",
        }
        for bib, rider in cfg.riders_by_bib.items()
    }


def build_workbook(
    csv_path: Path,
    xlsx_path: Path,
    sheet_name: str = "Results",
    source_xlsx: Optional[Path] = None,
) -> None:
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rider_meta = load_rider_meta(source_xlsx or infer_source_xlsx(csv_path))

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    wb.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True)

    headers = [
        "Pos",
        "Race",
        "BIB",
        "Start",
        "Stop",
        "Penalty",
        "Elapsed",
        "Last",
        "First",
        "Category",
        "Team",
        "Note",
    ]
    ws.append(headers)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row_num, src in enumerate(rows, start=2):
        bib_text = str(src.get("bib", "")).strip()
        meta = rider_meta.get(bib_text, {})
        category = src.get("category", "") or meta.get("category", "")
        team = src.get("team", "") or meta.get("team", "")
        ws[f"A{row_num}"] = (
            f'=IF(OR(J{row_num}="",G{row_num}=""),"",'
            f'1+COUNTIFS($J$2:$J$1048576,J{row_num},$G$2:$G$1048576,"<"&G{row_num})'
            f'+COUNTIFS($J$2:$J$1048576,J{row_num},$G$2:$G$1048576,G{row_num},$C$2:$C$1048576,"<"&C{row_num}))'
        )
        set_time_cell(ws, f"B{row_num}", src.get("race_time", ""))
        ws[f"C{row_num}"] = int(bib_text) if bib_text.isdigit() else bib_text
        set_time_cell(ws, f"D{row_num}", src.get("start_time", ""))
        set_time_cell(ws, f"E{row_num}", src.get("stop_time", ""))
        ws[f"F{row_num}"] = ""
        ws[f"G{row_num}"] = f'=IF(OR(E{row_num}="",D{row_num}=""),"",E{row_num}-D{row_num}+IF(F{row_num}="",0,F{row_num}/86400))'
        ws[f"G{row_num}"].number_format = "[h]:mm:ss.00"
        ws[f"H{row_num}"] = src.get("last_name", "")
        ws[f"I{row_num}"] = src.get("first_name", "")
        ws[f"J{row_num}"] = category
        ws[f"K{row_num}"] = team
        ws[f"L{row_num}"] = ""

    category_values = [str(ws[f"J{row_num}"].value or "") for row_num in range(2, ws.max_row + 1)]
    category_width = max([len("Category"), *(len(v) for v in category_values)], default=len("Category")) + 2

    widths = {
        "A": 5,
        "B": 12,
        "C": 5,
        "D": 12,
        "E": 12,
        "F": 6,
        "G": 12,
        "H": 18,
        "I": 18,
        "J": category_width,
        "K": 22,
        "L": 18,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    for col in ("B", "D", "E", "F", "G"):
        for row_num in range(2, ws.max_row + 1):
            ws[f"{col}{row_num}"].alignment = Alignment(horizontal="center")
    for row_num in range(2, ws.max_row + 1):
        ws[f"C{row_num}"].alignment = Alignment(horizontal="right")

    wb.save(xlsx_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert TT CSV export from lapsrv into an editable XLSX results sheet.")
    p.add_argument("csv_file", help="Input TT CSV file from lapsrv")
    p.add_argument("--xlsx", help="Output XLSX path; defaults beside the CSV")
    p.add_argument("--source-xlsx", help="CrossMgr XLSX used to backfill category/team by bib; default is inferred from the CSV filename")
    p.add_argument("--sheet-name", default="Results", help="Worksheet name")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_file)
    xlsx_path = Path(args.xlsx) if args.xlsx else csv_path.with_suffix(".xlsx")
    source_xlsx = Path(args.source_xlsx) if args.source_xlsx else None
    build_workbook(csv_path, xlsx_path, sheet_name=args.sheet_name, source_xlsx=source_xlsx)
    print(xlsx_path)


if __name__ == "__main__":
    main()
