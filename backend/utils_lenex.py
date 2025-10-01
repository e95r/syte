from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models import Competition, Participant, ResultFile, TeamRegistration
from services.results import parse_results_csv, persist_results
from settings import settings
from utils import slugify


@dataclass(slots=True)
class LenexParticipant:
    last_name: str
    first_name: str
    middle_name: str = ""
    gender: str = "U"
    birth_date: date | None = None
    age_category: str = ""
    distance: str = ""


@dataclass(slots=True)
class LenexTeam:
    team_name: str
    representative_name: str
    representative_phone: str
    representative_email: str
    status: str = "pending"
    participants: list[LenexParticipant] = field(default_factory=list)


@dataclass(slots=True)
class LenexResultDocument:
    label: str
    kind: str
    filename: str
    content: bytes


@dataclass(slots=True)
class LenexCompetition:
    title: str
    slug: str
    city: str = ""
    pool_name: str = ""
    address: str = ""
    start_date: datetime | None = None
    end_date: datetime | None = None
    stage: str = ""


@dataclass(slots=True)
class LenexData:
    competition: LenexCompetition
    teams: list[LenexTeam]
    results: list[LenexResultDocument]


class LenexError(ValueError):
    """Ошибка работы с LENEX."""


_REGISTRATION_COLUMNS = [
    "team_name",
    "representative_name",
    "representative_phone",
    "representative_email",
    "status",
    "last_name",
    "first_name",
    "middle_name",
    "gender",
    "birth_date",
    "age_category",
    "distance",
]

_REQUIRED_REGISTRATION_COLUMNS = set(_REGISTRATION_COLUMNS)

_RESULT_COLUMNS = [
    "label",
    "kind",
    "filename",
    "content_base64",
]

_REQUIRED_RESULT_COLUMNS = set(_RESULT_COLUMNS)


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                return dt
            return dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise LenexError(f"Не удалось разобрать дату/время: {value}") from exc


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise LenexError(f"Не удалось разобрать дату рождения: {value}") from exc


def parse_lenex(xml_bytes: bytes) -> LenexData:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise LenexError("Некорректный XML-файл LENEX") from exc

    if root.tag.upper() != "LENEX":
        raise LenexError("Ожидался корневой элемент LENEX")

    meet = root.find("./MEETS/MEET")
    if meet is None:
        raise LenexError("В файле LENEX отсутствует блок MEET")

    title = _text(meet.find("NAME")) or _text(meet.find("SHORTNAME"))
    if not title:
        raise LenexError("В файле LENEX не указано название соревнования")

    slug = _text(meet.find("CODE")) or slugify(title)
    start_date = _parse_datetime(_text(meet.find("STARTDATE")))
    end_date = _parse_datetime(_text(meet.find("ENDDATE")))
    city = _text(meet.find("CITY"))
    stage = _text(meet.find("STAGE"))

    pool_node = meet.find("POOL")
    pool_name = _text(pool_node.find("NAME")) if pool_node is not None else ""
    address = _text(pool_node.find("ADDRESS")) if pool_node is not None else _text(meet.find("ADDRESS"))

    competition = LenexCompetition(
        title=title,
        slug=slug,
        city=city,
        pool_name=pool_name,
        address=address,
        start_date=start_date,
        end_date=end_date,
        stage=stage,
    )

    teams: dict[str, LenexTeam] = {}
    for club in meet.findall("./CLUBS/CLUB"):
        team_name = club.get("name") or _text(club.find("NAME"))
        if not team_name:
            continue
        representative_name = _text(club.find("CONTACT/NAME"))
        representative_phone = _text(club.find("CONTACT/PHONE"))
        representative_email = _text(club.find("CONTACT/EMAIL"))
        status = (_text(club.find("STATUS")) or "pending").lower()
        team = LenexTeam(
            team_name=team_name,
            representative_name=representative_name,
            representative_phone=representative_phone,
            representative_email=representative_email,
            status=status,
        )
        teams[team_name.strip().lower()] = team

    entries = meet.findall("./ENTRIES/ENTRY")
    for entry in entries:
        club_name = entry.get("clubName") or _text(entry.find("CLUBNAME"))
        if not club_name:
            continue
        key = club_name.strip().lower()
        team = teams.get(key)
        if team is None:
            team = LenexTeam(
                team_name=club_name,
                representative_name="",
                representative_phone="",
                representative_email="",
            )
            teams[key] = team
        status = entry.get("status") or _text(entry.find("STATUS"))
        if status:
            team.status = status.lower()
        for athlete in entry.findall("ATHLETE"):
            participant = LenexParticipant(
                last_name=_text(athlete.find("LASTNAME")),
                first_name=_text(athlete.find("FIRSTNAME")),
                middle_name=_text(athlete.find("MIDDLENAME")),
                gender=(_text(athlete.find("GENDER")) or "U").upper(),
                birth_date=_parse_date(_text(athlete.find("BIRTHDATE"))),
                age_category=_text(athlete.find("AGECATEGORY")),
                distance=_text(athlete.find("DISTANCE")),
            )
            team.participants.append(participant)

    results: list[LenexResultDocument] = []
    for doc in meet.findall("./DOCUMENTS/DOCUMENT"):
        label = doc.get("label") or _text(doc.find("LABEL"))
        kind = (doc.get("kind") or _text(doc.find("KIND")) or doc.get("type") or "").lower() or "pdf"
        filename = doc.get("filename") or _text(doc.find("FILENAME")) or f"{slug}-{len(results)+1}.{kind or 'dat'}"
        encoding = (doc.get("encoding") or "base64").lower()
        if encoding != "base64":
            raise LenexError("Поддерживается только base64-кодирование вложений LENEX")
        payload = _text(doc)
        try:
            content = base64.b64decode(payload) if payload else b""
        except (ValueError, TypeError) as exc:
            raise LenexError(f"Не удалось декодировать документ результатов '{label}'") from exc
        results.append(
            LenexResultDocument(
                label=label or filename,
                kind=kind or Path(filename).suffix.lstrip(".") or "pdf",
                filename=Path(filename).name,
                content=content,
            )
        )

    return LenexData(competition=competition, teams=list(teams.values()), results=results)


def _load_competition(db: Session, competition_id: int) -> Competition:
    stmt = (
        select(Competition)
        .where(Competition.id == competition_id)
        .options(
            selectinload(Competition.registrations).selectinload(TeamRegistration.participants),
            selectinload(Competition.results),
        )
    )
    competition = db.execute(stmt).scalar_one_or_none()
    if competition is None:
        raise LenexError(f"Соревнование с ID {competition_id} не найдено")
    return competition


def _ensure_unique_slug(db: Session, slug: str, existing_id: int | None = None) -> str:
    base_slug = slug or "competition"
    candidate = base_slug
    counter = 1
    while True:
        stmt = select(Competition).where(Competition.slug == candidate)
        if existing_id is not None:
            stmt = stmt.where(Competition.id != existing_id)
        if db.execute(stmt).first() is None:
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


def _reset_participants(db: Session, registration: TeamRegistration, participants: Sequence[LenexParticipant]) -> None:
    for participant in list(registration.participants):
        db.delete(participant)
    registration.participants.clear()
    for pdata in participants:
        if not pdata.last_name or not pdata.first_name:
            continue
        participant = Participant(
            last_name=pdata.last_name,
            first_name=pdata.first_name,
            middle_name=pdata.middle_name or "",
            gender=(pdata.gender or "U").upper(),
            birth_date=pdata.birth_date or date(1900, 1, 1),
            age_category=pdata.age_category or "",
            distance=pdata.distance or "",
        )
        registration.participants.append(participant)


def _write_result_document(competition: Competition, document: LenexResultDocument) -> Path:
    dest_dir = Path(settings.RESULTS_DIR) / competition.slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(document.filename or f"{slugify(document.label)}.{document.kind or 'dat'}").name
    if not safe_name:
        safe_name = f"result-{competition.id}-{int(datetime.now().timestamp())}.{document.kind or 'dat'}"
    dest_path = dest_dir / safe_name
    with dest_path.open("wb") as file_handle:
        file_handle.write(document.content)
    return dest_path


def import_lenex(db: Session, xml_bytes: bytes) -> Competition:
    data = parse_lenex(xml_bytes)
    comp_data = data.competition
    raw_slug = comp_data.slug or slugify(comp_data.title)
    stmt = (
        select(Competition)
        .where(Competition.slug == raw_slug)
        .options(
            selectinload(Competition.registrations).selectinload(TeamRegistration.participants),
            selectinload(Competition.results),
        )
    )
    competition = db.execute(stmt).scalar_one_or_none()
    if competition is None:
        slug = _ensure_unique_slug(db, raw_slug, None)
        competition = Competition(slug=slug, title=comp_data.title, start_date=datetime.utcnow())
        db.add(competition)
        db.flush()
    else:
        slug = competition.slug

    competition.title = comp_data.title
    competition.city = comp_data.city
    competition.pool_name = comp_data.pool_name
    competition.address = comp_data.address
    competition.stage = comp_data.stage
    competition.start_date = comp_data.start_date or competition.start_date
    competition.end_date = comp_data.end_date

    existing_registrations = {
        (
            reg.display_team_name.strip().lower(),
            reg.representative_email.strip().lower(),
        ): reg
        for reg in competition.registrations
    }

    for team in data.teams:
        if not (team.team_name or team.representative_name):
            continue
        normalized_team_name = (team.team_name or team.representative_name or "").strip()
        key = (
            normalized_team_name.lower(),
            team.representative_email.strip().lower(),
        )
        registration = existing_registrations.get(key)
        if registration is None:
            registration = TeamRegistration(
                competition_id=competition.id,
                team_name=team.team_name or None,
                representative_name=team.representative_name,
                representative_phone=team.representative_phone,
                representative_email=team.representative_email,
                status=team.status or "pending",
                is_deleted=False,
            )
            competition.registrations.append(registration)
        else:
            registration.team_name = team.team_name or None
            registration.representative_name = team.representative_name
            registration.representative_phone = team.representative_phone
            registration.representative_email = team.representative_email
            registration.status = team.status or registration.status
            registration.is_deleted = False
        _reset_participants(db, registration, team.participants)

    existing_results = {res.label.lower(): res for res in competition.results}
    for document in data.results:
        key = document.label.lower()
        target = existing_results.get(key)
        dest_path = _write_result_document(competition, document)
        if target is None:
            target = ResultFile(
                competition_id=competition.id,
                label=document.label,
                kind=document.kind,
                file_path=str(dest_path),
            )
            db.add(target)
            competition.results.append(target)
        else:
            target.kind = document.kind
            target.file_path = str(dest_path)
            target.label = document.label

    db.commit()
    db.refresh(competition)
    return competition


def export_lenex(db: Session, competition_id: int) -> bytes:
    competition = _load_competition(db, competition_id)

    root = ET.Element("LENEX", attrib={"version": "3.0"})
    meets = ET.SubElement(root, "MEETS")
    meet = ET.SubElement(meets, "MEET")

    ET.SubElement(meet, "CODE").text = competition.slug
    ET.SubElement(meet, "NAME").text = competition.title
    if competition.city:
        ET.SubElement(meet, "CITY").text = competition.city
    if competition.stage:
        ET.SubElement(meet, "STAGE").text = competition.stage
    ET.SubElement(meet, "STARTDATE").text = (competition.start_date or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%S")
    if competition.end_date:
        ET.SubElement(meet, "ENDDATE").text = competition.end_date.strftime("%Y-%m-%dT%H:%M:%S")
    if competition.address or competition.pool_name:
        pool = ET.SubElement(meet, "POOL")
        if competition.pool_name:
            ET.SubElement(pool, "NAME").text = competition.pool_name
        if competition.address:
            ET.SubElement(pool, "ADDRESS").text = competition.address

    clubs = ET.SubElement(meet, "CLUBS")
    entries = ET.SubElement(meet, "ENTRIES")
    for registration in sorted(
        competition.registrations,
        key=lambda r: (r.display_team_name.lower(), r.id),
    ):
        if registration.is_deleted:
            continue
        club = ET.SubElement(
            clubs,
            "CLUB",
            attrib={"name": registration.display_team_name},
        )
        contact = ET.SubElement(club, "CONTACT")
        if registration.representative_name:
            ET.SubElement(contact, "NAME").text = registration.representative_name
        if registration.representative_phone:
            ET.SubElement(contact, "PHONE").text = registration.representative_phone
        if registration.representative_email:
            ET.SubElement(contact, "EMAIL").text = registration.representative_email
        ET.SubElement(club, "STATUS").text = registration.status or "pending"

        for participant in sorted(registration.participants, key=lambda p: (p.last_name.lower(), p.first_name.lower())):
            entry = ET.SubElement(
                entries,
                "ENTRY",
                attrib={"clubName": registration.display_team_name},
            )
            athlete = ET.SubElement(entry, "ATHLETE")
            ET.SubElement(athlete, "LASTNAME").text = participant.last_name
            ET.SubElement(athlete, "FIRSTNAME").text = participant.first_name
            if participant.middle_name:
                ET.SubElement(athlete, "MIDDLENAME").text = participant.middle_name
            ET.SubElement(athlete, "GENDER").text = (participant.gender or "U").upper()
            if participant.birth_date:
                ET.SubElement(athlete, "BIRTHDATE").text = participant.birth_date.strftime("%Y-%m-%d")
            if participant.age_category:
                ET.SubElement(athlete, "AGECATEGORY").text = participant.age_category
            if participant.distance:
                ET.SubElement(athlete, "DISTANCE").text = participant.distance

    documents = ET.SubElement(meet, "DOCUMENTS")
    for result in sorted(competition.results, key=lambda r: r.label.lower()):
        doc = ET.SubElement(
            documents,
            "DOCUMENT",
            attrib={
                "label": result.label,
                "kind": result.kind or Path(result.file_path).suffix.lstrip(".") or "pdf",
                "filename": Path(result.file_path).name,
                "encoding": "base64",
            },
        )
        file_path = Path(result.file_path)
        if not file_path.exists():
            raise LenexError(f"Файл результатов '{result.file_path}' не найден")
        doc.text = base64.b64encode(file_path.read_bytes()).decode("ascii")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_registrations_csv(db: Session, competition_id: int) -> bytes:
    competition = _load_competition(db, competition_id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_REGISTRATION_COLUMNS)
    writer.writeheader()
    for registration in competition.registrations:
        if registration.is_deleted:
            continue
        if not registration.participants:
            writer.writerow(
                {
                    "team_name": registration.team_name,
                    "representative_name": registration.representative_name,
                    "representative_phone": registration.representative_phone,
                    "representative_email": registration.representative_email,
                    "status": registration.status,
                    "last_name": "",
                    "first_name": "",
                    "middle_name": "",
                    "gender": "",
                    "birth_date": "",
                    "age_category": "",
                    "distance": "",
                }
            )
            continue
        for participant in registration.participants:
            writer.writerow(
                {
                    "team_name": registration.team_name,
                    "representative_name": registration.representative_name,
                    "representative_phone": registration.representative_phone,
                    "representative_email": registration.representative_email,
                    "status": registration.status,
                    "last_name": participant.last_name,
                    "first_name": participant.first_name,
                    "middle_name": participant.middle_name or "",
                    "gender": participant.gender or "",
                    "birth_date": participant.birth_date.strftime("%Y-%m-%d") if participant.birth_date else "",
                    "age_category": participant.age_category or "",
                    "distance": participant.distance or "",
                }
            )
    return output.getvalue().encode("utf-8")


def export_results_csv(db: Session, competition_id: int) -> bytes:
    competition = _load_competition(db, competition_id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_RESULT_COLUMNS)
    writer.writeheader()
    for result in competition.results:
        file_path = Path(result.file_path)
        if not file_path.exists():
            raise LenexError(f"Файл результатов '{result.file_path}' не найден")
        writer.writerow(
            {
                "label": result.label,
                "kind": result.kind,
                "filename": file_path.name,
                "content_base64": base64.b64encode(file_path.read_bytes()).decode("ascii"),
            }
        )
    return output.getvalue().encode("utf-8")


def _parse_registrations_csv(csv_bytes: bytes) -> list[LenexTeam]:
    try:
        decoded = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LenexError("CSV должен быть в кодировке UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    missing = _REQUIRED_REGISTRATION_COLUMNS.difference(reader.fieldnames or [])
    if missing:
        raise LenexError(f"В CSV отсутствуют обязательные колонки: {', '.join(sorted(missing))}")

    teams_map: dict[tuple[str, str], LenexTeam] = {}
    for idx, row in enumerate(reader, start=2):
        team_name = (row.get("team_name") or "").strip()
        if not team_name:
            raise LenexError(f"Строка {idx}: не заполнено поле team_name")
        rep_email = (row.get("representative_email") or "").strip()
        rep_name = (row.get("representative_name") or "").strip()
        rep_phone = (row.get("representative_phone") or "").strip()
        status = (row.get("status") or "pending").strip().lower()

        key = (team_name.lower(), rep_email.lower())
        team = teams_map.get(key)
        if team is None:
            team = LenexTeam(
                team_name=team_name,
                representative_name=rep_name,
                representative_phone=rep_phone,
                representative_email=rep_email,
                status=status,
            )
            teams_map[key] = team
        participant_last = (row.get("last_name") or "").strip()
        participant_first = (row.get("first_name") or "").strip()
        if participant_last or participant_first:
            participant = LenexParticipant(
                last_name=participant_last,
                first_name=participant_first,
                middle_name=(row.get("middle_name") or "").strip(),
                gender=(row.get("gender") or "U").strip().upper(),
                birth_date=_parse_date(row.get("birth_date")),
                age_category=(row.get("age_category") or "").strip(),
                distance=(row.get("distance") or "").strip(),
            )
            team.participants.append(participant)
    return list(teams_map.values())


def _parse_result_documents_csv(csv_bytes: bytes) -> list[LenexResultDocument]:
    try:
        decoded = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LenexError("CSV должен быть в кодировке UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    missing = _REQUIRED_RESULT_COLUMNS.difference(reader.fieldnames or [])
    if missing:
        raise LenexError(f"В CSV отсутствуют обязательные колонки: {', '.join(sorted(missing))}")

    results: list[LenexResultDocument] = []
    for idx, row in enumerate(reader, start=2):
        label = (row.get("label") or "").strip()
        if not label:
            raise LenexError(f"Строка {idx}: не заполнено поле label")
        kind = (row.get("kind") or "pdf").strip().lower()
        filename = (row.get("filename") or f"{slugify(label)}.{kind}").strip()
        payload = (row.get("content_base64") or "").strip()
        if not payload:
            raise LenexError(f"Строка {idx}: пустое поле content_base64")
        try:
            content = base64.b64decode(payload)
        except (ValueError, TypeError) as exc:
            raise LenexError(f"Строка {idx}: не удалось декодировать content_base64") from exc
        results.append(
            LenexResultDocument(
                label=label,
                kind=kind,
                filename=filename,
                content=content,
            )
        )
    return results


def import_registrations_csv(db: Session, competition_id: int, csv_bytes: bytes) -> Competition:
    competition = _load_competition(db, competition_id)
    teams = _parse_registrations_csv(csv_bytes)
    for team in teams:
        if not team.team_name:
            continue
        key = (team.team_name.strip().lower(), team.representative_email.strip().lower())
        registration = next(
            (
                reg
                for reg in competition.registrations
                if (reg.team_name.strip().lower(), reg.representative_email.strip().lower()) == key
            ),
            None,
        )
        if registration is None:
            registration = TeamRegistration(
                competition_id=competition.id,
                team_name=team.team_name,
                representative_name=team.representative_name,
                representative_phone=team.representative_phone,
                representative_email=team.representative_email,
                status=team.status or "pending",
                is_deleted=False,
            )
            competition.registrations.append(registration)
        else:
            registration.team_name = team.team_name
            registration.representative_name = team.representative_name
            registration.representative_phone = team.representative_phone
            registration.representative_email = team.representative_email
            registration.status = team.status or registration.status
            registration.is_deleted = False
        _reset_participants(db, registration, team.participants)
    db.commit()
    db.refresh(competition)
    return competition


def _decode_csv(csv_bytes: bytes) -> str:
    try:
        return csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LenexError("CSV должен быть в кодировке UTF-8") from exc


def import_results_csv(db: Session, competition_id: int, csv_bytes: bytes) -> Competition:
    competition = _load_competition(db, competition_id)
    decoded = _decode_csv(csv_bytes)
    reader = csv.DictReader(io.StringIO(decoded))
    fieldnames = [name.strip().lower() for name in (reader.fieldnames or [])]

    required_documents = {name.lower() for name in _REQUIRED_RESULT_COLUMNS}
    if required_documents.issubset(fieldnames):
        documents = _parse_result_documents_csv(csv_bytes)
        existing = {res.label.lower(): res for res in competition.results}
        for document in documents:
            dest_path = _write_result_document(competition, document)
            target = existing.get(document.label.lower())
            if target is None:
                target = ResultFile(
                    competition_id=competition.id,
                    label=document.label,
                    kind=document.kind,
                    file_path=str(dest_path),
                )
                db.add(target)
                competition.results.append(target)
            else:
                target.kind = document.kind
                target.file_path = str(dest_path)
                target.label = document.label
    else:
        rows = parse_results_csv(decoded)
        if not rows:
            raise LenexError(
                "CSV должен содержать колонки для результатов или вложений"
            )
        persist_results(db, competition, rows)

    db.commit()
    db.refresh(competition)
    return competition


__all__ = [
    "LenexCompetition",
    "LenexParticipant",
    "LenexTeam",
    "LenexResultDocument",
    "LenexData",
    "LenexError",
    "parse_lenex",
    "import_lenex",
    "export_lenex",
    "export_registrations_csv",
    "export_results_csv",
    "import_registrations_csv",
    "import_results_csv",
]
