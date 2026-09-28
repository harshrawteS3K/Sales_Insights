"""Normalized grid shared by Excel, PDF, and Word adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GridSheet:
    name: str
    rows: list[list[Any]] = field(default_factory=list)
    merged: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass
class NormalizedGrid:
    """Row/column values plus the sheet or page name. Parsers never see the source type."""

    document_type: str
    sheets: list[GridSheet] = field(default_factory=list)

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    @property
    def table_count(self) -> int:
        return sum(1 for sheet in self.sheets if sheet.rows)
