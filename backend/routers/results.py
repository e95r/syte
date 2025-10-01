from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from pathlib import Path

from db import get_db
from models import Competition, ResultFile
from security import admin_required
from settings import settings

router = APIRouter()

@router.post("/admin/competitions/{slug}/results/upload")
def upload_results(
    slug: str,
    label: str = Form("Итог"),
    kind: str = Form("pdf"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(admin_required)
):
    comp = db.execute(select(Competition).where(Competition.slug == slug)).scalar_one_or_none()
    if not comp:
        return RedirectResponse(url="/admin?tab=competitions", status_code=302)
    dest = Path(settings.RESULTS_DIR) / slug
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / file.filename
    with open(path, "wb") as f:
        f.write(file.file.read())
    rf = ResultFile(competition_id=comp.id, kind=kind, file_path=str(path), label=label)
    db.add(rf); db.commit()
    return RedirectResponse(url=f"/competitions/{slug}", status_code=302)
