from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from redis import Redis
from rq import Connection, Worker

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger("swimreg.worker")


def main() -> int:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is required")

    parsed = urlparse(redis_url)
    redis_target = parsed.hostname or "localhost"
    if parsed.port:
        redis_target = f"{redis_target}:{parsed.port}"
    redis_db = parsed.path.lstrip("/") or "0"

    logger.info(
        "worker_startup",
        extra={"redis_target": redis_target, "redis_db": redis_db},
    )
    connection = Redis.from_url(redis_url)
    queues = ["default"]

    with Connection(connection):
        worker = Worker(queues)
        worker.work()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
