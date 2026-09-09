"""Detect the sales header row within the first 20 rows of a sheet."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.erp_parser.header_mapper import map_headers, normalize_header_text


def _row_is_blank(row: Sequence[Any]) -> bool:
    return not any(str(c).strip() if c is not None else "" for c in row)


def _looks_like_title_row(row: Sequence[Any]) -> bool:
    """True for merged titles / company banners (few cells, long text, no qty-like tokens)."""
    texts = [normalize_header_text(c) for c in row if normalize_header_text(c)]
    if not texts:
        return True
    if len(texts) <= 2 and any(len(t) > 40 for t in texts):
        return True
    joined = " ".join(texts)
    title_tokens = (
        "sales report",
        "statement",
        "summary",
        "apcotex",
        "confidential",
        "export from",
    )
    if len(texts) <= 3 and any(tok in joined for tok in title_tokens):
        return True
    return False


def score_header_row(row: Sequence[Any]) -> Tuple[float, Dict[str, Any]]:
    """Score a candidate header row; higher is better."""
    if _row_is_blank(row) or _looks_like_title_row(row):
        return 0.0, map_headers([])

    mapped = map_headers(list(row))
    conf = mapped["confidences"]
    positions = mapped["positions"]
    has_monthly_qty = bool(mapped.get("quantity_columns"))

    # Require at least customer + quantity OR all three for a strong header
    mapped_count = sum(1 for f in ("customer", "product", "quantity") if positions[f] is not None)
    if mapped_count < 2 and not (positions.get("customer") is not None and positions.get("product") is not None and has_monthly_qty):
        return 0.0, mapped

    avg = (conf["customer"] + conf["product"] + conf["quantity"]) / 3.0
    # Bonus for having all three fields
    triad = 15.0 if mapped_count == 3 else 0.0
    if has_monthly_qty:
        triad = max(triad, 12.0)
    # Mild bonus for more non-empty header cells (real tables)
    populated = sum(1 for c in row if normalize_header_text(c))
    density = min(10.0, populated * 1.2)

    return round(avg + triad + density, 2), mapped


def detect_header_row(
    matrix: Sequence[Sequence[Any]],
    *,
    scan_rows: int = 20,
) -> Dict[str, Any]:
    """
    Find the best header row in the first ``scan_rows`` rows.

    Returns header_row (1-based), column_positions (1-based as in the prompt example),
    and full mapping metadata.
    """
    best_score = -1.0
    best_idx = 0
    best_mapped: Dict[str, Any] = map_headers([])

    limit = min(scan_rows, len(matrix))
    for idx in range(limit):
        score, mapped = score_header_row(matrix[idx])
        if score > best_score:
            best_score = score
            best_idx = idx
            best_mapped = mapped

    # Convert 0-based positions → 1-based column numbers for API clarity
    positions_0 = best_mapped["positions"]
    column_positions = {
        field: (positions_0[field] + 1 if positions_0[field] is not None else None)
        for field in ("customer", "product", "quantity")
    }

    return {
        "header_row": best_idx + 1,  # 1-based
        "header_row_index": best_idx,  # 0-based
        "header_score": best_score if best_score >= 0 else 0.0,
        "column_positions": column_positions,
        "mapping": best_mapped,
    }
