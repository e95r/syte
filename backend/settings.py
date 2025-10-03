from pathlib import Path
from typing import Dict

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "SwimReg"
    APP_VERSION: str = "0.1.0"
    ENV: str = "dev"

    SECRET_KEY: str = Field(..., min_length=1)
    DATABASE_URL: str = Field(..., min_length=1)

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_SECRET: str | None = None
    REFRESH_TOKEN_MAX_SESSIONS: int = 5

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800

    MEDIA_DIR: str = str(BASE_DIR / "storage" / "media")
    DOCS_DIR: str = str(BASE_DIR / "storage" / "docs")
    RESULTS_DIR: str = str(BASE_DIR / "storage" / "results")
    STATIC_DIR: str = str(BASE_DIR / "storage" / "static")

    LOG_DIR: str = str(BASE_DIR / "logs")
    LOG_LEVEL: str = "INFO"
    REQUEST_ID_HEADER: str = "X-Request-ID"
    REQUEST_LOG_EXCLUDE_PATHS: tuple[str, ...] = ("/health", "/healthz")
    PROXY_TRUSTED_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "swimproxy")

    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_PREFIX: str = "swimreg:cache"
    RATE_LIMIT_DEFAULT: str = "200/minute"

    LANGUAGE_COOKIE_NAME: str = "swimreg_lang"
    DEFAULT_LANGUAGE: str = "ru"
    LANGUAGES: Dict[str, str] = {"ru": "Русский"}
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

    @field_validator("PROXY_TRUSTED_HOSTS", mode="before")
    @classmethod
    def _parse_proxy_hosts(cls, value: object) -> tuple[str, ...]:
        """Normalise trusted proxy hosts from env variables."""

        if value is None:
            return ("127.0.0.1", "localhost", "swimproxy")
        if isinstance(value, str):
            hosts = [item.strip() for item in value.split(",") if item.strip()]
            return tuple(hosts) if hosts else ("127.0.0.1", "localhost", "swimproxy")
        if isinstance(value, (list, tuple, set)):
            hosts = [str(item).strip() for item in value if str(item).strip()]
            return tuple(hosts) if hosts else ("127.0.0.1", "localhost", "swimproxy")
        raise TypeError("PROXY_TRUSTED_HOSTS must be a string or an iterable of strings")


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
