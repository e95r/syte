from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), default="")
    is_admin = Column(Boolean, default=False)

    # новые поля профиля
    username = Column(String(64), unique=True, nullable=False, default="")
    avatar_path = Column(String(255), default="")   # относительный путь в /storage/avatars
    gender = Column(String(16), default="")         # "M"/"F" или пусто
    birth_date = Column(Date, nullable=True)
    phone = Column(String(32), default="")
    city = Column(String(128), default="")
    about = Column(Text, default="")

    # связи
    registrations = relationship("UserEventRegistration", back_populates="user", cascade="all,delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all,delete-orphan")
    reminders = relationship("Reminder", back_populates="user", cascade="all,delete-orphan")
    results = relationship("SwimResult", back_populates="user", cascade="all, delete-orphan")
    personal_bests = relationship(
        "UserPersonalBest",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    role_associations = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    email_verified_at   = Column(DateTime, nullable=True)
    phone_verified_at   = Column(DateTime, nullable=True)
    phone_otp           = Column(String(6), nullable=True)
    phone_otp_expires_at= Column(DateTime, nullable=True)
    delete_otp          = Column(String(6), nullable=True)
    delete_otp_expires_at = Column(DateTime, nullable=True)

    def has_role(self, role_name: str) -> bool:
        return any(role.name == role_name for role in self.roles)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    user_associations = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    users = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="role_associations")
    role = relationship("Role", back_populates="user_associations")



# --- быстрая регистрация пользователя на соревнование ---
class UserEventRegistration(Base):
    __tablename__ = "user_event_registrations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    distance = Column(String(64), default="")  # например, "50 в/с"
    status = Column(String(32), default="pending")  # pending/approved/rejected
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="registrations")
    competition = relationship("Competition")

    __table_args__ = (
        UniqueConstraint("user_id", "competition_id", name="uq_user_competition"),
        Index("ix_user_event_reg_user", "user_id"),
        Index("ix_user_event_reg_comp", "competition_id"),
    )


# --- уведомления пользователю ---
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(32), default="info")  # info/result/reminder
    title = Column(String(255), default="")
    body = Column(Text, default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user", "user_id"),
    )


# --- напоминания ---
class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    remind_at = Column(DateTime, nullable=False)  # когда напомнить
    channel = Column(String(16), default="email") # email/none (расширим позже)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="reminders")
    competition = relationship("Competition")

    __table_args__ = (
        Index("ix_reminders_user", "user_id"),
        Index("ix_reminders_comp", "competition_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(128), unique=True, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)

    user_agent = Column(String(255), default="")
    ip_address = Column(String(45), default="")

    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user", "user_id"),
    )

class CompetitionSeries(Base):
    __tablename__ = "competition_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    competitions = relationship("Competition", back_populates="series")


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    city: Mapped[str] = mapped_column(String(255), default="")
    pool_name: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    hero_image: Mapped[str] = mapped_column(String(255), default="")
    regulation_pdf: Mapped[str] = mapped_column(String(255), default="")
    live_stream_url: Mapped[str] = mapped_column(String(255), default="")
    stage: Mapped[str] = mapped_column(String(64), default="")
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    series = relationship("CompetitionSeries", back_populates="competitions")

    # БЫЛО: registrations = relationship("Registration", ...)
    registrations = relationship("TeamRegistration", back_populates="competition", cascade="all,delete")
    results = relationship("ResultFile", back_populates="competition", cascade="all,delete")
    swim_results = relationship(
        "SwimResult",
        back_populates="competition",
        cascade="all, delete-orphan",
    )
    heats = relationship(
        "Heat",
        back_populates="competition",
        cascade="all, delete-orphan",
        order_by="Heat.heat_number",
    )

class TeamRegistration(Base):
    """Заявка/команда на старт."""

    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), index=True
    )
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    team_representative: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    team_members_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    representative_name: Mapped[str] = mapped_column(String(255), nullable=False)
    representative_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    representative_email: Mapped[str] = mapped_column(String(255), nullable=False)

    competition = relationship("Competition", back_populates="registrations")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    participants = relationship(
        "Participant", back_populates="team", cascade="all, delete-orphan"
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/approved/rejected
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def members_count(self) -> int:
        if self.team_members_count:
            return self.team_members_count
        if self.participants:
            return len(self.participants)
        return 0

    @property
    def is_team_registration(self) -> bool:
        count = self.members_count
        return bool(self.team_name and count > 1)

    @property
    def team_summary(self) -> str:
        count = self.members_count or 1
        if self.is_team_registration:
            return f"команда {self.team_name}, {count} чл."
        return "команда (одиночный участник), 1 член"

    @property
    def display_team_name(self) -> str:
        if self.team_name:
            return self.team_name
        if self.representative_name:
            return self.representative_name
        return f"Одиночный участник #{self.id}"

class Participant(Base):
    """Участник в составе заявки."""
    __tablename__ = "participants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("registrations.id", ondelete="CASCADE"), index=True)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(255), default="")
    gender: Mapped[str] = mapped_column(String(8), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    age_category: Mapped[str] = mapped_column(String(64), nullable=False)
    distance: Mapped[str] = mapped_column(String(64), nullable=False)

    team = relationship("TeamRegistration", back_populates="participants")
    lanes = relationship("Lane", back_populates="participant")


class Heat(Base):
    __tablename__ = "heats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    distance: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    age_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    competition = relationship("Competition", back_populates="heats")
    lanes = relationship(
        "Lane",
        back_populates="heat",
        cascade="all, delete-orphan",
        order_by="Lane.lane_number",
    )

    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "session_name",
            "distance",
            "age_category",
            "heat_number",
            name="uq_heat_number_per_event",
        ),
    )


class Lane(Base):
    __tablename__ = "lanes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    heat_id: Mapped[int] = mapped_column(
        ForeignKey("heats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lane_number: Mapped[int] = mapped_column(Integer, nullable=False)
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    seed_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed_time_text: Mapped[str | None] = mapped_column(String(32), nullable=True)

    heat = relationship("Heat", back_populates="lanes")
    participant = relationship("Participant", back_populates="lanes")

    __table_args__ = (
        UniqueConstraint("heat_id", "lane_number", name="uq_lane_per_heat"),
    )

class News(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cover_image: Mapped[str] = mapped_column(String(255), default="")

class ResultFile(Base):
    __tablename__ = "result_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="pdf")
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    competition = relationship("Competition", back_populates="results")


class SwimResult(Base):
    __tablename__ = "swim_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_code: Mapped[str] = mapped_column(String(16), nullable=False)
    distance_label: Mapped[str] = mapped_column(String(128), nullable=False)
    stroke: Mapped[str] = mapped_column(String(32), default="")
    course: Mapped[str] = mapped_column(String(8), default="LCM", nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    time_text: Mapped[str] = mapped_column(String(32), nullable=False)
    fina_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    swim_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    heat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_personal_best: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="results")
    competition = relationship("Competition", back_populates="swim_results")

    __table_args__ = (
        Index("ix_swim_results_user_event_course", "user_id", "event_code", "course"),
        UniqueConstraint(
            "user_id",
            "competition_id",
            "event_code",
            "stage",
            "heat",
            name="uq_swim_result_unique_attempt",
        ),
    )


class UserPersonalBest(Base):
    __tablename__ = "user_personal_bests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_code: Mapped[str] = mapped_column(String(16), nullable=False)
    course: Mapped[str] = mapped_column(String(8), nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    time_text: Mapped[str] = mapped_column(String(32), nullable=False)
    fina_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("swim_results.id", ondelete="CASCADE"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="personal_bests")
    result = relationship("SwimResult")

    __table_args__ = (
        UniqueConstraint("user_id", "event_code", "course", name="uq_user_pb_event_course"),
        Index("ix_user_pb_user", "user_id"),
    )


class AppSetting(Base):
    """Простая хранилка ключ-значение для настроек интеграций."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json = Column(JSON, nullable=True)

    user = relationship("User")

    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
    )
