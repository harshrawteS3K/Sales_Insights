"""Repository for distributor ↔ customer mappings."""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.distributor_customer_mapping import DistributorCustomerMapping
from app.utils.customer_name import customer_name_key, normalize_customer_name
from app.utils.period_calendar import (
    is_quarter_strictly_before,
    quarter_sort_key,
)


class DistributorCustomerMappingRepository:
    """CRUD + upsert helpers for learned distributor customers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active_names(self, distributor_id: int) -> List[str]:
        """Return sorted active customer names for one distributor."""
        rows = self.db.scalars(
            select(DistributorCustomerMapping.customer_name)
            .where(
                DistributorCustomerMapping.distributor_id == distributor_id,
                DistributorCustomerMapping.is_active.is_(True),
            )
            .order_by(func.lower(DistributorCustomerMapping.customer_name).asc())
        ).all()
        return list(rows)

    def _sales_name_period_rows(
        self, distributor_id: int
    ) -> list[tuple[str, str]]:
        """ACTIVE sales customer_name + reporting_month for one distributor."""
        from app.models.report import Report
        from app.models.sales_record import SalesRecord

        rows = self.db.execute(
            select(SalesRecord.customer_name, Report.reporting_month)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                Report.distributor_id == distributor_id,
                Report.is_deleted.is_(False),
                SalesRecord.is_deleted.is_(False),
                SalesRecord.customer_name.is_not(None),
                SalesRecord.customer_name != "",
            )
        ).all()
        return [(str(n), str(p or "")) for n, p in rows]

    def list_names_before_quarter(
        self, distributor_id: int, before_quarter: str
    ) -> List[str]:
        """
        Customers previously submitted before ``before_quarter`` (exclusive).

        Primary source: ACTIVE sales on ACTIVE reports for this distributor whose
        ``reporting_month`` is chronologically before the requested quarter.
        Falls back to active mappings with ``first_seen_quarter`` before the cut-off
        when no prior sales rows are found (e.g. mapping-only data).
        """
        cut = (before_quarter or "").strip()
        if not cut or quarter_sort_key(cut) is None:
            return []

        by_key: dict[str, str] = {}
        for raw_name, reporting_month in self._sales_name_period_rows(distributor_id):
            period = (reporting_month or "").strip()
            if not period or not is_quarter_strictly_before(period, cut):
                continue
            display = normalize_customer_name(raw_name)
            if not display:
                continue
            key = customer_name_key(display)
            by_key.setdefault(key, display)

        if by_key:
            return sorted(by_key.values(), key=lambda n: n.casefold())

        # Fallback: mappings learned strictly before the requested quarter
        mapping_rows = self.db.scalars(
            select(DistributorCustomerMapping).where(
                DistributorCustomerMapping.distributor_id == distributor_id,
                DistributorCustomerMapping.is_active.is_(True),
            )
        ).all()
        for row in mapping_rows:
            seen = (row.first_seen_quarter or "").strip()
            if not seen or not is_quarter_strictly_before(seen, cut):
                continue
            display = normalize_customer_name(row.customer_name)
            if not display:
                continue
            key = customer_name_key(display)
            by_key.setdefault(key, display)

        return sorted(by_key.values(), key=lambda n: n.casefold())

    def list_names_for_template(
        self,
        distributor_id: int,
        requested_quarter: Optional[str] = None,
    ) -> List[str]:
        """
        All historical customers for a distributor (Master Data / package templates).

        Ordering:
        1. Customers seen in the distributor's latest submitted quarter (A–Z)
        2. Remaining historical customers (A–Z)

        ``requested_quarter`` is accepted for API compatibility but does **not** filter
        membership — Reporting Quarter is filled in Excel by the distributor.
        """
        _ = requested_quarter

        # name_key -> display; also track every period each name appeared in
        by_key: dict[str, str] = {}
        periods_by_key: dict[str, set[tuple[int, int]]] = {}
        global_periods: set[tuple[int, int]] = set()

        for raw_name, reporting_month in self._sales_name_period_rows(distributor_id):
            period = (reporting_month or "").strip()
            period_key = quarter_sort_key(period) if period else None
            display = normalize_customer_name(raw_name)
            if not display:
                continue
            name_key = customer_name_key(display)
            by_key.setdefault(name_key, display)
            if period_key is not None:
                global_periods.add(period_key)
                periods_by_key.setdefault(name_key, set()).add(period_key)

        if not by_key:
            # Mapping-table fallback (e.g. backfilled mappings without sales join)
            return self.list_active_names(distributor_id)

        latest_period = max(global_periods) if global_periods else None
        recent_by_key: dict[str, str] = {}
        historical_by_key: dict[str, str] = {}
        for name_key, display in by_key.items():
            periods = periods_by_key.get(name_key) or set()
            if latest_period is not None and latest_period in periods:
                recent_by_key[name_key] = display
            else:
                historical_by_key[name_key] = display

        ordered: list[str] = []
        seen: set[str] = set()
        for display in sorted(recent_by_key.values(), key=lambda n: n.casefold()):
            key = customer_name_key(display)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(display)
        for display in sorted(historical_by_key.values(), key=lambda n: n.casefold()):
            key = customer_name_key(display)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(display)
        return ordered

    def count_active(self, distributor_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(DistributorCustomerMapping)
                .where(
                    DistributorCustomerMapping.distributor_id == distributor_id,
                    DistributorCustomerMapping.is_active.is_(True),
                )
            )
            or 0
        )

    def find_by_distributor_and_key(
        self, distributor_id: int, name_key: str
    ) -> Optional[DistributorCustomerMapping]:
        return self.db.scalars(
            select(DistributorCustomerMapping).where(
                DistributorCustomerMapping.distributor_id == distributor_id,
                func.lower(DistributorCustomerMapping.customer_name) == name_key,
            )
        ).first()

    def upsert_customers(
        self,
        *,
        distributor_id: int,
        customer_names: Sequence[str],
        source_report_id: Optional[int] = None,
        first_seen_quarter: Optional[str] = None,
    ) -> tuple[int, List[str]]:
        """
        Insert missing mappings (case-insensitive). Reactivate inactive matches.

        Returns (inserted_or_reactivated_count, newly_learned_display_names).
        """
        learned: List[str] = []
        touched = 0
        seen_keys: set[str] = set()

        for raw in customer_names:
            display = normalize_customer_name(raw)
            if not display:
                continue
            key = customer_name_key(display)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            existing = self.find_by_distributor_and_key(distributor_id, key)
            if existing is None:
                self.db.add(
                    DistributorCustomerMapping(
                        distributor_id=distributor_id,
                        customer_name=display,
                        source_report_id=source_report_id,
                        first_seen_quarter=first_seen_quarter,
                        is_active=True,
                    )
                )
                learned.append(display)
                touched += 1
                continue

            changed = False
            if not existing.is_active:
                existing.is_active = True
                changed = True
                learned.append(existing.customer_name)
            if source_report_id and not existing.source_report_id:
                existing.source_report_id = source_report_id
                changed = True
            if first_seen_quarter and not existing.first_seen_quarter:
                existing.first_seen_quarter = first_seen_quarter
                changed = True
            if changed:
                touched += 1

        if touched:
            self.db.flush()
        return touched, learned
