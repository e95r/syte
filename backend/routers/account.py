import logging
import random
from datetime import date as date_cls, datetime as dt, timedelta

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from db import get_db
from models import (
    User,
    Competition,
    UserEventRegistration,
    TeamRegistration,
    Participant,
    Notification,
    Reminder,
)
from email_utils import send_email
from settings import settings
from routers.auth import current_user, clear_session_user
from utils import save_upload_file  # напишем ниже мини-хелпер
from services.results import fetch_results_for_user

router = APIRouter()
logger = logging.getLogger(__name__)

_COURSE_LABELS = {
    "LCM": "50 м (длинная дорожка)",
    "SCM": "25 м (короткая дорожка)",
    "SCY": "25 ярдов",
}


def _resolve_results_owner(
    request: Request,
    db: Session,
    username: str | None,
) -> tuple[User, User]:
    viewer = login_required(request, db)
    target = viewer
    if username:
        stmt = select(User).where(User.username == username)
        target = db.execute(stmt).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if viewer.id != target.id and not viewer.is_admin:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
    return viewer, target


def _group_results_by_event(results, bests):
    pb_map = {(pb.event_code, pb.course): pb for pb in bests}
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for result in results:
        key = (result.event_code, result.course)
        entry = grouped.setdefault(
            key,
            {
                "event_code": result.event_code,
                "course": result.course,
                "distance_label": result.distance_label,
                "results": [],
            },
        )
        if not entry["distance_label"]:
            entry["distance_label"] = result.distance_label
        entry["results"].append(result)
    for key, entry in grouped.items():
        entry["personal_best"] = pb_map.get(key)
        entry["results"].sort(
            key=lambda r: (
                r.time_ms,
                r.swim_date or date_cls.min,
                r.created_at,
            )
        )
    ordered = sorted(
        grouped.values(),
        key=lambda item: (item["course"], item["event_code"]),
    )
    return ordered


def _serialize_result(result) -> dict[str, object]:
    return {
        "id": result.id,
        "competition_id": result.competition_id,
        "competition_title": result.competition.title if result.competition else None,
        "event_code": result.event_code,
        "distance_label": result.distance_label,
        "course": result.course,
        "time_ms": result.time_ms,
        "time_text": result.time_text,
        "fina_points": result.fina_points,
        "swim_date": result.swim_date.isoformat() if result.swim_date else None,
        "stage": result.stage,
        "heat": result.heat,
        "place": result.place,
        "is_personal_best": result.is_personal_best,
    }


def _serialize_pb(pb) -> dict[str, object] | None:
    if pb is None:
        return None
    competition_title = None
    swim_date = None
    if pb.result and pb.result.competition:
        competition_title = pb.result.competition.title
        if pb.result.swim_date:
            swim_date = pb.result.swim_date.isoformat()
    return {
        "time_ms": pb.time_ms,
        "time_text": pb.time_text,
        "fina_points": pb.fina_points,
        "result_id": pb.result_id,
        "competition_title": competition_title,
        "swim_date": swim_date,
    }

def login_required(request: Request, db: Session) -> User:
    u = current_user(db, request)
    if not u:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return u

def build_account_context(
    request: Request,
    db: Session,
    user: User,
    **extra: object,
) -> dict:
    quick_regs = db.execute(
        select(UserEventRegistration)
        .options(selectinload(UserEventRegistration.competition))
        .where(UserEventRegistration.user_id == user.id)
        .order_by(UserEventRegistration.created_at.desc())
    ).scalars().all()
    notes = db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
    ).scalars().all()
    rems = db.execute(
        select(Reminder)
        .where(Reminder.user_id == user.id)
        .order_by(Reminder.remind_at.asc())
    ).scalars().all()

    now = dt.utcnow()
    delete_code_active = bool(
        user.delete_otp
        and user.delete_otp_expires_at
        and now <= user.delete_otp_expires_at
    )

    context = {
        "request": request,
        "user": user,
        "quick_regs": quick_regs,
        "notifications": notes,
        "reminders": rems,
        "delete_code_active": delete_code_active,
        "delete_code_expires_at": user.delete_otp_expires_at if delete_code_active else None,
        "delete_sent": delete_code_active,
        "delete_error": None,
    }
    context.update(extra)
    return context

@router.get("/account", response_class=HTMLResponse)
def account_dashboard(request: Request, db: Session = Depends(get_db)):
    u = current_user(db, request)
    if not u:
        return RedirectResponse(url="/login")
    delete_param = request.query_params.get("delete")
    extras: dict[str, object] = {}
    if delete_param is not None:
        extras["delete_sent"] = delete_param == "sent"
    context = build_account_context(request, db, u, **extras)
    return request.app.state.templates.TemplateResponse("account_dashboard.html", context)


@router.get("/account/results", response_class=HTMLResponse)
def account_results_page(
    request: Request,
    username: str | None = None,
    db: Session = Depends(get_db),
):
    viewer, target = _resolve_results_owner(request, db, username)
    results, bests = fetch_results_for_user(db, target)
    grouped = _group_results_by_event(results, bests)
    return request.app.state.templates.TemplateResponse(
        "account_results.html",
        {
            "request": request,
            "user": viewer,
            "target_user": target,
            "results": results,
            "personal_bests": bests,
            "grouped_events": grouped,
            "course_labels": _COURSE_LABELS,
        },
    )


@router.get("/account/results/data")
def account_results_data(
    request: Request,
    username: str | None = None,
    db: Session = Depends(get_db),
):
    viewer, target = _resolve_results_owner(request, db, username)
    results, bests = fetch_results_for_user(db, target)
    grouped = _group_results_by_event(results, bests)
    payload = [
        {
            "event_code": item["event_code"],
            "course": item["course"],
            "course_label": _COURSE_LABELS.get(item["course"], item["course"]),
            "distance_label": item["distance_label"],
            "personal_best": _serialize_pb(item["personal_best"]),
            "results": [_serialize_result(res) for res in item["results"]],
        }
        for item in grouped
    ]
    return {
        "target_user": {
            "id": target.id,
            "username": target.username,
            "full_name": target.full_name,
        },
        "viewer": {
            "id": viewer.id,
            "username": viewer.username,
            "is_admin": viewer.is_admin,
        },
        "events": payload,
    }


@router.get("/account/edit", response_class=HTMLResponse)
def account_edit_form(request: Request, db: Session = Depends(get_db)):
    u = login_required(request, db)
    return request.app.state.templates.TemplateResponse("account_edit.html", {"request": request, "user": u})

@router.post("/account/edit")
def account_edit(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    gender: str = Form(""),
    birth_date: str = Form(""),
    phone: str = Form(""),
    city: str = Form(""),
    about: str = Form(""),
    db: Session = Depends(get_db),
):
    u = login_required(request, db)
    # уникальность username при смене
    if username != u.username:
        exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if exists:
            return request.app.state.templates.TemplateResponse("account_edit.html", {"request": request, "user": u, "error": "Имя пользователя занято"}, status_code=400)
        u.username = username
    u.full_name = full_name
    u.gender = gender
    u.phone = phone
    u.city = city
    u.about = about
    if birth_date:
        u.birth_date = date_cls.fromisoformat(birth_date)
    db.commit()
    return RedirectResponse(url="/account", status_code=303)

@router.post("/account/password")
def account_password(request: Request, old_password: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    u = login_required(request, db)
    if not pwd.verify(old_password, u.hashed_password):
        raise HTTPException(status_code=400, detail="Старый пароль неверен")
    u.hashed_password = pwd.hash(new_password)
    db.commit()
    return RedirectResponse(url="/account", status_code=303)

@router.post("/account/avatar")
def account_avatar(request: Request, avatar: UploadFile = File(...), db: Session = Depends(get_db)):
    u = login_required(request, db)
    path = save_upload_file(avatar, folder="avatars")  # вернёт относительный путь под /storage
    u.avatar_path = path
    db.commit()
    return RedirectResponse(url="/account", status_code=303)

# Быстрая регистрация на соревнование (1 клик)
@router.post("/competitions/{slug}/quick-register")
@router.post("/competitions/{slug}/quick-register")
def quick_register(request: Request, slug: str, distance: str = Form(""), db: Session = Depends(get_db)):
    u = login_required(request, db)

    comp = db.execute(select(Competition).where(Competition.slug == slug)).scalar_one_or_none()
    if not comp or not comp.is_open:
        raise HTTPException(status_code=404, detail="Соревнование недоступно")

    # Проверяем, что профиль заполнен для автопереноса в заявку
    missing = []
    if not (u.full_name or "").strip():
        missing.append("ФИО")
    if not u.gender:
        missing.append("пол")
    if not u.birth_date:
        missing.append("дата рождения")

    if missing:
        # Показываем понятную страницу с просьбой дополнить профиль
        return request.app.state.templates.TemplateResponse(
            "quick_reg_incomplete.html",
            {
                "request": request,
                "competition": comp,
                "missing": missing,
            },
            status_code=400,
        )

    # одна запись на пользователя на одно соревнование
    exists = db.execute(
        select(UserEventRegistration).where(
            UserEventRegistration.user_id == u.id,
            UserEventRegistration.competition_id == comp.id,
        )
    ).scalar_one_or_none()
    if exists:
        return RedirectResponse(url=f"/competitions/{slug}?quick=exists", status_code=303)

    # быстрый маркер регистрации пользователя
    ureg = UserEventRegistration(user_id=u.id, competition_id=comp.id, distance=distance or "")
    db.add(ureg)
    db.flush()

    # создаём команду с контактом представителя из профиля
    team_name = u.username or (u.full_name or f"user-{u.id}")
    contact_name = u.full_name or team_name
    team = TeamRegistration(
        competition_id=comp.id,
        team_name=None,
        team_representative=None,
        team_members_count=1,
        representative_name=contact_name,
        representative_phone=u.phone or "",
        representative_email=u.email,
        status="pending",
    )
    db.add(team)
    db.flush()

    # разбор ФИО
    ln, fn, mn = "", "", ""
    parts = (u.full_name or "").split()
    if len(parts) == 1:
        fn = parts[0]
    elif len(parts) == 2:
        ln, fn = parts
    elif len(parts) >= 3:
        ln, fn, mn = parts[0], parts[1], " ".join(parts[2:])

    participant = Participant(
        team_id=team.id,
        last_name=ln,
        first_name=fn,
        middle_name=mn,
        gender=u.gender or "",
        birth_date=u.birth_date,          # теперь гарантировано не None
        age_category="",                  # при желании тут рассчитать
        distance=distance or "",
    )
    db.add(participant)

    team.team_members_count = 1

    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        return RedirectResponse(url=f"/competitions/{slug}?quick=error", status_code=303)

    subject_user = f"Заявка принята: {comp.title}"
    body_user = f"""
<p>Здравствуйте, {u.full_name or team.representative_name}!</p>
<p>Мы получили вашу заявку на старт <b>{comp.title}</b>.</p>
<p>{team.team_summary}.</p>
<p>Статус: <b>ожидает подтверждения</b></p>
"""

    subject_admin = f"[SwimReg] Новая быстрая заявка: {comp.title} — {team.team_summary}"
    body_admin = f"""
<p>Поступила новая быстрая регистрация на старт <b>{comp.title}</b>.</p>
<p><b>Заявка:</b> {team.team_summary}<br/>
<b>Представитель:</b> {team.representative_name}<br/>
<b>Тел.:</b> {team.representative_phone or '—'}<br/>
<b>E-mail:</b> {team.representative_email or '—'}</p>
<p>Перейдите в админку для подтверждения заявки.</p>
"""

    rep_email = (team.representative_email or "").strip()
    if rep_email:
        try:
            send_email(rep_email, subject_user, body_user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить письмо участнику быстрой регистрации: %s", exc)

    admin_targets = [addr.strip() for addr in (settings.ADMIN_EMAIL or "").split(",") if addr.strip()]
    for admin_email in admin_targets:
        try:
            send_email(admin_email, subject_admin, body_admin)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить уведомление администратору %s о быстрой регистрации: %s", admin_email, exc)

    return RedirectResponse(url=f"/competitions/{slug}?quick=success", status_code=303)

@router.post("/account/delete/send-code")
def account_delete_send_code(request: Request, db: Session = Depends(get_db)):
    u = login_required(request, db)
    code = f"{random.randint(0, 999999):06d}"
    u.delete_otp = code
    u.delete_otp_expires_at = dt.utcnow() + timedelta(minutes=30)

    subject = "Подтверждение удаления аккаунта"
    body = f"""
<p>Здравствуйте!</p>
<p>Вы запросили удаление аккаунта в сервисе SwimReg.</p>
<p>Введите код <b>{code}</b> на странице личного кабинета, чтобы подтвердить удаление. Код действителен 30 минут.</p>
<p>Если вы не запрашивали удаление, просто проигнорируйте это письмо.</p>
"""

    try:
        send_email(u.email, subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось отправить код удаления аккаунта пользователю %s: %s", u.id, exc)
        db.rollback()
        db.refresh(u)
        context = build_account_context(
            request,
            db,
            u,
            delete_error="Не удалось отправить письмо с кодом. Попробуйте ещё раз позже.",
        )
        return request.app.state.templates.TemplateResponse(
            "account_dashboard.html",
            context,
            status_code=500,
        )

    db.commit()
    logger.info("Отправлен код подтверждения удаления аккаунта пользователю %s", u.id)
    return RedirectResponse(url="/account?delete=sent", status_code=303)


@router.post("/account/delete/confirm")
def account_delete_confirm(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    u = login_required(request, db)
    now = dt.utcnow()
    if (
        not u.delete_otp
        or not u.delete_otp_expires_at
        or now > u.delete_otp_expires_at
        or code != u.delete_otp
    ):
        expired = bool(u.delete_otp_expires_at and now > u.delete_otp_expires_at)
        if expired:
            u.delete_otp = None
            u.delete_otp_expires_at = None
            db.commit()
            db.refresh(u)
        context = build_account_context(
            request,
            db,
            u,
            delete_error="Код неверный или устарел.",
            delete_sent=bool(u.delete_otp),
        )
        return request.app.state.templates.TemplateResponse(
            "account_dashboard.html",
            context,
            status_code=400,
        )

    email = u.email
    user_id = u.id
    db.delete(u)
    db.commit()
    clear_session_user(request)
    logger.info("Пользователь %s удалил аккаунт", user_id)
    return request.app.state.templates.TemplateResponse(
        "account_deleted.html",
        {"request": request, "email": email},
    )

@router.get("/account/phone", response_class=HTMLResponse)
def phone_form(request: Request, db: Session = Depends(get_db)):
    u = login_required(request, db)
    return request.app.state.templates.TemplateResponse("phone_verify.html", {"request": request, "user": u, "sent": False})

@router.post("/account/phone/send-code", response_class=HTMLResponse)
def phone_send_code(request: Request, phone: str = Form(...), db: Session = Depends(get_db)):
    u = login_required(request, db)
    # генерим код
    code = f"{random.randint(0, 999999):06d}"
    u.phone = phone
    u.phone_otp = code
    u.phone_otp_expires_at = dt.utcnow() + timedelta(minutes=10)
    db.commit()

    # В проде отправили бы SMS. В dev — пошлём код на e-mail, чтобы вы видели его в MailHog:
    from mailer import send_email
    send_email(u.email, "Код подтверждения телефона", f"<p>Код подтверждения: <b>{code}</b></p>")

    return request.app.state.templates.TemplateResponse("phone_verify.html", {"request": request, "user": u, "sent": True})

@router.post("/account/phone/confirm")
def phone_confirm(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    u = login_required(request, db)
    if not u.phone_otp or not u.phone_otp_expires_at or dt.utcnow() > u.phone_otp_expires_at or code != u.phone_otp:
        raise HTTPException(status_code=400, detail="Код неверный или устарел")
    u.phone_verified_at = dt.utcnow()
    u.phone_otp = None
    u.phone_otp_expires_at = None
    db.commit()
    return RedirectResponse(url="/account", status_code=303)

