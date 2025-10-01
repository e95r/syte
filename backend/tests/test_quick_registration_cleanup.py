import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure settings can load with in-memory/test values before importing application modules.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MEDIA_DIR", "/tmp/swimreg_media")
os.environ.setdefault("DOCS_DIR", "/tmp/swimreg_docs")
os.environ.setdefault("RESULTS_DIR", "/tmp/swimreg_results")
os.environ.setdefault("STATIC_DIR", "/tmp/swimreg_static")

from db import Base  # noqa: E402
from models import Competition, TeamRegistration, User, UserEventRegistration  # noqa: E402
from routers.admin import _sync_quick_registration_status  # noqa: E402


Session = sessionmaker(bind=create_engine("sqlite:///:memory:"))


def setup_function(_):
    # Recreate all tables before each test to ensure clean state.
    engine = Session.kw['bind']
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_sync_quick_registration_delete_removes_entry():
    session = Session()
    try:
        user = User(email="user@example.com", hashed_password="hashed")
        session.add(user)
        session.flush()

        comp = Competition(
            title="Test Event",
            slug="test-event",
            start_date=datetime.utcnow(),
        )
        session.add(comp)
        session.flush()

        reg = TeamRegistration(
            competition_id=comp.id,
            team_name="Team",
            representative_name="Rep",
            representative_phone="123",
            representative_email=user.email,
        )
        session.add(reg)
        session.flush()

        quick = UserEventRegistration(
            user_id=user.id,
            competition_id=comp.id,
            distance="",
        )
        session.add(quick)
        session.flush()

        _sync_quick_registration_status(session, reg, delete_quick=True)
        session.flush()

        remaining = session.execute(select(UserEventRegistration)).scalar_one_or_none()
        assert remaining is None
    finally:
        session.close()


def test_sync_quick_registration_status_update():
    session = Session()
    try:
        user = User(email="user2@example.com", hashed_password="hashed")
        session.add(user)
        session.flush()

        comp = Competition(
            title="Test Event 2",
            slug="test-event-2",
            start_date=datetime.utcnow(),
        )
        session.add(comp)
        session.flush()

        reg = TeamRegistration(
            competition_id=comp.id,
            team_name="Team 2",
            representative_name="Rep 2",
            representative_phone="456",
            representative_email=user.email,
        )
        session.add(reg)
        session.flush()

        quick = UserEventRegistration(
            user_id=user.id,
            competition_id=comp.id,
            distance="",
        )
        session.add(quick)
        session.flush()

        _sync_quick_registration_status(session, reg, "approved")
        session.flush()

        updated = session.execute(select(UserEventRegistration)).scalar_one()
        assert updated.status == "approved"
    finally:
        session.close()
