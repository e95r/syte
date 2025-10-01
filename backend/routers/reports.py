from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from weasyprint import HTML

from db import get_db
from models import Competition, Participant, TeamRegistration


router = APIRouter(prefix="/reports")


def _format_gender(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"m", "male", "man"}:
        return "М"
    if normalized in {"f", "female", "woman"}:
        return "Ж"
    return value or "—"


@router.get("/startlist/{competition_id}.pdf")
def startlist_pdf(
    competition_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    competition = db.execute(
        select(Competition)
        .options(
            selectinload(Competition.registrations)
            .selectinload(TeamRegistration.participants)
        )
        .where(Competition.id == competition_id)
    ).scalar_one_or_none()

    if competition is None:
        raise HTTPException(status_code=404, detail="Соревнование не найдено")

    status_map = {
        "approved": "Подтверждено",
        "pending": "Ожидает подтверждения",
        "rejected": "Отклонено",
    }

    active_registrations: list[TeamRegistration] = [
        registration
        for registration in competition.registrations
        if not registration.is_deleted
    ]

    active_registrations.sort(
        key=lambda reg: (
            0 if reg.status == "approved" else 1,
            (reg.team_name or "").lower(),
            reg.id,
        )
    )

    teams_payload: list[dict[str, object]] = []
    distance_totals: defaultdict[str, int] = defaultdict(int)

    for registration in active_registrations:
        participants_payload: list[dict[str, str]] = []
        participants: list[Participant] = list(registration.participants)
        participants.sort(
            key=lambda participant: (
                (participant.distance or "").lower(),
                participant.last_name.lower(),
                participant.first_name.lower(),
            )
        )

        for participant in participants:
            full_name = " ".join(
                filter(
                    None,
                    [
                        participant.last_name.strip(),
                        participant.first_name.strip(),
                        participant.middle_name.strip(),
                    ],
                )
            )
            birth_date = participant.birth_date.strftime("%d.%m.%Y")
            distance_label = participant.distance.strip() or "—"

            participants_payload.append(
                {
                    "full_name": full_name,
                    "gender": _format_gender(participant.gender),
                    "birth_date": birth_date,
                    "age_category": participant.age_category,
                    "distance": distance_label,
                }
            )

            distance_totals[distance_label] += 1

        teams_payload.append(
            {
                "team_name": registration.team_name or "Одиночный участник",
                "team_summary": registration.team_summary,
                "representative_name": registration.representative_name,
                "representative_phone": registration.representative_phone,
                "representative_email": registration.representative_email,
                "status": status_map.get(registration.status, registration.status),
                "participants": participants_payload,
            }
        )

    distance_summary = sorted(distance_totals.items(), key=lambda item: item[0].lower())
    total_participants = sum(distance_totals.values())

    template = request.app.state.templates.get_template("reports/startlist.html")
    html = template.render(
        {
            "request": request,
            "competition": competition,
            "teams": teams_payload,
            "distance_summary": distance_summary,
            "total_participants": total_participants,
            "generated_at": datetime.utcnow(),
        }
    )

    pdf_bytes = HTML(string=html, base_url=str(request.base_url)).write_pdf()
    filename = f"startlist-{competition_id}.pdf"

    headers = {
        "Content-Disposition": f"inline; filename={filename}",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
