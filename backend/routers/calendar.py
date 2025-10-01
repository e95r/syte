from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
import json

from db import get_db
from models import Competition

router = APIRouter()

@router.get("/calendar")
def calendar_page(request: Request, db: Session = Depends(get_db)):
    # Берём соревнования (можно фильтровать по диапазону дат при желании)
    comps = db.execute(
        select(Competition)
        .options(selectinload(Competition.series))
        .order_by(Competition.start_date.asc())
    ).scalars().all()

    events = []
    for c in comps:
        if not c.start_date:
            continue
        date_iso = c.start_date.date().isoformat()
        # классификация типа события для цветной метки
        kind = "other"
        stage_value = (getattr(c, "stage", "") or "").strip()
        stage_lower = stage_value.lower()
        if stage_lower:
            if "четверть" in stage_lower:
                kind = "qual"
            elif any(word in stage_lower for word in ["квали", "отбор", "серия", "group"]):
                kind = "qual"
            elif "финал" in stage_lower:
                kind = "final"
            elif "semi" in stage_lower or "полуфин" in stage_lower:
                kind = "final"
        elif c.end_date and c.end_date.date() != c.start_date.date():
            kind = "final"
        events.append({
            "date": date_iso,
            "title": c.title or "",
            "kind": kind,                   # "qual" / "final" / "other"
            "city": getattr(c, "city", "") or "",
            "link": f"/competitions/{c.slug}",
            "stage": stage_value,
            "series": c.series.name if getattr(c, "series", None) else "",
        })

    events_json = json.dumps(events, ensure_ascii=False)
    return request.app.state.templates.TemplateResponse(
        "calendar.html",
        {"request": request, "events_json": events_json},
    )
