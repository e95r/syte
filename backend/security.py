from datetime import datetime, timedelta, timezone
from typing import Optional, Callable
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from settings import settings
from db import get_db
from models import User

# Пароли
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Оставляем схему для /login (но не используем её в обязательном порядке внутри admin)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_access_token(data: dict, expires_minutes: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def _extract_token_from_request(request: Request) -> Optional[str]:
    # 1) Cookie admin_token
    tok = request.cookies.get("admin_token")
    if tok:
        return tok
    # 2) Authorization: Bearer <token>
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Строгая версия: требуется валидный токен (в cookie или в заголовке)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизован",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _extract_token_from_request(request)
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception
    return user

def _user_has_roles(user: User, required_roles: set[str]) -> bool:
    if not required_roles:
        return True
    if user.is_admin:
        return True
    user_role_names = {role.name for role in getattr(user, "roles", [])}
    return bool(user_role_names.intersection(required_roles))


def require_roles(*roles: str) -> Callable[..., User]:
    required = {role for role in roles if role}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if _user_has_roles(user, required):
            return user
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    return dependency


def admin_required(user: User = Depends(get_current_user)) -> User:
    if _user_has_roles(user, {"admin"}):
        return user
    raise HTTPException(status_code=403, detail="Требуются права администратора")

def get_current_user_or_none(request: Request, db: Session) -> Optional[User]:
    """Мягкая версия: вернёт пользователя или None (для страниц, где хотим редиректить на логин)."""
    token = _extract_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == int(user_id)).first()
    except jwt.PyJWTError:
        return None
