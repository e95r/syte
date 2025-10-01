from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_admin: bool
    class Config:
        from_attributes = True

class CompetitionCreate(BaseModel):
    title: str
    slug: str
    city: str = ""
    pool_name: str = ""
    address: str = ""
    start_date: datetime
    end_date: datetime | None = None
    is_open: bool = True
    live_stream_url: str = ""

class RegistrationMember(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    gender: str
    birth_date: date
    distance: str


class RegistrationCreate(BaseModel):
    athlete_name: str
    birthdate: date
    club: str = ""
    coach: str = ""
    phone: str = ""
    email: str = ""
    distance: str = ""
    team_name: str | None = None
    team_representative: str | None = None
    team_members: list[RegistrationMember] = Field(default_factory=list)
    team_members_count: int = 1

    @model_validator(mode="after")
    def _set_team_members_count(self) -> "RegistrationCreate":
        members = getattr(self, "team_members", None) or []
        self.team_members_count = max(len(members), 1)
        return self
