from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Heat, Lane, Participant, TeamRegistration


class SeedingError(Exception):
    """Raised when seeding cannot be completed."""


@dataclass
class _SeedingEntry:
    participant: Participant
    session_label: str | None
    distance_label: str
    age_category: str
    seed_time_ms: int | None
    seed_time_text: str | None


TIME_WITH_HOURS = re.compile(r"(?<!\d)(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?")
TIME_WITH_MINUTES = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")
TIME_SECONDS = re.compile(r"(?<!\d)(\d{1,2})[.,](\d{1,3})(?!\d)")


def _clean_label(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _normalize_key(value: str | None) -> str | None:
    cleaned = _clean_label(value)
    if cleaned is None:
        return None
    return cleaned.lower()


def _parse_time_to_ms(value: str) -> int | None:
    text = value.strip().replace(",", ".")
    if not text:
        return None

    if text.count(":") == 2:
        h, m, s = text.split(":")
        try:
            hours = int(h)
            minutes = int(m)
            seconds = float(s)
        except ValueError:
            return None
        total_seconds = hours * 3600 + minutes * 60 + seconds
    elif text.count(":") == 1:
        m, s = text.split(":")
        try:
            minutes = int(m)
            seconds = float(s)
        except ValueError:
            return None
        total_seconds = minutes * 60 + seconds
    else:
        try:
            total_seconds = float(text)
        except ValueError:
            return None

    return int(round(total_seconds * 1000))


def _format_time_ms(value: int | None) -> str | None:
    if value is None:
        return None

    total_ms = max(0, value)
    total_seconds, milliseconds = divmod(total_ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}".rstrip("0").rstrip(".")
    if minutes:
        return f"{minutes}:{seconds:02d}.{milliseconds:03d}".rstrip("0").rstrip(".")
    return f"{seconds}.{milliseconds:03d}".rstrip("0").rstrip(".")


def _extract_time_fragment(text: str) -> tuple[str, int | None, str | None]:
    candidate = None
    for pattern in (TIME_WITH_HOURS, TIME_WITH_MINUTES, TIME_SECONDS):
        match = pattern.search(text)
        if match:
            candidate = match.group(0)
            break

    if not candidate:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned, None, None

    time_ms = _parse_time_to_ms(candidate)
    display = candidate.replace(",", ".") if time_ms is not None else None
    without = (text[: match.start()] + text[match.end() :]).strip()
    without = re.sub(r"[()\[\]{}]", "", without)
    cleaned = re.sub(r"\s+", " ", without).strip(" -–—;,:")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = text.strip()
    return cleaned, time_ms, display


def _split_distance(raw_distance: str) -> tuple[str | None, str, int | None, str | None]:
    value = raw_distance or ""
    session_label = None
    distance_part = value.strip()
    if "|" in distance_part:
        first, second = distance_part.split("|", 1)
        session_label = _clean_label(first)
        distance_part = second

    distance_part = distance_part.strip()
    distance_clean, time_ms, display = _extract_time_fragment(distance_part)
    return session_label, distance_clean or value.strip(), time_ms, display


def _base_lane_order(lane_count: int) -> List[int]:
    if lane_count <= 0:
        raise SeedingError("Количество дорожек должно быть положительным")
    center_left = (lane_count + 1) // 2
    if lane_count % 2 == 0:
        center_left = lane_count // 2
        center_right = center_left + 1
    else:
        center_right = center_left
    order = []
    offset = 0
    while len(order) < lane_count:
        left = center_left - offset
        right = center_right + offset
        if offset == 0:
            order.append(center_left)
            if center_right != center_left:
                order.append(center_right)
        else:
            if left >= 1:
                order.append(left)
            if right <= lane_count:
                order.append(right)
        offset += 1
    return order[:lane_count]


def _serpentine_assign(entries: List[_SeedingEntry], lane_count: int) -> List[List[tuple[int, _SeedingEntry]]]:
    if not entries:
        return []

    base_order = _base_lane_order(lane_count)
    heat_count = (len(entries) + lane_count - 1) // lane_count
    heats: List[List[tuple[int, _SeedingEntry]]] = [[] for _ in range(heat_count)]

    for index, entry in enumerate(entries):
        block = index // lane_count
        heat_index = heat_count - 1 - block
        lane_pos = index % lane_count
        lane_order = base_order if block % 2 == 0 else list(reversed(base_order))
        lane_number = lane_order[lane_pos]
        heats[heat_index].append((lane_number, entry))

    for assignments in heats:
        assignments.sort(key=lambda item: item[0])
    return heats


def _collect_participants(
    db: Session,
    competition_id: int,
    session_filter: str | None,
    distance_filter: str | None,
) -> Dict[tuple[str | None, str, str], List[_SeedingEntry]]:
    stmt = (
        select(Participant)
        .join(Participant.team)
        .where(TeamRegistration.competition_id == competition_id)
        .where(TeamRegistration.is_deleted.is_(False))
    )

    participants = db.execute(stmt).scalars().all()

    groups: Dict[tuple[str | None, str, str], List[_SeedingEntry]] = {}

    session_norm_filter = _normalize_key(session_filter)
    distance_norm_filter = _normalize_key(distance_filter)

    for participant in participants:
        if participant.team and participant.team.status:
            if participant.team.status.lower() == "rejected":
                continue

        raw_distance = participant.distance or ""
        session_label, distance_label, time_ms, display_time = _split_distance(raw_distance)
        if not _clean_label(distance_label):
            continue
        age_category = _clean_label(participant.age_category) or ""

        session_norm = _normalize_key(session_label)
        distance_norm = _normalize_key(distance_label)

        if distance_norm_filter is not None and distance_norm != distance_norm_filter:
            continue

        effective_session_label = session_label
        effective_session_norm = session_norm
        if session_norm_filter is not None:
            if session_norm is not None and session_norm != session_norm_filter:
                continue
            effective_session_label = session_filter
            effective_session_norm = session_norm_filter

        key = (effective_session_norm, distance_norm or "", age_category.lower())
        display = _format_time_ms(time_ms) if display_time is None else display_time
        entry = _SeedingEntry(
            participant=participant,
            session_label=_clean_label(effective_session_label),
            distance_label=_clean_label(distance_label) or raw_distance.strip(),
            age_category=age_category,
            seed_time_ms=time_ms,
            seed_time_text=display,
        )
        groups.setdefault(key, []).append(entry)

    return groups


def recalculate_seeding(
    db: Session,
    competition_id: int,
    *,
    session_name: str | None = None,
    distance: str | None = None,
    lane_count: int = 8,
) -> dict:
    if lane_count <= 0:
        raise SeedingError("Количество дорожек должно быть больше нуля")

    competition_id = int(competition_id)

    session_clean = _clean_label(session_name)
    distance_clean = _clean_label(distance)

    # Удаляем существующие заплывы под указанный фильтр
    heat_stmt = select(Heat).where(Heat.competition_id == competition_id)
    if session_clean:
        heat_stmt = heat_stmt.where(func.lower(Heat.session_name) == session_clean.lower())
    if distance_clean:
        heat_stmt = heat_stmt.where(func.lower(Heat.distance) == distance_clean.lower())

    for heat in db.execute(heat_stmt).scalars().all():
        db.delete(heat)
    db.flush()

    groups = _collect_participants(db, competition_id, session_clean, distance_clean)

    heats_created = 0
    lanes_assigned = 0
    groups_summary: List[dict] = []

    for key in sorted(groups.keys(), key=lambda item: (item[0] or "", item[1], item[2])):
        entries = groups[key]
        if not entries:
            continue

        entries.sort(
            key=lambda item: (
                item.seed_time_ms is None,
                item.seed_time_ms if item.seed_time_ms is not None else 0,
                item.participant.last_name,
                item.participant.first_name,
                item.participant.id,
            )
        )

        heats_assignments = _serpentine_assign(entries, lane_count)
        for index, assignments in enumerate(heats_assignments, start=1):
            heat = Heat(
                competition_id=competition_id,
                session_name=entries[0].session_label,
                distance=entries[0].distance_label,
                age_category=entries[0].age_category or None,
                heat_number=index,
            )
            for lane_number, entry in assignments:
                display_time = entry.seed_time_text or _format_time_ms(entry.seed_time_ms)
                lane = Lane(
                    lane_number=lane_number,
                    participant_id=entry.participant.id,
                    seed_time_ms=entry.seed_time_ms,
                    seed_time_text=display_time,
                )
                heat.lanes.append(lane)
                lanes_assigned += 1
            db.add(heat)
            heats_created += 1

        groups_summary.append(
            {
                "session": entries[0].session_label,
                "distance": entries[0].distance_label,
                "age_category": entries[0].age_category,
                "participants": len(entries),
                "heats": len(heats_assignments),
            }
        )

    db.commit()

    return {
        "competition_id": competition_id,
        "session": session_clean,
        "distance": distance_clean,
        "lane_count": lane_count,
        "heats_created": heats_created,
        "lanes_assigned": lanes_assigned,
        "groups": groups_summary,
    }
