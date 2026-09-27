"""Classify an ERP layout family before a parser is chosen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from app.erp_parser.orchestrator.detector import fingerprint_sheet
from app.erp_parser.orchestrator.fingerprint import WorkbookFingerprint

_LABELS = {
    "metadata": "Sales Analysis Metadata",
    "stock_item_register": "Stock Item Register",
    "product_blocks": "Block Product",
    "cross_product_matrix": "Cross Product Matrix",
    "matrix_month": "Matrix Monthly",
    "header": "Standard Header",
    "unknown": "Future Unknown Layout",
}

_HEADER_KEYWORDS = {"CUSTOMER", "PRODUCT", "QTY", "QUANTITY", "PARTY"}


@dataclass
class LayoutClassification:
    layout_name: str
    parser_name: str
    confidence: float
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "layout_name": self.layout_name,
            "parser_name": self.parser_name,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def _header_signals(fingerprint: WorkbookFingerprint) -> bool:
    found = {item.upper() for item in fingerprint.candidate_keywords}
    identity = bool(found & {"CUSTOMER", "PARTY"})
    product = "PRODUCT" in found
    quantity = bool(found & {"QTY", "QUANTITY"})
    return identity and (product or quantity)


def classify_workbook(
    sheets: Sequence[Dict[str, Any]],
    fingerprint: WorkbookFingerprint,
) -> LayoutClassification:
    """Pick one layout family. Row numbers are not used."""
    best_name = "unknown"
    best_score = 0.0
    best_reason = "No known ERP family matched the workbook fingerprint"
    for sheet in sheets:
        for item in fingerprint_sheet(sheet.get("matrix") or []):
            score = float(item.get("fingerprint_confidence") or 0)
            name = str(item.get("parser_name") or "")
            if name == "header" and score < 90 and _header_signals(fingerprint):
                score = 92.0
                item = {**item, "reason": "Customer, Product, and quantity headers"}
            if score > best_score:
                best_score = score
                best_name = name or "unknown"
                best_reason = str(item.get("reason") or best_reason)
    if best_score < 70:
        return LayoutClassification(
            layout_name=_LABELS["unknown"],
            parser_name="unknown",
            confidence=round(best_score, 1),
            reason=best_reason,
        )
    return LayoutClassification(
        layout_name=_LABELS.get(best_name, _LABELS["unknown"]),
        parser_name=best_name,
        confidence=round(best_score, 1),
        reason=best_reason,
    )


def fingerprint_matched(classification: LayoutClassification) -> bool:
    return classification.parser_name != "unknown" and classification.confidence >= 90
