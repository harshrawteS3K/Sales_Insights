"""Semantic workbook fingerprint. Distributor names are not part of the DNA."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence

from app.erp_parser.workbook_detector import load_workbook_safe

_MONTH = re.compile(
    r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
)
_HEADER_TOKENS = {
    "customer",
    "customer name",
    "party",
    "party name",
    "product",
    "item",
    "qty",
    "quantity",
    "account name",
    "particulars",
}
_KEYWORDS = (
    "APCOTEX",
    "APCOFLEX",
    "QTY",
    "QUANTITY",
    "STOCK ITEM REGISTER",
    "SALES ANALYSIS",
    "CUSTOMER",
    "PRODUCT",
    "PARTY",
    "TOTAL",
)


def _clean(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return " ".join(text.split())


@dataclass
class WorkbookFingerprint:
    sheet_count: int = 0
    merged_cells: int = 0
    header_depth: int = 1
    repeating_month_groups: bool = False
    contains_total_columns: bool = False
    month_headers: List[str] = field(default_factory=list)
    candidate_keywords: List[str] = field(default_factory=list)
    digest: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sheet_count": self.sheet_count,
            "merged_cells": self.merged_cells,
            "header_depth": self.header_depth,
            "repeating_month_groups": self.repeating_month_groups,
            "contains_total_columns": self.contains_total_columns,
            "month_headers": self.month_headers,
            "candidate_keywords": self.candidate_keywords,
        }


def _merged_cell_count(path: Path) -> int:
    workbook = load_workbook_safe(path)
    try:
        total = 0
        for name in workbook.sheetnames:
            sheet = workbook[name]
            ranges = getattr(getattr(sheet, "merged_cells", None), "ranges", None)
            if ranges is None:
                continue
            total += len(list(ranges))
        return total
    finally:
        workbook.close()


def _header_depth(matrix: Sequence[Sequence[Any]]) -> int:
    depth = 0
    for row in matrix[:12]:
        texts = [_clean(cell) for cell in row if _clean(cell)]
        if not texts:
            continue
        headerish = sum(
            1
            for text in texts
            if text.casefold() in _HEADER_TOKENS or _MONTH.search(text) or text.casefold() == "total"
        )
        if headerish >= 2:
            depth += 1
            continue
        if depth:
            break
    return depth or 1


def build_fingerprint(
    path: Path,
    sheets: Sequence[Dict[str, Any]],
    *,
    merged_cells: int | None = None,
) -> WorkbookFingerprint:
    months: List[str] = []
    seen_months: set[str] = set()
    keywords: List[str] = []
    seen_keywords: set[str] = set()
    totals = False
    depth = 1
    for sheet in sheets:
        matrix = sheet.get("matrix") or []
        depth = max(depth, _header_depth(matrix))
        for row in matrix[:40]:
            for cell in row:
                text = _clean(cell)
                if not text:
                    continue
                upper = text.upper()
                if upper in {"TOTAL", "GRAND TOTAL"}:
                    totals = True
                for keyword in _KEYWORDS:
                    if keyword in upper and keyword not in seen_keywords:
                        seen_keywords.add(keyword)
                        keywords.append(keyword.title() if keyword.islower() else keyword)
                match = _MONTH.search(text)
                if match:
                    label = match.group(1)[:3].title()
                    if label not in seen_months:
                        seen_months.add(label)
                        months.append(label)
                    elif label in seen_months:
                        # A second occurrence of a month means repeating product blocks.
                        pass
    month_counts: Dict[str, int] = {}
    for sheet in sheets:
        for row in (sheet.get("matrix") or [])[:40]:
            found = []
            for cell in row:
                match = _MONTH.search(_clean(cell))
                if match:
                    found.append(match.group(1)[:3].title())
            for label in found:
                month_counts[label] = month_counts.get(label, 0) + 1
    repeating = any(count > 1 for count in month_counts.values())
    fingerprint = WorkbookFingerprint(
        sheet_count=len(sheets),
        merged_cells=merged_cells if merged_cells is not None else _merged_cell_count(path),
        header_depth=depth,
        repeating_month_groups=repeating,
        contains_total_columns=totals,
        month_headers=months[:12],
        candidate_keywords=keywords[:12],
    )
    payload = json.dumps(fingerprint.as_dict(), sort_keys=True, separators=(",", ":"))
    fingerprint.digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()
    return fingerprint
