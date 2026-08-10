"""Backfill distributor_customer_mappings from ACTIVE sales records.

Usage:
    python -m scripts.backfill_distributor_customer_mappings
"""

from __future__ import annotations

from app.database.session import SessionLocal
from app.services.distributor_service import DistributorService


def main() -> None:
    db = SessionLocal()
    try:
        result = DistributorService(db).backfill_customer_mappings(actor="backfill-script")
        db.commit()
        print("Backfill complete:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
