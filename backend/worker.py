from __future__ import annotations

import os

from redis import Redis
from rq import Connection, Worker

from logging_config import setup_logging

logger = setup_logging().getChild("worker")


def main() -> int:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is required")

    logger.info("Starting worker with Redis URL %s", redis_url)
    connection = Redis.from_url(redis_url)
    queues = ["default"]

    with Connection(connection):
        worker = Worker(queues)
        worker.work()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
