"""SQLAlchemy engine and session factory."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


@event.listens_for(engine, "connect")
def set_postgres_timezone(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
    """Ensure database connections use UTC."""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET TIME ZONE 'UTC'")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session with commit/rollback."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        db.rollback()
        from app.exceptions import AppException

        if isinstance(exc, AppException):
            logger.warning("Database session rolled back | reason={}", exc.message)
        else:
            logger.exception("Database session rolled back due to error")
        raise
    finally:
        db.close()


def check_database_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as exc:
        logger.error("Database connection failed: {}", exc)
        return False


DbSession = Annotated[Session, Depends(get_db)]
