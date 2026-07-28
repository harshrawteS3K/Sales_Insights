"""Reusable Excel row mappers."""

from typing import List

from app.models.sales_record import SalesRecord
from app.schemas.sales_record import ParsedSalesRow


class SalesRecordMapper:
    """Map parsed Excel rows to ORM entities."""

    @staticmethod
    def to_orm(
        row: ParsedSalesRow,
        *,
        report_id: int,
        distributor_id: int | None,
    ) -> SalesRecord:
        """Convert a parsed sales row into a SalesRecord entity."""
        return SalesRecord(
            sr_no=row.sr_no,
            customer_name=row.customer_name,
            segment=row.segment,
            product=row.product,
            opening_stock=row.opening_stock,
            closing_stock=row.closing_stock,
            quantity=row.quantity,
            quantity_display=row.quantity_display,
            period=row.period,
            unit=row.unit,
            row_hash=row.row_hash,
            report_id=report_id,
            distributor_id=distributor_id,
        )

    @classmethod
    def to_orm_many(
        cls,
        rows: List[ParsedSalesRow],
        *,
        report_id: int,
        distributor_id_by_name: dict[str, int],
    ) -> List[SalesRecord]:
        """Map many parsed rows, resolving distributor ids by name."""
        entities: List[SalesRecord] = []
        for row in rows:
            name = (row.distributor or "").strip()
            distributor_id = distributor_id_by_name.get(row.distributor)
            if distributor_id is None and name:
                distributor_id = distributor_id_by_name.get(name)
            if distributor_id is None and len(distributor_id_by_name) == 1:
                distributor_id = next(iter(distributor_id_by_name.values()))
            entities.append(
                cls.to_orm(row, report_id=report_id, distributor_id=distributor_id)
            )
        return entities
