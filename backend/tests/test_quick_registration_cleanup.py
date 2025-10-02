from sqlalchemy import select

from models import UserEventRegistration
from routers.admin import _sync_quick_registration_status

from . import factories


def test_sync_quick_registration_delete_removes_entry(db_session):
    user = factories.create_user(db_session, email="user@example.com")
    comp = factories.create_competition(db_session, title="Test Event", slug="test-event")
    reg = factories.create_team_registration(
        db_session,
        competition_id=comp.id,
        user=user,
        team_name="Team",
        representative_phone="123",
    )
    factories.create_quick_registration(
        db_session,
        user_id=user.id,
        competition_id=comp.id,
        distance="",
    )

    _sync_quick_registration_status(db_session, reg, delete_quick=True)
    db_session.flush()

    remaining = db_session.execute(select(UserEventRegistration)).scalar_one_or_none()
    assert remaining is None


def test_sync_quick_registration_status_update(db_session):
    user = factories.create_user(db_session, email="user2@example.com")
    comp = factories.create_competition(db_session, title="Test Event 2", slug="test-event-2")
    reg = factories.create_team_registration(
        db_session,
        competition_id=comp.id,
        user=user,
        team_name="Team 2",
        representative_phone="456",
    )
    factories.create_quick_registration(
        db_session,
        user_id=user.id,
        competition_id=comp.id,
        distance="",
    )

    _sync_quick_registration_status(db_session, reg, "approved")
    db_session.flush()

    updated = db_session.execute(select(UserEventRegistration)).scalar_one()
    assert updated.status == "approved"
