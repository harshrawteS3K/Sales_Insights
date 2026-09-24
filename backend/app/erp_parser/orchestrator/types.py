"""Shared result shape for every ERP parser candidate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParserResult:
    """One parser's extraction, scored independently of success/fail."""

    rows: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    parser_name: str = ""
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    extracted: Dict[str, Any] = field(default_factory=dict)
    mapped: Dict[str, Any] = field(default_factory=dict)
    sheet_name: str = ""
    header_row: int = 1
    sheet_score: float = 0.0
    llm_used: bool = False
    llm_tokens: int = 0
    llm_reason: str = ""

    @property
    def strategy(self) -> str:
        return self.parser_name
