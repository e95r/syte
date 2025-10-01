import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MEDIA_DIR", "/tmp/swimreg_media")
os.environ.setdefault("DOCS_DIR", "/tmp/swimreg_docs")
os.environ.setdefault("RESULTS_DIR", "/tmp/swimreg_results")
os.environ.setdefault("STATIC_DIR", "/tmp/swimreg_static")

from db import Base  # noqa: E402
from models import Competition, SwimResult, User, UserPersonalBest  # noqa: E402
from utils_lenex import import_results_csv  # noqa: E402


Session = sessionmaker(bind=create_engine("sqlite:///:memory:"))


def setup_function(_):
    engine = Session.kw['bind']
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_import_results_updates_personal_bests():
    session = Session()
    try:
        user = User(
            email="athlete@example.com",
            hashed_password="hashed",
            username="athlete",
            full_name="Иван Иванов",
            gender="M",
            birth_date=datetime(2000, 1, 1).date(),
        )
        session.add(user)
        session.flush()

        competition = Competition(
            title="Test Meet",
            slug="test-meet",
            start_date=datetime.utcnow(),
        )
        session.add(competition)
        session.flush()

        csv_payload = """full_name,distance,time,course,date
Иван Иванов,50 в/с,00:24.50,LCM,2024-05-10
""".encode("utf-8")

        import_results_csv(session, competition.id, csv_payload)

        results = session.execute(select(SwimResult)).scalars().all()
        assert len(results) == 1
        result = results[0]
        assert result.time_text == "24.5" or result.time_text.startswith("0:24")
        assert result.is_personal_best is True

        pb = session.execute(select(UserPersonalBest)).scalar_one()
        assert pb.user_id == user.id
        assert pb.result_id == result.id
        assert pb.time_ms == result.time_ms
    finally:
        session.close()
