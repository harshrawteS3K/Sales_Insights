"""Seed default Admin and User accounts for local / EC2 bootstrapping."""

from app.core.logging import get_logger, setup_logging
from app.database.session import SessionLocal
from app.enums import UserRole
from app.models.user import User

logger = get_logger(__name__)

DEFAULT_USERS = [
    {
        "email": "admin@apcotex.com",
        "full_name": "System Admin",
        "title": "Administrator",
        "role": UserRole.ADMIN.value,
        "department": "IT",
    },
    {
        "email": "user@apcotex.com",
        "full_name": "Sales User",
        "title": "Sales Analyst",
        "role": UserRole.USER.value,
        "department": "Sales",
    },
]


def seed() -> None:
    """Insert default users when missing."""
    setup_logging()
    db = SessionLocal()
    try:
        created = 0
        for payload in DEFAULT_USERS:
            exists = (
                db.query(User)
                .filter(User.email == payload["email"], User.is_deleted.is_(False))
                .first()
            )
            if exists:
                continue
            db.add(User(**payload))
            created += 1
        db.commit()
        logger.info("Seed complete | created={}", created)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
