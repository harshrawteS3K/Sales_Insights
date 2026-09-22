"""File system helpers for uploads and downloads."""

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from app.constants import ALLOWED_EXCEL_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES
from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions import ValidationAppError

logger = get_logger(__name__)


def ensure_dir(path: Path | str) -> Path:
    """Create directory if missing and return Path."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def validate_excel_filename(filename: str) -> str:
    """Validate that a filename has an allowed Excel extension (.xlsx or .xlsm)."""
    if not filename:
        raise ValidationAppError("Filename is required")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXCEL_EXTENSIONS:
        raise ValidationAppError(
            f"Unsupported file type '{extension}'. Allowed: .xlsx, .xlsm, .xls"
        )
    return extension


def cleanup_upload(path: Path | str | None, *, reason: str = "processed") -> None:
    """Best-effort delete of a temporary upload file (never raises)."""
    if not path:
        return
    target = Path(path)
    try:
        if target.is_file():
            target.unlink(missing_ok=True)
            logger.info("Cleaned up upload file | path={} | reason={}", target.name, reason)
    except OSError as exc:
        logger.warning("Failed to clean up upload file | path={} | error={}", target, exc)


async def save_upload_file(upload: UploadFile, destination_dir: Path | str) -> Path:
    """Persist an uploaded file under destination_dir and return the path."""
    validate_excel_filename(upload.filename or "")
    target_dir = ensure_dir(destination_dir)
    unique_name = f"{uuid.uuid4().hex}_{Path(upload.filename or 'upload.xlsx').name}"
    target_path = target_dir / unique_name

    size = 0
    with target_path.open("wb") as buffer:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE_BYTES:
                buffer.close()
                target_path.unlink(missing_ok=True)
                raise ValidationAppError(
                    f"File exceeds maximum upload size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB"
                )
            buffer.write(chunk)

    await upload.seek(0)
    logger.info("Saved upload {} ({} bytes) to {}", upload.filename, size, target_path)
    return target_path


def save_bytes(data: bytes, destination_dir: Path | str, filename: str) -> Path:
    """Write raw bytes to destination_dir/filename."""
    validate_excel_filename(filename)
    target_dir = ensure_dir(destination_dir)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    target_path = target_dir / unique_name
    target_path.write_bytes(data)
    logger.info("Saved bytes file {} ({} bytes)", target_path, len(data))
    return target_path


def copy_stream(source: BinaryIO, destination: Path) -> int:
    """Copy a binary stream to destination and return bytes written."""
    ensure_dir(destination.parent)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(source, buffer)
        return destination.stat().st_size


def get_upload_subdir(kind: str) -> Path:
    """Resolve a named upload subdirectory."""
    mapping = {
        "master": Path(settings.upload_dir) / "master",
        "reports": Path(settings.upload_dir) / "reports",
        "attachments": Path(settings.upload_dir) / "attachments",
        "temp_imports": Path(settings.upload_dir) / "temp_imports",
        "imports": Path(settings.upload_dir) / "imports",
    }
    target = mapping.get(kind, Path(settings.upload_dir) / kind)
    return ensure_dir(target)
