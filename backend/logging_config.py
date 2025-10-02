"""Application logging configuration helpers."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from settings import settings

_FILE_HANDLER_NAME = "swimreg.file"
_STREAM_HANDLER_NAME = "swimreg.stdout"

_REQUEST_ID_CTX: ContextVar[str | None] = ContextVar("request_id", default=None)
_TRACE_ID_CTX: ContextVar[str | None] = ContextVar("trace_id", default=None)

_STANDARD_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "request_id",
    "stack_info",
    "thread",
    "threadName",
    "trace_id",
}


@dataclass
class RequestContextTokens:
    """Handles the lifecycle of context variables used for logging."""

    request: Token[str | None]
    trace: Token[str | None]


class RequestContextFilter(logging.Filter):
    """Inject request context information into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = _REQUEST_ID_CTX.get()
        record.trace_id = _TRACE_ID_CTX.get()
        return True


class JSONLogFormatter(logging.Formatter):
    """Render log records as JSON for log aggregation stacks."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03d"

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        log_payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pathname": record.pathname,
            "lineno": record.lineno,
            "func": record.funcName,
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            log_payload["request_id"] = request_id

        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_payload["trace_id"] = trace_id

        if record.exc_info:
            log_payload["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_payload["stack"] = self.formatStack(record.stack_info)

        extra = self._collect_extra(record)
        if extra:
            log_payload["extra"] = extra

        return json.dumps(log_payload, ensure_ascii=False)

    @staticmethod
    def _collect_extra(record: logging.LogRecord) -> Dict[str, Any]:
        extra: Dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith("_"):
                extra[key] = value
        return extra


def bind_request_context(request_id: str, trace_id: str | None = None) -> RequestContextTokens:
    """Store the identifiers that should accompany subsequent log records."""

    request_token = _REQUEST_ID_CTX.set(request_id)
    trace_token = _TRACE_ID_CTX.set(trace_id or request_id)
    return RequestContextTokens(request=request_token, trace=trace_token)


def reset_request_context(tokens: RequestContextTokens) -> None:
    """Reset request-specific context after the request is complete."""

    _REQUEST_ID_CTX.reset(tokens.request)
    _TRACE_ID_CTX.reset(tokens.trace)


def get_request_id() -> str | None:
    """Return the currently bound request identifier, if any."""

    return _REQUEST_ID_CTX.get()


def setup_logging() -> logging.Logger:
    """Configure JSON logging with both file rotation and stdout output."""

    log_level_name = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "application.log"

    formatter = JSONLogFormatter()
    context_filter = RequestContextFilter()

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    already_has_file_handler = any(
        getattr(handler, "name", "") == _FILE_HANDLER_NAME for handler in root_logger.handlers
    )
    if not already_has_file_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
        )
        file_handler.name = _FILE_HANDLER_NAME
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root_logger.addHandler(file_handler)

    already_has_stream_handler = any(
        getattr(handler, "name", "") == _STREAM_HANDLER_NAME for handler in root_logger.handlers
    )
    if not already_has_stream_handler:
        stream_handler = logging.StreamHandler(stream=sys.stdout)
        stream_handler.name = _STREAM_HANDLER_NAME
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(context_filter)
        root_logger.addHandler(stream_handler)

    return logging.getLogger("swimreg")


__all__ = [
    "bind_request_context",
    "get_request_id",
    "reset_request_context",
    "setup_logging",
]

