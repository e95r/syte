"""Utilities for computing FINA points for individual race results.

The module contains a compact table of base times (in seconds) for the most
popular Olympic pool events. The table is intentionally small but it covers the
strokes and distances that are used throughout the application and in the test
suite. The values correspond to long-course (LCM) and short-course (SCM) world
record times from the official FINA points table revision for 2023.

`calculate_fina_points` returns an integer with the rounded amount of points or
``None`` if the event/time combination is not supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = [
    "calculate_fina_points",
    "normalize_event_code",
    "normalize_course",
]


@dataclass(frozen=True)
class _BaseTime:
    seconds: float


# The structure is: gender -> course -> event_code -> base time (seconds)
_BASE_TIMES: Mapping[str, Mapping[str, Mapping[str, _BaseTime]]] = {
    "M": {
        "LCM": {
            "50FR": _BaseTime(20.91),
            "100FR": _BaseTime(46.86),
            "200FR": _BaseTime(102.00),
            "400FR": _BaseTime(220.07),
            "800FR": _BaseTime(452.12),
            "1500FR": _BaseTime(871.02),
            "50BK": _BaseTime(23.71),
            "100BK": _BaseTime(51.60),
            "200BK": _BaseTime(111.92),
            "50BR": _BaseTime(25.95),
            "100BR": _BaseTime(56.88),
            "200BR": _BaseTime(125.48),
            "50FL": _BaseTime(22.27),
            "100FL": _BaseTime(49.45),
            "200FL": _BaseTime(110.34),
            "200IM": _BaseTime(114.00),
            "400IM": _BaseTime(243.84),
        },
        "SCM": {
            "50FR": _BaseTime(20.16),
            "100FR": _BaseTime(44.84),
            "200FR": _BaseTime(99.13),
            "400FR": _BaseTime(212.25),
            "800FR": _BaseTime(443.16),
            "1500FR": _BaseTime(846.88),
            "50BK": _BaseTime(22.11),
            "100BK": _BaseTime(48.33),
            "200BK": _BaseTime(100.92),
            "50BR": _BaseTime(25.25),
            "100BR": _BaseTime(55.34),
            "200BR": _BaseTime(119.65),
            "50FL": _BaseTime(21.75),
            "100FL": _BaseTime(48.08),
            "200FL": _BaseTime(108.24),
            "200IM": _BaseTime(111.95),
            "400IM": _BaseTime(238.65),
        },
    },
    "F": {
        "LCM": {
            "50FR": _BaseTime(23.61),
            "100FR": _BaseTime(51.71),
            "200FR": _BaseTime(112.98),
            "400FR": _BaseTime(235.38),
            "800FR": _BaseTime(484.79),
            "1500FR": _BaseTime(920.48),
            "50BK": _BaseTime(26.98),
            "100BK": _BaseTime(57.45),
            "200BK": _BaseTime(123.35),
            "50BR": _BaseTime(29.30),
            "100BR": _BaseTime(64.13),
            "200BR": _BaseTime(138.95),
            "50FL": _BaseTime(24.43),
            "100FL": _BaseTime(55.48),
            "200FL": _BaseTime(121.81),
            "200IM": _BaseTime(126.12),
            "400IM": _BaseTime(260.85),
        },
        "SCM": {
            "50FR": _BaseTime(22.93),
            "100FR": _BaseTime(50.25),
            "200FR": _BaseTime(111.00),
            "400FR": _BaseTime(231.25),
            "800FR": _BaseTime(476.18),
            "1500FR": _BaseTime(910.40),
            "50BK": _BaseTime(25.27),
            "100BK": _BaseTime(55.60),
            "200BK": _BaseTime(119.23),
            "50BR": _BaseTime(28.56),
            "100BR": _BaseTime(63.07),
            "200BR": _BaseTime(133.82),
            "50FL": _BaseTime(24.38),
            "100FL": _BaseTime(54.59),
            "200FL": _BaseTime(118.43),
            "200IM": _BaseTime(122.90),
            "400IM": _BaseTime(254.13),
        },
    },
}


_STROKE_ALIASES = {
    "free": "FR",
    "freestyle": "FR",
    "вольный": "FR",
    "вольн": "FR",
    "кроль": "FR",
    "в/с": "FR",
    "back": "BK",
    "backstroke": "BK",
    "спина": "BK",
    "на спине": "BK",
    "breast": "BR",
    "breaststroke": "BR",
    "брасс": "BR",
    "fly": "FL",
    "butterfly": "FL",
    "баттерфляй": "FL",
    "дельфин": "FL",
    "im": "IM",
    "medley": "IM",
    "complex": "IM",
    "комплекс": "IM",
    "комплексное": "IM",
}


def normalize_course(value: str | None) -> str:
    """Normalise course description to LCM/SCM/SCY."""

    if not value:
        return "LCM"
    candidate = value.strip().upper()
    if candidate in {"LC", "LCM", "L"}:
        return "LCM"
    if candidate in {"SC", "SCM", "S"}:
        return "SCM"
    if candidate in {"SCY", "Y"}:
        return "SCY"
    if "50" in candidate:
        return "LCM"
    if "25" in candidate:
        return "SCM"
    return candidate or "LCM"


def _extract_distance(text: str) -> int | None:
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _detect_stroke(text: str) -> str | None:
    lowered = text.lower()
    for key, code in _STROKE_ALIASES.items():
        if key in lowered:
            return code
    return None


def normalize_event_code(distance_label: str, stroke_label: str | None = None) -> str | None:
    """Return canonical event code (e.g. ``50FR``) for the provided labels."""

    combined = " ".join(filter(None, [distance_label or "", stroke_label or ""]))
    distance = _extract_distance(combined)
    if distance is None:
        return None
    stroke = _detect_stroke(combined)
    if stroke is None:
        return None
    if stroke == "IM" and distance not in {100, 200, 400}:
        return None
    if distance not in {25, 50, 100, 150, 200, 400, 800, 1500}:
        # Restrict to common pool events. 25/150 mostly for SCM specialities.
        return None
    return f"{distance}{stroke}"


def _get_base_time(gender: str, course: str, event_code: str) -> _BaseTime | None:
    gender_key = (gender or "").strip().upper()
    course_key = normalize_course(course)
    if gender_key not in _BASE_TIMES:
        return None
    events = _BASE_TIMES[gender_key].get(course_key)
    if not events:
        return None
    return events.get(event_code)


def calculate_fina_points(
    gender: str,
    event_code: str,
    time_ms: int,
    course: str = "LCM",
) -> int | None:
    """Calculate FINA points for the provided performance.

    Args:
        gender: ``"M"`` for men or ``"F"`` for women.
        event_code: canonical event code (for example ``"100FR"``).
        time_ms: performance time in milliseconds.
        course: pool course string (``LCM``/``SCM``/``SCY``).

    Returns:
        Integer amount of points (rounded to the nearest whole number) or
        ``None`` if the event is not supported.
    """

    if time_ms <= 0:
        return None
    base_time = _get_base_time(gender, course, event_code)
    if base_time is None:
        return None
    swim_seconds = time_ms / 1000.0
    ratio = base_time.seconds / swim_seconds
    if ratio <= 0:
        return None
    points = int(round(1000 * (ratio ** 3)))
    return max(points, 0)
