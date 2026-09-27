"""Open one workbook and hand the same object to every later stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

from app.erp_parser.workbook_detector import (
    hidden_column_indexes,
    matrix_from_worksheet,
    merged_map_for_sheet,
    merged_range_count,
    sheet_is_empty,
)
from app.erp_parser.workbook_loader import load_workbook_any
from app.exceptions import ExcelProcessingError


@dataclass
class PreparedWorkbook:
    """In-memory result of a single workbook open."""

    path: Path
    candidate_sheets: List[str] = field(default_factory=list)
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    raw_matrices: Dict[str, List[List[Any]]] = field(default_factory=dict)
    merged_cells: int = 0


def open_workbook_once(path: Union[str, Path]) -> PreparedWorkbook:
    """Load the file once. Hidden columns, merges, and matrices are taken from that object."""
    file_path = Path(path)
    from app.erp_parser.orchestrator.normalizer import normalize_matrix

    workbook = load_workbook_any(file_path)
    try:
        candidates: List[str] = []
        for name in workbook.sheetnames:
            if sheet_is_empty(workbook[name]):
                continue
            candidates.append(name)
        if not candidates:
            raise ExcelProcessingError("Workbook has no non-empty worksheets")

        visible: List[str] = []
        for name in candidates:
            if getattr(workbook[name], "sheet_state", "visible") == "visible":
                visible.append(name)
        names = visible or candidates

        raw: Dict[str, List[List[Any]]] = {}
        sheets: List[Dict[str, Any]] = []
        for name in candidates:
            worksheet = workbook[name]
            merged = merged_map_for_sheet(worksheet)
            matrix = matrix_from_worksheet(worksheet, merged_map=merged)
            raw[name] = matrix
            if name not in names or not matrix:
                continue
            width = max(len(row) for row in matrix)
            hidden = hidden_column_indexes(worksheet, width)
            normalized = normalize_matrix(matrix, hidden)
            if normalized:
                sheets.append({"sheet_name": name, "matrix": normalized})

        return PreparedWorkbook(
            path=file_path,
            candidate_sheets=candidates,
            sheets=sheets,
            raw_matrices=raw,
            merged_cells=merged_range_count(workbook),
        )
    finally:
        workbook.close()
