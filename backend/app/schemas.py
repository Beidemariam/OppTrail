import json
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

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


def stripped(value: str) -> str:
    """A required text field, trimmed, and refused if that leaves nothing.

    `Field(min_length=1)` cannot do this on its own: Pydantic checks the length
    of what arrived and this runs afterwards, so `"   "` satisfied the
    constraint and was then stored as `""` -- a real hole in
    `OpportunityBase.name` and `account_name` before milestone 4.1 found it by
    writing the same pattern next to it.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Enter a value")
    return trimmed


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
        return stripped(value)

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
        # A partial `PATCH` may omit these; sending one blank is still a refusal
        # rather than a silent empty name.
        return stripped(value) if value is not None else value

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


# --- Bulk actions (milestone 2.4c) ------------------------------------------

# The board holds every opportunity the reader can see — `useOpportunities`
# walks `GET /api/v2/opportunities` to its last page (D-093) — up to the
# 400-opportunity scale milestone 2.3 built for, so a select-all is bounded by
# that rather than by an arbitrary request-size guess.
BULK_ACTION_MAX_IDS = 400


# Which extra field each action carries, and therefore which one it refuses
# without. Declared as data rather than as a chain of `if`s because the
# validator below has to answer both halves -- required, and not-for-anyone-
# else -- and a fifth action should extend one line rather than four
# (milestone 3.0a).
BulkAction = Literal["delete", "set_stage", "assign_owner", "add_to_view"]

BULK_ACTION_FIELDS: dict[str, str | None] = {
    "delete": None,
    "set_stage": "stage",
    "assign_owner": "new_owner_email",
    "add_to_view": "view_id",
}


class BulkOpportunityAction(BaseModel):
    """One request over many opportunities (`docs/UX.md`'s action bar).

    All four of the action bar's non-export actions live here. Each reuses a
    rule that exists elsewhere rather than inventing one: `delete` and
    `set_stage` are `delete_opportunity`/`update_opportunity` done per id
    (owner-only), `assign_owner` is owner-only for the same reason every
    other opportunity write is, and `add_to_view` writes to the caller's own
    saved view, so its rule is that view's creator-only write plus read
    access to each opportunity (D-105, D-106). Export is the fifth and is not
    here: it answers with a file rather than a per-item result (D-107).
    """

    ids: list[int] = Field(min_length=1, max_length=BULK_ACTION_MAX_IDS)
    action: BulkAction
    stage: Stage | None = None
    new_owner_email: str | None = None
    view_id: int | None = None

    @field_validator("new_owner_email")
    @classmethod
    def normalize_new_owner_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value

    @model_validator(mode="after")
    def validate_field_matches_action(self) -> "BulkOpportunityAction":
        required = BULK_ACTION_FIELDS[self.action]
        for field, expected in BULK_ACTION_FIELDS.items():
            if expected is None or expected == required:
                continue
            if getattr(self, expected) is not None:
                raise ValueError(f"{expected} is only valid for the {field} action")
        if required is not None and getattr(self, required) is None:
            raise ValueError(f"{required} is required for the {self.action} action")
        return self


class BulkActionResultItem(BaseModel):
    """One id's outcome. `error` is the same message the single-item route
    would have raised, so a client already reading `detail`-style permission
    errors does not learn a second vocabulary.
    """

    id: int
    status: Literal["ok", "error"]
    error: str | None = None


class BulkActionResponse(BaseModel):
    results: list[BulkActionResultItem]


EntryType = Literal[
    "call",
    "email",
    "meeting",
    "demo",
    "proposal",
    "contract",
    "stage_change",
    "other",
    "site_visit",
    "objection",
    "competitor_intel",
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
        return stripped(value)

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
        return stripped(value) if value is not None else value

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, value: str | None) -> str | None:
        return canonical_timestamp(value) if value is not None else value

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


# The classic GitHub issue/PR reaction set (milestone 3.3a) -- familiar rather
# than invented, which is what keeps this a fixed seven-item control instead of
# a picker `docs/DESIGN-SYSTEM.md`'s restraint would rule out.
ReactionEmoji = Literal["👍", "👎", "😄", "🎉", "❤️", "🚀", "👀"]


class ReactionPublic(BaseModel):
    """One person's reaction to one comment or reply (milestone 3.3a).

    Individual rows rather than a server-aggregated `{emoji, count}` shape --
    the same choice `versioning.py` and `activity.py` make, reading raw data
    back and letting the client interpret it (`lib/activity.ts`,
    `VersionChanges.tsx`) rather than baking one reader's view into the
    response.
    """

    id: int
    comment_id: int
    emoji: str
    user_id: int
    user_name: str
    created_at: str


class ReactionCreate(BaseModel):
    emoji: ReactionEmoji


class CommentPublic(BaseModel):
    """One comment, whether it opened a thread or replied to one.

    `parent_id` is NULL for a thread root (milestone 3.3). Threading is one
    level deep by rule rather than by column (D-127), so this is also the
    shape of every reply and a reply never carries replies of its own.
    `reactions` (milestone 3.3a) is on every comment, roots and replies alike.
    """

    id: int
    note_id: int
    parent_id: int | None
    body: str
    created_by: int
    author_name: str
    created_at: str
    reactions: list[ReactionPublic]


class CommentThread(CommentPublic):
    """A thread root read with its replies and its resolved state.

    Resolving belongs to the thread, so these three fields live on the root
    and only the root — a reply's own row carries NULL in all of them
    (`routes_timeline.resolve_comment` refuses a reply). Reading a thread is
    what a note's comments are; writing one still answers with the single
    `CommentPublic` that was written.
    """

    resolved_at: str | None
    resolved_by: int | None
    resolved_by_name: str | None
    replies: list[CommentPublic]


class NotePublic(BaseModel):
    id: int
    entry_id: int
    body: str
    created_by: int
    author_name: str
    created_at: str
    updated_at: str
    edited: bool
    comments: list[CommentThread]


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
    # This entry's number within its own opportunity (milestone 3.9,
    # **D-139**): #1 is the oldest thing that happened on the deal. Computed,
    # not stored -- `timeline_utils.ENTRY_SEQUENCE_SQL` is the one definition,
    # read here and by the AI's context so a cited number and a printed one
    # cannot disagree. It is a reading aid, not an identity: the id is what
    # `?entry=` links carry.
    sequence: int
    notes: list[NotePublic]


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()


class NoteUpdate(BaseModel):
    """A note edit, carrying the state the editor was written against.

    `updated_at` is ADR 0003's edit guard: the client sends back the value it
    read, and `PATCH /api/v2/notes/{id}` answers 409 if the note has moved
    since. It is required rather than optional because an optional guard is no
    guard -- a client that omits it is exactly the client that clobbers.

    It is not validated as a timestamp here. Anything that is not the note's
    current `updated_at` is a conflict, and a malformed value is one of those:
    reporting it as a 422 would tell a caller their *format* was wrong when
    what is wrong is that they are editing a stale note.
    """

    body: str = Field(min_length=1)
    updated_at: str

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()


# --- Edit history (milestone 2.10) -----------------------------------------

# One model per versioned table, each naming the fields that table snapshots
# (`app/versioning.py`). They are not folded into one generic model with a
# free-form payload: a history screen that has to guess at a field's type is a
# screen the generated client cannot type either.


class NoteVersionPublic(BaseModel):
    id: int
    note_id: int
    version_number: int
    body: str
    edited_by: int
    editor_name: str
    created_at: str


class OpportunityVersionPublic(BaseModel):
    id: int
    opportunity_id: int
    version_number: int
    name: str
    account_name: str
    value: Decimal
    currency: str
    stage: Stage
    expected_close_date: str | None
    edited_by: int
    editor_name: str
    created_at: str

    @field_serializer("value")
    def serialize_value(self, value: Decimal) -> str:
        return str(value)


class TimelineEntryVersionPublic(BaseModel):
    id: int
    entry_id: int
    version_number: int
    type: EntryType
    title: str
    body: str
    event_timestamp: str
    follow_up_date: str | None
    edited_by: int
    editor_name: str
    created_at: str


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)
    # Absent means "open a new thread on this note", which is what every
    # comment written before milestone 3.3 did. Whether the named comment is
    # a legal parent — same note, still here, and itself a root — is resolved
    # against the database in `routes_timeline.create_comment`.
    parent_id: int | None = None

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


class OpportunityMemberPublic(BaseModel):
    """One person who can read this opportunity (milestone 3.2, **D-123**).

    The mention autocomplete's source, and the reason this is not
    `SharePublic`: a mention only notifies someone who already has access
    (`notification_service.notify_mentions`), so the list a composer offers has
    to be the owner *and* the shares, while a share row describes a grant and
    has no row for the owner at all. It carries no `invited_by` and no
    `created_at` -- who invited whom is the sharing panel's business, and that
    stays owner-only.
    """

    user_id: int
    email: str
    name: str
    role: CurrentUserRole


class WatcherPublic(BaseModel):
    """One person following this opportunity (milestone 3.3a).

    Owner-only to read, like `SharePublic` beside it -- but unlike a share,
    watching carries no role and grants no access of its own: `FEATURES.md`
    §7 names watching an opportunity you are *not* shared on as the point of
    the feature (D-129), so this list can and does include people
    `OpportunityMemberPublic` would never return.
    """

    id: int
    opportunity_id: int
    user_id: int
    user_name: str
    user_email: str
    created_at: str


class WatchStatus(BaseModel):
    """Whether the caller is currently watching -- the read and both writes
    share this one shape, so toggling costs no second request to learn the
    result (milestone 3.3a).
    """

    watching: bool


class TaskCreate(BaseModel):
    """A task as written (milestone 4.1, `docs/FEATURES.md` §8).

    `assignee_email` rather than an id, like `ShareCreate`: a person is named
    by the address the reader typed or picked, and resolving it is the route's
    job -- which is also where naming somebody nobody has heard of becomes a
    422 about the request rather than a silent unassigned task.
    """

    title: str = Field(min_length=1, max_length=500)
    # Markdown, like every other body in this app, so the composer and
    # `MarkdownText` already handle it (milestone 4.2a). Optional and empty by
    # default: "call them back Thursday" needs no elaboration, and requiring one
    # would put a second field in front of the common case.
    description: str = ""
    assignee_email: str | None = None
    due_date: str | None = None
    entry_id: int | None = None

    @field_validator("assignee_email")
    @classmethod
    def normalize_assignee_email(cls, value: str | None) -> str | None:
        # Lowercased like `ShareCreate.email`, because signup stores it that
        # way: an assignee typed with a capital would otherwise resolve to
        # nobody and the task would be refused for a reason nobody could see.
        return value.strip().lower() if value else value

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return stripped(value)

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None


class TaskUpdate(BaseModel):
    """A partial edit, the shape every other `PATCH` in this app takes.

    `due_date` and `assignee_email` are both nullable *and* optional, which are
    two different things here and the reason `model_fields_set` decides what to
    write: absent means "leave it", `null` means "clear it". Completion is not
    here -- it is `POST .../complete` and `.../reopen`, for the reason resolving
    a thread is (D-128): it changes no field a person typed, and making it a
    `PATCH` field would let one request both rename and close a task, which is
    two events in the log pretending to be one.
    """

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    assignee_email: str | None = None
    due_date: str | None = None

    @field_validator("assignee_email")
    @classmethod
    def normalize_assignee_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        return stripped(value) if value is not None else value

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: str | None) -> str | None:
        # `None` clears the date; the route tells "clear it" from "leave it
        # alone" by whether the key was sent at all, not by the value.
        return canonical_date(value) if value else None


class TaskPublic(BaseModel):
    id: int
    opportunity_id: int
    # Carried on every task because the two cross-opportunity readers -- My
    # Tasks and the calendar -- show tasks from several deals at once, and a
    # task is meaningless without the one it belongs to. It is the reason
    # `FollowUpPublic` carried it too, before milestone 4.2 replaced that read
    # with this one.
    opportunity_name: str
    entry_id: int | None
    entry_title: str | None
    title: str
    description: str
    assignee_id: int | None
    assignee_name: str | None
    due_date: str | None
    # `NULL` means open. The pair answers "when" and "who" rather than just
    # "whether", which a boolean could not (D-095's lesson, applied at the
    # start this time rather than after a migration).
    completed_at: str | None
    completed_by: int | None
    completed_by_name: str | None
    created_by: int
    author_name: str | None
    created_at: str
    updated_at: str


class TaskVersionPublic(BaseModel):
    """One recorded state of a task (milestone 4.2a, `AGENTS.md` invariant 8).

    The fourth history of the shape the other three already have. `assignee_id`
    rather than a name is the stored snapshot; `assignee_name` is resolved on
    read so the history reads as "assigned to Gavin" rather than "assignee 3".
    """

    id: int
    task_id: int
    version_number: int
    title: str
    description: str
    assignee_id: int | None
    assignee_name: str | None
    due_date: str | None
    edited_by: int
    editor_name: str | None
    created_at: str


AuditAction = Literal[
    "opportunity_deleted",
    "opportunity_restored",
    "share_added",
    "share_role_changed",
    "share_removed",
    "owner_changed",
    "timeline_entry_deleted",
    "timeline_entry_restored",
    "note_deleted",
    "note_restored",
    "comment_deleted",
    "comment_restored",
    "task_deleted",
    "task_restored",
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


# An ownership transfer is a change of who may do everything to the record,
# which is the access question `AGENTS.md` invariant 7 puts in the audit log
# (milestone 3.0a). The previous owner is named as well as the new one: the
# forensic question is who handed it on, not only who holds it now.
class AuditDetailOwnerChanged(BaseModel):
    from_user_id: int
    to_user_id: int
    to_email: str


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


# Undo writes its own audit row rather than removing the delete's, so the log
# reads as the sequence of things that happened (milestone 2.4b). A restore
# records the same identifying fields its delete did; the action name is what
# distinguishes them.
class AuditDetailOpportunityRestored(BaseModel):
    name: str
    account_name: str | None
    stage: str


class AuditDetailTimelineEntryRestored(BaseModel):
    entry_id: int
    type: EntryType
    title: str
    author_id: int


class AuditDetailNoteRestored(BaseModel):
    note_id: int
    entry_id: int
    author_id: int


class AuditDetailCommentRestored(BaseModel):
    comment_id: int
    note_id: int
    author_id: int


# A task's identifying fields are its title and who it was for: an owner
# reading the log wants to know which action item disappeared, and "the one
# assigned to Gavin" is how a person refers to it.
class AuditDetailTaskDeleted(BaseModel):
    task_id: int
    title: str
    assignee_id: int | None
    author_id: int


class AuditDetailTaskRestored(BaseModel):
    task_id: int
    title: str
    assignee_id: int | None
    author_id: int


AuditDetail = (
    AuditDetailOpportunityDeleted
    | AuditDetailOpportunityRestored
    | AuditDetailShareAdded
    | AuditDetailShareRoleChanged
    | AuditDetailShareRemoved
    | AuditDetailOwnerChanged
    | AuditDetailTimelineEntryDeleted
    | AuditDetailTimelineEntryRestored
    | AuditDetailNoteDeleted
    | AuditDetailNoteRestored
    | AuditDetailCommentDeleted
    | AuditDetailCommentRestored
    | AuditDetailTaskDeleted
    | AuditDetailTaskRestored
)

AUDIT_DETAIL_MODELS: dict[str, type[BaseModel]] = {
    "opportunity_deleted": AuditDetailOpportunityDeleted,
    "opportunity_restored": AuditDetailOpportunityRestored,
    "share_added": AuditDetailShareAdded,
    "share_role_changed": AuditDetailShareRoleChanged,
    "share_removed": AuditDetailShareRemoved,
    "owner_changed": AuditDetailOwnerChanged,
    "timeline_entry_deleted": AuditDetailTimelineEntryDeleted,
    "timeline_entry_restored": AuditDetailTimelineEntryRestored,
    "note_deleted": AuditDetailNoteDeleted,
    "note_restored": AuditDetailNoteRestored,
    "comment_deleted": AuditDetailCommentDeleted,
    "comment_restored": AuditDetailCommentRestored,
    "task_deleted": AuditDetailTaskDeleted,
    "task_restored": AuditDetailTaskRestored,
}


class AuditLogEntryPublic(BaseModel):
    id: int
    opportunity_id: int
    actor_id: int | None
    actor_name: str | None
    action: AuditAction
    detail: AuditDetail
    created_at: str


# --- Unified activity log (milestone 3.0) ----------------------------------

# One row of the merged log, discriminated on which mechanism recorded it
# (`app/activity.py`). The three shapes are kept apart rather than flattened
# into one wide model with everything nullable: a reader of the generated
# client should not have to discover by experiment that `version_number` is
# absent on an audit row.


class ActivitySystemEvent(BaseModel):
    """A system timeline entry — created, stage changed, sharing changed.

    Carries the sentence the timeline already shows, so the feed and the
    timeline say the same thing about the same event.
    """

    source: Literal["system_entry"] = "system_entry"
    entry_id: int
    title: str
    body: str


class ActivityAuditEvent(BaseModel):
    """An audit log row — a deletion or a restore. Owner-only, like the log."""

    source: Literal["audit_log"] = "audit_log"
    action: AuditAction
    detail: AuditDetail


class ActivityEditEvent(BaseModel):
    """A version row, read as the edit that produced it.

    `changed_fields` names the columns this version moved against the one
    before it, in the order `app/versioning.py` declares them. The values
    themselves are not here: what they said is the history screen's answer
    (`GET .../versions`), and this row is the occurrence.
    """

    source: Literal["version"] = "version"
    target: Literal["opportunity", "timeline_entry", "note", "task"]
    target_id: int
    version_number: int
    changed_fields: list[str]


# Discriminated rather than inferred: the tag is what a client switches on,
# and it is what puts a `oneOf` with a mapping into the OpenAPI schema so the
# generated TypeScript narrows on `detail.source` instead of on field presence.
ActivityDetail = Annotated[
    ActivitySystemEvent | ActivityAuditEvent | ActivityEditEvent,
    Field(discriminator="source"),
]


class ActivityEventPublic(BaseModel):
    id: int
    opportunity_id: int
    occurred_at: str
    actor_id: int | None
    actor_name: str | None
    detail: ActivityDetail


class AiAskRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class AiAskResponse(BaseModel):
    answer: str
    # The entry numbers the answer cited (milestone 3.9, **D-140**) -- the
    # per-deal sequence the timeline prints, not row ids, so a reader can find
    # what the model named. Renamed from `referenced_entry_ids`, which became a
    # lie the moment the context started citing numbers;
    # `docs/ROADMAP.md`'s breaking-changes table records it.
    referenced_entry_numbers: list[int]


class HealthStatus(BaseModel):
    status: Literal["ok"]
    schema_version: str
    database_writable: bool
    last_backup_at: str | None


NotificationType = Literal[
    "share_added",
    "share_role_changed",
    "share_removed",
    "owner_changed",
    "mention",
    "shared_activity",
    "comment",
    # Being handed a task is the same kind of event as being handed an
    # opportunity (`owner_changed`, 3.0a): somebody else decided you now owe
    # something, which is the one change nobody asks for. `notifications.type`
    # carries no CHECK constraint, so this costs no migration.
    "task_assigned",
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


class NotificationPayloadOwnerChanged(BaseModel):
    """Being handed a deal is the one access change nobody asked for, so it
    is told the same way a share is (milestone 3.0a). The previous owner is
    the actor, so they are not notified of their own action."""

    opportunity_id: int
    actor_id: int


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


class NotificationPayloadTaskAssigned(BaseModel):
    """Being handed a task, told the way being handed a deal is (3.0a's
    `owner_changed`): somebody else decided you now owe something. The task's
    title rides along because the inbox sentence names it, and a notification
    that says only "you were assigned a task" makes the reader open the deal to
    find out which one. The assigner is the actor, so assigning something to
    yourself notifies nobody."""

    opportunity_id: int
    actor_id: int
    task_id: int
    title: str
    due_date: str | None


NotificationPayload = (
    NotificationPayloadShareAdded
    | NotificationPayloadShareRoleChanged
    | NotificationPayloadShareRemoved
    | NotificationPayloadOwnerChanged
    | NotificationPayloadMention
    | NotificationPayloadTaskAssigned
    | NotificationPayloadSharedActivity
    | NotificationPayloadComment
)

NOTIFICATION_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "share_added": NotificationPayloadShareAdded,
    "share_role_changed": NotificationPayloadShareRoleChanged,
    "share_removed": NotificationPayloadShareRemoved,
    "owner_changed": NotificationPayloadOwnerChanged,
    "mention": NotificationPayloadMention,
    "shared_activity": NotificationPayloadSharedActivity,
    "comment": NotificationPayloadComment,
    "task_assigned": NotificationPayloadTaskAssigned,
}


class NotificationPublic(BaseModel):
    """`read_at` is the source of truth (milestone 1.7), so a client can tell
    not just whether a notification was read but order a history by it. The
    older boolean `read` was v1's and went with it, though the column stays —
    see `CLAUDE.md`'s "Notifications". `grouped_key` rides along now,
    unpopulated, ahead of v3's digest batching (D-141) -- see the migration's
    docstring for why it is added before it is used.
    """

    id: int
    type: NotificationType
    payload: NotificationPayload
    read_at: str | None
    grouped_key: str | None
    created_at: str


class NotificationMarkAllReadResponse(BaseModel):
    marked: int


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


# --- Saved views (milestone 2.2) -------------------------------------------

SavedViewEntity = Literal["opportunities", "timeline"]

MAX_VIEW_PARAMS_JSON_LENGTH = 2000


def _bounded_params(value: dict[str, str]) -> dict[str, str]:
    """`filters`/`sort` are literally a saved `URLSearchParams` (`lib/viewState.ts`),
    so they are validated as opaque key/value strings rather than a fixed
    schema -- a new filter field is then a frontend change, not a migration.
    The size cap exists only to bound one client's storage, not to interpret
    the content.
    """
    if len(json.dumps(value)) > MAX_VIEW_PARAMS_JSON_LENGTH:
        raise ValueError("Saved view parameters are too large")
    return value


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    entity: SavedViewEntity
    filters: dict[str, str] = Field(default_factory=dict)
    sort: dict[str, str] = Field(default_factory=dict)
    group_by: str | None = Field(default=None, max_length=50)
    is_shared: bool = False
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("filters", "sort")
    @classmethod
    def bounded_params(cls, value: dict[str, str]) -> dict[str, str]:
        return _bounded_params(value)


class SavedViewUpdate(BaseModel):
    """Every field optional: a rename does not have to resend the filters."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    filters: dict[str, str] | None = None
    sort: dict[str, str] | None = None
    group_by: str | None = Field(default=None, max_length=50)
    is_shared: bool | None = None
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("filters", "sort")
    @classmethod
    def bounded_params(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return _bounded_params(value) if value is not None else value


class SavedViewPublic(BaseModel):
    id: int
    created_by: int
    creator_name: str
    name: str
    entity: SavedViewEntity
    filters: dict[str, str]
    sort: dict[str, str]
    group_by: str | None
    is_shared: bool
    is_default: bool
    created_at: str
    updated_at: str
