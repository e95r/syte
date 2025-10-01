from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date as date_cls
import logging

from db import get_db
from models import Competition, TeamRegistration, Participant
from email_utils import send_email
from settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def calculate_age_category(birth_date: date_cls) -> str:
    today = date_cls.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    if age < 10:
        return "Дети до 10"
    if age < 14:
        return "Юниоры 10-13"
    if age < 18:
        return "Юноши 14-17"
    if age < 30:
        return "Взрослые 18-29"
    if age < 50:
        return "Мастера 30-49"
    return "Ветераны 50+"


@router.get("/competitions/{slug}/register", response_class=HTMLResponse)
def register_form(request: Request, slug: str, db: Session = Depends(get_db)):
    comp = db.execute(
        select(Competition).where(Competition.slug == slug)
    ).scalar_one_or_none()
    if not comp or not comp.is_open:
        raise HTTPException(status_code=404, detail="Регистрация недоступна")
    return request.app.state.templates.TemplateResponse(
        "register.html",
        {"request": request, "competition": comp},
    )


@router.post("/competitions/{slug}/register")
def register_submit(
    request: Request,
    slug: str,
    register_team: str = Form("off"),
    team_name: str | None = Form(None),
    team_representative: str = Form(""),
    representative_phone: str = Form(""),
    representative_email: str = Form(""),

    # несколько участников → несколько одноимённых полей
    last_name: list[str] = Form(...),
    first_name: list[str] = Form(...),
    middle_name: list[str] | None = Form(None),  # может отсутствовать у части записей
    gender: list[str] = Form(...),
    birth_date: list[str] = Form(...),  # YYYY-MM-DD
    distance: list[str] = Form(...),

    db: Session = Depends(get_db),
):
    comp = db.execute(
        select(Competition).where(Competition.slug == slug)
    ).scalar_one_or_none()
    if not comp or not comp.is_open:
        raise HTTPException(status_code=404, detail="Регистрация недоступна")

    register_value = (register_team or "").strip().lower()
    is_team_registration = register_value in {"1", "true", "on", "yes"}

    normalized_team_name = team_name.strip() if team_name else None
    representative_name = team_representative.strip()
    representative_phone = representative_phone.strip()
    representative_email = representative_email.strip()

    if is_team_registration and not normalized_team_name:
        return RedirectResponse(
            url=f"/competitions/{slug}?registered=missing_team_name",
            status_code=303,
        )

    mn_list = middle_name or []
    n = min(
        len(last_name),
        len(first_name),
        len(gender),
        len(birth_date),
        len(distance),
    )

    if not is_team_registration:
        n = min(n, 1)

    if n == 0:
        return RedirectResponse(
            url=f"/competitions/{slug}?registered=missing_participant",
            status_code=303,
        )

    if len(mn_list) < n:
        mn_list = mn_list + [""] * (n - len(mn_list))

    participants_payload: list[dict[str, object]] = []
    for i in range(n):
        ln = last_name[i].strip()
        fn = first_name[i].strip()
        mn = mn_list[i].strip() if mn_list[i] else ""
        bd = date_cls.fromisoformat(birth_date[i])
        dist = distance[i].strip()
        full_name = " ".join(filter(None, [ln, fn, mn]))

        participants_payload.append(
            {
                "last_name": ln,
                "first_name": fn,
                "middle_name": mn,
                "gender": gender[i],
                "birth_date": bd,
                "distance": dist,
                "full_name": full_name,
            }
        )

    contact_name = representative_name or participants_payload[0]["full_name"] or "Участник"

    team = TeamRegistration(
        competition_id=comp.id,
        team_name=normalized_team_name if is_team_registration else None,
        team_representative=representative_name if is_team_registration else None,
        team_members_count=len(participants_payload),
        representative_name=contact_name,
        representative_phone=representative_phone,
        representative_email=representative_email,
    )
    db.add(team)
    db.flush()  # получить team.id

    for payload in participants_payload:
        bd = payload["birth_date"]
        participant = Participant(
            team_id=team.id,
            last_name=payload["last_name"],
            first_name=payload["first_name"],
            middle_name=payload["middle_name"],
            gender=payload["gender"],
            birth_date=bd,
            age_category=calculate_age_category(bd),
            distance=payload["distance"],
        )
        db.add(participant)

    team_summary = team.team_summary

    # Письма: регистранту и ответственному (MailHog на http://localhost:8025)
    if team.is_team_registration:
        subject_user = f"Заявка команды принята: {comp.title}"
        team_line = (
            f"<p>Команда: <b>{normalized_team_name}</b><br/>Участников: {team.members_count}</p>"
            if normalized_team_name
            else ""
        )
        body_user = (
            f"<p>Здравствуйте, {contact_name}!</p>"
            f"<p>Ваша командная заявка на соревнование <b>{comp.title}</b> получена и ожидает подтверждения организатора.</p>"
            f"{team_line}"
            "<p>Статус: <b>ожидает подтверждения</b></p>"
        )
    else:
        subject_user = f"Заявка принята: {comp.title}"
        body_user = (
            f"<p>Здравствуйте, {contact_name}!</p>"
            f"<p>Ваша заявка на участие в соревновании <b>{comp.title}</b> получена и ожидает подтверждения организатора.</p>"
            "<p>Статус: <b>ожидает подтверждения</b></p>"
        )

    subject_admin = f"[SwimReg] Новая заявка: {comp.title} — {team_summary}"
    body_admin = f"""
<p>Поступила новая заявка на старт <b>{comp.title}</b>.</p>
<p><b>Заявка:</b> {team_summary}<br/>
<b>Контактное лицо:</b> {contact_name}<br/>
<b>Тел.:</b> {representative_phone or "—"}<br/>
<b>E-mail:</b> {representative_email or "—"}</p>
<p>Перейдите в админку для подтверждения.</p>
"""

    if representative_email:
        try:
            send_email(representative_email, subject_user, body_user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить письмо участнику: %s", exc)

    admin_targets = [addr.strip() for addr in (settings.ADMIN_EMAIL or "").split(",") if addr.strip()]
    for admin_email in admin_targets:
        try:
            send_email(admin_email, subject_admin, body_admin)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить уведомление администратору %s: %s", admin_email, exc)

    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        return RedirectResponse(url=f"/competitions/{slug}?registered=error", status_code=303)

    # после POST → 303 на страницу соревнования
    return RedirectResponse(url=f"/competitions/{slug}?registered=success", status_code=303)
