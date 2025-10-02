"""Test data factories for the SwimReg backend."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from models import Competition, TeamRegistration, User, UserEventRegistration

_DEFAULT_BIRTH_DATE = date(2000, 1, 1)


def create_user(session: Session, *, email: str = "athlete@example.com", **overrides: Any) -> User:
    """Create and persist a user with predictable defaults."""

    username = overrides.pop("username", email.split("@")[0])
    user = User(
        email=email,
        username=username,
        hashed_password=overrides.pop("hashed_password", "hashed"),
        full_name=overrides.pop("full_name", "Иван Иванов"),
        gender=overrides.pop("gender", "M"),
        birth_date=overrides.pop("birth_date", _DEFAULT_BIRTH_DATE),
        **overrides,
    )
    session.add(user)
    session.flush()
    return user


def create_competition(
    session: Session,
    *,
    title: str = "Test Meet",
    slug: str = "test-meet",
    start_date: datetime | None = None,
    is_open: bool = True,
    **overrides: Any,
) -> Competition:
    competition = Competition(
        title=title,
        slug=slug,
        start_date=start_date or datetime.utcnow(),
        is_open=is_open,
        **overrides,
    )
    session.add(competition)
    session.flush()
    return competition


def create_team_registration(
    session: Session,
    *,
    competition_id: int,
    user: User,
    team_name: str = "Test Team",
    representative_phone: str = "1234567",
    representative_email: str | None = None,
    **overrides: Any,
) -> TeamRegistration:
    registration = TeamRegistration(
        competition_id=competition_id,
        team_name=overrides.pop("team_name", team_name),
        representative_name=overrides.pop("representative_name", user.full_name),
        representative_phone=overrides.pop("representative_phone", representative_phone),
        representative_email=overrides.pop("representative_email", representative_email or user.email),
        **overrides,
    )
    session.add(registration)
    session.flush()
    return registration


def create_quick_registration(
    session: Session,
    *,
    user_id: int,
    competition_id: int,
    distance: str = "50 в/с",
    status: str = "pending",
    **overrides: Any,
) -> UserEventRegistration:
    registration = UserEventRegistration(
        user_id=user_id,
        competition_id=competition_id,
        distance=distance,
        status=status,
        **overrides,
    )
    session.add(registration)
    session.flush()
    return registration


__all__ = [
    "create_user",
    "create_competition",
    "create_team_registration",
    "create_quick_registration",
]
