from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import date, datetime

# идентификаторы Alembic
revision = "0002_rework_registrations"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def _calc_age_category(birth: date) -> str:
    if not birth:
        return ""
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    if age < 10:
        return "Дети до 10"
    if age < 14:
        return "Юниоры 10-13"
    if age < 18:
        return "Юноши 14-17"
    if age < 30:
        return "Взрослые 18-29"
    if age < 50:
        return "Мастера 30-49"
    return "Ветераны 50+"


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Переименуем старую таблицу registrations -> registrations_old (если существует)
    insp = sa.inspect(conn)
    existing_tables = insp.get_table_names()
    had_old = False
    if "registrations" in existing_tables:
        op.rename_table("registrations", "registrations_old")
        had_old = True

    # 2) Новая таблица заявок (команда/заявка)
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("competition_id", sa.Integer, sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_name", sa.String(length=255), nullable=False),
        sa.Column("representative_name", sa.String(length=255), nullable=False),
        sa.Column("representative_phone", sa.String(length=64), nullable=False),
        sa.Column("representative_email", sa.String(length=255), nullable=False),
    )

    # 3) Новая таблица участников заявки
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("registrations.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("middle_name", sa.String(length=255), nullable=True),
        sa.Column("gender", sa.String(length=8), nullable=False),
        sa.Column("birth_date", sa.Date, nullable=False),
        sa.Column("age_category", sa.String(length=64), nullable=False),
        sa.Column("distance", sa.String(length=64), nullable=False),
    )

    # 4) Перенос данных (если была старая таблица)
    if had_old:
        # старый формат:
        # id, competition_id, athlete_name, birthdate, club, coach, phone, email, distance, created_at
        # Преобразуем: каждая запись -> заявка (team_name = "Личный зачёт") + 1 участник
        try:
            rows = conn.execute(text("SELECT id, competition_id, athlete_name, birthdate, phone, email, distance FROM registrations_old")).fetchall()
        except Exception:
            rows = []

        insert_team = text("""
            INSERT INTO registrations (competition_id, team_name, representative_name, representative_phone, representative_email)
            VALUES (:competition_id, :team_name, :representative_name, :representative_phone, :representative_email)
            RETURNING id
        """)
        insert_part = text("""
            INSERT INTO participants (team_id, last_name, first_name, middle_name, gender, birth_date, age_category, distance)
            VALUES (:team_id, :last_name, :first_name, :middle_name, :gender, :birth_date, :age_category, :distance)
        """)

        for r in rows:
            comp_id = r[1]
            full = (r[2] or "").strip()
            birth = r[3]
            phone = (r[4] or "")
            email = (r[5] or "")
            dist = (r[6] or "")

            # Грубый сплит ФИО: "Фамилия Имя Отчество"
            last_name, first_name, middle_name = "", "", ""
            if full:
                parts = full.split()
                if len(parts) == 1:
                    last_name = parts[0]
                elif len(parts) == 2:
                    last_name, first_name = parts
                else:
                    last_name, first_name, middle_name = parts[0], parts[1], " ".join(parts[2:])

            # Пол неизвестен в старых данных — оставим "U" (unknown)
            gender = "U"
            age_cat = _calc_age_category(birth) if isinstance(birth, (date, datetime)) else ""

            team_id = conn.execute(insert_team, {
                "competition_id": comp_id,
                "team_name": "Личный зачёт",
                "representative_name": full or "Представитель",
                "representative_phone": phone or "",
                "representative_email": email or "",
            }).scalar_one()

            conn.execute(insert_part, {
                "team_id": team_id,
                "last_name": last_name or "Фамилия",
                "first_name": first_name or "Имя",
                "middle_name": middle_name,
                "gender": gender,
                "birth_date": birth if isinstance(birth, date) else None,
                "age_category": age_cat,
                "distance": dist or "",
            })

        # Удаляем старую таблицу
        op.drop_table("registrations_old")


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # Восстановим старую схему: registrations (одиночные записи), без сложной обратной миграции.
    if "registrations" in tables and "participants" in tables:
        # 1) создаём old-формат
        op.create_table(
            "registrations_old",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("competition_id", sa.Integer, sa.ForeignKey("competitions.id"), nullable=False),
            sa.Column("athlete_name", sa.String(255), nullable=False),
            sa.Column("birthdate", sa.Date),
            sa.Column("club", sa.String(255), server_default=""),
            sa.Column("coach", sa.String(255), server_default=""),
            sa.Column("phone", sa.String(64), server_default=""),
            sa.Column("email", sa.String(255), server_default=""),
            sa.Column("distance", sa.String(64), server_default=""),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.UniqueConstraint("competition_id", "athlete_name", "birthdate", name="uq_reg_athlete")
        )

        # 2) примитивная обратная миграция: берём только первого участника из каждой новой заявки
        try:
            rows = conn.execute(text("""
                SELECT r.competition_id, r.representative_name, r.representative_phone, r.representative_email,
                       p.last_name, p.first_name, p.middle_name, p.birth_date, p.distance
                FROM registrations r
                LEFT JOIN LATERAL (
                    SELECT * FROM participants p2 WHERE p2.team_id = r.id ORDER BY p2.id ASC LIMIT 1
                ) p ON true
            """)).fetchall()
        except Exception:
            rows = []

        ins_old = text("""
            INSERT INTO registrations_old (competition_id, athlete_name, birthdate, phone, email, distance)
            VALUES (:competition_id, :athlete_name, :birthdate, :phone, :email, :distance)
        """)
        for r in rows:
            comp_id, rep_name, phone, email, ln, fn, mn, bd, dist = r
            fio = " ".join([x for x in [ln, fn, mn] if x])
            conn.execute(ins_old, {
                "competition_id": comp_id,
                "athlete_name": fio or (rep_name or "Участник"),
                "birthdate": bd,
                "phone": phone or "",
                "email": email or "",
                "distance": dist or "",
            })

        # 3) удаляем новые таблицы и возвращаем имя
        op.drop_table("participants")
        op.drop_table("registrations")
        op.rename_table("registrations_old", "registrations")
