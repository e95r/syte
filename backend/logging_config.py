"""Centralised logging configuration for the application."""

from __future__ import annotations

import json
import logging
import logging.config
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Final

from settings import settings

_REQUEST_ID: Final[ContextVar[str]] = ContextVar("request_id", default="-")
_RESERVED_RECORD_ATTRS: Final[set[str]] = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


def get_request_id() -> str:
    """Return the request id bound to the current context."""

    request_id = _REQUEST_ID.get()
    return request_id if request_id else "-"


def bind_request_id(request_id: str) -> Token[str]:
    """Attach the request id to the logging context."""

    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Reset the request id context to a previous value."""

    _REQUEST_ID.reset(token)


class RequestIdFilter(logging.Filter):
    """Inject the current request id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - standard filter signature
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as JSON objects."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - interface defined by logging
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "message": message,
            "request_id": getattr(record, "request_id", "-"),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            if value is None:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)


def build_logging_config(log_level: str | None = None) -> dict[str, Any]:
    """Create a dictionary config suitable for logging.dictConfig."""

    level = (log_level or settings.LOG_LEVEL).upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "logging_config.RequestIdFilter"},
        },
        "formatters": {
            "json": {"()": "logging_config.JsonFormatter"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["request_id"],
                "formatter": "json",
            },
            "null": {"class": "logging.NullHandler"},
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["null"],
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "gunicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "gunicorn.access": {
                "handlers": ["null"],
                "propagate": False,
            },
        },
    }


def setup_logging() -> logging.Logger:
    """Apply the logging configuration and return the app logger."""

    logging.captureWarnings(True)
    logging.config.dictConfig(build_logging_config())
    return logging.getLogger("swimreg")


__all__ = [
    "JsonFormatter",
    "RequestIdFilter",
    "bind_request_id",
    "build_logging_config",
    "get_request_id",
    "reset_request_id",
    "setup_logging",
]
