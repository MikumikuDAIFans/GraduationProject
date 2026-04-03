"""Logging setup utilities."""

from __future__ import annotations

import logging
import sys

from loguru import logger

from app.core.config import get_settings


class InterceptHandler(logging.Handler):
    """Route stdlib logs through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    """Configure application-wide structured logging."""
    settings = get_settings()

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [InterceptHandler()]

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        enqueue=False,
        backtrace=settings.app_env == "development",
        diagnose=settings.app_env == "development",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level:<8} | "
            "{extra[component]} | "
            "{message}"
        ),
    )
    logger.configure(extra={"component": "app"})
