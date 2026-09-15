"""Score worksheets to pick the best sales-data sheet."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.header_mapper import (
    best_field_match,
    normalize_header_text,
)
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix

logger = get_logger(__name__)


def _populated_cells(matrix: Sequence[Sequence[Any]], *, max_rows: int = 80) -> Tuple[int, int]:
    rows_with_data = 0
    cols_hit: set[int] = set()
    for r_idx, row in enumerate(matrix[:max_rows]):
        row_has = False
        for c_idx, cell in enumerate(row):
            text = str(cell).strip() if cell is not None else ""
            if text:
                row_has = True
                cols_hit.add(c_idx)
        if row_has:
            rows_with_data += 1
    return rows_with_data, len(cols_hit)


def _header_keyword_hits(matrix: Sequence[Sequence[Any]], *, scan_rows: int = 20) -> dict[str, float]:
    """Scan early rows for customer/product/quantity-like headers (incl. month pivots)."""
    from app.erp_parser.header_mapper import is_month_header

    best = {"customer": 0.0, "product": 0.0, "quantity": 0.0}
    for row in matrix[:scan_rows]:
        for cell in row:
            text = normalize_header_text(cell)
            if not text:
                continue
            if is_month_header(text):
                best["quantity"] = max(best["quantity"], 96.0)
                continue
            for field in ("customer", "product", "quantity"):
                _label, score, _method = best_field_match(text, field)
                if score > best[field]:
                    best[field] = score
    return best


def score_sheet(matrix: Sequence[Sequence[Any]]) -> float:
    """
    Score a sheet for likelihood of containing ERP sales lines.

    Rewards populated density and presence of customer/product/qty headers.
    """
    if not matrix:
        return 0.0

    pop_rows, pop_cols = _populated_cells(matrix)
    density = min(40.0, pop_rows * 0.35 + pop_cols * 1.2)

    hits = _header_keyword_hits(matrix)
    header_pts = (
        hits["customer"] * 25.0
        + hits["product"] * 20.0
        + hits["quantity"] * 25.0
    ) / 100.0  # max ~70 if all perfect

    # Mild bonus when all three fields appear in early rows
    triad = sum(1 for f in ("customer", "product", "quantity") if hits[f] >= 70)
    triad_bonus = 10.0 if triad == 3 else (5.0 if triad == 2 else 0.0)

    return round(density + header_pts + triad_bonus, 2)


def detect_best_sheet(
    path: Union[str, Path],
    *,
    allow_llm_fallback: bool = True,
    min_score: float = 25.0,
) -> Tuple[str, float]:
    """
    Choose the highest-scoring non-empty worksheet.

    When all deterministic scores are weak, optionally ask the LLM which sheet
    holds sales data.

    Returns ``(sheet_name, sheet_score)``.
    """
    candidates = list_candidate_sheets(path)
    scored: List[Tuple[str, float]] = []
    for name in candidates:
        try:
            matrix = read_sheet_matrix(path, name)
            scored.append((name, score_sheet(matrix)))
        except Exception:  # noqa: BLE001
            scored.append((name, 0.0))

    scored.sort(key=lambda t: t[1], reverse=True)
    best_name, best_score = scored[0]

    if allow_llm_fallback and best_score < min_score:
        try:
            from app.erp_parser.llm_sheet_resolver import LLMSheetResolver

            llm_name, llm_conf = LLMSheetResolver().pick_sheet(path, candidates=candidates)
            logger.info(
                "Sheet pick via LLM | sheet={} | llm_conf={} | python_best={} ({})",
                llm_name,
                llm_conf,
                best_name,
                best_score,
            )
            return llm_name, max(best_score, float(llm_conf) * 0.9)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM sheet pick skipped | err={}", exc)

    return best_name, best_score
