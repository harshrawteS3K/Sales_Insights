"""Workbook loading and candidate sheet discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Sequence, Union

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.exceptions import ExcelProcessingError

ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def sheet_is_empty(ws: Worksheet, *, max_rows: int = 200, max_cols: int = 40) -> bool:
    """True when the sheet has no non-empty cells in the scanned window."""
    for row in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
        for cell in row:
            if _cell_text(cell):
                return False
    return True


def load_workbook_safe(path: Union[str, Path]):
    """Load an .xlsx/.xlsm workbook with openpyxl (data_only=False to keep formulas readable)."""
    file_path = Path(path)
    if not file_path.exists():
        raise ExcelProcessingError(f"Excel file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ExcelProcessingError(
            f"Unsupported workbook type '{suffix}'. Only .xlsx and .xlsm are accepted."
        )
    try:
        return load_workbook(file_path, data_only=True, read_only=False)
    except Exception as exc:  # noqa: BLE001
        raise ExcelProcessingError(f"Unable to open workbook: {exc}") from exc


def list_candidate_sheets(path: Union[str, Path]) -> List[str]:
    """
    Return non-empty worksheet titles.

    Ignores completely empty sheets. No filename heuristics.
    """
    wb = load_workbook_safe(path)
    try:
        names: List[str] = []
        for name in wb.sheetnames:
            ws = wb[name]
            if sheet_is_empty(ws):
                continue
            names.append(name)
        if not names:
            raise ExcelProcessingError("Workbook has no non-empty worksheets")
        return names
    finally:
        wb.close()


def resolve_sheet_name(path: Union[str, Path], sheet_name: str) -> str:
    """Resolve a sheet title with exact, casefold, and fuzzy contains matching."""
    wanted = (sheet_name or "").strip()
    if not wanted:
        raise ExcelProcessingError("Sheet name is empty")
    # Never treat multi-sheet display labels as real titles
    if "," in wanted or wanted.endswith("…") or wanted.endswith("..."):
        raise ExcelProcessingError(f"Sheet not found: {wanted}")

    wb = load_workbook_safe(path)
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()

    if wanted in names:
        return wanted
    folded = {n.casefold(): n for n in names}
    if wanted.casefold() in folded:
        return folded[wanted.casefold()]
    # Prefix / contains (e.g. "Apr-25" vs "Apr-25 ")
    for n in names:
        if n.strip().casefold() == wanted.casefold():
            return n
    for n in names:
        if wanted.casefold() in n.casefold() or n.casefold() in wanted.casefold():
            return n
    raise ExcelProcessingError(f"Sheet not found: {wanted}")


def read_sheet_matrix(
    path: Union[str, Path],
    sheet_name: str,
    *,
    max_rows: int = 5000,
    max_cols: int = 60,
) -> List[List[Any]]:
    """Read a worksheet into a dense matrix of cell values (merged cells unwrapped)."""
    resolved = resolve_sheet_name(path, sheet_name)
    wb = load_workbook_safe(path)
    try:
        ws = wb[resolved]

        # Unwrap merged cells so header/title spans appear in every covered cell.
        merged_map: dict[tuple[int, int], Any] = {}
        for merged in list(ws.merged_cells.ranges):
            min_row, min_col, max_row, max_col = (
                merged.min_row,
                merged.min_col,
                merged.max_row,
                merged.max_col,
            )
            top_left = ws.cell(min_row, min_col).value
            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    merged_map[(r, c)] = top_left

        rows: List[List[Any]] = []
        for r_idx, row in enumerate(
            ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=False),
            start=1,
        ):
            values: List[Any] = []
            any_value = False
            for c_idx, cell in enumerate(row, start=1):
                val = merged_map.get((r_idx, c_idx), cell.value)
                if _cell_text(val):
                    any_value = True
                values.append(val)
            if any_value or rows:
                # Keep leading blank rows only until first content; trailing handled later
                rows.append(values)

        # Trim trailing all-blank rows
        while rows and not any(_cell_text(v) for v in rows[-1]):
            rows.pop()
        return rows
    finally:
        wb.close()


def detect_workbook(path: Union[str, Path]) -> dict:
    """Public workbook detection summary."""
    candidates = list_candidate_sheets(path)
    return {
        "path": str(path),
        "candidate_sheets": candidates,
        "sheet_count": len(candidates),
    }
