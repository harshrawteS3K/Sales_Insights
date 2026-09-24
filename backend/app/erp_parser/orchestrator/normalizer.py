"""In-memory worksheet normalization. The file on disk is not modified."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, Union

from openpyxl.utils import get_column_letter

from app.erp_parser.workbook_detector import list_candidate_sheets, load_workbook_safe, read_sheet_matrix

_HEADER_WORDS = {
    "customer",
    "customer name",
    "party",
    "party name",
    "particulars",
    "product",
    "item",
    "material",
    "account name",
    "qty",
    "quantity",
    "nett sale qty",
    "net sale qty",
    "outwards",
    "inwards",
    "date",
    "unit",
    "buyer",
}


def _text(value: Any) -> str:
    if value is None or isinstance(value, (datetime, date)):
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return not isinstance(value, (int, float, datetime, date)) and _text(value) == ""


def _month_name(value: date) -> str:
    return f"{value.strftime('%B')} {value.year}"


def _hidden_column_indexes(path: Path, sheet_name: str, width: int) -> set[int]:
    wb = load_workbook_safe(path)
    try:
        ws = wb[sheet_name]
        hidden: set[int] = set()
        for idx in range(1, width + 1):
            dim = ws.column_dimensions.get(get_column_letter(idx))
            if dim is not None and bool(getattr(dim, "hidden", False)):
                hidden.add(idx - 1)
        return hidden
    finally:
        wb.close()


def _headerish(value: Any) -> bool:
    text = _text(value).casefold().rstrip(".").strip()
    return bool(text) and text in _HEADER_WORDS


def _convert_header_dates(matrix: List[List[Any]]) -> None:
    """Turn datetime header cells into month labels. Transaction dates stay intact."""
    for row in matrix[:25]:
        dates = [cell for cell in row if isinstance(cell, (datetime, date))]
        if len(dates) < 2:
            continue
        labels = [_text(cell) for cell in row if _text(cell)]
        if labels and not all(_headerish(label) for label in labels):
            continue
        for idx, cell in enumerate(row):
            if isinstance(cell, datetime):
                row[idx] = _month_name(cell.date())
            elif isinstance(cell, date):
                row[idx] = _month_name(cell)


def _uppercase_header_tokens(matrix: List[List[Any]]) -> None:
    for row in matrix[:25]:
        for idx, cell in enumerate(row):
            text = _text(cell)
            if text and text.casefold() in _HEADER_WORDS:
                row[idx] = text.upper()


def _trim_and_numbers(matrix: List[List[Any]]) -> None:
    for row in matrix:
        for idx, cell in enumerate(row):
            if isinstance(cell, str):
                row[idx] = cell.strip()


def _drop_empty(matrix: List[List[Any]]) -> List[List[Any]]:
    rows = [row for row in matrix if not all(_is_blank(cell) for cell in row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    for row in rows:
        if len(row) < width:
            row.extend([None] * (width - len(row)))
    keep = [
        col
        for col in range(width)
        if any(not _is_blank(row[col]) for row in rows)
    ]
    if not keep:
        return []
    return [[row[col] for col in keep] for row in rows]


def normalize_sheet_matrix(
    path: Union[str, Path],
    sheet_name: str,
) -> List[List[Any]]:
    """Merged cells are already expanded by the workbook reader."""
    file_path = Path(path)
    matrix = [list(row) for row in read_sheet_matrix(file_path, sheet_name)]
    if not matrix:
        return []
    width = max(len(row) for row in matrix)
    hidden = _hidden_column_indexes(file_path, sheet_name, width)
    if hidden:
        matrix = [
            [cell for idx, cell in enumerate(row) if idx not in hidden]
            for row in matrix
        ]
    _trim_and_numbers(matrix)
    _convert_header_dates(matrix)
    _uppercase_header_tokens(matrix)
    return _drop_empty(matrix)


def visible_sheets(path: Union[str, Path]) -> List[str]:
    """Non-empty visible worksheets, in workbook order."""
    file_path = Path(path)
    names = list_candidate_sheets(file_path)
    wb = load_workbook_safe(file_path)
    try:
        visible = []
        for name in names:
            ws = wb[name]
            if getattr(ws, "sheet_state", "visible") == "visible":
                visible.append(name)
        return visible or names
    finally:
        wb.close()


def normalize_workbook(path: Union[str, Path]) -> List[Dict[str, Any]]:
    sheets: List[Dict[str, Any]] = []
    for name in visible_sheets(path):
        matrix = normalize_sheet_matrix(path, name)
        if matrix:
            sheets.append({"sheet_name": name, "matrix": matrix})
    return sheets
