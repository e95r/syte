import gettext
from functools import lru_cache
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.coder import PickleCoder

from db import Base, engine
from limiter import limiter
from routers import (
    account as account_router,
    admin,
    auth,
    calendar as calendar_router,
    data_io,
    public,
    reports,
    registrations,
    results,
)
from settings import settings

app = FastAPI(title=settings.APP_NAME)
instrumentator = Instrumentator()
instrumentator.instrument(app)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/storage", StaticFiles(directory="storage"), name="storage")
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")
app.mount("/docsfiles", StaticFiles(directory=settings.DOCS_DIR), name="docsfiles")
app.mount("/results", StaticFiles(directory=settings.RESULTS_DIR), name="results")

# Templates
templates = Jinja2Templates(directory="templates")
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_translations(gettext.NullTranslations(), newstyle=True)
templates.env.globals.update(
    {
        "available_languages": settings.LANGUAGES,
        "default_language": settings.DEFAULT_LANGUAGE,
        "language_cookie_name": settings.LANGUAGE_COOKIE_NAME,
    }
)
app.state.templates = templates


@lru_cache(maxsize=8)
def _load_translations(language: str) -> gettext.NullTranslations:
    locale_dir = Path(settings.LOCALE_DIR)
    try:
        return gettext.translation("messages", localedir=locale_dir, languages=[language])
    except FileNotFoundError:
        return gettext.NullTranslations()


@app.middleware("http")
async def apply_i18n(request: Request, call_next):
    language = request.cookies.get(settings.LANGUAGE_COOKIE_NAME, settings.DEFAULT_LANGUAGE)
    if language not in settings.LANGUAGES:
        language = settings.DEFAULT_LANGUAGE

    translations = _load_translations(language)
    templates.env.install_gettext_translations(translations, newstyle=True)
    request.state.language = language
    request.state.gettext = translations.gettext

    response = await call_next(request)
    return response

# DB init
Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def on_startup() -> None:
    redis = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    app.state.redis = redis
    FastAPICache.init(
        RedisBackend(redis),
        prefix=settings.CACHE_PREFIX,
        coder=PickleCoder(),
    )

    instrumentator.expose(app, include_in_schema=False)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    redis = getattr(app.state, "redis", None)
    if redis:
        await redis.close()


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/home")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(content=b"", media_type="image/x-icon")


# Routers
app.include_router(calendar_router.router, tags=["calendar"])
app.include_router(auth.router, tags=["auth"])
app.include_router(account_router.router, tags=["account"])
app.include_router(public.router, tags=["public"])
app.include_router(admin.router, tags=["admin"])
app.include_router(registrations.router, tags=["registration"])
app.include_router(results.router, tags=["results"])
