"""Gunicorn configuration for the FastAPI service."""

from __future__ import annotations

import multiprocessing
import os

from logging_config import build_logging_config
from settings import settings


def _worker_count() -> int:
    if workers := os.getenv("GUNICORN_WORKERS"):
        return max(1, int(workers))
    cpu_count = multiprocessing.cpu_count()
    return max(2, min(cpu_count * 2 + 1, 8))


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
worker_class = "uvicorn.workers.UvicornWorker"
workers = _worker_count()
threads = int(os.getenv("GUNICORN_THREADS", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "0")) or 0
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "0")) or 0
forwarded_allow_ips = "*"
errorlog = "-"
loglevel = settings.LOG_LEVEL.lower()
accesslog = None
preload_app = True
logconfig_dict = build_logging_config(settings.LOG_LEVEL)
proc_name = os.getenv("GUNICORN_PROC_NAME", "swimreg")
