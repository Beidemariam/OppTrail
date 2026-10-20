import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
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


# --- Custom fields (milestone 6.1, ADR 0006) --------------------------------

CustomFieldEntity = Literal["opportunity", "entry"]
CustomFieldType = Literal[
    "text",
    "number",
    "date",
    "select",
    "multi_select",
    "checkbox",
    "user",
]

# A key is what identifies a field inside the JSON column, so it has to be
# usable as an object key, as a query parameter and as an expression index's
# path (`json_extract(custom_values, '$.region')`) without quoting. The
# pattern is deliberately narrower than JSON allows: lower-case, digits and
# underscores, starting with a letter.
CUSTOM_FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"
MAX_CUSTOM_FIELD_OPTIONS = 50

# The value set a write may carry. Typed as `object` rather than a union,
# because what a value is allowed to be depends on a definition this schema
# cannot see -- `custom_fields.validated_values` is where that is decided,
# against the live definition set and inside the request's transaction.
CustomValues = dict[str, object]


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
    # Whether this caller administers the deployment (R.1c, **D-215**).
    # Derived from `ADMIN_EMAILS` rather than stored, and sent so the screens
    # can stop offering the two writes an administrator alone may make -- a
    # form that submits into a 403 is the thing `lib/permissions.ts` exists to
    # prevent. It decides which controls are drawn and never who may do what:
    # `permissions.require_admin` is the only enforcement.
    is_admin: bool = False


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
    # A whole value set, not a patch: see `custom_fields.validated_values`.
    # `None` means the caller did not mention custom fields, which on a create
    # is an empty set and on a `PATCH` is "leave what is there".
    custom_values: CustomValues | None = None

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
    custom_values: CustomValues | None = None

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
    # Only keys with a live definition (ADR 0006: the JSON is never trusted on
    # read), so archiving a field hides it without rewriting any row.
    custom_values: CustomValues = Field(default_factory=dict)

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


# Who may read an entry (milestone R.1b). Two values, CHECK-constrained in the
# schema beside `type`: `shared` is the deal's history, `private` is readable
# by its author alone.
EntryVisibility = Literal["shared", "private"]

# What a *new* entry is, when the client does not say — the human's ruling of
# 2026-10-14: *"privacy is set upfront and let's make it by default with a tick
# box to reveal it."* One constant, because the argument for the other default
# is a real one and flipping it should be one edit and a test, not an audit.
#
# Existing rows are `shared` (revision 0021): nothing written before this
# feature existed was authored with privacy in mind, and backfilling history as
# private would hide what people have already read.
DEFAULT_ENTRY_VISIBILITY: EntryVisibility = "private"


class TimelineEntryCreate(BaseModel):
    type: EntryType = "other"
    title: str = Field(min_length=1)
    body: str = ""
    event_timestamp: str
    follow_up_date: str | None = None
    # `docs/FEATURES.md` §3: a custom field appears "automatically in Table
    # columns, filters, and the entry form", so the entry form posts one.
    custom_values: CustomValues | None = None
    visibility: EntryVisibility = DEFAULT_ENTRY_VISIBILITY

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
    custom_values: CustomValues | None = None
    # Sealing and unsealing are an ordinary partial edit of the entry, not a
    # route of their own (R.1b): it is a field of the record, it is versioned
    # like the others, and the rule for who may change it is the rule for who
    # may change any of them. Sealing additionally withdraws the notifications
    # the entry caused, which the route does.
    visibility: EntryVisibility | None = None

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


class AttachmentPublic(BaseModel):
    """One file on an entry (milestone 4.3, `docs/FEATURES.md` §6).

    `sha256` is in the payload because it is what the file *is* -- two
    attachments with one digest are one document, which is worth being able to
    see -- and because it is how the stored file is addressed (ADR 0008). It is
    not a download token: the download route resolves the digest from the row
    the id names, after the same permission check as every other read, so
    knowing a digest grants nothing.

    `byte_size` rather than a formatted size: the reader's locale is the
    client's business, and the PDF export's manifest (milestone 4.4) formats it
    differently from the screen.
    """

    id: int
    entry_id: int
    sha256: str
    filename: str
    content_type: str
    byte_size: int
    uploaded_by: int
    uploader_name: str
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
    comments: list[CommentThread]


class PrivateNotePublic(BaseModel):
    """One person's own notes on one deal (milestone R.1b).

    Not a `NotePublic`: that hangs off an entry and is part of the deal's
    history. This hangs off nothing and is never part of it — no entry, no
    author field (there is only ever one reader), no comments, no versions.
    """

    opportunity_id: int
    body: str
    updated_at: str | None


class PrivateNoteUpdate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return value.strip()


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
    # Who may read it (R.1b). A sealed entry still travels — with its number,
    # its author and its time, and with everything else emptied — so that a
    # count, a page and an entry number mean the same thing to everybody.
    visibility: EntryVisibility = "shared"
    # The rule that wrote this entry, or `None` for everything a person wrote
    # (milestone 6.3a, **D-181**). It is the one fact the client cannot infer:
    # every automated entry is `system_generated`, and a system entry a person
    # caused -- "Opportunity created", a stage somebody moved, a share -- stays
    # undeletable, while this one can be deleted by the deal's owner or the
    # rule's creator. A button offered on the wrong one would be a button the
    # API refuses, so the distinction travels with the row.
    automation_rule_id: int | None = None
    custom_values: CustomValues = Field(default_factory=dict)
    notes: list[NotePublic]
    # The entry's files, read with it rather than through a list route of
    # their own (milestone 4.3) -- the shape a note's comments already have,
    # and for the same reason: an entry is the page unit, so its attachments
    # travel with it and a page of entries costs one more query rather than
    # one per card. The four writes that answer with an entry send `[]`, like
    # `notes`: the client invalidates the timeline and reads it back.
    attachments: list[AttachmentPublic]


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


# A task is for a handful of people, not a mailing list. The cap exists so one
# request cannot write an unbounded number of rows, which is the same reason
# `BULK_ACTION_MAX_IDS` exists; nothing in `FEATURES.md` §8 asks for more.
MAX_TASK_ASSIGNEES = 10


class TaskAssigneePublic(BaseModel):
    """One person a task is for (milestone 4.6).

    A list of these replaced the `assignee_id`/`assignee_name` pair: a task can
    be handed to several people, and two shapes for one fact is how a client
    comes to believe the wrong one. Ids and names arrive in the same order,
    ascending by id, which is the order the version snapshot records too.
    """

    user_id: int
    name: str


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
    # A list since milestone 4.6, replacing `assignee_email`. Empty means
    # nobody, which is what an unassigned task always was.
    assignee_emails: list[str] = Field(default_factory=list, max_length=MAX_TASK_ASSIGNEES)
    due_date: str | None = None
    entry_id: int | None = None

    @field_validator("assignee_emails")
    @classmethod
    def normalize_assignee_emails(cls, value: list[str]) -> list[str]:
        # Lowercased like `ShareCreate.email`, because signup stores it that
        # way: an assignee typed with a capital would otherwise resolve to
        # nobody and the task would be refused for a reason nobody could see.
        return [email.strip().lower() for email in value if email.strip()]

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
    # The whole list, or absent. Sending `[]` clears it; not sending the key
    # leaves it alone -- the same "absent means leave it" rule `due_date`
    # follows, which is why `model_fields_set` decides and not the value.
    assignee_emails: list[str] | None = Field(default=None, max_length=MAX_TASK_ASSIGNEES)
    due_date: str | None = None

    @field_validator("assignee_emails")
    @classmethod
    def normalize_assignee_emails(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [email.strip().lower() for email in value if email.strip()]

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


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return stripped(value)


class TaskCommentPublic(BaseModel):
    """One line of a task's discussion (milestone 4.5).

    Flat: no `parent_id`, no resolved pair, no reactions (**D-162**). It is
    immutable like every other comment in this app (invariant 2), so there is
    no `updated_at` and no `edited` marker -- the absence of those fields is
    the shape of the rule rather than an omission.
    """

    id: int
    task_id: int
    body: str
    created_by: int
    author_name: str
    created_at: str


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
    # Everyone this task is for (milestone 4.6), ascending by id. Empty is a
    # task nobody owes, which is what an unassigned one always was.
    assignees: list[TaskAssigneePublic]
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
    # The task's discussion, read with it rather than through a list route of
    # its own (milestone 4.5) -- the shape a note's comments already have, so a
    # page of tasks costs one more query rather than one per row. The writes
    # answer with the single comment they wrote, like `POST /notes/{id}/comments`.
    comments: list[TaskCommentPublic]


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
    # A list since milestone 4.6, from the snapshot's `assignee_ids`. A version
    # written before that revision carries one id and reads as a one-person
    # list, which is what it always meant.
    assignees: list[TaskAssigneePublic]
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
    "attachment_deleted",
    "attachment_restored",
    "task_comment_deleted",
    "task_comment_restored",
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


# An attachment is identified in the log by its name and its size: "which
# document disappeared" is answered by the filename, and the size is what
# tells two drafts of one proposal apart when both were called `proposal.pdf`.
class AuditDetailAttachmentDeleted(BaseModel):
    attachment_id: int
    entry_id: int
    filename: str
    byte_size: int


class AuditDetailAttachmentRestored(BaseModel):
    attachment_id: int
    entry_id: int
    filename: str
    byte_size: int


# A task comment is identified in the log by the task it was on and who wrote
# it: the body is gone from every read once it is deleted, and an owner asking
# what happened wants to know which discussion lost a line.
class AuditDetailTaskCommentDeleted(BaseModel):
    comment_id: int
    task_id: int
    author_id: int


class AuditDetailTaskCommentRestored(BaseModel):
    comment_id: int
    task_id: int
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
    | AuditDetailAttachmentDeleted
    | AuditDetailAttachmentRestored
    | AuditDetailTaskCommentDeleted
    | AuditDetailTaskCommentRestored
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
    "attachment_deleted": AuditDetailAttachmentDeleted,
    "attachment_restored": AuditDetailAttachmentRestored,
    "task_comment_deleted": AuditDetailTaskCommentDeleted,
    "task_comment_restored": AuditDetailTaskCommentRestored,
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
    # Date-scoped summaries (milestone 6.4, `docs/FEATURES.md` §14). Dates
    # rather than timestamps because the control is a date range and because
    # `until` means the whole of that day -- `ai_service.build_timeline_context`
    # is where that is turned into a bound. Both optional and independent:
    # "since March" and "before the demo" are both real questions.
    since: str | None = None
    until: str | None = None

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("since", "until")
    @classmethod
    def canonical_bound(cls, value: str | None) -> str | None:
        return canonical_date(value) if value else None

    @model_validator(mode="after")
    def range_runs_forwards(self) -> "AiAskRequest":
        if self.since and self.until and self.since > self.until:
            raise ValueError("The range ends before it starts")
        return self


class AiAskResponse(BaseModel):
    answer: str
    # The entry numbers the answer cited (milestone 3.9, **D-140**) -- the
    # per-deal sequence the timeline prints, not row ids, so a reader can find
    # what the model named. Renamed from `referenced_entry_ids`, which became a
    # lie the moment the context started citing numbers;
    # `docs/ROADMAP.md`'s breaking-changes table records it.
    referenced_entry_numbers: list[int]


JobName = Literal["automations", "backup"]
JobStatus = Literal["started", "succeeded", "failed"]


class JobRunPublic(BaseModel):
    """One execution of a periodic job (milestone 6.5, ADR 0004).

    `status` left at `started` with no `finished_at` is not a missing value:
    it is the signature of a process that died mid-job, which is the failure a
    finished-only log cannot show.
    """

    id: int
    job: JobName
    status: JobStatus
    detail: str | None
    started_at: str
    finished_at: str | None


class HealthStatus(BaseModel):
    status: Literal["ok"]
    schema_version: str
    database_writable: bool
    last_backup_at: str | None
    # The newest run of each job (milestone 6.5). On the probe rather than
    # only on an authenticated read because `docs/ARCHITECTURE.md`'s
    # Observability section names the failure this answers: "a silently dead
    # scheduler is the most likely v2 production failure", and whatever is
    # watching this endpoint is what would notice. It leaks nothing -- a job
    # name, a status and a time (**D-183**).
    jobs: list[JobRunPublic] = Field(default_factory=list)


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
    # A comment on a task you wrote or owe (milestone 4.5). Its own type rather
    # than `shared_activity`, for the reason `task_assigned` has one: it goes to
    # the two people the task is about rather than to everyone on the deal, and
    # an inbox line that cannot say which is which is a worse inbox.
    "task_comment",
    # A rule did something, or wants somebody told (milestone 6.3). Its own
    # type because the actor is not a person: the inbox sentence has to name
    # the rule, which is the only thing that makes an automated nudge
    # distinguishable from a colleague's (`docs/FEATURES.md` §11's "traceable").
    "automation",
]

# What a notification is about. "attachment" since milestone 4.3: a file
# landing on a shared deal is activity on it, told through the same
# `shared_activity` notification a note is rather than a type of its own --
# the sentence the inbox shows comes from the payload's `title`.
SourceType = Literal["entry", "note", "comment", "attachment"]

# What the search index holds. It was the same literal as `SourceType` until
# milestone 4.3 split them, and they stayed apart: this one is the set of
# things the FTS5 index stores terms for. Attachments joined it in **4.8** on
# the human's ruling -- indexed by *filename*, which is the only text a file
# has here, since nothing reads what is inside one (D-158). That milestone
# also widened ADR 0007's encoding from `* 4` to `* 8` (**D-167**), so this
# list has room for four more rather than none.
SearchKind = Literal["entry", "note", "comment", "attachment"]


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


class NotificationPayloadTaskComment(BaseModel):
    """Somebody said something about a task you wrote or owe (milestone 4.5).

    The task's title rides along for the reason `task_assigned`'s does: an
    inbox line that says only "new comment on a task" sends the reader looking
    for which one. The two recipients are a set, so the person who both wrote
    the task and owes it is told once.
    """

    opportunity_id: int
    actor_id: int
    task_id: int
    title: str


class NotificationPayloadAutomation(BaseModel):
    """What a rule wants this reader to know (milestone 6.3).

    `rule_name` rides along for the reason every other payload here carries a
    title: an inbox line that says only "an automation fired" sends the reader
    hunting for which one, and the rule's name is the only part of it they
    wrote themselves. `rule_id` is beside it so the sentence can link to the
    rule rather than only to the deal.
    """

    opportunity_id: int
    rule_id: int
    rule_name: str
    title: str
    body: str | None


NotificationPayload = (
    NotificationPayloadShareAdded
    | NotificationPayloadShareRoleChanged
    | NotificationPayloadShareRemoved
    | NotificationPayloadOwnerChanged
    | NotificationPayloadMention
    | NotificationPayloadTaskAssigned
    | NotificationPayloadTaskComment
    | NotificationPayloadSharedActivity
    | NotificationPayloadComment
    | NotificationPayloadAutomation
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
    "task_comment": NotificationPayloadTaskComment,
    "automation": NotificationPayloadAutomation,
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

    kind: SearchKind
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


# --- Dashboard (milestone 6.2, `docs/FEATURES.md` §10) ----------------------


class PipelineStage(BaseModel):
    stage: Stage
    deals: int
    value: str


class WinLoss(BaseModel):
    won: int
    lost: int
    won_value: str
    # `None` when nothing has closed: a team that has closed nothing has no
    # win rate, and 0.0 would read as having lost everything.
    rate: float | None


class StageDuration(BaseModel):
    stage: Stage
    # `None` where nothing has been measured. §10: earlier history "is absent
    # and should be labelled as such rather than silently shown as zero".
    average_days: float | None
    spans: int


class TimeInStage(BaseModel):
    stages: list[StageDuration]
    # The oldest stage change this database holds, which is how far back the
    # numbers above can be trusted. `None` when none has been recorded.
    earliest_change: str | None


class StalledOpportunity(BaseModel):
    opportunity_id: int
    name: str
    account_name: str
    stage: Stage
    value: str
    last_activity_at: str


class RepActivity(BaseModel):
    author_id: int
    author_name: str
    # `%Y-%W`, computed in SQLite over the stored fixed-width timestamp.
    week: str
    items: int


class ForecastStage(BaseModel):
    stage: Stage
    value: str
    probability: float
    weighted_value: str


class Forecast(BaseModel):
    weighted_value: str
    # The assumptions, returned beside the number: a forecast whose ramp
    # nobody can see is a number nobody should act on.
    stages: list[ForecastStage]


class DashboardPublic(BaseModel):
    """All six aggregations in one answer.

    One request rather than six, because a dashboard draws them together and
    six round trips would make the slowest one the whole screen's latency.
    Each is still measured separately against §10's 300 ms budget, which is
    what the CI assertion is about.
    """

    # The currency the four summing metrics are in, or `None` when the
    # accessible deals carry more than one -- in which case a total is a
    # number and not an amount, and the screen says so (milestone 6.2).
    currency: str | None
    pipeline: list[PipelineStage]
    win_loss: WinLoss
    time_in_stage: TimeInStage
    stalled: list[StalledOpportunity]
    activity: list[RepActivity]
    forecast: Forecast


# --- Custom field definitions (milestone 6.1) -------------------------------


class CustomFieldBase(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    required: bool = False
    position: int = 0
    # Only meaningful for `select` and `multi_select`; validated as empty for
    # every other type, because an option list on a checkbox is a definition
    # that says two different things.
    options: list[str] = Field(default_factory=list)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return stripped(value)

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        cleaned = [option.strip() for option in value if option.strip()]
        if len(cleaned) > MAX_CUSTOM_FIELD_OPTIONS:
            raise ValueError(f"A field may have at most {MAX_CUSTOM_FIELD_OPTIONS} options")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Options must be distinct")
        return cleaned


class CustomFieldCreate(CustomFieldBase):
    entity_type: CustomFieldEntity
    key: str = Field(min_length=1, max_length=40, pattern=CUSTOM_FIELD_KEY_PATTERN)
    type: CustomFieldType

    @model_validator(mode="after")
    def options_match_the_type(self) -> "CustomFieldCreate":
        chooses = self.type in ("select", "multi_select")
        if chooses and not self.options:
            raise ValueError("A select field needs at least one option")
        if not chooses and self.options:
            raise ValueError("Only select fields carry options")
        return self


class CustomFieldUpdate(CustomFieldBase):
    """What may change about a live field.

    Not `key`, `entity_type` or `type`: a key is what the stored JSON is
    filed under and a type is what every stored value already satisfies, so
    changing either would mean a data migration per field. ADR 0006's last
    consequence says the UI should archive and create instead, and refusing
    them here is what makes that the only route.

    Every field is required rather than optional -- unlike the `PATCH`
    schemas elsewhere in this app -- because a definition is small, read
    whole, and edited in one form.
    """


class CustomFieldPublic(BaseModel):
    id: int
    entity_type: CustomFieldEntity
    key: str
    label: str
    type: CustomFieldType
    options: list[str]
    required: bool
    position: int
    created_by: int
    created_at: str
    updated_at: str
    archived_at: str | None


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


# --- Automations (milestone 6.3) --------------------------------------------
#
# `docs/FEATURES.md` §11's constraint is the shape, not a limit bolted onto a
# general engine: one trigger, a flat ANDed condition list, one action. There
# is no rule-to-rule edge anywhere in these models, which is what removes loop
# detection from the design entirely.

AutomationTrigger = Literal[
    # Fired by a human write, inline after the commit that caused it.
    "stage_changed",
    "entry_created",
    "field_changed",
    # Fired by the clock. Evaluated by `POST /automation-rules/{id}/run` today
    # and by milestone 6.5's scheduler against the same function.
    "no_activity",
    "close_date_approaching",
]

AutomationAction = Literal["create_task", "notify_user", "add_entry", "change_stage"]

# `failed` is in the vocabulary and nothing writes it yet -- the same shape
# `notifications.grouped_key` has carried since milestone 1.7 (**D-095**), and
# for the same reason: it belongs to a caller one milestone away. A firing that
# raises today rolls back whole and is logged by `fire_event_after_commit` or
# answered as a 500; milestone 6.5's scheduler is the caller that needs the
# *outcome* recorded instead, because "a silently dead scheduler is the
# likeliest production failure". Writing it there is a query change rather than
# a migration.
AutomationOutcome = Literal["applied", "skipped", "failed"]

# Who an action lands on. Two answers, because a rule is written by one person
# about deals that may be owned by another: `owner` is the deal's owner (the
# "remind me" of §11's own example, when a rep writes a rule over their own
# pipeline), and `rule_creator` is whoever wrote the rule (a manager watching
# a team's deals wants their own task list to grow, not everybody else's).
AutomationRecipient = Literal["owner", "rule_creator"]

ConditionOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"]

# The opportunity fields a condition may compare and a `field_changed` trigger
# may watch. Deliberately not every column: `id`, `owner_id` and the
# timestamps are identity and bookkeeping rather than things a rule is about,
# and offering them would invite rules that read as data joins.
CONDITION_FIELDS: tuple[str, ...] = (
    "stage",
    "value",
    "currency",
    "name",
    "account_name",
    "expected_close_date",
)

# Compared as a number rather than as text. Everything else compares as a
# string, which is correct for the dates here only because they are canonical
# `YYYY-MM-DD` (`time_utils`) and therefore sort lexicographically.
NUMERIC_CONDITION_FIELDS: tuple[str, ...] = ("value",)

# A condition may also name a custom field, as `custom:<key>` -- the same
# prefix the frontend's column and filter keys use (milestone 6.1), so a field
# called `stage` is still not the stage.
CUSTOM_CONDITION_PREFIX = "custom:"

MAX_AUTOMATION_CONDITIONS = 5

# §11: rules are "capped in number". Per creator rather than globally, because
# a rule acts with its creator's authority (**D-173**) -- a global cap would
# let one person's twenty rules lock everybody else out of writing one.
MAX_ENABLED_RULES_PER_CREATOR = 20

# `no_activity` and `close_date_approaching` both count in days, and a window
# longer than a year is a rule that will never be understood by the person who
# reads it next.
MAX_TRIGGER_DAYS = 365


def _condition_field(value: str) -> str:
    if value.startswith(CUSTOM_CONDITION_PREFIX):
        key = value[len(CUSTOM_CONDITION_PREFIX) :]
        if not re.fullmatch(CUSTOM_FIELD_KEY_PATTERN, key):
            raise ValueError(f"'{value}' is not a custom field key")
        return value
    if value not in CONDITION_FIELDS:
        allowed = ", ".join(CONDITION_FIELDS)
        raise ValueError(f"'{value}' cannot be compared; use one of {allowed} or custom:<key>")
    return value


class AutomationCondition(BaseModel):
    """One comparison. ANDed with its siblings and never ORed (§11).

    The value arrives as a string whatever the field's type, because the
    condition list is stored as JSON and read back by a Python evaluator that
    knows which fields are numeric (`NUMERIC_CONDITION_FIELDS`). A typed union
    per field would be the more precise model and would buy nothing: the
    comparison still has to cope with a custom field whose type lives in a
    definition row rather than in this schema.
    """

    field: str = Field(min_length=1, max_length=60)
    op: ConditionOperator
    value: str = Field(max_length=200)

    @field_validator("field")
    @classmethod
    def known_field(cls, value: str) -> str:
        return _condition_field(value.strip())

    @model_validator(mode="after")
    def comparison_is_meaningful(self) -> "AutomationCondition":
        if self.op == "contains" and self.field in NUMERIC_CONDITION_FIELDS:
            raise ValueError(f"'{self.field}' is a number; 'contains' does not apply to it")
        if self.field in NUMERIC_CONDITION_FIELDS:
            try:
                Decimal(self.value)
            except InvalidOperation:
                raise ValueError(f"'{self.value}' is not a number") from None
        return self


class AutomationTriggerConfig(BaseModel):
    """Every trigger's parameters in one model, each optional.

    One model rather than a discriminated union per trigger (the shape D-010
    weighed for notification payloads and declined for the same reason): the
    whole set is five keys, the builder renders one form with the fields the
    chosen trigger uses, and `AutomationRuleBase` is where the cross-field
    rule lives -- which keys this trigger *requires* and which it refuses.
    """

    # stage_changed
    to_stage: str | None = None
    from_stage: str | None = None
    # entry_created
    entry_type: EntryType | None = None
    # field_changed
    field: str | None = None
    # no_activity, close_date_approaching
    days: int | None = Field(default=None, ge=1, le=MAX_TRIGGER_DAYS)

    @field_validator("to_stage", "from_stage")
    @classmethod
    def known_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in STAGES:
            raise ValueError(f"'{value}' is not a stage")
        return value

    @field_validator("field")
    @classmethod
    def watchable_field(cls, value: str | None) -> str | None:
        return _condition_field(value.strip()) if value is not None else value


class AutomationActionConfig(BaseModel):
    """Every action's parameters, the same way, with the same cross-field
    validation in `AutomationRuleBase`."""

    # create_task, notify_user, add_entry
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=2000)
    # create_task, notify_user
    recipient: AutomationRecipient = "owner"
    # create_task -- relative, because a rule fires on a day nobody picked.
    due_in_days: int | None = Field(default=None, ge=0, le=MAX_TRIGGER_DAYS)
    # add_entry
    entry_type: EntryType | None = None
    # change_stage
    stage: str | None = None

    @field_validator("title", "body")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return stripped(value) if value is not None else value

    @field_validator("stage")
    @classmethod
    def known_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in STAGES:
            raise ValueError(f"'{value}' is not a stage")
        return value


# Which `trigger_config` key each trigger needs, and which each action needs.
# Written as data because the check is the same in both directions -- required
# keys present, and nothing else set -- and because the builder's form reads
# the same two tables through the generated schema.
TRIGGER_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "stage_changed": (),
    "entry_created": (),
    "field_changed": ("field",),
    "no_activity": ("days",),
    "close_date_approaching": ("days",),
}

TRIGGER_OPTIONAL_KEYS: dict[str, tuple[str, ...]] = {
    "stage_changed": ("to_stage", "from_stage"),
    "entry_created": ("entry_type",),
    "field_changed": (),
    "no_activity": (),
    "close_date_approaching": (),
}

ACTION_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "create_task": ("title",),
    "notify_user": ("title",),
    "add_entry": ("title",),
    "change_stage": ("stage",),
}

ACTION_OPTIONAL_KEYS: dict[str, tuple[str, ...]] = {
    "create_task": ("body", "recipient", "due_in_days"),
    "notify_user": ("body", "recipient"),
    "add_entry": ("body", "entry_type"),
    "change_stage": (),
}


class AutomationRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    trigger_type: AutomationTrigger
    trigger: AutomationTriggerConfig = Field(default_factory=AutomationTriggerConfig)
    conditions: list[AutomationCondition] = Field(default_factory=list)
    action_type: AutomationAction
    action: AutomationActionConfig = Field(default_factory=AutomationActionConfig)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return stripped(value)

    @field_validator("conditions")
    @classmethod
    def bounded_conditions(cls, value: list[AutomationCondition]) -> list[AutomationCondition]:
        if len(value) > MAX_AUTOMATION_CONDITIONS:
            raise ValueError(f"A rule may have at most {MAX_AUTOMATION_CONDITIONS} conditions")
        return value

    @model_validator(mode="after")
    def config_matches_the_kind(self) -> "AutomationRuleBase":
        """A parameter set that does not belong to the chosen kind is a 422,
        not a silently ignored key.

        This is the same judgement `CustomFieldCreate.options_match_the_type`
        makes: a definition carrying options for a checkbox says two different
        things, and so does a `no_activity` rule carrying a stage to match.
        The alternative -- accepting and ignoring the extra key -- produces a
        rule whose stored form does not mean what the person who wrote it
        read on screen.
        """
        self._check("trigger", self.trigger, TRIGGER_REQUIRED_KEYS, TRIGGER_OPTIONAL_KEYS)
        self._check("action", self.action, ACTION_REQUIRED_KEYS, ACTION_OPTIONAL_KEYS)
        if self.action_type == "add_entry" and self.action.entry_type == "stage_change":
            # A rule writing a `stage_change` entry would feed milestone 6.2's
            # time-in-stage aggregation -- which reads exactly that type -- with
            # a stage change that never happened. The `change_stage` action
            # writes one properly, having actually moved the deal.
            raise ValueError(
                "A rule cannot write a stage change entry; use the change stage action"
            )
        return self

    def _check(
        self,
        label: str,
        config: BaseModel,
        required: dict[str, tuple[str, ...]],
        optional: dict[str, tuple[str, ...]],
    ) -> None:
        kind = self.trigger_type if label == "trigger" else self.action_type
        allowed = set(required[kind]) | set(optional[kind])
        defaults = type(config)()
        for key in required[kind]:
            if getattr(config, key) is None:
                raise ValueError(f"A '{kind}' {label} needs '{key}'")
        for key in type(config).model_fields:
            if key in allowed:
                continue
            if getattr(config, key) != getattr(defaults, key):
                raise ValueError(f"A '{kind}' {label} does not take '{key}'")


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(AutomationRuleBase):
    """Read whole, edited in one form, written whole -- like a custom field
    definition and unlike the `PATCH` schemas over content. A rule is small
    and its parts constrain each other, so a partial update would have to
    re-validate against the stored half anyway."""


class AutomationRulePublic(BaseModel):
    id: int
    name: str
    trigger_type: AutomationTrigger
    trigger: AutomationTriggerConfig
    conditions: list[AutomationCondition]
    action_type: AutomationAction
    action: AutomationActionConfig
    enabled: bool
    created_by: int
    creator_name: str
    created_at: str
    updated_at: str
    archived_at: str | None


class AutomationRunPublic(BaseModel):
    """What a rule did, or would have done.

    `dry_run` is the mode and `outcome` is the answer, so a preview row still
    says whether it would have applied. `entry_id` is the system entry §11
    requires every automated write to leave, and is NULL on a skip and on
    every dry run -- nothing was written to point at.
    """

    id: int
    rule_id: int
    rule_name: str
    opportunity_id: int
    opportunity_name: str
    outcome: AutomationOutcome
    reason: str | None
    entry_id: int | None
    dry_run: bool
    created_at: str


class AutomationRunResponse(BaseModel):
    """The answer to running a rule by hand, in either mode.

    Not paginated, unlike the run log: this is the result of one action the
    caller just took, capped by `AUTOMATION_RUN_LIMIT` deals rather than by a
    cursor over something that is still changing (the choice milestone 6.2
    made for an aggregate, for the same reason).
    """

    dry_run: bool
    considered: int
    runs: list[AutomationRunPublic]


# --- The AI's filter proposal (milestone 6.4) -------------------------------

# The sort fields the board offers, mirroring `lib/domain.ts`'s `sortFields`.
# Written out rather than derived because the model is told this list and the
# answer is checked against it: a value the board cannot sort by would be a
# filter that silently does nothing.
FILTER_SORT_FIELDS: tuple[str, ...] = (
    "updated_at",
    "name",
    "account_name",
    "stage",
    "value",
    "expected_close_date",
    "owner_name",
    "created_at",
)


class AiFilterRequest(BaseModel):
    request: str = Field(min_length=1, max_length=300)

    @field_validator("request")
    @classmethod
    def strip_request(cls, value: str) -> str:
        return stripped(value)


class AiFilterProposal(BaseModel):
    """A filter the model suggested, after validation (**D-186**).

    `docs/FEATURES.md` §14 calls this "the safest high-value AI feature here,
    because its output is a query the user can inspect" -- and the inspection
    only means anything if what is shown is what would be applied. So every
    field here is one the board already has, parsed out of the model's JSON
    and dropped if it is not: an unknown stage, a sort field that does not
    exist, a value that is not a number. The same rule ADR 0006 applies to a
    custom value read from a JSON column, for the same reason.

    `ignored` is what was dropped, and it is shown. A proposal that quietly
    discards half of what somebody asked for is a proposal they would accept
    believing it did more.
    """

    # Exactly the filters the board has, and no more. An earlier draft of
    # this carried `owner`, `closing_before` and `closing_after` as well --
    # fields the filter bar does not offer -- which would have made a
    # proposal that cannot be applied, inspectable and useless. That is
    # D-179's mistake in the other direction: inventing a capability rather
    # than a constraint. A request for one of them is reported in `ignored`.
    q: str | None = None
    stage: str | None = None
    min_value: str | None = None
    max_value: str | None = None
    stalled: bool | None = None
    sort: str | None = None
    direction: Literal["asc", "desc"] | None = None


class AiFilterResponse(BaseModel):
    proposal: AiFilterProposal
    # Keys the model answered with that this app does not have, or could not
    # read. Named rather than counted: "I ignored `region`" is actionable and
    # "I ignored one thing" is not.
    ignored: list[str]
    # True when nothing survived validation, which is a different answer from
    # a filter that happens to be empty -- the screen says so rather than
    # offering an Apply that would do nothing.
    empty: bool
