"""Hand every supported document to the orchestrator as a workbook path."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

from app.erp_parser.documents.detector import detect_document
from app.erp_parser.documents.docx_adapter import docx_to_grid
from app.erp_parser.documents.materialize import materialize_grid
from app.erp_parser.documents.pdf_adapter import pdf_to_grid


def adapter_for(document_type: str) -> str:
    """Adapter name for a detected document. Excel types share one adapter."""
    return {
        "XLSX": "Excel Adapter",
        "XLSM": "Excel Adapter",
        "XLS": "Excel Adapter",
        "PDF": "PDF Adapter",
        "DOCX": "DOCX Adapter",
    }.get((document_type or "").upper(), "Excel Adapter")


@dataclass
class OpenedDocument:
    workbook_path: Path
    document_type: str
    engine: str
    confidence: int
    signature_override: bool
    source_path: Path


@contextmanager
def orchestrator_workbook(path: Union[str, Path]) -> Iterator[OpenedDocument]:
    """Yield the original Excel path, or a temporary grid workbook for PDF and Word."""
    source = Path(path)
    detection = detect_document(source)
    temporary: Path | None = None
    workbook_path = source
    if detection.document_type == "PDF":
        temporary = materialize_grid(pdf_to_grid(source), source_name=source.name)
        workbook_path = temporary
    elif detection.document_type == "DOCX":
        temporary = materialize_grid(docx_to_grid(source), source_name=source.name)
        workbook_path = temporary
    try:
        yield OpenedDocument(
            workbook_path=workbook_path,
            document_type=detection.document_type,
            engine=detection.engine,
            confidence=detection.confidence,
            signature_override=detection.signature_override,
            source_path=source,
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
