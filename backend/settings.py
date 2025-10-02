from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent
ENV_DIR = BASE_DIR / "env"


def _env_file_candidates() -> Tuple[Path, ...]:
    """Return configuration files ordered by precedence.

    The loader looks for environment-specific files inside ``backend/env`` and
    falls back to a project-level ``.env``. Files that do not exist are ignored
    by ``pydantic-settings`` so that developers can decide which ones to
    provide locally. ``.env.prod`` is always evaluated last and therefore has
    the highest priority when present, matching the production-first approach
    described in the deployment checklist.
    """

    env_name = os.getenv("ENV") or os.getenv("APP_ENV")
    candidates: Iterable[Path] = (
        ENV_DIR / ".env",
        ENV_DIR / ".env.local",
        *(
            (ENV_DIR / f".env.{env_name}",)
            if env_name
            else ()
        ),
        ENV_DIR / ".env.dev",
        ENV_DIR / ".env.stage",
        ENV_DIR / ".env.prod",
        BASE_DIR / ".env",
    )

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            unique_candidates.append(path)
            seen.add(path)
    return tuple(unique_candidates)


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_env_file_candidates(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "SwimReg"
    ENV: str = "dev"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800

    MEDIA_DIR: str = str(BASE_DIR / "storage" / "media")
    DOCS_DIR: str = str(BASE_DIR / "storage" / "docs")
    RESULTS_DIR: str = str(BASE_DIR / "storage" / "results")
    STATIC_DIR: str = str(BASE_DIR / "static")

    LOG_DIR: str = str(BASE_DIR / "logs")
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 5 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_PREFIX: str = "swimreg:cache"
    RATE_LIMIT_DEFAULT: str = "200/minute"

    LANGUAGE_COOKIE_NAME: str = "swimreg_lang"
    DEFAULT_LANGUAGE: str = "ru"
    LANGUAGES: Dict[str, str] = {"ru": "Русский", "en": "English"}
    LOCALE_DIR: str = str(BASE_DIR / "locales")

    SMTP_HOST: str = "mailhog"
    SMTP_PORT: int = 1025
    SMTP_TLS: bool = False
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    FROM_EMAIL: str = "no-reply@swimreg.local"
    ADMIN_EMAIL: str = "organizer@swimreg.local"

    S3_ENDPOINT: str = "http://minio:9000"
    S3_BUCKET: str = "swimreg"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"


def ensure_directories(settings_obj: "Settings") -> None:
    for path in [
        settings_obj.MEDIA_DIR,
        settings_obj.DOCS_DIR,
        settings_obj.RESULTS_DIR,
        settings_obj.STATIC_DIR,
        settings_obj.LOG_DIR,
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)


settings = Settings()
ensure_directories(settings)
