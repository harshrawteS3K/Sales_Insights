"""Deterministic ERP extraction accuracy (no LLM).

Accuracy = how correctly the full workbook was mapped and extracted.
Same number everywhere (list, preview, import). Not a separate 'confidence'.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


def _band(score: float) -> str:
    if score >= 90:
        return "green"
    if score >= 75:
        return "yellow"
    return "red"


def compute_erp_confidence(
    *,
    field_confidences: Mapping[str, float],
    sheet_score: float,
    extracted_rows: int,
    quantity_ok: int,
    quantity_fail: int,
    skipped_invalid: int,
) -> Dict[str, Any]:
    """
    Single Accuracy score (0–100) for the complete Excel file.

    - 75% column-mapping quality (Customer / Product / Sales Quantity)
    - 25% row extraction success across the whole file

    ``sheet_score`` is retained for diagnostics only — it does **not** swing
    the published Accuracy (that caused 76% vs 99% flicker).
    """
    cust = float(field_confidences.get("customer") or 0)
    prod = float(field_confidences.get("product") or 0)
    qty = float(field_confidences.get("quantity") or 0)

    mapping_accuracy = (cust + prod + qty) / 3.0

    attempted = max(0, int(extracted_rows) + int(skipped_invalid))
    if attempted <= 0:
        coverage = 0.0
    else:
        coverage = 100.0 * (int(extracted_rows) / attempted)

    # Prefer quantity_ok signal when present (monthly pivot / parse path)
    qty_attempts = int(quantity_ok) + int(quantity_fail)
    if qty_attempts > 0:
        qty_coverage = 100.0 * (int(quantity_ok) / qty_attempts)
        coverage = (coverage + qty_coverage) / 2.0

    overall = round(0.75 * mapping_accuracy + 0.25 * coverage, 1)
    overall = max(0.0, min(100.0, overall))

    # Soft-cap if a required field is weakly mapped
    if cust < 50 or prod < 50 or qty < 50:
        overall = min(overall, 74.0)

    if extracted_rows <= 0:
        overall = min(overall, 40.0)

    components = {
        "mapping_accuracy": round(mapping_accuracy, 2),
        "file_coverage": round(coverage, 2),
        # Kept for older UI/diagnostics; not used in overall
        "sheet_detection": round(min(100.0, max(0.0, float(sheet_score))), 2),
    }

    return {
        # Canonical published score (Accuracy)
        "overall_confidence": overall,
        "accuracy": overall,
        "customer_confidence": round(cust, 1),
        "product_confidence": round(prod, 1),
        "quantity_confidence": round(qty, 1),
        "band": _band(overall),
        "components": components,
        "weights": {
            "mapping_accuracy": 75,
            "file_coverage": 25,
        },
    }


# Alias — Accuracy is the product term; confidence is legacy API naming.
compute_erp_accuracy = compute_erp_confidence
