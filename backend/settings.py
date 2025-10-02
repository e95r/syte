from pathlib import Path
from typing import Dict

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    APP_NAME: str = "SwimReg"
    APP_VERSION: str = "0.1.0"
    ENV: str = "dev"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_SECRET: str | None = None
    REFRESH_TOKEN_MAX_SESSIONS: int = 5
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800

    MEDIA_DIR: str
    DOCS_DIR: str
    RESULTS_DIR: str
    STATIC_DIR: str

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

    class Config:
        env_file = ".env"


def ensure_directories(settings_obj: "Settings") -> None:
    for path in [
        settings_obj.MEDIA_DIR,
        settings_obj.DOCS_DIR,
        settings_obj.RESULTS_DIR,
        settings_obj.STATIC_DIR,
        settings_obj.LOG_DIR,
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)


settings = Settings()  # type: ignore[call-arg]
ensure_directories(settings)
