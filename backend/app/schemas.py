from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator


Stage = Literal[
    "Prospecting",
    "Qualification",
    "Needs Analysis",
    "Proposal",
    "Negotiation",
    "Closed Won",
    "Closed Lost",
]

STAGES: list[str] = [
    "Prospecting",
    "Qualification",
    "Needs Analysis",
    "Proposal",
    "Negotiation",
    "Closed Won",
    "Closed Lost",
]


class UserPublic(BaseModel):
    id: int
    email: str
    name: str
    created_at: str


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return email

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(BaseModel):
    user: UserPublic


class OpportunityBase(BaseModel):
    name: str = Field(min_length=1)
    account_name: str = Field(min_length=1)
    value: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stage: Stage = "Prospecting"
    expected_close_date: str | None = None

    @field_validator("name", "account_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    account_name: str | None = Field(default=None, min_length=1)
    value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stage: Stage | None = None
    expected_close_date: str | None = None

    @field_validator("name", "account_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value


class OpportunityPublic(BaseModel):
    id: int
    name: str
    account_name: str
    value: Decimal
    currency: str
    stage: str
    owner_id: int
    owner_name: str
    expected_close_date: str | None
    created_at: str
    updated_at: str
    stalled: bool = False

    @field_serializer("value")
    def serialize_value(self, value: Decimal) -> str:
        return str(value)


class OpportunityListResponse(BaseModel):
    stages: list[str]
    opportunities: list[OpportunityPublic]


EntryType = Literal[
    "call",
    "email",
    "meeting",
    "demo",
    "proposal",
    "contract",
    "stage_change",
    "other",
]


class TimelineEntryCreate(BaseModel):
    type: EntryType = "other"
    title: str = Field(min_length=1)
    body: str = ""
    event_timestamp: str
    follow_up_date: str | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()


class TimelineEntryUpdate(BaseModel):
    type: EntryType | None = None
    title: str | None = Field(default=None, min_length=1)
    body: str | None = None
    event_timestamp: str | None = None
    follow_up_date: str | None = None

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class CommentPublic(BaseModel):
    id: int
    note_id: int
    body: str
    created_by: int
    author_name: str
    created_at: str


class NotePublic(BaseModel):
    id: int
    entry_id: int
    body: str
    created_by: int
    author_name: str
    created_at: str
    updated_at: str
    edited: bool
    comments: list[CommentPublic]


class TimelineEntryPublic(BaseModel):
    id: int
    opportunity_id: int
    type: str
    title: str
    body: str
    event_timestamp: str
    follow_up_date: str | None
    created_by: int | None
    author_name: str | None
    system_generated: bool
    created_at: str
    notes: list[NotePublic]


class TimelineResponse(BaseModel):
    entries: list[TimelineEntryPublic]


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()


class NoteUpdate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()


class NoteVersionPublic(BaseModel):
    id: int
    note_id: int
    version_number: int
    body: str
    edited_by: int
    editor_name: str
    created_at: str


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()
