"""Turn an Outlook email body into the same grid Excel already uses.

HTML tables are read with BeautifulSoup. Plain aligned text is the fallback.
The LLM never sees these rows.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from app.erp_parser.documents.grid import GridSheet, NormalizedGrid
from app.erp_parser.header_dictionary import normalize_header_text
from app.erp_parser.header_mapper import is_month_header

SHEET_NAME = "Email Body"
_SEPARATOR_RE = re.compile(r"^[\s|:\-]+$")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


def extract_email_body_grid(html: str = "", text: str = "") -> Optional[NormalizedGrid]:
    """Return one sheet named ``Email Body``, or None when no month table exists."""
    rows = _rows_from_html(html) if (html or "").strip() else None
    if not rows:
        plain = text or ""
        if not plain.strip() and html:
            plain = _html_to_text(html)
        rows = _rows_from_text(plain)
    if not rows or not _has_month_row(rows):
        return None
    return NormalizedGrid(
        document_type="Email Body",
        sheets=[GridSheet(name=SHEET_NAME, rows=rows)],
    )


def email_body_workbook_bytes(html: str = "", text: str = "") -> Optional[bytes]:
    """Materialize the body grid as xlsx bytes for the existing attachment path."""
    from app.erp_parser.documents.materialize import materialize_grid

    grid = extract_email_body_grid(html, text)
    if grid is None:
        return None
    path = materialize_grid(grid, source_name="Email Body.xlsx")
    try:
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _rows_from_html(html: str) -> Optional[List[List[str]]]:
    if "<table" not in (html or "").lower():
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    rows: List[List[str]] = []

    def walk(node: object) -> None:
        for child in getattr(node, "children", []):
            name = getattr(child, "name", None)
            if name == "table":
                rows.extend(_table_rows(child))
            elif name in {"script", "style"}:
                continue
            elif name:
                walk(child)
            else:
                text = _clean_cell(str(child))
                if text:
                    rows.append([text])

    walk(soup.body or soup)
    if not _has_month_row(rows):
        return None
    return rows


def _table_rows(table: object) -> List[List[str]]:
    rows: List[List[str]] = []
    for tr in table.find_all("tr"):  # type: ignore[attr-defined]
        cells = [_clean_cell(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html or "")
    return BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)


def _rows_from_text(text: str) -> Optional[List[List[str]]]:
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or _SEPARATOR_RE.match(line):
            continue
        if line.startswith("**") and line.endswith("**"):
            line = line.strip("*").strip()
        lines.append(line)
    if not lines:
        return None
    month_count = 0
    for line in lines:
        cells = _split_line(line, month_count=0)
        hits = sum(1 for cell in cells if is_month_header(normalize_header_text(cell)))
        if hits >= 2:
            month_count = hits
            break
    return [_split_line(line, month_count=month_count) for line in lines]


def _split_line(line: str, *, month_count: int) -> List[str]:
    if "|" in line:
        return [_clean_cell(part) for part in line.strip().strip("|").split("|")]
    tokens = line.split()
    months: List[str] = []
    working = list(tokens)
    while working and is_month_header(normalize_header_text(working[-1])):
        months.insert(0, working.pop())
    if len(months) >= 2:
        label = " ".join(working).strip()
        return [label, *months] if label else months
    nums: List[str] = []
    working = list(tokens)
    while working and _NUMBER_RE.match(working[-1].replace(" ", "")):
        nums.insert(0, working.pop())
    if nums and (len(nums) == month_count or (month_count == 0 and len(nums) >= 2)):
        return [" ".join(working).strip(), *nums]
    return [_clean_cell(line)]


def _has_month_row(rows: Sequence[Sequence[str]]) -> bool:
    for row in rows[:20]:
        hits = sum(1 for cell in row if is_month_header(normalize_header_text(cell)))
        if hits >= 2:
            return True
    return False


def _clean_cell(value: object) -> str:
    text = re.sub(r"[*]+", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()
