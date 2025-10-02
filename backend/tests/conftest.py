from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Stable directories for media/documents to keep tests hermetic.
_TEST_FS_ROOT = Path(tempfile.gettempdir()) / "swimreg-test-artifacts"
for name in ("media", "docs", "results", "static", "logs"):
    target = _TEST_FS_ROOT / name
    target.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MEDIA_DIR", str((_TEST_FS_ROOT / "media").resolve()))
os.environ.setdefault("DOCS_DIR", str((_TEST_FS_ROOT / "docs").resolve()))
os.environ.setdefault("RESULTS_DIR", str((_TEST_FS_ROOT / "results").resolve()))
os.environ.setdefault("STATIC_DIR", str((_TEST_FS_ROOT / "static").resolve()))
os.environ.setdefault("LOG_DIR", str((_TEST_FS_ROOT / "logs").resolve()))

from db import Base  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Provide an isolated SQLite session per test with a dedicated database file."""

    db_path = tmp_path / "test.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


__all__ = ["db_session"]
