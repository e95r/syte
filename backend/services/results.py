from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from models import Competition, SwimResult, User, UserPersonalBest
from utils_fina import calculate_fina_points, normalize_course, normalize_event_code

logger = logging.getLogger(__name__)


_TIME_WITH_HOURS = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?$")
_TIME_WITH_MINUTES = re.compile(r"^(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")
_TIME_SECONDS = re.compile(r"^(\d{1,2})(?:[.,](\d{1,3}))?$")


@dataclass(slots=True)
class ParsedSwimResult:
    full_name: str
    distance_label: str
    time_text: str
    course: str
    gender: str | None = None
    email: str | None = None
    username: str | None = None
    birth_date: date | None = None
    stroke: str | None = None
    swim_date: date | None = None
    stage: str | None = None
    heat: str | None = None
    place: int | None = None

    def time_ms(self) -> int | None:
        return parse_time_to_ms(self.time_text)


def parse_time_to_ms(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    match = _TIME_WITH_HOURS.match(text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        frac = match.group(4)
        milliseconds = int(frac.ljust(3, "0")) if frac else 0
        total = ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds
        return total
    match = _TIME_WITH_MINUTES.match(text)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        frac = match.group(3)
        milliseconds = int(frac.ljust(3, "0")) if frac else 0
        total = (minutes * 60 + seconds) * 1000 + milliseconds
        return total
    match = _TIME_SECONDS.match(text)
    if match:
        seconds = int(match.group(1))
        frac = match.group(2)
        milliseconds = int(frac.ljust(3, "0")) if frac else 0
        return seconds * 1000 + milliseconds
    try:
        total_seconds = float(text.replace(",", "."))
    except ValueError:
        return None
    return int(round(total_seconds * 1000))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _clean(value: str | None) -> str:
    return value.strip() if value else ""


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_results_csv(decoded: str) -> list[ParsedSwimResult]:
    reader = csv.DictReader(decoded.splitlines())
    if not reader.fieldnames:
        return []
    rows: list[ParsedSwimResult] = []
    for index, row in enumerate(reader, start=2):
        full_name = _clean(row.get("full_name") or row.get("name"))
        if not full_name:
            last = _clean(row.get("last_name"))
            first = _clean(row.get("first_name"))
            middle = _clean(row.get("middle_name"))
            full_name = " ".join(filter(None, [last, first, middle]))
        if not full_name:
            logger.debug("CSV row %s skipped: missing full name", index)
            continue
        distance = _clean(row.get("distance") or row.get("event") or row.get("race"))
        if not distance:
            logger.debug("CSV row %s skipped: missing distance label", index)
            continue
        time_value = _clean(row.get("time") or row.get("result_time") or row.get("swim_time"))
        if not time_value:
            logger.debug("CSV row %s skipped: missing time", index)
            continue
        course = normalize_course(row.get("course") or row.get("pool") or row.get("course_type"))
        gender = _clean(row.get("gender") or row.get("sex")) or None
        username = _clean(row.get("username")) or None
        email = _clean(row.get("email") or row.get("user_email")) or None
        stroke = _clean(row.get("stroke") or row.get("style")) or None
        birth = parse_date(row.get("birth_date") or row.get("dob"))
        swim_date = parse_date(row.get("date") or row.get("swim_date") or row.get("race_date"))
        stage = _clean(row.get("stage") or row.get("round") or row.get("phase")) or None
        heat = _clean(row.get("heat") or row.get("race") or row.get("run")) or None
        place = _safe_int(row.get("place") or row.get("rank") or row.get("position"))
        parsed = ParsedSwimResult(
            full_name=full_name,
            distance_label=distance,
            time_text=time_value,
            course=course,
            gender=gender,
            email=email,
            username=username,
            birth_date=birth,
            stroke=stroke,
            swim_date=swim_date,
            stage=stage,
            heat=heat,
            place=place,
        )
        if parsed.time_ms() is None:
            logger.debug("CSV row %s skipped: could not parse time '%s'", index, time_value)
            continue
        rows.append(parsed)
    return rows


def resolve_user(db: Session, parsed: ParsedSwimResult) -> User | None:
    def by_statement(stmt: Select[tuple[User]]) -> User | None:
        return db.execute(stmt.limit(1)).scalar_one_or_none()

    if parsed.username:
        user = by_statement(select(User).where(User.username == parsed.username))
        if user:
            return user
    if parsed.email:
        user = by_statement(select(User).where(User.email == parsed.email))
        if user:
            return user
    normalized = " ".join(part for part in parsed.full_name.split() if part)
    if not normalized:
        return None
    stmt = select(User).where(User.full_name.ilike(normalized))
    if parsed.birth_date:
        stmt = stmt.where(User.birth_date == parsed.birth_date)
    user = by_statement(stmt)
    if user:
        return user
    stmt = select(User).where(User.username.ilike(normalized))
    return by_statement(stmt)


def _format_time_ms(value: int) -> str:
    total_ms = max(0, value)
    total_seconds, milliseconds = divmod(total_ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}".rstrip("0").rstrip(".")
    if minutes:
        return f"{minutes}:{seconds:02d}.{milliseconds:03d}".rstrip("0").rstrip(".")
    return f"{seconds}.{milliseconds:03d}".rstrip("0").rstrip(".")


def _ensure_result(
    db: Session,
    user: User,
    competition: Competition,
    parsed: ParsedSwimResult,
    event_code: str,
    time_ms: int,
    fina_points: int | None,
) -> SwimResult:
    stmt = (
        select(SwimResult)
        .where(SwimResult.user_id == user.id)
        .where(SwimResult.competition_id == competition.id)
        .where(SwimResult.event_code == event_code)
        .where(SwimResult.stage == parsed.stage)
        .where(SwimResult.heat == parsed.heat)
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is None:
        existing = SwimResult(
            user_id=user.id,
            competition_id=competition.id,
            event_code=event_code,
            distance_label=parsed.distance_label,
            stroke=parsed.stroke or "",
            course=parsed.course,
            time_ms=time_ms,
            time_text=_format_time_ms(time_ms),
            fina_points=fina_points,
            swim_date=parsed.swim_date,
            stage=parsed.stage,
            heat=parsed.heat,
            place=parsed.place,
            is_personal_best=False,
        )
        db.add(existing)
        return existing

    existing.distance_label = parsed.distance_label
    existing.stroke = parsed.stroke or existing.stroke
    existing.course = parsed.course
    existing.time_ms = time_ms
    existing.time_text = _format_time_ms(time_ms)
    existing.fina_points = fina_points
    existing.swim_date = parsed.swim_date
    existing.stage = parsed.stage
    existing.heat = parsed.heat
    existing.place = parsed.place
    return existing


def _recalculate_personal_best(db: Session, user_id: int, event_code: str, course: str) -> None:
    stmt = (
        select(SwimResult)
        .where(SwimResult.user_id == user_id)
        .where(SwimResult.event_code == event_code)
        .where(SwimResult.course == course)
        .order_by(SwimResult.time_ms.asc(), SwimResult.swim_date.asc().nullslast(), SwimResult.id.asc())
    )
    results = db.execute(stmt).scalars().all()
    best = results[0] if results else None
    for result in results:
        result.is_personal_best = best is not None and result.id == best.id
    pb_stmt = (
        select(UserPersonalBest)
        .where(UserPersonalBest.user_id == user_id)
        .where(UserPersonalBest.event_code == event_code)
        .where(UserPersonalBest.course == course)
    )
    pb = db.execute(pb_stmt).scalar_one_or_none()
    if best is None:
        if pb:
            db.delete(pb)
        return
    if pb is None:
        pb = UserPersonalBest(
            user_id=user_id,
            event_code=event_code,
            course=course,
            time_ms=best.time_ms,
            time_text=best.time_text,
            fina_points=best.fina_points,
            result_id=best.id,
        )
        db.add(pb)
    else:
        pb.time_ms = best.time_ms
        pb.time_text = best.time_text
        pb.fina_points = best.fina_points
        pb.result_id = best.id


def persist_results(db: Session, competition: Competition, rows: Sequence[ParsedSwimResult]) -> list[SwimResult]:
    if not rows:
        return []
    stored: list[SwimResult] = []
    recalculation_targets: set[tuple[int, str, str]] = set()
    for parsed in rows:
        user = resolve_user(db, parsed)
        if not user:
            logger.info(
                "Result for '%s' skipped — user not found", parsed.full_name
            )
            continue
        time_ms = parsed.time_ms()
        if time_ms is None:
            continue
        event_code = normalize_event_code(parsed.distance_label, parsed.stroke)
        if event_code is None:
            logger.info(
                "Result for '%s' skipped — unsupported distance '%s'",
                parsed.full_name,
                parsed.distance_label,
            )
            continue
        gender = user.gender or parsed.gender or ""
        fina_points = calculate_fina_points(gender, event_code, time_ms, parsed.course)
        result = _ensure_result(db, user, competition, parsed, event_code, time_ms, fina_points)
        stored.append(result)
        recalculation_targets.add((user.id, event_code, parsed.course))
    db.flush()
    for user_id, event_code, course in recalculation_targets:
        _recalculate_personal_best(db, user_id, event_code, course)
    return stored


def fetch_results_for_user(db: Session, user: User) -> tuple[list[SwimResult], list[UserPersonalBest]]:
    results = (
        db.execute(
            select(SwimResult)
            .options(selectinload(SwimResult.competition))
            .where(SwimResult.user_id == user.id)
            .order_by(
                SwimResult.swim_date.desc().nullslast(),
                SwimResult.created_at.desc(),
                SwimResult.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    bests = (
        db.execute(
            select(UserPersonalBest)
            .options(
                selectinload(UserPersonalBest.result).selectinload(SwimResult.competition)
            )
            .where(UserPersonalBest.user_id == user.id)
            .order_by(UserPersonalBest.course.asc(), UserPersonalBest.event_code.asc())
        )
        .scalars()
        .all()
    )
    return results, bests


__all__ = [
    "ParsedSwimResult",
    "fetch_results_for_user",
    "parse_results_csv",
    "persist_results",
    "parse_time_to_ms",
]
