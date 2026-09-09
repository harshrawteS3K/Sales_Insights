"""Configurable ERP header synonym dictionary (JSON source of truth)."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_KEYS = ("customer", "product", "quantity")
MAX_HEADER_LEN = 100

DEFAULT_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "header_dictionary.json"
)


def normalize_header_text(value: Any) -> str:
    """
    Central header normalization for matching and persistence.

    - lowercase
    - trim
    - remove trailing colon(s)
    - collapse whitespace
    - treat ``_`` / ``-`` as spaces; strip other punctuation (keep ``.`` ``/``)
    """
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[:：]+\s*$", "", text).strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s./]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class HeaderDictionary:
    """Thread-safe, in-memory cache over ``header_dictionary.json``."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else DEFAULT_DICTIONARY_PATH
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, List[str]]] = None

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_loaded(self) -> Dict[str, List[str]]:
        with self._lock:
            if self._cache is None:
                self._cache = self._read_file()
            return self._cache

    def _read_file(self) -> Dict[str, List[str]]:
        if not self._path.is_file():
            raise FileNotFoundError(f"Header dictionary not found: {self._path}")
        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return self._normalize_payload(raw, persist_ready=False)

    def _normalize_payload(
        self, raw: Any, *, persist_ready: bool
    ) -> Dict[str, List[str]]:
        if not isinstance(raw, dict):
            raise ValueError("Header dictionary must be a JSON object")

        result: Dict[str, List[str]] = {}
        for key in REQUIRED_KEYS:
            if key not in raw:
                raise ValueError(f"Missing required key: {key}")
            items = raw[key]
            if not isinstance(items, list):
                raise ValueError(f"'{key}' must be a list of strings")
            cleaned: List[str] = []
            seen: set[str] = set()
            for item in items:
                if item is None:
                    raise ValueError(f"'{key}' contains an empty header")
                text = normalize_header_text(item)
                if not text:
                    raise ValueError(f"'{key}' contains an empty header")
                if len(text) > MAX_HEADER_LEN:
                    raise ValueError(
                        f"'{key}' header exceeds {MAX_HEADER_LEN} characters: {text!r}"
                    )
                if text in seen:
                    raise ValueError(f"Duplicate header in '{key}': {text}")
                seen.add(text)
                cleaned.append(text)
            if persist_ready and not cleaned:
                raise ValueError(f"'{key}' must contain at least one header")
            result[key] = cleaned
        return result

    def get_all(self) -> Dict[str, List[str]]:
        data = self._ensure_loaded()
        return {k: list(v) for k, v in data.items()}

    def get_customer_headers(self) -> List[str]:
        return list(self._ensure_loaded()["customer"])

    def get_product_headers(self) -> List[str]:
        return list(self._ensure_loaded()["product"])

    def get_quantity_headers(self) -> List[str]:
        return list(self._ensure_loaded()["quantity"])

    def get_synonyms(self, field: str) -> List[str]:
        data = self._ensure_loaded()
        if field not in data:
            raise KeyError(field)
        return list(data[field])

    def reload(self) -> Dict[str, List[str]]:
        """Force re-read from disk (thread-safe)."""
        with self._lock:
            self._cache = self._read_file()
            return {k: list(v) for k, v in self._cache.items()}

    def update(
        self, payload: Dict[str, List[str]]
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]]]:
        """
        Validate, atomically persist, and refresh cache.

        Returns ``(new_data, added, removed)`` keyed by field.
        """
        cleaned = self._normalize_payload(payload, persist_ready=True)
        with self._lock:
            previous = self._cache if self._cache is not None else self._read_file()
            added: Dict[str, List[str]] = {}
            removed: Dict[str, List[str]] = {}
            for key in REQUIRED_KEYS:
                old_set = set(previous.get(key) or [])
                new_set = set(cleaned[key])
                added[key] = sorted(new_set - old_set)
                removed[key] = sorted(old_set - new_set)

            self._atomic_write(cleaned)
            self._cache = cleaned
            return (
                {k: list(v) for k, v in cleaned.items()},
                added,
                removed,
            )

    def _atomic_write(self, data: Dict[str, List[str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="header_dictionary_",
            suffix=".json",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self._path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


# Process-wide singleton used by the ERP parser and admin API.
_DICTIONARY = HeaderDictionary()


def get_header_dictionary() -> HeaderDictionary:
    return _DICTIONARY


def get_customer_headers() -> List[str]:
    return _DICTIONARY.get_customer_headers()


def get_product_headers() -> List[str]:
    return _DICTIONARY.get_product_headers()


def get_quantity_headers() -> List[str]:
    return _DICTIONARY.get_quantity_headers()


def reload_header_dictionary() -> Dict[str, List[str]]:
    return _DICTIONARY.reload()
