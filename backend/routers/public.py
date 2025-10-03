from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload
from starlette.requests import Request
from sqlalchemy import select, desc

from db import get_db
from models import AppSetting, Competition, News, ResultFile
from settings import settings

router = APIRouter()

@router.on_event("startup")
def _startup():
    from app import app
    router.templates = app.state.templates

@router.get("/home", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    comps = db.execute(
        select(Competition)
        .options(selectinload(Competition.series))
        .order_by(Competition.start_date)
    ).scalars().all()
    news = db.execute(select(News).order_by(desc(News.published_at)).limit(5)).scalars().all()
    return request.app.state.templates.TemplateResponse("index.html", {"request": request, "comps": comps, "news": news})

@router.get("/competitions", response_class=HTMLResponse)
def competitions(request: Request, db: Session = Depends(get_db)):
    comps = db.execute(
        select(Competition)
        .options(selectinload(Competition.series))
        .order_by(Competition.start_date)
    ).scalars().all()
    return request.app.state.templates.TemplateResponse("competitions.html", {"request": request, "comps": comps})

@router.get("/competitions/{slug}", response_class=HTMLResponse)
def competition_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    comp = db.execute(
        select(Competition)
        .options(selectinload(Competition.series))
        .where(Competition.slug == slug)
    ).scalar_one_or_none()
    results = db.execute(select(ResultFile).where(ResultFile.competition_id == comp.id)).scalars().all() if comp else []
    return request.app.state.templates.TemplateResponse("competition_detail.html", {"request": request, "c": comp, "results": results})

@router.get("/calendar", response_class=HTMLResponse)
def calendar(request: Request, db: Session = Depends(get_db)):
    comps = db.execute(select(Competition).order_by(Competition.start_date)).scalars().all()
    return request.app.state.templates.TemplateResponse("calendar.html", {"request": request, "comps": comps})

@router.get("/news", response_class=HTMLResponse)
def news_list(request: Request, db: Session = Depends(get_db)):
    items = db.execute(select(News).order_by(News.published_at.desc())).scalars().all()
    return request.app.state.templates.TemplateResponse("news.html", {"request": request, "items": items})

@router.get("/stats", response_class=HTMLResponse)
def stats(request: Request, db: Session = Depends(get_db)):
    comps = db.execute(
        select(Competition)
        .options(selectinload(Competition.series))
        .order_by(Competition.start_date.desc())
    ).scalars().all()
    return request.app.state.templates.TemplateResponse("stats.html", {"request": request, "comps": comps})

@router.get("/contacts", response_class=HTMLResponse)
def contacts(request: Request):
    return request.app.state.templates.TemplateResponse("contacts.html", {"request": request})


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    defaults = {
        "about_title": "О клубе",
        "about_subtitle": "Наша команда объединяет любителей плавания и соревнований.",
        "about_body": (
            "<p>Мы организуем тренировки, старты и мероприятия для пловцов любого уровня."\
            " Присоединяйтесь, чтобы расти, соревноваться и находить единомышленников.</p>"
        ),
    }
    rows = db.execute(
        select(AppSetting).where(AppSetting.key.in_(defaults.keys()))
    ).scalars().all()
    settings_map = defaults.copy()
    for row in rows:
        settings_map[row.key] = row.value

    context = {
        "request": request,
        "title": settings_map["about_title"],
        "subtitle": settings_map["about_subtitle"],
        "body": settings_map["about_body"],
    }
    return request.app.state.templates.TemplateResponse("about.html", context)


@router.get("/lang/{lang_code}", name="set_language")
def set_language(lang_code: str, request: Request):
    lang_code = lang_code.lower()
    if lang_code not in settings.LANGUAGES:
        lang_code = settings.DEFAULT_LANGUAGE

    redirect_target = request.query_params.get("next") or request.headers.get("referer") or "/home"
    parsed = urlparse(redirect_target)
    if parsed.netloc and parsed.netloc != request.url.hostname:
        redirect_target = "/home"
    if not redirect_target.startswith("/"):
        redirect_target = "/home"

    response = RedirectResponse(redirect_target, status_code=303)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        lang_code,
        max_age=30 * 24 * 60 * 60,
        httponly=False,
        samesite="lax",
    )
    return response
