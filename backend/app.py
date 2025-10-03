import gettext
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.middleware.sessions import SessionMiddleware


from db import Base, engine
from limiter import limiter
from logging_config import bind_request_id, reset_request_id, setup_logging
from routers import (
    account as account_router,
    admin,
    auth,
    calendar as calendar_router,
    public,
    registrations,
    results,
)
from settings import settings

setup_logging()
logger = logging.getLogger("swimreg.app")
request_logger = logging.getLogger("swimreg.requests")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_,.:]{4,128}$")
_EXCLUDED_PATHS = set(settings.REQUEST_LOG_EXCLUDE_PATHS)


def _resolve_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "-"


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
instrumentator = Instrumentator()
instrumentator.instrument(app)

app.state.limiter = limiter
rate_limit_handler = cast(
    Callable[[Request, Exception], Response],
    _rate_limit_exceeded_handler,
)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
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
install_translations = getattr(templates.env, "install_gettext_translations")
install_translations(gettext.NullTranslations(), newstyle=True)
templates.env.globals.update(
    {
        "available_languages": settings.LANGUAGES,
        "default_language": settings.DEFAULT_LANGUAGE,
        "language_cookie_name": settings.LANGUAGE_COOKIE_NAME,
    }
)
app.state.templates = templates


@app.get("/debug/whoami")
async def debug_whoami(request: Request) -> dict[str, str | None]:
    """Expose proxy-resolved client information for troubleshooting."""

    client_host = request.client.host if request.client else None
    headers = request.headers

    return {
        "client_host": client_host,
        "url_scheme": request.url.scheme,
        "x_forwarded_for": headers.get("x-forwarded-for"),
        "x_forwarded_proto": headers.get("x-forwarded-proto"),
        "x_forwarded_host": headers.get("x-forwarded-host"),
        "x_forwarded_port": headers.get("x-forwarded-port"),
    }


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
    install_translations = getattr(templates.env, "install_gettext_translations")
    install_translations(translations, newstyle=True)
    request.state.language = language
    request.state.gettext = translations.gettext

    response = await call_next(request)
    return response


@app.middleware("http")
async def request_context(request: Request, call_next):
    if request.url.path in _EXCLUDED_PATHS:
        return await call_next(request)

    raw_request_id = request.headers.get(settings.REQUEST_ID_HEADER, "")
    request_id = raw_request_id if _REQUEST_ID_PATTERN.match(raw_request_id) else uuid4().hex
    token = bind_request_id(request_id)
    request.state.request_id = request_id

    start_time = time.perf_counter()
    client_ip = _resolve_client_ip(request)
    user_agent = request.headers.get("user-agent", "-")

    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - defensive logging path
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        status_code = getattr(exc, "status_code", 500)
        request_logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_agent": user_agent,
            },
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers.setdefault(settings.REQUEST_ID_HEADER, request_id)
        content_length = response.headers.get("content-length")
        request_logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "content_length": content_length,
            },
        )
        return response
    finally:
        reset_request_id(token)


# DB init
Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        "startup_complete",
        extra={
            "environment": settings.ENV,
            "version": settings.APP_VERSION,
        },
    )

    instrumentator.expose(app, include_in_schema=False)


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


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}
