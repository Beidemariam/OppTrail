from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from .time_utils import parse_timestamp, to_canonical


def canonical_timestamp(value: str) -> str:
    """Normalize a client timestamp to fixed-width UTC ISO-8601.

    Rejecting bad input here keeps every stored timestamp comparable and
    sortable; an unparsed value would otherwise surface as a 500 much later,
    when the dashboard tries to read it back.
    """
    try:
        parsed = parse_timestamp(value.strip())
    except ValueError as exc:
        raise ValueError("Enter a valid ISO-8601 timestamp") from exc
    return to_canonical(parsed)


def canonical_date(value: str) -> str:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("Enter a valid date as YYYY-MM-DD") from exc


Stage = Literal[
    "Prospecting",
    "Qualification",
    "Needs Analysis",
    "Proposal",
    "Negotiation",
    "Closed Won",
    "Closed Lost",
]

ShareRole = Literal["viewer", "editor"]

CurrentUserRole = Literal["owner", "viewer", "editor"]

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


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


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

    @field_validator("expected_close_date")
    @classmethod
    def validate_expected_close_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


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

    @field_validator("expected_close_date")
    @classmethod
    def validate_expected_close_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


class OpportunityPublic(BaseModel):
    id: int
    name: str
    account_name: str
    value: Decimal
    currency: str
    stage: Stage
    owner_id: int
    owner_name: str
    expected_close_date: str | None
    created_at: str
    updated_at: str
    stalled: bool = False
    current_user_role: CurrentUserRole = "owner"

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

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, value: str) -> str:
        return canonical_timestamp(value)

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


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

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, value: str | None) -> str | None:
        return canonical_timestamp(value) if value is not None else value

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


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
    type: EntryType
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


class ShareCreate(BaseModel):
    email: str
    role: ShareRole

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ShareUpdate(BaseModel):
    role: ShareRole


class SharePublic(BaseModel):
    user_id: int
    email: str
    name: str
    role: ShareRole
    invited_by: int
    invited_by_name: str
    created_at: str


class ShareListResponse(BaseModel):
    shares: list[SharePublic]


AuditAction = Literal[
    "opportunity_deleted",
    "share_added",
    "share_role_changed",
    "share_removed",
    "timeline_entry_deleted",
    "note_deleted",
    "comment_deleted",
]


class AuditDetailOpportunityDeleted(BaseModel):
    name: str
    account_name: str | None
    stage: str


class AuditDetailShareAdded(BaseModel):
    user_id: int
    email: str
    role: ShareRole


class AuditDetailShareRoleChanged(BaseModel):
    user_id: int
    email: str
    from_role: ShareRole
    to_role: ShareRole


class AuditDetailShareRemoved(BaseModel):
    user_id: int
    email: str
    role: ShareRole


class AuditDetailTimelineEntryDeleted(BaseModel):
    entry_id: int
    type: EntryType
    title: str
    author_id: int


class AuditDetailNoteDeleted(BaseModel):
    note_id: int
    entry_id: int
    author_id: int


class AuditDetailCommentDeleted(BaseModel):
    comment_id: int
    note_id: int
    author_id: int


AuditDetail = (
    AuditDetailOpportunityDeleted
    | AuditDetailShareAdded
    | AuditDetailShareRoleChanged
    | AuditDetailShareRemoved
    | AuditDetailTimelineEntryDeleted
    | AuditDetailNoteDeleted
    | AuditDetailCommentDeleted
)

AUDIT_DETAIL_MODELS: dict[str, type[BaseModel]] = {
    "opportunity_deleted": AuditDetailOpportunityDeleted,
    "share_added": AuditDetailShareAdded,
    "share_role_changed": AuditDetailShareRoleChanged,
    "share_removed": AuditDetailShareRemoved,
    "timeline_entry_deleted": AuditDetailTimelineEntryDeleted,
    "note_deleted": AuditDetailNoteDeleted,
    "comment_deleted": AuditDetailCommentDeleted,
}


class AuditLogEntryPublic(BaseModel):
    id: int
    opportunity_id: int
    actor_id: int | None
    actor_name: str | None
    action: AuditAction
    detail: AuditDetail
    created_at: str


class AiAskRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class AiAskResponse(BaseModel):
    answer: str
    referenced_entry_ids: list[int]


class HealthStatus(BaseModel):
    status: Literal["ok"]
    schema_version: str
    database_writable: bool
    last_backup_at: str | None


NotificationType = Literal[
    "share_added",
    "share_role_changed",
    "share_removed",
    "mention",
    "shared_activity",
    "comment",
]

SourceType = Literal["entry", "note", "comment"]


class NotificationPayloadShareAdded(BaseModel):
    opportunity_id: int
    actor_id: int
    role: ShareRole


class NotificationPayloadShareRoleChanged(BaseModel):
    opportunity_id: int
    actor_id: int
    from_role: ShareRole
    to_role: ShareRole


class NotificationPayloadShareRemoved(BaseModel):
    opportunity_id: int
    actor_id: int
    role: ShareRole


class NotificationPayloadMention(BaseModel):
    opportunity_id: int
    source_type: SourceType
    source_id: int
    actor_id: int
    email: str


class NotificationPayloadSharedActivity(BaseModel):
    opportunity_id: int
    source_type: SourceType
    source_id: int
    actor_id: int
    title: str


class NotificationPayloadComment(BaseModel):
    opportunity_id: int
    source_type: SourceType
    source_id: int
    actor_id: int


NotificationPayload = (
    NotificationPayloadShareAdded
    | NotificationPayloadShareRoleChanged
    | NotificationPayloadShareRemoved
    | NotificationPayloadMention
    | NotificationPayloadSharedActivity
    | NotificationPayloadComment
)

NOTIFICATION_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "share_added": NotificationPayloadShareAdded,
    "share_role_changed": NotificationPayloadShareRoleChanged,
    "share_removed": NotificationPayloadShareRemoved,
    "mention": NotificationPayloadMention,
    "shared_activity": NotificationPayloadSharedActivity,
    "comment": NotificationPayloadComment,
}


class NotificationPublic(BaseModel):
    id: int
    type: NotificationType
    payload: NotificationPayload
    read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    notifications: list[NotificationPublic]


class SnippetMatch(BaseModel):
    """Where one matched word sits inside `SearchSnippet.text`."""

    start: int
    length: int


class SearchSnippet(BaseModel):
    """A search result's excerpt as plain text, plus the offsets to highlight.

    Offsets rather than markup: the API never emits something a client has to
    remember to escape, and the excerpt stays the text it came from.
    """

    text: str
    matches: list[SnippetMatch]


class SearchResultPublic(BaseModel):
    """One match, with enough context to link to it and to group by deal.

    `entry_id` is the timeline entry the match sits under -- for a note or a
    comment that is its ancestor entry, and for an entry it is the entry
    itself -- so every result addresses one place in one timeline.
    """

    kind: SourceType
    id: int
    opportunity_id: int
    opportunity_name: str
    entry_id: int
    note_id: int | None
    title: str | None
    snippet: SearchSnippet
    timestamp: str
    author_id: int | None
    author_name: str | None
