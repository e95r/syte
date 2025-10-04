"""Entry point for running the FastAPI backend on Beget shared hosting."""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _detect_project_root() -> Path:
    """Locate the backend package regardless of the file's location."""

    candidates = [
        BASE_DIR,
        BASE_DIR.parent,
        BASE_DIR.parent.parent,
    ]
    for candidate in candidates:
        backend_dir = candidate / "backend"
        if backend_dir.exists():
            return backend_dir
    raise RuntimeError("Cannot find 'backend' directory next to passenger_wsgi.py")


PROJECT_ROOT = _detect_project_root()

# Ensure that the backend package is importable when Passenger loads this file.
for path in {PROJECT_ROOT, PROJECT_ROOT.parent}:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backend.wsgi import application  # noqa: E402  isort:skip
