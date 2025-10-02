from sqlalchemy import select

from models import SwimResult, UserPersonalBest
from utils_lenex import import_results_csv

from . import factories


def test_import_results_updates_personal_bests(db_session):
    user = factories.create_user(db_session)
    competition = factories.create_competition(db_session)

    csv_payload = """full_name,distance,time,course,date
Иван Иванов,50 в/с,00:24.50,LCM,2024-05-10
""".encode("utf-8")

    import_results_csv(db_session, competition.id, csv_payload)

    results = db_session.execute(select(SwimResult)).scalars().all()
    assert len(results) == 1
    result = results[0]
    assert result.time_text == "24.5" or result.time_text.startswith("0:24")
    assert result.is_personal_best is True

    pb = db_session.execute(select(UserPersonalBest)).scalar_one()
    assert pb.user_id == user.id
    assert pb.result_id == result.id
    assert pb.time_ms == result.time_ms
