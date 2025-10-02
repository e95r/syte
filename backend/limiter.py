from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Sequence

from slowapi import Limiter
from slowapi.util import get_remote_address

from settings import settings

_GRANULARITY_ALIASES = {
    "s": "second",
    "sec": "second",
    "second": "second",
    "m": "minute",
    "min": "minute",
    "minute": "minute",
    "h": "hour",
    "hr": "hour",
    "hour": "hour",
    "d": "day",
    "day": "day",
}

_LIMIT_PATTERN = re.compile(r"(?P<count>\d+)\s*/\s*(?P<granularity>[A-Za-z]+)")


def _normalize_limit_value(limit: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        count = match.group("count")
        granularity = match.group("granularity").lower()
        normalized = _GRANULARITY_ALIASES.get(granularity, granularity)
        return f"{count}/{normalized}"

    return _LIMIT_PATTERN.sub(_replace, limit)


def _normalize_limits(raw_limits: str | Sequence[str] | None) -> list[str]:
    if raw_limits is None:
        return []

    if isinstance(raw_limits, str):
        limits: Iterable[str] = [raw_limits]
    else:
        limits = list(raw_limits)

    return [_normalize_limit_value(limit) for limit in limits]


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=_normalize_limits(settings.RATE_LIMIT_DEFAULT),
    storage_uri="redis://swimredis:6379/0",
)
