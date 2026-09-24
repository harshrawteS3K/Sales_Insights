"""Weighted confidence for orchestrator decisions. Does not replace field diagnostics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence


def _qty_ok(row: Dict[str, Any]) -> bool:
    raw = row.get("sales_quantity", row.get("quantity"))
    if raw is None or raw == "":
        return False
    try:
        return isinstance(raw, (int, float, Decimal)) or Decimal(str(raw)) == Decimal(str(raw))
    except Exception:  # noqa: BLE001
        return False


def score_extraction(
    rows: Sequence[Dict[str, Any]],
    *,
    distributor_label: str = "",
    reporting_quarter: Optional[str] = None,
) -> float:
    """
    Customer 25, Product 25, numeric quantity 20, quarter 15, distributor 15.

    95–100 auto accept, 90–94 accept with warning, 70–89 LLM, below 70 human review.
    """
    if not rows:
        return 0.0
    total = len(rows)
    customers = sum(1 for row in rows if str(row.get("customer_name") or "").strip())
    products = sum(1 for row in rows if str(row.get("product") or "").strip())
    quantities = sum(1 for row in rows if _qty_ok(row))
    quarters = sum(1 for row in rows if str(row.get("period") or row.get("reporting_quarter") or "").strip())
    if quarters == 0 and (reporting_quarter or "").strip():
        quarters = total
    distributor_hit = 1.0 if (distributor_label or "").strip() else 0.0
    score = (
        25.0 * (customers / total)
        + 25.0 * (products / total)
        + 20.0 * (quantities / total)
        + 15.0 * (quarters / total)
        + 15.0 * distributor_hit
    )
    return round(max(0.0, min(100.0, score)), 1)


def decision_band(score: float) -> str:
    if score >= 95:
        return "auto_accept"
    if score >= 90:
        return "accept_warning"
    if score >= 70:
        return "llm"
    return "human_review"


def apply_score(result: Any, **kwargs: Any) -> Any:
    result.confidence = score_extraction(result.rows, **kwargs)
    band = decision_band(result.confidence)
    if band == "accept_warning":
        result.warnings.append("Accepted with warning. Confidence is between 90 and 94.")
    elif band == "human_review":
        result.warnings.append("Human review required. Confidence is below 70.")
    return result
