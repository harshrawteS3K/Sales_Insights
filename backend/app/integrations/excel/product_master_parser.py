"""
APCOTEX Product Master parser — multi-block worksheet support.

Real Product Master files place several independent tables side-by-side, e.g.:

  B:C  Industry Type Description | Product Code   (PAPER)
  E:F  Industry Type Description | Product Code   (CARPET)
  H:I  …                                          (CONSTRUCTION B2B)
  K:L  …                                          (CONSTRUCTION B2C)

This module scans every sheet for adjacent header pairs (alias-matched),
parses each block independently, then merges into one product list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from app.core.logging import get_logger
from app.exceptions import ExcelProcessingError
from app.integrations.excel.headers import (
    compact_header,
    match_product_master_field,
    normalize_header,
)
from app.utils.quantity import safe_str

logger = get_logger(__name__)

# Stop a block after this many consecutive blank data rows
_MAX_CONSECUTIVE_BLANKS = 8


@dataclass
class ProductMasterBlock:
    """One detected Industry/Product header pair and its data rows."""

    sheet_name: str
    header_row: int  # 1-based Excel row
    industry_col: int  # 1-based
    code_col: int  # 1-based
    industry_header_raw: str
    code_header_raw: str
    rows_imported: int = 0
    rows_skipped_blank: int = 0


@dataclass
class ProductMasterParseResult:
    records: List[dict] = field(default_factory=list)
    duplicates_ignored: int = 0
    blocks: List[ProductMasterBlock] = field(default_factory=list)
    sheet_name: str = ""


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return safe_str(value)


def _load_sheet_grid(path: Path) -> Tuple[str, List[List[Any]]]:
    """Return (sheet_name, rows) for the densest worksheet (memory-efficient)."""
    suffix = path.suffix.lower()
    if suffix == ".xls":
        df = pd.read_excel(path, sheet_name=0, header=None, engine="xlrd")
        rows = [[None if pd.isna(v) else v for v in row] for row in df.values.tolist()]
        return "Sheet1", rows

    # Pass 1: score sheets without retaining grids
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        best_name = workbook.sheetnames[0]
        best_score = -1
        for sheet in workbook.worksheets:
            score = 0
            for row in sheet.iter_rows(values_only=True):
                score += sum(1 for c in row if c is not None and str(c).strip())
            if score > best_score:
                best_score = score
                best_name = sheet.title
    finally:
        workbook.close()

    # Pass 2: load only the winning sheet
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook[best_name]
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        return best_name, rows
    finally:
        workbook.close()


def _pad_row(row: Sequence[Any], width: int) -> List[Any]:
    cells = list(row)
    if len(cells) < width:
        cells.extend([None] * (width - len(cells)))
    return cells


def detect_product_master_blocks(
    sheet_name: str,
    rows: List[List[Any]],
) -> List[ProductMasterBlock]:
    """
    Scan the grid for adjacent header pairs that map to industry_type + product_code.

    Supports either column order: Industry|Code or Code|Industry.
    """
    if not rows:
        return []

    max_cols = max((len(r) for r in rows), default=0)
    blocks: List[ProductMasterBlock] = []
    # Avoid registering the same header pair twice (same cols, nearby rows)
    seen_keys: set[Tuple[int, int, int]] = set()

    for r_idx, raw in enumerate(rows):
        row = _pad_row(raw, max_cols)
        for c_idx in range(max_cols - 1):
            left = match_product_master_field(row[c_idx])
            right = match_product_master_field(row[c_idx + 1])
            if not left or not right:
                continue
            if {left, right} != {"industry_type", "product_code"}:
                continue
            # Require two different fields (not Industry|Industry)
            if left == right:
                continue

            industry_col = c_idx + 1 if left == "industry_type" else c_idx + 2
            code_col = c_idx + 2 if left == "industry_type" else c_idx + 1
            key = (industry_col, code_col, r_idx)
            # Collapse near-duplicate detections on same columns (within 2 rows)
            if any(
                abs(r_idx - prev_r) <= 2 and ic == industry_col and cc == code_col
                for ic, cc, prev_r in seen_keys
            ):
                continue
            seen_keys.add(key)

            industry_raw = _cell_str(row[industry_col - 1])
            code_raw = _cell_str(row[code_col - 1])
            block = ProductMasterBlock(
                sheet_name=sheet_name,
                header_row=r_idx + 1,
                industry_col=industry_col,
                code_col=code_col,
                industry_header_raw=industry_raw,
                code_header_raw=code_raw,
            )
            blocks.append(block)
            logger.info(
                "ProductMaster Block Detected | sheet={} | header_row={} | "
                "cols={}:{} | industry_header={!r} (→ industry_type) | "
                "code_header={!r} (→ product_code) | normalized=({}, {})",
                sheet_name,
                block.header_row,
                get_column_letter(industry_col),
                get_column_letter(code_col),
                industry_raw,
                code_raw,
                compact_header(industry_raw),
                compact_header(code_raw),
            )

    return blocks


def _parse_block_rows(
    rows: List[List[Any]],
    block: ProductMasterBlock,
    *,
    max_cols: int,
) -> List[dict]:
    """Extract product rows under a header block; skip blanks; stop on next header."""
    records: List[dict] = []
    consecutive_blanks = 0
    start = block.header_row  # 0-based index of first data row = header_row (1-based) 

    for r_idx in range(start, len(rows)):
        row = _pad_row(rows[r_idx], max_cols)
        # Stop if this row itself is another industry/product header pair on these cols
        left = match_product_master_field(row[block.industry_col - 1])
        right = match_product_master_field(row[block.code_col - 1])
        if left and right and {left, right} == {"industry_type", "product_code"}:
            break

        industry = _cell_str(row[block.industry_col - 1])
        code = _cell_str(row[block.code_col - 1])

        if not industry and not code:
            consecutive_blanks += 1
            block.rows_skipped_blank += 1
            if consecutive_blanks >= _MAX_CONSECUTIVE_BLANKS:
                break
            continue

        consecutive_blanks = 0

        # Incomplete row — skip only this row
        if not industry or not code:
            block.rows_skipped_blank += 1
            continue

        # Skip if either cell looks like a repeated header mid-sheet
        if match_product_master_field(industry) and match_product_master_field(code):
            continue

        records.append(
            {
                "industry_type": industry,
                "product_code": code,
                "product_name": code,
                "segment": industry,
            }
        )

    block.rows_imported = len(records)
    return records


def parse_product_master_workbook(path: Union[str, Path]) -> ProductMasterParseResult:
    """
    Production Product Master parse: detect all blocks, merge, dedupe.

    Backward compatible with single-table layouts (one block from column A).
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ExcelProcessingError(f"Excel file not found: {file_path}")

    sheet_name, rows = _load_sheet_grid(file_path)
    max_cols = max((len(r) for r in rows), default=0)

    logger.info(
        "ProductMaster Workbook | path={} | sheet={} | rows={} | cols={}",
        file_path.name,
        sheet_name,
        len(rows),
        max_cols,
    )

    blocks = detect_product_master_blocks(sheet_name, rows)
    if not blocks:
        # Helpful diagnostics for missing headers
        sample_headers: List[str] = []
        for raw in rows[:30]:
            for cell in raw:
                text = _cell_str(cell)
                if text:
                    sample_headers.append(
                        f"{text!r}→{compact_header(text) or normalize_header(text)}"
                    )
                if len(sample_headers) >= 40:
                    break
            if len(sample_headers) >= 40:
                break
        raise ExcelProcessingError(
            "Product master: missing required columns ['industry_type', 'product_code']. "
            "Could not find any Industry Type Description / Product Code header block.",
            details={
                "sheet": sheet_name,
                "sample_cells": sample_headers[:40],
                "hint": "Expected headers like 'Industry Type Description' and 'Product Code' "
                "(any casing/spacing). Multi-block side-by-side tables are supported.",
            },
        )

    logger.info(
        "ProductMaster Detected Blocks | sheet={} | count={}",
        sheet_name,
        len(blocks),
    )

    merged: List[dict] = []
    for block in blocks:
        block_rows = _parse_block_rows(rows, block, max_cols=max_cols)
        merged.extend(block_rows)
        logger.info(
            "ProductMaster Block Parsed | sheet={} | cols={}:{} | "
            "header_row={} | rows_imported={} | blanks_skipped={}",
            sheet_name,
            get_column_letter(block.industry_col),
            get_column_letter(block.code_col),
            block.header_row,
            block.rows_imported,
            block.rows_skipped_blank,
        )

    # Dedupe: Industry Type + Product Code (case-insensitive); product_code uniqueness for DB
    seen_combo: set[Tuple[str, str]] = set()
    seen_codes: set[str] = set()
    records: List[dict] = []
    duplicates_ignored = 0

    for row in merged:
        industry = row["industry_type"]
        code = row["product_code"]
        combo = (industry.casefold(), code.casefold())
        code_key = code.casefold()
        if combo in seen_combo or code_key in seen_codes:
            duplicates_ignored += 1
            continue
        seen_combo.add(combo)
        seen_codes.add(code_key)
        records.append(row)

    if not records:
        raise ExcelProcessingError(
            "No valid product rows found (need Industry Type Description + Product Code "
            "with non-empty values under at least one header block)",
            details={"blocks_detected": len(blocks), "sheet": sheet_name},
        )

    logger.info(
        "ProductMaster Merge Complete | sheet={} | blocks={} | "
        "merged_raw={} | duplicates_ignored={} | inserted={}",
        sheet_name,
        len(blocks),
        len(merged),
        duplicates_ignored,
        len(records),
    )
    for i, block in enumerate(blocks, start=1):
        logger.info(
            "ProductMaster Summary | Block {} | Columns {}:{} | Rows Imported {}",
            i,
            get_column_letter(block.industry_col),
            get_column_letter(block.code_col),
            block.rows_imported,
        )
    logger.info("ProductMaster Summary | Total Imported {}", len(records))

    return ProductMasterParseResult(
        records=records,
        duplicates_ignored=duplicates_ignored,
        blocks=blocks,
        sheet_name=sheet_name,
    )
