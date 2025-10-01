from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from models import User
from security import require_roles
from utils import write_audit
from utils_lenex import (
    LenexError,
    export_lenex,
    export_registrations_csv,
    export_results_csv,
    import_lenex,
    import_registrations_csv,
    import_results_csv,
)

router = APIRouter(prefix="/data", tags=["data-io"])


@router.post("/import/lenex", status_code=status.HTTP_201_CREATED)
async def import_lenex_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    try:
        payload = await file.read()
    except Exception as exc:  # pragma: no cover - FastAPI handles IO
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {exc}") from exc

    if not payload:
        raise HTTPException(status_code=400, detail="Пустой файл LENEX")

    try:
        competition = import_lenex(db, payload)
    except LenexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit(
        db=db,
        user_id=current_user.id,
        action="lenex_import",
        object_type="competition",
        object_id=competition.id,
        meta={"filename": file.filename},
        ip=request.client.host if request.client else None,
    )

    return {
        "status": "ok",
        "competition_id": competition.id,
        "competition_slug": competition.slug,
    }


@router.get("/export/lenex/{competition_id}")
def export_lenex_endpoint(
    competition_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    try:
        payload = export_lenex(db, competition_id)
    except LenexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = f"competition-{competition_id}.lef"
    response = StreamingResponse(BytesIO(payload), media_type="application/xml")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"

    write_audit(
        db=db,
        user_id=current_user.id,
        action="lenex_export",
        object_type="competition",
        object_id=competition_id,
        meta={"filename": filename},
        ip=request.client.host if request.client else None,
    )
    return response


@router.post("/import/csv", status_code=status.HTTP_201_CREATED)
async def import_csv_endpoint(
    request: Request,
    competition_id: int = Form(...),
    csv_type: str = Form(..., alias="type"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    try:
        payload = await file.read()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {exc}") from exc

    if not payload:
        raise HTTPException(status_code=400, detail="Пустой CSV файл")

    csv_type = (csv_type or "").strip().lower()
    if csv_type not in {"registrations", "results"}:
        raise HTTPException(status_code=400, detail="Недопустимый тип CSV (registrations|results)")

    try:
        if csv_type == "registrations":
            competition = import_registrations_csv(db, competition_id, payload)
        else:
            competition = import_results_csv(db, competition_id, payload)
    except LenexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit(
        db=db,
        user_id=current_user.id,
        action="csv_import",
        object_type="competition",
        object_id=competition.id,
        meta={"type": csv_type, "filename": file.filename},
        ip=request.client.host if request.client else None,
    )

    return {
        "status": "ok",
        "competition_id": competition.id,
        "type": csv_type,
    }


@router.get("/export/csv/{competition_id}")
def export_csv_endpoint(
    competition_id: int,
    request: Request,
    csv_type: str = Query(..., alias="type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    csv_type = (csv_type or "").strip().lower()
    if csv_type not in {"registrations", "results"}:
        raise HTTPException(status_code=400, detail="Недопустимый тип CSV (registrations|results)")

    try:
        if csv_type == "registrations":
            payload = export_registrations_csv(db, competition_id)
            filename = f"competition-{competition_id}-registrations.csv"
        else:
            payload = export_results_csv(db, competition_id)
            filename = f"competition-{competition_id}-results.csv"
    except LenexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response = StreamingResponse(BytesIO(payload), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"

    write_audit(
        db=db,
        user_id=current_user.id,
        action="csv_export",
        object_type="competition",
        object_id=competition_id,
        meta={"type": csv_type, "filename": filename},
        ip=request.client.host if request.client else None,
    )
    return response
