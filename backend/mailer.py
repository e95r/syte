from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_NAME = "SwimReg"
FROM_ADDR = "no-reply@swimreg.local"


_templates_dir = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_email(template_name: str, context: dict[str, Any]) -> str:
    template = _env.get_template(f"emails/{template_name}")
    return template.render(**context)


def send_email(to: str, subject: str, html: str) -> None:
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((FROM_NAME, FROM_ADDR))
    msg["To"] = to

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(FROM_ADDR, [to], msg.as_string())


def build_registration_approved_email(registration: Any, competition: Any) -> tuple[str, str]:
    """Return subject and HTML body for an approved registration notification."""

    is_team = getattr(registration, "is_team_registration", False)
    template_name = (
        "registration_approved_team.html"
        if is_team
        else "registration_approved_single.html"
    )
    subject = "Ваша заявка команды одобрена" if is_team else "Ваша заявка одобрена"
    html = _render_email(
        template_name,
        {
            "registration": registration,
            "competition": competition,
        },
    )
    return subject, html
