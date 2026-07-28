"""Centralized Loguru-based logging configuration."""

import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings


def setup_logging() -> None:
    """Configure application-wide Loguru sinks."""
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format=log_format,
        colorize=True,
        backtrace=True,
        diagnose=settings.is_development,
    )

    log_path = Path(settings.log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path / "app_{time:YYYY-MM-DD}.log"),
        level=settings.log_level.upper(),
        format=log_format,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=settings.is_development,
    )

    logger.add(
        str(log_path / "error_{time:YYYY-MM-DD}.log"),
        level="ERROR",
        format=log_format,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    logger.add(
        str(log_path / "graph_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=log_format,
        filter=lambda record: "graph" in record["name"].lower()
        or "graph" in str(record["extra"]).lower()
        or "Graph" in record["message"],
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        enqueue=True,
    )

    logger.add(
        str(log_path / "excel_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=log_format,
        filter=lambda record: "excel" in record["name"].lower()
        or "excel" in record["message"].lower()
        or "parser" in record["name"].lower(),
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        enqueue=True,
    )

    logger.add(
        str(log_path / "database_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=log_format,
        filter=lambda record: "database" in record["name"].lower()
        or "repository" in record["name"].lower()
        or "sqlalchemy" in record["name"].lower(),
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        enqueue=True,
    )

    logger.info(
        "Logging initialized | env={} | level={}",
        settings.app_env,
        settings.log_level,
    )


def get_logger(name: str = __name__):
    """Return a contextualized logger bound to a module name."""
    return logger.bind(module=name)
