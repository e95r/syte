"""Prometheus business metrics helpers for SwimReg."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Iterator

from prometheus_client import Counter, Histogram

_REGISTRATION_SUBMISSIONS = Counter(
    "swimreg_registration_submissions_total",
    "Number of registration form submissions processed by the application.",
    ("competition", "registration_type", "status"),
)

_REGISTRATION_PARTICIPANTS = Counter(
    "swimreg_registration_participants_total",
    "Total number of individual participants included in successful submissions.",
    ("competition", "registration_type"),
)

_REGISTRATION_DURATION = Histogram(
    "swimreg_registration_duration_seconds",
    "Time spent handling registration submissions end-to-end.",
    ("competition", "status"),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
)


@contextmanager
def registration_metrics(competition_slug: str, registration_type: str) -> Iterator[Callable[[int], None]]:
    """Track duration and outcome for a registration submission.

    The context manager yields a callback that must be invoked with the number
    of participants when the submission succeeds. If the callback is not
    executed (because an exception is raised or the request fails), the metrics
    are recorded with an ``error`` status. This makes it easy to build alerts on
    failed registrations and latency SLOs.
    """

    start = time.perf_counter()
    status = "error"
    participant_count = 0

    def mark_success(count: int) -> None:
        nonlocal status, participant_count
        status = "success"
        participant_count = max(0, count)

    try:
        yield mark_success
    finally:
        duration = max(0.0, time.perf_counter() - start)
        _REGISTRATION_DURATION.labels(competition=competition_slug, status=status).observe(duration)
        _REGISTRATION_SUBMISSIONS.labels(
            competition=competition_slug,
            registration_type=registration_type,
            status=status,
        ).inc()
        if status == "success" and participant_count:
            _REGISTRATION_PARTICIPANTS.labels(
                competition=competition_slug,
                registration_type=registration_type,
            ).inc(participant_count)


__all__ = ["registration_metrics"]
