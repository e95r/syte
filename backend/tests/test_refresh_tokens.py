from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models import RefreshToken, User
from security import hash_password
from services.auth_sessions import (
    issue_refresh_token,
    revoke_all_sessions,
    rotate_refresh_token,
)
from settings import settings


def _make_user(db_session) -> User:
    user = User(
        email="athlete@example.com",
        username="athlete",
        hashed_password=hash_password("secret"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_issue_refresh_token_persists_session(db_session):
    user = _make_user(db_session)

    token_value, session_obj = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    db_session.commit()

    assert token_value
    assert session_obj.user_id == user.id
    assert session_obj.token_hash != token_value
    assert session_obj.fingerprint
    assert session_obj.expires_at > datetime.now(timezone.utc)


def test_rotate_refresh_token_creates_new_session(db_session):
    user = _make_user(db_session)
    token_value, session_obj = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    db_session.commit()

    returned_user, new_token, new_session = rotate_refresh_token(
        db_session,
        token_value,
        "pytest",
        "127.0.0.1",
    )
    db_session.commit()
    db_session.refresh(session_obj)

    assert returned_user.id == user.id
    assert new_token != token_value
    assert new_session.id != session_obj.id
    assert session_obj.is_revoked is True


def test_rotate_refresh_token_revokes_on_fingerprint_mismatch(db_session):
    user = _make_user(db_session)
    token_value, session_obj = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    db_session.commit()

    with pytest.raises(ValueError):
        rotate_refresh_token(db_session, token_value, "another", "10.0.0.5")
    db_session.commit()
    db_session.refresh(session_obj)

    assert session_obj.is_revoked is True


def test_revoke_all_sessions_marks_tokens_revoked(db_session):
    user = _make_user(db_session)
    for _ in range(3):
        issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    db_session.commit()

    updated = revoke_all_sessions(db_session, user.id)
    db_session.commit()

    tokens = db_session.query(RefreshToken).filter_by(user_id=user.id).all()
    assert updated == len(tokens)
    assert tokens and all(t.is_revoked for t in tokens)


def test_issue_refresh_token_respects_session_limit(db_session, monkeypatch):
    user = _make_user(db_session)
    monkeypatch.setattr(settings, "REFRESH_TOKEN_MAX_SESSIONS", 2)

    first, first_session = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    second, second_session = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    third, third_session = issue_refresh_token(db_session, user, "pytest", "127.0.0.1")
    db_session.commit()

    db_session.refresh(first_session)
    db_session.refresh(second_session)
    db_session.refresh(third_session)

    assert first != second != third
    assert first_session.is_revoked is True
    assert second_session.is_revoked is False
    assert third_session.is_revoked is False
    assert {second_session.id, third_session.id} == {
        t.id for t in db_session.query(RefreshToken).filter_by(is_revoked=False)
    }
