"""Workbook loading and candidate sheet discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Sequence, Union

from openpyxl.worksheet.worksheet import Worksheet

from app.erp_parser.workbook_loader import load_workbook_any
from app.exceptions import ExcelProcessingError


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
    """Load .xlsx, .xlsm, or .xls. The caller receives one workbook surface."""
    return load_workbook_any(path)


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


def merged_map_for_sheet(ws: Any) -> dict[tuple[int, int], Any]:
    """Expand each merged range from its top-left value. Built once per sheet."""
    merged_map: dict[tuple[int, int], Any] = {}
    ranges = getattr(getattr(ws, "merged_cells", None), "ranges", None) or []
    for merged in list(ranges):
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
    return merged_map


def merged_range_count(wb: Any) -> int:
    total = 0
    for name in wb.sheetnames:
        ranges = getattr(getattr(wb[name], "merged_cells", None), "ranges", None)
        if ranges is None:
            continue
        total += len(list(ranges))
    return total


def hidden_column_indexes(ws: Any, width: int) -> set[int]:
    from openpyxl.utils import get_column_letter

    hidden: set[int] = set()
    for idx in range(1, width + 1):
        dim = ws.column_dimensions.get(get_column_letter(idx))
        if dim is not None and bool(getattr(dim, "hidden", False)):
            hidden.add(idx - 1)
    return hidden


def matrix_from_worksheet(
    ws: Any,
    *,
    max_rows: int = 5000,
    max_cols: int = 60,
    merged_map: dict[tuple[int, int], Any] | None = None,
) -> List[List[Any]]:
    """Dense matrix. Merged cells are filled from the shared map."""
    if merged_map is None:
        merged_map = merged_map_for_sheet(ws)
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
            rows.append(values)
    while rows and not any(_cell_text(v) for v in rows[-1]):
        rows.pop()
    return rows


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
        return matrix_from_worksheet(wb[resolved], max_rows=max_rows, max_cols=max_cols)
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
