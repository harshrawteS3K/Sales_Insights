"""Detect document type from magic bytes, then MIME. The filename is not trusted."""

from __future__ import annotations

import mimetypes
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from app.core.logging import get_logger

logger = get_logger(__name__)

_PDF_MAGIC = b"%PDF"
_OLE_MAGIC = bytes.fromhex("D0CF11E0")
_ZIP_MAGIC = b"PK"

_EXT_FOR_TYPE = {
    "XLSX": {".xlsx"},
    "XLSM": {".xlsm"},
    "XLS": {".xls"},
    "PDF": {".pdf"},
    "DOCX": {".docx"},
}

_MIME_TYPE = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.ms-excel.sheet.macroenabled.12": "XLSM",
    "application/vnd.ms-excel": "XLS",
    "application/excel": "XLS",
}

_ENGINE = {
    "XLSX": "openpyxl",
    "XLSM": "openpyxl",
    "XLS": "xlrd",
    "PDF": "pdfplumber",
    "DOCX": "python-docx",
}


@dataclass(frozen=True)
class DocumentDetection:
    document_type: str
    engine: str
    confidence: int
    signature_override: bool
    extension: str


def detect_document(path: Union[str, Path]) -> DocumentDetection:
    """Return type, engine, and confidence. Magic bytes win over the extension."""
    file_path = Path(path)
    extension = file_path.suffix.lower()
    kind, confidence = _from_signature(file_path)
    if kind is None:
        kind = _MIME_TYPE.get(_mime(file_path, extension), "")
        confidence = 70 if kind else 0
    if not kind:
        raise ValueError(f"Unsupported document '{file_path.name}'")
    override = extension not in _EXT_FOR_TYPE.get(kind, set()) and bool(extension)
    status = "Signature Override" if override else "Matched"
    logger.info(
        "File: {}\nExtension: {}\nDetected: {}\nEngine: {}\nStatus: {}",
        file_path.name,
        extension or "(none)",
        kind,
        _ENGINE[kind],
        status,
    )
    return DocumentDetection(
        document_type=kind,
        engine=_ENGINE[kind],
        confidence=confidence,
        signature_override=override,
        extension=extension,
    )


def _from_signature(path: Path) -> tuple[str | None, int]:
    with path.open("rb") as handle:
        signature = handle.read(8)
    if signature.startswith(_PDF_MAGIC):
        return "PDF", 99
    if signature.startswith(_OLE_MAGIC):
        return "XLS", 99
    if signature.startswith(_ZIP_MAGIC):
        return _zip_kind(path), 99
    return None, 0


def _zip_kind(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return "DOCX"
    if any(name.startswith("xl/") for name in names):
        if "xl/vbaProject.bin" in names:
            return "XLSM"
        return "XLSX"
    return None


def _mime(path: Path, extension: str) -> str:
    guessed, _encoding = mimetypes.guess_type(path.name)
    return (guessed or "").lower()
