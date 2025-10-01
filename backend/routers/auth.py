from datetime import datetime as dt
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
from passlib.context import CryptContext

# Контекст для bcrypt-хеширования паролей
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

from db import get_db
from models import User
from schemas import Token
from security import create_access_token, verify_password
from limiter import limiter

# Для подтверждения e-mail
from tokens import make_email_token, load_email_token
from mailer import send_email

router = APIRouter()

# =========================
# Общие утилиты сессий
# =========================

def set_session_user(request: Request, user_id: int) -> None:
    request.session["uid"] = user_id

def clear_session_user(request: Request) -> None:
    request.session.pop("uid", None)

def current_user(db: Session, request: Request) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

# =========================
# 1) OAuth2: вход и выдача access_token (API)
# =========================

@router.post("/login", response_model=Token)
@limiter.limit("5/min")
def login_token(request: Request,
                form_data: OAuth2PasswordRequestForm = Depends(),
                db: Session = Depends(get_db)):
    """
    OAuth2 password flow: username = email, password = пароль.
    Возвращает JWT access_token.
    """
    user = db.execute(select(User).where(User.email == form_data.username)).scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверные учётные данные")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

# =========================
# 2) Админ-вход (через форму, cookie)
# =========================

@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return request.app.state.templates.TemplateResponse("login.html", {"request": request, "error": ""})

@router.post("/admin/login", response_class=HTMLResponse)
def admin_login_submit(request: Request,
                       email: str = Form(...),
                       password: str = Form(...),
                       db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password) or not user.is_admin:
        return request.app.state.templates.TemplateResponse("login.html", {"request": request, "error": "Неверно"})
    token = create_access_token({"sub": str(user.id)})
    resp = RedirectResponse(url="/admin", status_code=302)
    # cookie только для админки
    resp.set_cookie("admin_token", token, httponly=True, max_age=3600 * 12)
    return resp

# =========================
# 3) Пользовательская регистрация/вход/выход (сессии)
# =========================

@router.get("/auth/register", response_class=HTMLResponse)
def auth_register_form(request: Request):
    return request.app.state.templates.TemplateResponse(
        "auth_register.html", {"request": request, "consent_checked": False}
    )

@router.post("/auth/register")
@limiter.limit("5/min")
def auth_register(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(""),
    password: str = Form(...),
    personal_data_consent: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    # проверки уникальности
    error = None
    consent_checked = bool(personal_data_consent)

    if not consent_checked:
        error = "Чтобы продолжить, подтвердите согласие на обработку персональных данных"
    elif db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        error = "Email уже занят"
    elif db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        error = "Имя пользователя уже занято"

    if error:
        return request.app.state.templates.TemplateResponse(
            "auth_register.html",
            {
                "request": request,
                "error": error,
                "email": email,
                "username": username,
                "full_name": full_name,
                "consent_checked": consent_checked,
            },
            status_code=400,
        )

    u = User(
        email=email.strip(),
        username=username.strip(),
        full_name=(full_name or username).strip(),
        hashed_password=pwd_ctx.hash(password),  # ← хэшируем здесь
    )

    # Если в вашей модели нет метода hash_password, раскомментируйте строку ниже и удалите строку выше:
    # from passlib.context import CryptContext; pwd = CryptContext(schemes=["bcrypt"], deprecated="auto"); u.hashed_password = pwd.hash(password)

    db.add(u)
    db.commit()
    set_session_user(request, u.id)

    # Отправка письма с подтверждением e-mail (MailHog)
    token = make_email_token(u.id, u.email)
    verify_url = f"{BASE_URL}/auth/verify-email?token={token}"
    html = request.app.state.templates.get_template("email_verify_message.html").render({"verify_url": verify_url})
    send_email(u.email, "Подтверждение e-mail", html)

    # Покажем страницу «Проверьте почту»
    return request.app.state.templates.TemplateResponse(
        "verify_email_sent.html", {"request": request, "email": u.email}
    )

@router.get("/auth/login", response_class=HTMLResponse)
def auth_login_form(request: Request):
    return request.app.state.templates.TemplateResponse("auth_login.html", {"request": request})

@router.post("/auth/login")
@limiter.limit("5/min")
def auth_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return request.app.state.templates.TemplateResponse("auth_login.html", {"request": request, "error": "Неверно"}, status_code=401)
    set_session_user(request, user.id)
    return RedirectResponse(url="/account", status_code=303)

@router.post("/auth/logout")
def auth_logout(request: Request):
    clear_session_user(request)
    # Чистим и админскую cookie на всякий случай
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("admin_token")
    return resp

# =========================
# 4) Подтверждение e-mail
# =========================

@router.post("/auth/resend-email")
def resend_email(request: Request, db: Session = Depends(get_db)):
    """
    Повторная отправка письма подтверждения для текущего пользователя.
    """
    u = current_user(db, request)
    if not u:
        raise HTTPException(status_code=401, detail="Требуется вход")
    token = make_email_token(u.id, u.email)
    verify_url = f"{BASE_URL}/auth/verify-email?token={token}"
    html = request.app.state.templates.get_template("email_verify_message.html").render({"verify_url": verify_url})
    send_email(u.email, "Подтверждение e-mail", html)
    return request.app.state.templates.TemplateResponse(
        "verify_email_sent.html", {"request": request, "email": u.email}
    )

@router.get("/auth/verify-email", response_class=HTMLResponse)
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Обработка ссылки из письма. Помечает email как подтверждённый.
    """
    data = load_email_token(token)
    if not data:
        return HTMLResponse("<h1>Ссылка недействительна или устарела</h1>", status_code=400)
    u = db.get(User, data["uid"])
    if not u or u.email != data["email"]:
        return HTMLResponse("<h1>Неверный токен</h1>", status_code=400)
    if not u.email_verified_at:
        u.email_verified_at = dt.utcnow()
        db.commit()
    return request.app.state.templates.TemplateResponse("verify_email_done.html", {"request": request})
