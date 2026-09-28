"""PDF tables to a normalized grid. Text pages are not OCR'd."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.erp_parser.documents.grid import GridSheet, NormalizedGrid
from app.erp_parser.pdf_stock_register import looks_like_pdf_stock_register
from app.exceptions import ExcelProcessingError

logger = get_logger(__name__)


def pdf_to_grid(path: Path) -> NormalizedGrid:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ExcelProcessingError("pdfplumber is not installed") from exc

    sheets: list[GridSheet] = []
    with pdfplumber.open(str(path)) as document:
        for number, page in enumerate(document.pages, start=1):
            plain = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
            if looks_like_pdf_stock_register(plain):
                sheets.append(GridSheet(name=f"Page {number}", rows=[[line] for line in plain]))
                continue
            tables = _page_tables(page)
            if not tables and _needs_ocr(page):
                tables = [_ocr_table(page)]
            if not tables:
                tables = _camelot_tables(path, number)
            if not tables:
                text_rows = _rows_from_words(page)
                if text_rows:
                    tables = [text_rows]
            for table_index, table in enumerate(tables, start=1):
                rows = _clean_table(table)
                if not rows:
                    continue
                name = f"Page {number}" if len(tables) == 1 else f"Page {number} Table {table_index}"
                sheets.append(GridSheet(name=name, rows=rows))
    if not sheets:
        raise ExcelProcessingError(f"No tables found in '{path.name}'")
    return NormalizedGrid(document_type="PDF", sheets=sheets)


def _page_tables(page: Any) -> list[list[list[Any]]]:
    """Ruled tables first, then text-aligned tables. Text pages are not sent to OCR."""
    found = list(page.extract_tables() or [])
    if found:
        return found
    try:
        found = list(
            page.extract_tables(
                table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 4,
                    "join_tolerance": 4,
                }
            )
            or []
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF text table read skipped | err={}", exc)
        return []
    return found


def _rows_from_words(page: Any) -> list[list[Any]]:
    """Group positioned words into a grid when the PDF has no explicit table."""
    try:
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF word read skipped | err={}", exc)
        return []
    if not words:
        return []
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (round(float(item.get("top") or 0), 0), float(item.get("x0") or 0))):
        top = float(word.get("top") or 0)
        if not lines or abs(top - float(lines[-1][0].get("top") or 0)) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    rows: list[list[Any]] = []
    for line in lines:
        ordered = sorted(line, key=lambda item: float(item.get("x0") or 0))
        cells: list[Any] = []
        buffer = ""
        last_x1 = None
        for word in ordered:
            text = str(word.get("text") or "").strip()
            if not text:
                continue
            x0 = float(word.get("x0") or 0)
            if last_x1 is not None and x0 - last_x1 > 14 and buffer:
                cells.append(buffer)
                buffer = text
            else:
                buffer = f"{buffer} {text}".strip()
            last_x1 = float(word.get("x1") or x0)
        if buffer:
            cells.append(buffer)
        if cells:
            rows.append(cells)
    return rows


def _needs_ocr(page: Any) -> bool:
    chars = getattr(page, "chars", None) or []
    images = getattr(page, "images", None) or []
    return not chars and bool(images)


def _ocr_table(page: Any) -> list[list[str]]:
    try:
        import pytesseract
    except ImportError:
        logger.warning("Scanned PDF page skipped | OCR library is not installed")
        return []
    try:
        image = page.to_image(resolution=200).original
        text = pytesseract.image_to_string(image) or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scanned PDF page skipped | err={}", exc)
        return []
    rows = []
    for line in text.splitlines():
        cells = [part.strip() for part in line.split("  ") if part.strip()]
        if cells:
            rows.append(cells)
    return rows


def _camelot_tables(path: Path, page_number: int) -> list[list[list[Any]]]:
    try:
        import camelot
    except ImportError:
        return []
    tables: list[list[list[Any]]] = []
    for flavor in ("lattice", "stream"):
        try:
            found = camelot.read_pdf(str(path), pages=str(page_number), flavor=flavor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Camelot table read skipped | page={} | flavor={} | err={}", page_number, flavor, exc)
            continue
        for table in found:
            frame = getattr(table, "df", None)
            if frame is None:
                continue
            rows = frame.values.tolist()
            if rows:
                tables.append(rows)
        if tables:
            return tables
    return tables


def _clean_table(table: list[list[Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    width = 0
    for raw in table or []:
        cells = [None if cell is None or str(cell).strip() == "" else str(cell).replace("\n", " ").strip() for cell in raw]
        if any(cell is not None for cell in cells):
            rows.append(cells)
            width = max(width, len(cells))
    if not rows:
        return []
    for row in rows:
        if len(row) < width:
            row.extend([None] * (width - len(row)))
    _fill_merged_text(rows)
    return rows


def _fill_merged_text(rows: list[list[Any]]) -> None:
    """Repeat a blank leading label when the rest of the row has values."""
    previous = None
    for row in rows:
        if not row:
            continue
        if row[0] is None and previous is not None and any(cell is not None for cell in row[1:]):
            row[0] = previous
        elif row[0] is not None:
            previous = row[0]
