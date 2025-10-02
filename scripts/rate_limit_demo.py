#!/usr/bin/env python3
"""Quick helper to demonstrate SlowAPI throttling on /auth/login.

Run the script against a running instance of the application. Provide the
base URL along with valid credentials so that the first five attempts succeed
and the sixth is rejected with HTTP 429::

    python scripts/rate_limit_demo.py https://localhost auth@example.com secret

The script prints the HTTP status code for each request so it is easy to see
when the limiter kicks in. After running the script you can also verify that
SlowAPI used Redis for bookkeeping, for example::

    docker compose exec redis redis-cli KEYS "limits:*"
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


@dataclass
class AttemptResult:
    index: int
    status_code: int
    body_preview: str


def _perform_login_attempt(url: str, payload: dict[str, str], index: int) -> AttemptResult:
    encoded = urlencode(payload).encode()
    request = Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(request) as response:  # nosec: URL constructed from CLI input
            body = response.read().decode("utf-8", "ignore")
            status_code = response.getcode() or 0
    except HTTPError as exc:  # the limiter responds with HTTPError-friendly payloads
        body = exc.read().decode("utf-8", "ignore")
        status_code = exc.code

    preview = body[:120].replace("\n", " ").strip()
    return AttemptResult(index=index, status_code=status_code, body_preview=preview)


def _print_results(results: Iterable[AttemptResult]) -> None:
    for result in results:
        print(f"attempt {result.index}: HTTP {result.status_code} — {result.body_preview}")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(
            "Usage: python scripts/rate_limit_demo.py <base_url> <username> <password>",
            file=sys.stderr,
        )
        return 1

    base_url, username, password = argv[1], argv[2], argv[3]
    target = urljoin(base_url.rstrip("/") + "/", "auth/login")
    payload = {"username": username, "password": password}

    results = [
        _perform_login_attempt(target, payload, attempt)
        for attempt in range(1, 7)
    ]
    _print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
