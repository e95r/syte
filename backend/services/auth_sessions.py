from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from models import RefreshToken, User
from settings import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_secret_key() -> bytes:
    key = settings.REFRESH_TOKEN_SECRET or settings.SECRET_KEY
    return key.encode("utf-8")


def _hash_token(token: str) -> str:
    return hmac.new(_get_secret_key(), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_fingerprint(user_agent: str, ip_address: str) -> str:
    raw = f"{user_agent.strip()}|{ip_address.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(
    db: Session,
    user: User,
    user_agent: str,
    ip_address: str,
) -> tuple[str, RefreshToken]:
    """Create and persist a new refresh token session for the user."""
    token = secrets.token_urlsafe(48)
    token_hash = _hash_token(token)
    fingerprint = _build_fingerprint(user_agent, ip_address)
    expires_at = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session = RefreshToken(
        user=user,
        token_hash=token_hash,
        fingerprint=fingerprint,
        expires_at=expires_at,
        last_used_at=_now(),
        user_agent=user_agent[:255],
        ip_address=ip_address[:45],
    )

    db.add(session)
    _prune_old_sessions(db, user.id)
    db.flush()
    return token, session


def _prune_old_sessions(db: Session, user_id: int) -> None:
    max_sessions = max(settings.REFRESH_TOKEN_MAX_SESSIONS, 1)
    active_sessions = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
        )
        .order_by(RefreshToken.last_used_at.desc().nullslast(), RefreshToken.created_at.desc())
        .all()
    )
    for session in active_sessions[max_sessions:]:
        session.is_revoked = True


def revoke_refresh_token(db: Session, token: RefreshToken) -> None:
    token.is_revoked = True
    db.add(token)


def revoke_all_sessions(db: Session, user_id: int) -> int:
    updated = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
        .update({RefreshToken.is_revoked: True}, synchronize_session=False)
    )
    return updated or 0


def rotate_refresh_token(
    db: Session,
    token_value: str,
    user_agent: str,
    ip_address: str,
) -> tuple[User, str, RefreshToken]:
    token_hash = _hash_token(token_value)
    session: Optional[RefreshToken] = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
        )
        .one_or_none()
    )
    if session is None:
        raise ValueError("invalid_refresh_token")

    if session.expires_at <= _now():
        session.is_revoked = True
        db.add(session)
        raise ValueError("expired_refresh_token")

    fingerprint = _build_fingerprint(user_agent, ip_address)
    if session.fingerprint != fingerprint:
        session.is_revoked = True
        db.add(session)
        raise ValueError("fingerprint_mismatch")

    session.last_used_at = _now()
    db.add(session)

    new_token, new_session = issue_refresh_token(db, session.user, user_agent, ip_address)
    session.is_revoked = True
    db.add(session)

    return session.user, new_token, new_session
