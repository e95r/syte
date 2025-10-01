from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from starlette.requests import Request
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session, selectinload
from datetime import datetime
from pathlib import Path
from io import BytesIO
from typing import Optional
import os
import re

import requests

from db import get_db
from models import (
    AppSetting,
    Competition,
    CompetitionSeries,
    News,
    ResultFile,
    Role,
    TeamRegistration,
    User,
    UserEventRegistration,
)
from email_utils import send_email
from mailer import build_registration_approved_email
from security import get_current_user_or_none, hash_password, require_roles
from settings import settings
from openpyxl import Workbook
from utils import slugify, write_audit
from utils_seeding import SeedingError, recalculate_seeding



router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except IsADirectoryError:
        pass


def _remove_stored_file(url_or_path: Optional[str]) -> None:
    if not url_or_path:
        return

    value = url_or_path.strip()
    if not value:
        return

    base_map = {
        "/media/": Path(settings.MEDIA_DIR),
        "/docsfiles/": Path(settings.DOCS_DIR),
        "/results/": Path(settings.RESULTS_DIR),
    }

    normalized = value.lstrip("/")

    for prefix, base in base_map.items():
        if value.startswith(prefix):
            relative = value[len(prefix):].lstrip("/")
            if relative:
                _unlink_if_exists(base / relative)
            return

        alt_prefix = prefix.lstrip("/")
        if alt_prefix and normalized.startswith(alt_prefix):
            relative = normalized[len(alt_prefix):].lstrip("/")
            if relative:
                _unlink_if_exists(base / relative)
            return

    path = Path(value)
    if path.is_file():
        _unlink_if_exists(path)


VK_SETTING_DEFAULTS: dict[str, str] = {
    "vk_enabled": "0",
    "vk_access_token": "",
    "vk_group_id": "",
    "vk_api_version": "5.199",
    "vk_message_signature": "",
}


ABOUT_PAGE_DEFAULTS: dict[str, str] = {
    "about_title": "О клубе",
    "about_subtitle": "Наша команда объединяет любителей плавания и соревнований.",
    "about_body": (
        "<p>Мы организуем тренировки, соревнования и образовательные программы для пловцов любого уровня.</p>"
        "<p>Миссия клуба — развивать любительское плавание, поддерживать спортсменов и создавать сообщество единомышленников.</p>"
        "<p>Открыты к сотрудничеству с тренерами, спортивными школами и партнёрами. Пишите нам, если хотите присоединиться!</p>"
    ),
}


def _load_settings(db: Session, defaults: dict[str, str]) -> dict[str, str]:
    keys = list(defaults.keys())
    rows = db.execute(select(AppSetting).where(AppSetting.key.in_(keys))).scalars().all()
    result = defaults.copy()
    for row in rows:
        result[row.key] = row.value
    return result


def _save_settings(db: Session, items: dict[str, str]) -> None:
    for key, value in items.items():
        obj = db.get(AppSetting, key)
        if obj:
            obj.value = value
        else:
            obj = AppSetting(key=key, value=value)
            db.add(obj)
    db.commit()


def _sync_quick_registration_status(
    db: Session,
    registration: TeamRegistration,
    status: Optional[str] = None,
    *,
    delete_quick: bool = False,
) -> None:
    if not registration.representative_email:
        return
    user = db.execute(select(User).where(User.email == registration.representative_email)).scalar_one_or_none()
    if not user:
        return
    quick = db.execute(
        select(UserEventRegistration).where(
            UserEventRegistration.user_id == user.id,
            UserEventRegistration.competition_id == registration.competition_id,
        )
    ).scalar_one_or_none()
    if quick:
        if delete_quick:
            db.delete(quick)
        elif status is not None:
            quick.status = status


def _vk_message_from_html(title: str, html_body: str, signature: str = "") -> str:
    # Грубое преобразование HTML → текста без лишних переносов
    text = html_body or ""
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    parts = [title.strip()]
    if text:
        parts.append(text)
    if signature.strip():
        parts.append(signature.strip())
    return "\n\n".join(parts)


def _post_news_to_vk(news: News, settings_map: dict[str, str]) -> tuple[bool, str]:
    if settings_map.get("vk_enabled") != "1":
        return False, "VK posting disabled"

    access_token = settings_map.get("vk_access_token", "").strip()
    group_id_raw = settings_map.get("vk_group_id", "").strip()
    api_version = settings_map.get("vk_api_version", "5.199").strip() or "5.199"
    signature = settings_map.get("vk_message_signature", "")

    if not access_token or not group_id_raw:
        return False, "VK settings incomplete"

    try:
        group_id = int(group_id_raw)
    except ValueError:
        return False, "VK group id must be integer"

    base_url = os.getenv("BASE_URL", "http://localhost:8080")
    link = f"{base_url.rstrip('/')}/news#{news.slug}"
    message = _vk_message_from_html(news.title, news.body, signature)
    if link not in message:
        message = f"{message}\n\nПодробнее: {link}"

    payload = {
        "access_token": access_token,
        "v": api_version,
        "owner_id": f"-{abs(group_id)}",
        "from_group": 1,
        "message": message[:4000],
    }

    try:
        response = requests.post("https://api.vk.com/method/wall.post", data=payload, timeout=10)
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        return False, f"VK request failed: {exc}"

    if "error" in data:
        err = data["error"]
        return False, f"VK error {err.get('error_code')}: {err.get('error_msg')}"

    return True, "OK"

@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_none(request, db)
    if not user or not (user.is_admin or user.has_role("admin")):
        return RedirectResponse(url="/admin/login", status_code=302)

    comps = db.execute(
        select(Competition)
        .options(
            selectinload(Competition.results),
            selectinload(Competition.series),
        )
        .order_by(Competition.start_date.desc())
    ).scalars().all()
    news = db.execute(select(News).order_by(News.published_at.desc())).scalars().all()
    series_list = db.execute(select(CompetitionSeries).order_by(CompetitionSeries.name.asc())).scalars().all()
    vk_settings = _load_settings(db, VK_SETTING_DEFAULTS)
    about_settings = _load_settings(db, ABOUT_PAGE_DEFAULTS)
    return request.app.state.templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "comps": comps,
            "news": news,
            "series_list": series_list,
            "vk_settings": vk_settings,
            "about_settings": about_settings,
        },
    )
@router.post("/admin/competitions/create")
def admin_comp_create(
    request: Request,
    title: str = Form(...),
    city: str = Form(""),
    pool_name: str = Form(""),
    address: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(""),
    stage: str = Form(""),
    series_id: str = Form(""),
    new_series_name: str = Form(""),
    is_open: str = Form(None),  # чекбокс присылает "on" или ничего
    live_stream_url: str = Form(""),
    hero: UploadFile | None = File(None),
    regulation: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    from sqlalchemy import select
    from starlette import status

    # 1) slug + уникальность
    slug = slugify(title)
    # если такой slug уже есть — добавим метку времени
    exists = db.execute(select(Competition).where(Competition.slug == slug)).scalar_one_or_none()
    if exists:
        slug = f"{slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 2) булево из чекбокса
    is_open_bool = True if (is_open and str(is_open).lower() in {"on", "true", "1"}) else False

    # 3) подготовка серии/этапа
    stage_value = (stage or "").strip()[:64]

    series_obj: CompetitionSeries | None = None
    new_series_clean = (new_series_name or "").strip()
    if new_series_clean:
        existing = db.execute(
            select(CompetitionSeries).where(CompetitionSeries.name == new_series_clean)
        ).scalar_one_or_none()
        if existing:
            series_obj = existing
        else:
            series_obj = CompetitionSeries(name=new_series_clean)
            db.add(series_obj)
            db.flush()
    else:
        series_id_clean = (series_id or "").strip()
        if series_id_clean:
            try:
                series_obj = db.get(CompetitionSeries, int(series_id_clean))
            except ValueError:
                series_obj = None

    # 4) создание сущности
    comp = Competition(
        title=title,
        slug=slug,
        city=city,
        pool_name=pool_name,
        address=address,
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date) if end_date else None,
        is_open=is_open_bool,
        live_stream_url=live_stream_url,
        stage=stage_value,
    )

    if series_obj:
        comp.series = series_obj

    # 5) файлы — сохраняем только если реально выбран файл (есть filename)
    if hero and getattr(hero, "filename", ""):
        dest = Path(settings.MEDIA_DIR) / "heroes"
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / f"{slug}_{hero.filename}"
        with open(p, "wb") as f:
            f.write(hero.file.read())
        comp.hero_image = f"/media/heroes/{p.name}"

    if regulation and getattr(regulation, "filename", ""):
        dest = Path(settings.DOCS_DIR) / slug
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / regulation.filename
        with open(p, "wb") as f:
            f.write(regulation.file.read())
        comp.regulation_pdf = f"/docsfiles/{slug}/{p.name}"

    # 6) сохранение
    db.add(comp)
    db.commit()

    write_audit(
        db,
        current_user.id,
        "competition_create",
        object_type="competition",
        object_id=comp.id,
        meta={"title": comp.title, "slug": comp.slug},
        ip=_client_ip(request),
    )

    # 7) корректный редирект после POST (303 See Other)
    return RedirectResponse(url="/admin?tab=competitions", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/competitions/{comp_id}/series")
def admin_comp_update_series(
    request: Request,
    comp_id: int,
    stage: str = Form(""),
    series_id: str = Form(""),
    new_series_name: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    comp = db.get(Competition, comp_id)
    if not comp:
        return RedirectResponse(url="/admin?tab=competitions&series_updated=0", status_code=303)

    stage_value = (stage or "").strip()[:64]
    comp.stage = stage_value

    series_obj: CompetitionSeries | None = None
    new_series_clean = (new_series_name or "").strip()
    if new_series_clean:
        existing = db.execute(
            select(CompetitionSeries).where(CompetitionSeries.name == new_series_clean)
        ).scalar_one_or_none()
        if existing:
            series_obj = existing
        else:
            series_obj = CompetitionSeries(name=new_series_clean)
            db.add(series_obj)
            db.flush()
    else:
        series_id_clean = (series_id or "").strip()
        if series_id_clean:
            try:
                series_obj = db.get(CompetitionSeries, int(series_id_clean))
            except ValueError:
                series_obj = None

    comp.series = series_obj
    db.commit()

    write_audit(
        db,
        current_user.id,
        "competition_update",
        object_type="competition",
        object_id=comp.id,
        meta={
            "stage": comp.stage,
            "series_id": comp.series_id,
            "series_name": comp.series.name if comp.series else None,
        },
        ip=_client_ip(request),
    )

    return RedirectResponse(url="/admin?tab=competitions&series_updated=1", status_code=303)


@router.post("/admin/competitions/{competition_id}/seeding/recalculate")
def admin_comp_recalculate_seeding(
    request: Request,
    competition_id: int,
    session_name: str | None = None,
    distance: str | None = None,
    lane_count: int = 8,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    try:
        summary = recalculate_seeding(
            db,
            competition_id,
            session_name=session_name,
            distance=distance,
            lane_count=lane_count,
        )
    except SeedingError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit(
        db,
        current_user.id,
        "seeding_recalculate",
        object_type="competition",
        object_id=competition_id,
        meta={
            "session": summary.get("session"),
            "distance": summary.get("distance"),
            "lane_count": summary.get("lane_count"),
            "heats_created": summary.get("heats_created"),
            "lanes_assigned": summary.get("lanes_assigned"),
            "groups": summary.get("groups", []),
        },
        ip=_client_ip(request),
    )

    return summary


@router.post("/admin/news/create")
def admin_news_create(
    title: str = Form(...),
    body: str = Form(""),
    cover: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    from utils import slugify
    slug = slugify(title)
    n = News(title=title, slug=slug, body=body)
    if cover:
        dest = Path(settings.MEDIA_DIR) / "covers"; dest.mkdir(parents=True, exist_ok=True)
        p = dest / f"{slug}_{cover.filename}"
        with open(p, "wb") as f: f.write(cover.file.read())
        n.cover_image = f"/media/covers/{p.name}"
    db.add(n); db.commit()

    vk_settings = _load_settings(db, VK_SETTING_DEFAULTS)
    posted, message = _post_news_to_vk(n, vk_settings)
    if posted:
        return RedirectResponse(url="/admin?tab=news&news_created=1&vk_posted=1", status_code=302)
    if vk_settings.get("vk_enabled") == "1":
        # Сохраним текст ошибки в параметр запроса, чтобы подсветить администратору
        return RedirectResponse(url=f"/admin?tab=news&vk_error={requests.utils.quote(message)}", status_code=302)

    return RedirectResponse(url="/admin?tab=news&news_created=1", status_code=302)


@router.post("/admin/integrations/vk")
def admin_save_vk_settings(
    request: Request,
    vk_enabled: str | None = Form(None),
    vk_access_token: str = Form(""),
    vk_group_id: str = Form(""),
    vk_api_version: str = Form("5.199"),
    vk_message_signature: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    enabled_value = "1" if vk_enabled and str(vk_enabled).lower() in {"1", "on", "true"} else "0"
    payload = {
        "vk_enabled": enabled_value,
        "vk_access_token": vk_access_token.strip(),
        "vk_group_id": vk_group_id.strip(),
        "vk_api_version": vk_api_version.strip() or "5.199",
        "vk_message_signature": vk_message_signature.strip(),
    }
    _save_settings(db, payload)

    write_audit(
        db,
        current_user.id,
        "settings_update",
        object_type="settings",
        object_id=None,
        meta={
            "section": "vk",
            "vk_enabled": enabled_value,
            "vk_group_id": payload["vk_group_id"],
            "vk_api_version": payload["vk_api_version"],
        },
        ip=_client_ip(request),
    )
    return RedirectResponse(url="/admin?tab=integrations&vk_saved=1", status_code=303)


@router.post("/admin/pages/about")
def admin_save_about_page(
    request: Request,
    title: str = Form(""),
    subtitle: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    payload = {
        "about_title": title.strip() or ABOUT_PAGE_DEFAULTS["about_title"],
        "about_subtitle": subtitle.strip() or ABOUT_PAGE_DEFAULTS["about_subtitle"],
        "about_body": body.strip() or ABOUT_PAGE_DEFAULTS["about_body"],
    }
    _save_settings(db, payload)
    write_audit(
        db,
        current_user.id,
        "settings_update",
        object_type="settings",
        meta={"section": "about", "title": payload["about_title"]},
        ip=_client_ip(request),
    )
    return RedirectResponse(url="/admin?tab=pages&about_saved=1", status_code=303)


@router.post("/admin/competitions/{comp_id}/delete")
def admin_comp_delete(
    request: Request,
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    comp = db.get(Competition, comp_id)
    if comp:
        meta = {"title": comp.title, "slug": comp.slug}
        if comp.hero_image:
            _remove_stored_file(comp.hero_image)
        if comp.regulation_pdf:
            _remove_stored_file(comp.regulation_pdf)

        for result in list(comp.results or []):
            _remove_stored_file(result.file_path)

        for registration in list(comp.registrations or []):
            db.delete(registration)

        db.delete(comp)
        db.commit()
        write_audit(
            db,
            current_user.id,
            "competition_delete",
            object_type="competition",
            object_id=comp_id,
            meta=meta,
            ip=_client_ip(request),
        )

    return RedirectResponse(url="/admin?tab=competitions", status_code=303)


@router.post("/admin/news/{news_id}/delete")
def admin_news_delete(
    news_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = db.get(News, news_id)
    if item:
        if item.cover_image:
            _remove_stored_file(item.cover_image)
        db.delete(item)
        db.commit()

    return RedirectResponse(url="/admin?tab=news", status_code=303)


@router.post("/admin/results/{result_id}/delete")
def admin_result_delete(
    request: Request,
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    result = db.get(ResultFile, result_id)
    if result:
        meta = {"kind": result.kind, "file_path": result.file_path}
        _remove_stored_file(result.file_path)
        db.delete(result)
        db.commit()
        write_audit(
            db,
            current_user.id,
            "result_delete",
            object_type="result",
            object_id=result_id,
            meta=meta,
            ip=_client_ip(request),
        )

    return RedirectResponse(url="/admin?tab=competitions", status_code=303)

@router.get("/admin/init", include_in_schema=False)
def admin_init(db: Session = Depends(get_db)):
    from sqlalchemy import select

    admin_role = db.execute(select(Role).where(Role.name == "admin")).scalar_one_or_none()
    if not admin_role:
        admin_role = Role(name="admin", description="Администратор")
        db.add(admin_role)
        db.flush()

    user = db.query(User).filter(User.email == "admin@local").first()
    if not user:
        user = User(
            email="admin@local",
            full_name="Admin",
            hashed_password=hash_password("Admin#2025!"),
            is_admin=True,
        )
        if admin_role:
            user.roles.append(admin_role)
        db.add(user)
        db.commit()
    else:
        if admin_role and admin_role not in user.roles:
            user.roles.append(admin_role)
            db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@router.get("/admin/registrations", response_class=HTMLResponse)
def admin_reg_list(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    status_param = request.query_params.get("status", "active").lower()
    if status_param not in {"active", "trash"}:
        status_param = "active"
    show_deleted = status_param == "trash"

    search_query = request.query_params.get("q", "").strip()
    like_pattern = None
    if search_query:
        escaped = search_query.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
        like_pattern = f"%{escaped}%"

    query = (
        select(TeamRegistration)
        .options(
            selectinload(TeamRegistration.competition),
            selectinload(TeamRegistration.participants),
        )
        .order_by(TeamRegistration.created_at.desc())
    )

    if show_deleted:
        query = query.where(TeamRegistration.is_deleted.is_(True))
    else:
        query = query.where(TeamRegistration.is_deleted.is_(False))

    if like_pattern:
        escape_char = "\\"
        query = query.where(
            or_(
                TeamRegistration.team_name.ilike(like_pattern, escape=escape_char),
                TeamRegistration.representative_name.ilike(like_pattern, escape=escape_char),
                TeamRegistration.representative_email.ilike(like_pattern, escape=escape_char),
            )
        )

    regs = db.execute(query).scalars().all()

    grouped: dict[int | None, dict[str, object]] = {}
    order: list[int | None] = []
    for reg in regs:
        comp = reg.competition
        key = comp.id if comp else None
        if key not in grouped:
            grouped[key] = {"competition": comp, "registrations": []}
            order.append(key)
        grouped[key]["registrations"].append(reg)

    grouped_regs = [grouped[key] for key in order]

    active_count = db.scalar(
        select(func.count()).select_from(TeamRegistration).where(TeamRegistration.is_deleted.is_(False))
    ) or 0
    trash_count = db.scalar(
        select(func.count()).select_from(TeamRegistration).where(TeamRegistration.is_deleted.is_(True))
    ) or 0

    current_query = request.url.query
    return_to = request.url.path + (f"?{current_query}" if current_query else "")

    return request.app.state.templates.TemplateResponse(
        "admin/registrations.html",
        {
            "request": request,
            "grouped_registrations": grouped_regs,
            "current_status": status_param,
            "search_query": search_query,
            "active_count": active_count,
            "trash_count": trash_count,
            "return_to": return_to,
        },
    )


@router.post("/admin/registrations/clear")
def admin_reg_clear(
    request: Request,
    target: str = Form("trash"),
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    redirect_url = return_to or "/admin/registrations"
    if target == "active":
        regs = (
            db.execute(select(TeamRegistration).where(TeamRegistration.is_deleted.is_(False)))
            .scalars()
            .all()
        )
        if regs:
            now = datetime.utcnow()
            affected_ids = []
            for reg in regs:
                reg.is_deleted = True
                reg.deleted_at = now
                _sync_quick_registration_status(db, reg, delete_quick=True)
                affected_ids.append(reg.id)
            db.commit()
            write_audit(
                db,
                current_user.id,
                "registration_bulk_soft_delete",
                object_type="registration",
                meta={"target": target, "affected_ids": affected_ids},
                ip=_client_ip(request),
            )
    elif target == "trash":
        regs = (
            db.execute(select(TeamRegistration).where(TeamRegistration.is_deleted.is_(True)))
            .scalars()
            .all()
        )
        if regs:
            affected_ids = []
            for reg in regs:
                _sync_quick_registration_status(db, reg, delete_quick=True)
                affected_ids.append(reg.id)
                db.delete(reg)
            db.commit()
            write_audit(
                db,
                current_user.id,
                "registration_bulk_purge",
                object_type="registration",
                meta={"target": target, "affected_ids": affected_ids},
                ip=_client_ip(request),
            )
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/admin/registrations/{reg_id}/approve")
def admin_reg_approve(
    request: Request,
    reg_id: int,
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    reg = db.get(TeamRegistration, reg_id)
    if reg and not reg.is_deleted:
        comp = reg.competition or db.get(Competition, reg.competition_id)
        reg.status = "approved"
        _sync_quick_registration_status(db, reg, "approved")
        comp_id = reg.competition_id
        db.commit()
        write_audit(
            db,
            current_user.id,
            "registration_approve",
            object_type="registration",
            object_id=reg.id,
            meta={"competition_id": comp_id},
            ip=_client_ip(request),
        )
        if reg.representative_email:
            subject, body = build_registration_approved_email(reg, comp)
            try:
                send_email(reg.representative_email, subject, body)
            except Exception:
                pass
    redirect_url = return_to or "/admin/registrations"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/admin/registrations/{reg_id}/reject")
def admin_reg_reject(
    request: Request,
    reg_id: int,
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    reg = db.get(TeamRegistration, reg_id)
    if reg and not reg.is_deleted:
        comp = reg.competition or db.get(Competition, reg.competition_id)
        reg.status = "rejected"
        _sync_quick_registration_status(db, reg, "rejected")
        comp_id = reg.competition_id
        db.commit()
        write_audit(
            db,
            current_user.id,
            "registration_reject",
            object_type="registration",
            object_id=reg.id,
            meta={"competition_id": comp_id},
            ip=_client_ip(request),
        )
        if reg.representative_email:
            subject = f"Заявка отклонена: {comp.title if comp else 'соревнование'}"
            body = (
                "<p>Здравствуйте, {name}!</p>"
                "<p>К сожалению, заявка {team_summary} на соревнование <b>{comp}</b> была отклонена.</p>"
                "<p>Свяжитесь с организаторами для уточнения деталей.</p>"
            ).format(
                name=reg.representative_name,
                team_summary=reg.team_summary,
                comp=comp.title if comp else "",
            )
            try:
                send_email(reg.representative_email, subject, body)
            except Exception:
                pass
    redirect_url = return_to or "/admin/registrations"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/admin/registrations/{reg_id}/delete")
def admin_reg_delete(
    request: Request,
    reg_id: int,
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    reg = db.get(TeamRegistration, reg_id)
    if reg and not reg.is_deleted:
        reg.is_deleted = True
        reg.deleted_at = datetime.utcnow()
        _sync_quick_registration_status(db, reg, delete_quick=True)
        comp_id = reg.competition_id
        db.commit()
        write_audit(
            db,
            current_user.id,
            "registration_soft_delete",
            object_type="registration",
            object_id=reg.id,
            meta={"competition_id": comp_id},
            ip=_client_ip(request),
        )
    redirect_url = return_to or "/admin/registrations"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/admin/registrations/{reg_id}/restore")
def admin_reg_restore(
    request: Request,
    reg_id: int,
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    reg = db.get(TeamRegistration, reg_id)
    if reg and reg.is_deleted:
        reg.is_deleted = False
        reg.deleted_at = None
        comp_id = reg.competition_id
        db.commit()
        write_audit(
            db,
            current_user.id,
            "registration_restore",
            object_type="registration",
            object_id=reg.id,
            meta={"competition_id": comp_id},
            ip=_client_ip(request),
        )
    redirect_url = return_to or "/admin/registrations"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/admin/registrations/{reg_id}/purge")
def admin_reg_purge(
    request: Request,
    reg_id: int,
    return_to: str = Form("/admin/registrations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    reg = db.get(TeamRegistration, reg_id)
    if reg and reg.is_deleted:
        _sync_quick_registration_status(db, reg, delete_quick=True)
        comp_id = reg.competition_id
        db.delete(reg)
        db.commit()
        write_audit(
            db,
            current_user.id,
            "registration_purge",
            object_type="registration",
            object_id=reg_id,
            meta={"competition_id": comp_id},
            ip=_client_ip(request),
        )
    redirect_url = return_to or "/admin/registrations"
    return RedirectResponse(url=redirect_url, status_code=303)
@router.get("/admin/registrations/export.xlsx")
def admin_reg_export(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    # формируем книгу
    wb = Workbook()
    ws = wb.active
    ws.title = "Registrations"

    # шапка
    headers = [
        "Регистрация ID", "Старт", "Слаг", "Команда", "Статус", "Создано",
        "Представитель", "Телефон", "Email",
        "Фамилия", "Имя", "Отчество", "Пол", "Дата рождения", "Категория", "Дистанция"
    ]
    ws.append(headers)

    # данные
    regs = (
        db.execute(
            select(TeamRegistration)
            .where(TeamRegistration.is_deleted.is_(False))
            .order_by(TeamRegistration.created_at.desc())
        )
        .scalars()
        .all()
    )

    for reg in regs:
        comp = db.get(Competition, reg.competition_id)
        for p in (reg.participants or [None]):
            ws.append([
                reg.id,
                comp.title if comp else "",
                comp.slug if comp else "",
                reg.team_summary,
                reg.status,
                reg.created_at.strftime("%Y-%m-%d %H:%M"),
                reg.representative_name,
                reg.representative_phone,
                reg.representative_email,
                getattr(p, "last_name", ""),
                getattr(p, "first_name", ""),
                getattr(p, "middle_name", ""),
                getattr(p, "gender", ""),
                getattr(p, "birth_date", "").strftime("%Y-%m-%d") if getattr(p, "birth_date", None) else "",
                getattr(p, "age_category", ""),
                getattr(p, "distance", ""),
            ])

    # отдаём файл
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="registrations.xlsx"'}
    )
