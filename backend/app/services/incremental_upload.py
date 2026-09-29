"""Row-level comparison of a parsed upload against consolidated sales.

Identity is distributor, customer, product, transaction date, and financial year.
Quantity is not part of the identity. It only distinguishes an exact copy from
a modification. Outlook Sync does not call this module.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.utils.period_calendar import fy_short_display, parse_quarter_label

logger = get_logger(__name__)

NEW = "new"
EXACT = "exact"
MODIFIED = "modified"
REPLACE = "replace"
KEEP = "keep"
ADD = "add"
_ACTIONS = {REPLACE, KEEP, ADD}


def financial_year_of(period: str) -> str:
    spec = parse_quarter_label(period or "")
    if spec and spec.year:
        return fy_short_display(spec.year)
    return (period or "").strip()


def transaction_date_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("source_month")
        or row.get("transaction_date")
        or row.get("period")
        or ""
    ).strip()


def _qty(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0)).quantize(Decimal("0.001"))
    except Exception:
        return Decimal("0.000")


def _identity(customer: str, product: str, when: str, financial_year: str) -> tuple:
    return (
        customer.strip().casefold(),
        product.strip().casefold(),
        when.strip().casefold(),
        financial_year.strip().casefold(),
    )


def load_existing(db: Session, distributor_id: int) -> List[Dict[str, Any]]:
    """Active consolidated rows for one distributor. Historical reports stay in place."""
    rows = db.execute(
        select(
            SalesRecord.id,
            SalesRecord.customer_name,
            SalesRecord.product,
            SalesRecord.quantity,
            SalesRecord.source_month,
            SalesRecord.period,
        )
        .join(Report, Report.id == SalesRecord.report_id)
        .where(
            SalesRecord.is_deleted.is_(False),
            Report.is_deleted.is_(False),
            SalesRecord.distributor_id == distributor_id,
        )
    ).all()
    loaded: List[Dict[str, Any]] = []
    for record_id, customer, product, quantity, source_month, period in rows:
        loaded.append(
            {
                "id": int(record_id),
                "customer_name": customer or "",
                "product": product or "",
                "quantity": quantity,
                "source_month": source_month or "",
                "period": period or "",
            }
        )
    return loaded


def analyse_rows(
    incoming: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Classify every incoming row. Modified rows are the only ones returned in full."""
    index: Dict[tuple, Dict[str, Any]] = {}
    for row in existing:
        period = str(row.get("period") or "")
        key = _identity(
            str(row.get("customer_name") or ""),
            str(row.get("product") or ""),
            transaction_date_of(row),
            financial_year_of(period),
        )
        current = index.get(key)
        if current is None or int(row.get("id") or 0) >= int(current.get("id") or 0):
            index[key] = dict(row)

    classified: List[Dict[str, Any]] = []
    modified_rows: List[Dict[str, Any]] = []
    for offset, row in enumerate(incoming):
        customer = str(row.get("customer_name") or row.get("customer") or "").strip()
        product = str(row.get("product") or "").strip()
        period = str(row.get("period") or row.get("reporting_quarter") or "").strip()
        when = transaction_date_of(row)
        incoming_qty = _qty(row.get("sales_quantity") if row.get("sales_quantity") is not None else row.get("quantity"))
        key = _identity(customer, product, when, financial_year_of(period))
        found = index.get(key)
        if found is None:
            kind = NEW
            existing_qty = None
            existing_id = None
        else:
            existing_qty = _qty(found.get("quantity"))
            existing_id = int(found["id"])
            kind = EXACT if existing_qty == incoming_qty else MODIFIED
        item = {
            "row_index": offset,
            "kind": kind,
            "customer": customer,
            "product": product,
            "date": when or period,
            "period": period,
            "existing_id": existing_id,
            "existing_qty": float(existing_qty) if existing_qty is not None else None,
            "incoming_qty": float(incoming_qty),
        }
        classified.append(item)
        if kind == MODIFIED and existing_qty is not None:
            modified_rows.append(
                {
                    "row_index": offset,
                    "customer": customer,
                    "product": product,
                    "date": when or period,
                    "existing_qty": float(existing_qty),
                    "incoming_qty": float(incoming_qty),
                    "difference": float(incoming_qty - existing_qty),
                    "existing_id": existing_id,
                }
            )

    new_count = sum(1 for item in classified if item["kind"] == NEW)
    exact_count = sum(1 for item in classified if item["kind"] == EXACT)
    modified_count = len(modified_rows)
    if modified_count:
        status = "human_review"
        recommendation = (
            f"Import {new_count} new records. "
            f"Skip {exact_count} duplicates. "
            f"Review {modified_count} modified rows."
        )
    elif new_count == 0 and exact_count:
        status = "duplicate_upload"
        recommendation = "Duplicate upload. No records will be inserted."
    else:
        status = "ready"
        recommendation = (
            f"Import {new_count} new records. Skip {exact_count} duplicates."
        )
    payload = {
        "analysed": len(classified),
        "new_count": new_count,
        "exact_count": exact_count,
        "modified_count": modified_count,
        "status": status,
        "recommendation": recommendation,
        "modified_rows": modified_rows,
        "rows": classified,
    }
    logger.info(
        "Incremental analysis | analysed={} | new={} | exact={} | modified={} | status={}",
        payload["analysed"],
        new_count,
        exact_count,
        modified_count,
        status,
    )
    return payload


def decision_map(decisions: Optional[Iterable[Mapping[str, Any]]]) -> Dict[int, str]:
    mapped: Dict[int, str] = {}
    for item in decisions or []:
        try:
            index = int(item.get("row_index"))
        except (TypeError, ValueError):
            continue
        action = str(item.get("action") or "").strip().lower()
        if action in _ACTIONS:
            mapped[index] = action
    return mapped


def needs_review(plan: Mapping[str, Any], decisions: Optional[Iterable[Mapping[str, Any]]]) -> bool:
    """True when a modified row has no Replace, Keep, or Add decision."""
    chosen = decision_map(decisions)
    for row in plan.get("modified_rows") or []:
        if chosen.get(int(row["row_index"])) not in _ACTIONS:
            return True
    return False


def rows_for_insert(
    incoming: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    decisions: Optional[Iterable[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """New rows, plus modified rows the reviewer chose to add as a new version."""
    chosen = decision_map(decisions)
    selected: List[Dict[str, Any]] = []
    for item in plan.get("rows") or []:
        kind = item["kind"]
        index = int(item["row_index"])
        if kind == NEW:
            selected.append(dict(incoming[index]))
        elif kind == MODIFIED and chosen.get(index) == ADD:
            selected.append(dict(incoming[index]))
    return selected


def rows_for_replace(
    plan: Mapping[str, Any],
    decisions: Optional[Iterable[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    chosen = decision_map(decisions)
    return [
        row
        for row in (plan.get("modified_rows") or [])
        if chosen.get(int(row["row_index"])) == REPLACE
    ]


def public_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Drop the full classified list. The reviewer sees modified rows only."""
    return {
        "analysed": int(plan.get("analysed") or 0),
        "new_count": int(plan.get("new_count") or 0),
        "exact_count": int(plan.get("exact_count") or 0),
        "modified_count": int(plan.get("modified_count") or 0),
        "status": str(plan.get("status") or "ready"),
        "recommendation": str(plan.get("recommendation") or ""),
        "modified_rows": list(plan.get("modified_rows") or []),
    }
