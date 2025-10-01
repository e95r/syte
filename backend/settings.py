from pathlib import Path
from typing import Dict

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    APP_NAME: str = "SwimReg"
    ENV: str = "dev"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    DATABASE_URL: str

    MEDIA_DIR: str
    DOCS_DIR: str
    RESULTS_DIR: str
    STATIC_DIR: str

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
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)


settings = Settings()
ensure_directories(settings)
