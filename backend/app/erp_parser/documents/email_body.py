"""Turn an Outlook email body into the same grid Excel already uses.

HTML tables and flattened Outlook markup are both accepted. A business-matrix
detector looks for month columns, a product line, customer names, and a
numeric grid. The LLM never extracts rows.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Sequence

from app.erp_parser.documents.grid import GridSheet, NormalizedGrid
from app.erp_parser.header_dictionary import normalize_header_text
from app.erp_parser.header_mapper import is_month_header

SHEET_NAME = "Email Body"
LLM_MARK = "__llm__"
_SEPARATOR_RE = re.compile(r"^[\s|:\-]+$")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_BLOCK_TAGS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}
# Product families and grade codes. Not limited to one SKU.
_PRODUCT_RE = re.compile(
    r"(?ix)(?:"
    r"\bapcotex\b"
    r"|\b(?:sr|tx|hsr|nvc|nbr)[-\s]?\d{2,4}\b"
    r"|\b(?:nbr|latex)\b"
    r"|\b[A-Za-z]{2,8}[-\s]\d{2,4}\b"
    r")"
)
_CUSTOMER_RE = re.compile(
    r"(?ix)\b(?:"
    r"m\s*/\s*s\.?"
    r"|pvt\.?\s*ltd"
    r"|private\s+limited"
    r"|limited"
    r"|ltd"
    r"|industries"
    r"|corporation"
    r"|traders"
    r"|fabrics?"
    r"|textiles?"
    r")\b"
)


def extract_email_body_grid(html: str = "", text: str = "") -> Optional[NormalizedGrid]:
    """Return one sheet named ``Email Body``, or None when no sales matrix exists."""
    best_rows: Optional[List[List[str]]] = None
    best_score = -1
    best_placed = -1
    llm_used = False
    for rows in _candidate_grids(html, text):
        score = business_matrix_score(rows)
        placed = _products_with_customers(rows)
        if score > best_score or (score == best_score and placed > best_placed):
            best_rows = rows
            best_score = score
            best_placed = placed
    if best_rows is None or best_score < 80:
        assisted = _llm_layout_rows(html, text, best_rows)
        if assisted:
            assisted_score = business_matrix_score(assisted)
            if assisted_score >= best_score:
                best_rows = assisted
                best_score = assisted_score
                llm_used = True
    if not best_rows or best_score < 80 or not _has_month_row(best_rows):
        return None
    if llm_used:
        best_rows = _mark_llm(best_rows)
    return NormalizedGrid(
        document_type="Email Body",
        sheets=[GridSheet(name=SHEET_NAME, rows=best_rows)],
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


def business_matrix_score(rows: Sequence[Sequence[str]]) -> int:
    """0–100 from month columns, a product line, customers, and a numeric grid."""
    if not rows:
        return 0
    months = _month_count(rows)
    product = any(_is_product_text(_row_label(row)) for row in rows)
    customers = _customer_hits(rows)
    numbers = _numeric_cells(rows)
    score = 0
    if months >= 2:
        score += 30
    if product:
        score += 25
    if customers >= 1:
        score += 25
    if numbers >= 4:
        score += 20
    elif numbers >= 2:
        score += 10
    return score


def _products_with_customers(rows: Sequence[Sequence[str]]) -> int:
    """Product banners that are followed by a quantity row, in document order."""
    placed = 0
    for index, row in enumerate(rows):
        label = _row_label(row)
        if not _is_product_text(label) or _numeric_cells([row]) > 0:
            continue
        if any(_numeric_cells([later]) >= 2 for later in rows[index + 1 : index + 12]):
            placed += 1
    return placed


def _candidate_grids(html: str, text: str) -> List[List[List[str]]]:
    found: List[List[List[str]]] = []
    if (html or "").strip():
        table_rows = _rows_from_html_tables(html)
        if table_rows:
            found.append(table_rows)
        flat_rows = _rows_from_text("\n".join(_flatten_html_lines(html)))
        if flat_rows:
            found.append(flat_rows)
    if (text or "").strip():
        text_rows = _rows_from_text(text)
        if text_rows:
            found.append(text_rows)
    return found


def _rows_from_html_tables(html: str) -> Optional[List[List[str]]]:
    if "<table" not in (html or "").lower():
        return None
    soup = _soup(html)
    if soup is None:
        return None
    rows: List[List[str]] = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [
                _clean_cell(cell.get_text(" ", strip=True))
                for cell in tr.find_all(["td", "th"])
            ]
            if any(cells):
                rows.append(cells)
        if table.find_next_sibling() is None:
            continue
    # Product banners that sit between tables are not inside tr/td.
    outside = _flatten_html_lines(html, skip_tables=True)
    if outside:
        extra = _rows_from_text("\n".join(outside)) or []
        if extra:
            rows = _merge_outside_lines(rows, extra)
    return rows or None


def _merge_outside_lines(table_rows: List[List[str]], outside: List[List[str]]) -> List[List[str]]:
    """Keep table order and append product lines that were not already captured."""
    seen = {_row_label(row).casefold() for row in table_rows if _row_label(row)}
    merged = list(table_rows)
    for row in outside:
        label = _row_label(row)
        if label and label.casefold() not in seen and _is_product_text(label) and _numeric_cells([row]) == 0:
            merged.append(row)
            seen.add(label.casefold())
    return merged


def _flatten_html_lines(html: str, *, skip_tables: bool = False) -> List[str]:
    """One visual row per block. Spans inside a row stay on that row."""
    soup = _soup(html)
    if soup is None:
        return []
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    lines: List[str] = []

    def walk(node: object) -> None:
        for child in list(getattr(node, "children", []) or []):
            name = getattr(child, "name", None)
            if name in {"script", "style"}:
                continue
            if name == "table":
                if skip_tables:
                    continue
                for tr in child.find_all("tr"):
                    cells = [
                        _clean_cell(cell.get_text(" ", strip=True))
                        for cell in tr.find_all(["td", "th"])
                    ]
                    if any(cells):
                        lines.append("\t".join(cells))
                continue
            if name == "br":
                lines.append("")
                continue
            if name in _BLOCK_TAGS:
                if _has_block_child(child):
                    walk(child)
                else:
                    text = _clean_cell(child.get_text(" ", strip=True))
                    if text:
                        lines.append(text)
                continue
            if name:
                walk(child)
            else:
                text = _clean_cell(str(child))
                if text:
                    lines.append(text)

    walk(soup.body or soup)
    return [line for line in lines if line.strip()]


def _has_block_child(tag: object) -> bool:
    for child in getattr(tag, "children", []) or []:
        name = getattr(child, "name", None)
        if name in _BLOCK_TAGS or name in {"table", "br"}:
            return True
    return False


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    return BeautifulSoup(html or "", "html.parser")


def _rows_from_text(text: str) -> Optional[List[List[str]]]:
    lines = []
    for raw in (text or "").replace("\xa0", " ").splitlines():
        line = raw.strip()
        if not line or _SEPARATOR_RE.match(line):
            continue
        if line.startswith("**") and line.endswith("**"):
            line = line.strip("*").strip()
        lines.append(line)
    if not lines:
        return None
    rows = _assemble_rows(lines)
    return rows or None


def _assemble_rows(lines: Sequence[str]) -> List[List[str]]:
    """Align pipe, tab, and space tables, then stack Outlook's one-cell-per-line markup."""
    month_count = 0
    for line in lines:
        cells = _split_line(line, month_count=0)
        hits = sum(1 for cell in cells if _is_month(cell))
        if hits >= 2:
            month_count = hits
            break
    pieces: List[List[str]] = []
    loose: List[str] = []

    def flush_loose() -> None:
        if loose:
            pieces.extend(_group_loose_tokens(loose))
            loose.clear()

    for line in lines:
        cells = _split_line(line, month_count=month_count)
        month_hits = sum(1 for cell in cells if _is_month(cell))
        number_hits = sum(1 for cell in cells if _is_number(cell))
        if len(cells) >= 2 and (month_hits >= 2 or number_hits >= 2):
            flush_loose()
            pieces.append(cells)
        elif len(cells) == 1:
            loose.append(cells[0])
        elif cells:
            flush_loose()
            pieces.append(cells)
    flush_loose()
    return pieces


def _group_loose_tokens(tokens: Sequence[str]) -> List[List[str]]:
    """Join a vertical month run or quantity run back onto the label above it."""
    rows: List[List[str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _is_month(token):
            start = index
            while index < len(tokens) and _is_month(tokens[index]):
                index += 1
            months = list(tokens[start:index])
            if len(months) >= 2 and rows and len(rows[-1]) == 1:
                rows[-1] = [rows[-1][0], *months]
            else:
                rows.append(months)
            continue
        if _is_number(token):
            start = index
            while index < len(tokens) and _is_number(tokens[index]):
                index += 1
            numbers = list(tokens[start:index])
            if len(numbers) >= 2 and rows and len(rows[-1]) == 1:
                rows[-1] = [rows[-1][0], *numbers]
            else:
                rows.append(numbers)
            continue
        rows.append([token])
        index += 1
    return rows


def _split_line(line: str, *, month_count: int) -> List[str]:
    if "\t" in line:
        return [_clean_cell(part) for part in line.split("\t")]
    if "|" in line:
        return [_clean_cell(part) for part in line.strip().strip("|").split("|")]
    tokens = line.split()
    months: List[str] = []
    working = list(tokens)
    while working and _is_month(working[-1]):
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


def _llm_layout_rows(
    html: str,
    text: str,
    rows: Optional[List[List[str]]],
) -> Optional[List[List[str]]]:
    """Ask for column layout only when the deterministic score is below 80.

    The model returns header positions. Python still builds every quantity row.
    """
    preview_rows = rows or _rows_from_text(text or "") or []
    if _month_count(preview_rows) < 2 and not _month_count_in_text(html or text):
        return None
    sample = preview_rows[:15]
    months = _month_labels(sample)
    payload = {
        "extracted_text": (text or _visible_text(html))[:4000],
        "header_candidates": sample[:5],
        "first_rows": sample,
        "month_candidates": months,
    }
    system = (
        "Classify an email sales matrix. Return JSON only. "
        "Do not list customers or quantities. "
        '{"layout_type":"cross_product_matrix","customer_column":0,'
        '"product_header_row":1,"month_columns":["Apr","May","Jun"]}'
    )
    try:
        from app.llm.bedrock_client import complete
        from app.llm.model_registry import default_model

        completion = complete(
            system=system,
            user=json.dumps(payload),
            model_id=default_model().display_name,
            timeout=8,
            reason="email body layout",
        )
        meta = _json_object(completion.text)
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    month_columns = [str(item).strip() for item in (meta.get("month_columns") or []) if str(item).strip()]
    if len(month_columns) < 2 or not preview_rows:
        return None
    customer_column = int(meta.get("customer_column") or 0)
    return _apply_layout(preview_rows, customer_column, month_columns)


def _apply_layout(
    rows: Sequence[Sequence[str]],
    customer_column: int,
    month_columns: Sequence[str],
) -> List[List[str]]:
    """Rebuild a grid from layout metadata. Values stay in the original cells."""
    aligned: List[List[str]] = []
    for row in rows:
        cells = [_clean_cell(cell) for cell in row]
        if not any(cells):
            continue
        month_hits = [cell for cell in cells if _is_month(cell)]
        if len(month_hits) >= 2:
            label = cells[customer_column] if customer_column < len(cells) else ""
            aligned.append([label, *month_columns])
            continue
        aligned.append(cells)
    return aligned


def _json_object(raw: str) -> Optional[dict]:
    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _visible_text(html: str) -> str:
    return "\n".join(_flatten_html_lines(html))


def _mark_llm(rows: List[List[str]]) -> List[List[str]]:
    if not rows:
        return rows
    marked = [list(row) for row in rows]
    marked[0] = [*marked[0], LLM_MARK]
    return marked


def _has_month_row(rows: Sequence[Sequence[str]]) -> bool:
    return _month_count(rows) >= 2


def _month_count(rows: Sequence[Sequence[str]]) -> int:
    best = 0
    for row in rows[:20]:
        hits = sum(1 for cell in row if _is_month(cell))
        if hits > best:
            best = hits
    return best


def _month_labels(rows: Sequence[Sequence[str]]) -> List[str]:
    for row in rows[:20]:
        labels = [_clean_cell(cell) for cell in row if _is_month(cell)]
        if len(labels) >= 2:
            return labels
    return []


def _month_count_in_text(raw: str) -> bool:
    hits = sum(1 for token in re.split(r"\s+", raw or "") if _is_month(token))
    return hits >= 2


def _customer_hits(rows: Sequence[Sequence[str]]) -> int:
    count = 0
    for row in rows:
        label = _row_label(row)
        if not label or _is_month(label):
            continue
        if _numeric_cells([row]) < 1:
            continue
        if _CUSTOMER_RE.search(label) or _numeric_cells([row]) >= 2:
            count += 1
    return count


def _numeric_cells(rows: Sequence[Sequence[str]]) -> int:
    return sum(1 for row in rows for cell in row if _is_number(cell))


def _row_label(row: Sequence[str]) -> str:
    for cell in row:
        text = _clean_cell(cell)
        if text and not _is_month(text) and not _is_number(text) and text != LLM_MARK:
            return text
    return ""


def _is_product_text(value: str) -> bool:
    return bool(value and _PRODUCT_RE.search(value))


def _is_month(value: object) -> bool:
    return is_month_header(normalize_header_text(value))


def _is_number(value: object) -> bool:
    return bool(_NUMBER_RE.match(_clean_cell(value).replace(" ", "")))


def _clean_cell(value: object) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"[*]+", "", text)
    return re.sub(r"\s+", " ", text).strip()
