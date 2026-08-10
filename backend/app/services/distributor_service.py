"""Distributor service."""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.exceptions import ConflictError
from app.models.distributor import Distributor
from app.repositories.distributor_customer_mapping_repository import (
    DistributorCustomerMappingRepository,
)
from app.repositories.distributor_repository import DistributorRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.distributor import DistributorCreate, DistributorInfo, DistributorUpdate
from app.services.audit_service import AuditService
from app.utils.distributor_name import normalize_distributor_name

logger = get_logger(__name__)


class DistributorService:
    """Business logic for distributors."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DistributorRepository(db)
        self.customer_maps = DistributorCustomerMappingRepository(db)
        self.audit = AuditService(db)

    def list_distributors(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Distributor]:
        """List distributors."""
        if search:
            items = self.repo.search(search, skip=skip, limit=limit)
        else:
            items = self.repo.list(skip=skip, limit=limit, order_by=Distributor.name.asc())
        if active_only:
            items = [d for d in items if d.is_active]
        return items

    def count_distributors(
        self, *, search: Optional[str] = None, active_only: bool = False
    ) -> int:
        """Return total distributors matching the same filters as list_distributors."""
        if search:
            return self.repo.count_search(search)
        if active_only:
            return len(
                [
                    d
                    for d in self.repo.list(limit=5000, order_by=Distributor.id.asc())
                    if d.is_active
                ]
            )
        return self.repo.count()

    def customer_count(self, distributor_id: int) -> int:
        return self.customer_maps.count_active(distributor_id)

    def list_customers(self, distributor_id: int) -> List[str]:
        """Active mapped customer names for one distributor."""
        self.repo.get_or_raise(distributor_id)
        return self.customer_maps.list_active_names(distributor_id)

    def list_customers_before_quarter(
        self, distributor_id: int, before_quarter: str
    ) -> List[str]:
        """Customers submitted in any quarter strictly before ``before_quarter``."""
        self.repo.get_or_raise(distributor_id)
        return self.customer_maps.list_names_before_quarter(
            distributor_id, before_quarter
        )

    def get_distributor(self, distributor_id: int) -> Distributor:
        """Get distributor by id."""
        return self.repo.get_or_raise(distributor_id)

    def create_distributor(
        self,
        payload: DistributorCreate,
        *,
        actor: str = "system",
    ) -> Distributor:
        """Create a distributor."""
        if payload.email:
            existing = self.repo.get_by_email(str(payload.email).lower())
            if existing:
                raise ConflictError(f"Distributor with email {payload.email} already exists")
        name = normalize_distributor_name(payload.name)
        code = (payload.code or "").strip() or None
        entity = Distributor(
            name=name,
            company=payload.company or name,
            code=code,
            contact_person=(payload.contact_person or "").strip() or None,
            address=payload.address,
            email=str(payload.email).lower() if payload.email else None,
            cc_email=str(payload.cc_email).lower() if payload.cc_email else None,
            phone=payload.phone,
            region=payload.region,
            state=payload.state,
            city=payload.city,
            pincode=payload.pincode,
            is_active=payload.is_active,
            notes=payload.notes,
        )
        created = self.repo.create(entity)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.CREATED,
                details=f"Created distributor {created.name}",
                entity_type="distributor",
                entity_id=str(created.id),
            )
        )
        logger.info("Created distributor id={} name={}", created.id, created.name)
        return created

    def update_distributor(
        self,
        distributor_id: int,
        payload: DistributorUpdate,
        *,
        actor: str = "system",
    ) -> Distributor:
        """Update a distributor."""
        distributor = self.repo.get_or_raise(distributor_id)
        data = payload.model_dump(exclude_unset=True)
        if "email" in data and data["email"]:
            data["email"] = str(data["email"]).lower()
        if "cc_email" in data and data["cc_email"]:
            data["cc_email"] = str(data["cc_email"]).lower()
        if "code" in data and data["code"] is not None:
            data["code"] = str(data["code"]).strip() or None
        if "contact_person" in data and data["contact_person"] is not None:
            data["contact_person"] = str(data["contact_person"]).strip() or None
        if "name" in data and data["name"]:
            data["name"] = normalize_distributor_name(data["name"])
        updated = self.repo.update(distributor, data)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"Updated distributor {updated.name}",
                entity_type="distributor",
                entity_id=str(updated.id),
            )
        )
        return updated

    def deactivate_distributor(
        self, distributor_id: int, *, actor: str = "system"
    ) -> Distributor:
        """Mark distributor inactive without cascading soft-delete of reports."""
        distributor = self.repo.get_or_raise(distributor_id)
        updated = self.repo.update(distributor, {"is_active": False})
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"Deactivated distributor {updated.name}",
                entity_type="distributor",
                entity_id=str(updated.id),
            )
        )
        return updated

    def delete_distributor(self, distributor_id: int, *, actor: str = "system") -> Distributor:
        """
        Soft-delete a distributor and cascade to active reports + sales.

        Keeps Consolidated / dashboard free of orphaned active children.
        Prefer ``deactivate_distributor`` for operational pause.
        """
        from app.repositories.report_repository import ReportRepository
        from app.repositories.sales_record_repository import SalesRecordRepository

        distributor = self.repo.get_or_raise(distributor_id)
        reports_repo = ReportRepository(self.db)
        sales_repo = SalesRecordRepository(self.db)

        active_reports = reports_repo.list_active_for_distributor(distributor_id)
        sales_deleted = 0
        for report in active_reports:
            sales_deleted += sales_repo.soft_delete_for_report(report.id)
            reports_repo.soft_delete(report)

        deleted = self.repo.soft_delete(distributor)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=(
                    f"Deleted distributor {deleted.name} | "
                    f"reports_soft_deleted={len(active_reports)} | "
                    f"sales_soft_deleted={sales_deleted}"
                ),
                entity_type="distributor",
                entity_id=str(deleted.id),
            )
        )
        logger.info(
            "Distributor soft-deleted with cascade | id={} | name={} | reports={} | sales={}",
            deleted.id,
            deleted.name,
            len(active_reports),
            sales_deleted,
        )
        return deleted

    def details_map(self) -> Dict[str, DistributorInfo]:
        """Return frontend distributor detail map."""
        raw = self.repo.as_info_map()
        return {key: DistributorInfo(**value) for key, value in raw.items()}

    def learn_customers_from_import(
        self,
        *,
        distributor_id: int,
        customer_names: List[str],
        source_report_id: Optional[int],
        reporting_quarter: Optional[str],
        actor: str = "system",
    ) -> List[str]:
        """Upsert mappings after successful import; audit newly learned names."""
        if not customer_names:
            logger.info(
                "Customer mapping learn skipped | distributor_id={} | empty customer list",
                distributor_id,
            )
            return []
        logger.info(
            "Learning customer mapping | distributor_id={} | customers={} | quarter={}",
            distributor_id,
            len(customer_names),
            reporting_quarter,
        )
        touched, learned = self.customer_maps.upsert_customers(
            distributor_id=distributor_id,
            customer_names=customer_names,
            source_report_id=source_report_id,
            first_seen_quarter=reporting_quarter,
        )
        logger.info(
            "Customer mapping learn complete | distributor_id={} | touched={} | newly_learned={}",
            distributor_id,
            touched,
            learned,
        )
        if learned:
            dist = self.repo.get_by_id(distributor_id)
            label = (dist.company if dist else None) or (dist.name if dist else distributor_id)
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.CREATED,
                    details=(
                        f"New Customer Learned for Distributor | "
                        f"distributor={label} | customers={', '.join(learned)} | "
                        f"quarter={reporting_quarter or ''}"
                    ),
                    entity_type="distributor",
                    entity_id=str(distributor_id),
                    module="Distributors",
                    status="Success",
                    extra_metadata={
                        "learned_customers": learned,
                        "source_report_id": source_report_id,
                        "reporting_quarter": reporting_quarter,
                    },
                )
            )
        return learned

    def backfill_customer_mappings(self, *, actor: str = "system") -> dict:
        """
        Rebuild distributor_customer_mappings from ACTIVE sales records.

        Safe to re-run: upserts are case-insensitive and idempotent.
        """
        from sqlalchemy import select

        from app.models.report import Report
        from app.models.sales_record import SalesRecord

        rows = self.db.execute(
            select(
                Report.distributor_id,
                Report.id,
                Report.reporting_month,
                SalesRecord.customer_name,
            )
            .join(SalesRecord, SalesRecord.report_id == Report.id)
            .where(
                Report.is_deleted.is_(False),
                SalesRecord.is_deleted.is_(False),
                Report.distributor_id.is_not(None),
                SalesRecord.customer_name.is_not(None),
                SalesRecord.customer_name != "",
            )
            .order_by(Report.id.asc())
        ).all()

        # Keep earliest report as source for each (distributor_id, customer key)
        grouped: dict[int, dict[str, tuple[str, int, Optional[str]]]] = {}
        for distributor_id, report_id, reporting_month, customer_name in rows:
            if not distributor_id or not customer_name:
                continue
            from app.utils.customer_name import customer_name_key, normalize_customer_name

            display = normalize_customer_name(customer_name)
            if not display:
                continue
            key = customer_name_key(display)
            bucket = grouped.setdefault(int(distributor_id), {})
            if key not in bucket:
                bucket[key] = (display, int(report_id), reporting_month)

        distributors_touched = 0
        mappings_touched = 0
        newly_learned = 0
        for distributor_id, customers in grouped.items():
            names = [display for display, _, _ in customers.values()]
            # Prefer earliest report id among this batch for audit source
            source_report_id = min(rid for _, rid, _ in customers.values())
            quarters = {q for _, _, q in customers.values() if q}
            quarter = next(iter(quarters), None) if len(quarters) == 1 else None
            touched, learned = self.customer_maps.upsert_customers(
                distributor_id=distributor_id,
                customer_names=names,
                source_report_id=source_report_id,
                first_seen_quarter=quarter,
            )
            if touched:
                distributors_touched += 1
                mappings_touched += touched
                newly_learned += len(learned)

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=(
                    f"Backfilled distributor customer mappings | "
                    f"distributors={distributors_touched} | "
                    f"touched={mappings_touched} | newly_learned={newly_learned}"
                ),
                entity_type="distributor",
                module="Distributors",
                status="Success",
                extra_metadata={
                    "distributors_touched": distributors_touched,
                    "mappings_touched": mappings_touched,
                    "newly_learned": newly_learned,
                    "source_rows": len(rows),
                },
            )
        )
        logger.info(
            "Customer mapping backfill complete | distributors={} | touched={} | learned={} | rows={}",
            distributors_touched,
            mappings_touched,
            newly_learned,
            len(rows),
        )
        return {
            "distributors_touched": distributors_touched,
            "mappings_touched": mappings_touched,
            "newly_learned": newly_learned,
            "source_rows": len(rows),
        }
