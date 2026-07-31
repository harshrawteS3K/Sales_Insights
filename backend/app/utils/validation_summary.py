"""Build persisted Excel validation summaries from parser skip messages."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Sequence


def build_validation_summary(
    *,
    expected_rows: int,
    imported_rows: int,
    incomplete_rows: int,
    row_errors: Sequence[str],
    confidence_score: int | None = None,
) -> Dict[str, Any]:
    """
    Aggregate skip reasons into a durable validation summary for a report.

    Does not change import behaviour — only summarizes what the parser already skipped.
    """
    reason_counts: Counter[str] = Counter()
    for msg in row_errors:
        text = str(msg)
        # Messages look like: "Row 3 (excel row 12): Missing Customer; Missing Product"
        reasons_part = text.split(":", 1)[-1] if ":" in text else text
        for chunk in reasons_part.split(";"):
            reason = chunk.strip()
            if not reason:
                continue
            # Normalize common prefixes
            lower = reason.lower()
            if "missing customer" in lower:
                key = "Missing Customer"
            elif "missing product" in lower:
                key = "Missing Product"
            elif "missing quantity" in lower or "invalid quantity" in lower:
                key = "Missing / Invalid Quantity"
            elif "missing sales" in lower or "missing value" in lower:
                key = "Missing Sales Value"
            elif "missing month" in lower or "missing reporting" in lower:
                key = "Missing Month"
            elif "missing segment" in lower:
                key = "Missing Segment"
            elif "missing distributor" in lower:
                key = "Missing Distributor"
            elif "mandatory column" in lower or "missing column" in lower:
                key = "Missing Mandatory Columns"
            elif "opening stock" in lower or "closing stock" in lower:
                key = "Invalid Stock Value"
            elif "invalid" in lower and ("numeric" in lower or "number" in lower or "format" in lower):
                key = "Invalid Numeric / Format"
            elif "blank" in lower or "empty" in lower:
                key = "Blank Rows"
            else:
                key = reason
            reason_counts[key] += 1

    warnings = [
        {"reason": reason, "count": count}
        for reason, count in sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    summary: Dict[str, Any] = {
        "total_rows": int(expected_rows),
        "imported_rows": int(imported_rows),
        "skipped_rows": int(incomplete_rows),
        "warning_count": len(warnings),
        "warnings": warnings,
        "row_errors": list(row_errors)[:100],  # cap stored detail for UI
    }
    if confidence_score is not None:
        summary["confidence_score"] = int(confidence_score)
    return summary


def validation_user_message(summary: Dict[str, Any] | None) -> str | None:
    """Short UI banner text when rows were skipped."""
    if not summary:
        return None
    skipped = int(summary.get("skipped_rows") or 0)
    imported = int(summary.get("imported_rows") or 0)
    warnings = summary.get("warnings") or []
    if skipped <= 0 and not warnings:
        return None
    if skipped > 0:
        return (
            f"Report imported successfully. {skipped} row(s) were skipped because mandatory "
            f"fields were missing or invalid. The remaining {imported} row(s) were imported successfully."
        )
    return "Report imported successfully. Review the validation summary for data quality notes."
