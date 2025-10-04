"""WSGI adapter for running the FastAPI application on hosts without ASGI support."""
from __future__ import annotations

import os

from asgiref.wsgi import ASGItoWSGI

# Ensure the app picks up the same settings module when imported by Passenger.
os.environ.setdefault("SETTINGS_MODULE", "settings")

from .app import app as asgi_app  # noqa: E402  isort:skip

application = ASGItoWSGI(asgi_app)
