"""Application logging configuration helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from settings import settings

_HANDLER_NAME = "swimreg.file"


def setup_logging() -> logging.Logger:
    """Configure rotating file logging for the application.

    The function is idempotent – repeated calls will not attach duplicate
    handlers. Log files are written to ``settings.LOG_DIR`` and rotated to
    prevent unbounded growth while still keeping recent history available for
    troubleshooting.
    """

    log_level_name = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "application.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    already_configured = any(
        getattr(handler, "name", "") == _HANDLER_NAME for handler in root_logger.handlers
    )
    if not already_configured:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
        )
        file_handler.name = _HANDLER_NAME
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return logging.getLogger("swimreg")


__all__ = ["setup_logging"]

