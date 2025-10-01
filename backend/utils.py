import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models import AuditLog

# Примитивная транслитерация кириллицы → латиница
_CYR = {
    "а": "a",  "б": "b",  "в": "v",  "г": "g",  "д": "d",
    "е": "e",  "ё": "e",  "ж": "zh", "з": "z",  "и": "i",
    "й": "y",  "к": "k",  "л": "l",  "м": "m",  "н": "n",
    "о": "o",  "п": "p",  "р": "r",  "с": "s",  "т": "t",
    "у": "u",  "ф": "f",  "х": "h",  "ц": "c",  "ч": "ch",
    "ш": "sh", "щ": "sch","ъ": "",   "ы": "y",  "ь": "",
    "э": "e",  "ю": "yu", "я": "ya",
}

def _translit_ru(s: str) -> str:
    out = []
    for ch in s:
        lower = ch.lower()
        rep = _CYR.get(lower)
        if rep is None:
            out.append(ch)
        else:
            out.append(rep.upper() if ch.isupper() else rep)
    return "".join(out)

def slugify(value: str) -> str:
    # 1) Попытка через ASCII-нормализацию
    ascii_ = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9\-]+", "-", ascii_).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    if slug:
        return slug

    # 2) Транслитерация кириллицы и повторная очистка
    tr = _translit_ru(value)
    tr = unicodedata.normalize("NFKD", tr)
    slug = re.sub(r"[^a-zA-Z0-9\-]+", "-", tr).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    if slug:
        return slug

    # 3) Надёжный фолбэк
    return "event-" + datetime.now().strftime("%Y%m%d%H%M%S")

def save_upload(file_bytes: bytes, base_dir: str, filename: str) -> str:
    """Сохраняет байты файла в base_dir/filename. Возвращает абсолютный путь."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / filename
    with open(path, "wb") as f:
        f.write(file_bytes)
    return str(path)

def save_upload_file(upload, folder: str) -> str:
    storage = Path("/app/storage")
    target_dir = storage / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename).suffix.lower()
    name = secrets.token_hex(10) + suffix
    p = target_dir / name
    with p.open("wb") as f:
        f.write(upload.file.read())
    # вернуть относительный путь от /app/storage
    return f"{folder}/{name}"


def write_audit(
    db: Session,
    user_id: int | None,
    action: str,
    object_type: str | None = None,
    object_id: int | None = None,
    meta: Any = None,
    ip: str | None = None,
) -> AuditLog:
    if meta is not None and not isinstance(meta, (dict, list)):
        meta_value = {"value": meta}
    else:
        meta_value = meta

    entry = AuditLog(
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip=ip,
        meta_json=meta_value,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

