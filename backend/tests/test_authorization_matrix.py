"""The authorization matrix required by brief §6.4.

Every endpoint the app serves is checked against all five actors — owner,
editor, viewer, an unrelated signed-in user, and an anonymous caller — and the
list of endpoints is read out of the running app (`tests/route_registry.py`),
so a route that ships without a matrix entry fails the suite rather than going
unexamined.

Two conventions the expectations encode, both from `CLAUDE.md`:

- Absence of access is 404, not 403, so opportunity existence does not leak.
  An unrelated user therefore sees 404 on opportunity-scoped routes while a
  viewer, who does have access, sees 403 when the action is beyond their role.
- Changing an existing timeline item is reserved to its author or the
  opportunity owner (DECISIONS.md D-005). The fixture's entry, note and comment
  are authored by the owner, so the editor's 403 on those rows is the tightened
  rule that F.5 introduced and this matrix is the place F.5's carried-over item
  lands.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pytest
from conftest import CsrfClient
from fastapi.testclient import TestClient
from route_registry import Endpoint, iter_endpoints

from app.main import app
from app.settings import settings

# WeasyPrint needs native libraries that are only installed in the container
# (see CLAUDE.md's WeasyPrint section and tests/test_export.py); missing them
# surfaces as an OSError from cffi, not an ImportError, so
# `pytest.importorskip` would not catch it.
try:
    import weasyprint  # noqa: F401

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False

PDF_EXPORT_ENDPOINT = Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/export/pdf")

Actor = Literal["anonymous", "unrelated", "viewer", "editor", "owner"]

# Least-privileged first. Within one endpoint's test the calls run in this
# order, so every rejection is observed before the call that is allowed to
# change state.
ACTORS: tuple[Actor, ...] = ("anonymous", "unrelated", "viewer", "editor", "owner")

PASSWORD = "password123"


@dataclass
class World:
    """One opportunity, its three participants, and an outsider."""

    clients: dict[Actor, TestClient]
    user_ids: dict[Actor, int]
    emails: dict[Actor, str]
    opportunity_id: int
    entry_id: int
    note_id: int
    # The note's current `updated_at`, for the PATCH's edit guard (ADR 0003).
    note_updated_at: str
    comment_id: int
    notification_id: int
    saved_view_id: int
    # Deleted rows, for the restore endpoints: there is nothing to restore
    # about a live one, and a restore of what is already here is a 404.
    deleted_entry_id: int
    deleted_note_id: int
    deleted_comment_id: int
    deleted_opportunity_id: int
    # Milestone 4.1. `task_id` is the owner's own task, so the author-or-owner
    # cases are read against a row the editor did not write -- which is the
    # distinction D-005's rule turns on.
    task_id: int
    deleted_task_id: int
    # Milestone 4.3. Uploaded by the **owner**, so the editor's 403 on the
    # delete is D-005's rule read against a file they did not upload.
    attachment_id: int
    deleted_attachment_id: int
    # Milestone 4.5, on the owner's task and written by the owner, so the
    # editor's 403 on the delete is D-005 read against a comment they did not
    # write.
    task_comment_id: int
    deleted_task_comment_id: int
    # Milestone 6.1. A definition is not opportunity-scoped and not personal
    # either, so neither `permissions.py` nor the saved views' creator-only
    # rule applies: any authenticated caller may define, edit and archive a
    # field (**D-171**). `archived_field_id` is there so the restore route is
    # exercised against a row that is actually archived.
    custom_field_id: int
    archived_field_id: int
    # Milestone 6.3. Written by the **owner** actor, so the creator-only rule
    # (**D-173**) is read against a rule the other four did not write -- and
    # creating one is open to all of them, which is the asymmetry this
    # feature turns on: a rule grants nobody authority they did not have.
    automation_rule_id: int


@dataclass(frozen=True)
class Case:
    """What one endpoint is expected to answer, per actor.

    `expected` maps an actor to a status code. `SAME_FOR_EVERYONE` marks the
    handful of surfaces that are deliberately identity-independent (health, the
    API 404 catch-all, the static frontend); there the assertion is that the
    response does not vary by caller, which is the property worth protecting.

    `files` is the multipart alternative to `body`, for the one route in the app
    that takes a file (milestone 4.3): the upload is a real multipart request
    here rather than a JSON stand-in, because what the parser does with it is
    part of what is being authorized.
    """

    expected: dict[Actor, int] | None
    url: Callable[[World], str]
    body: Callable[[World, Actor], Any] | None = None
    files: Callable[[World, Actor], Any] | None = None
    same_for_everyone: bool = False
    notes: str = ""


SAME_FOR_EVERYONE = Case(expected=None, url=lambda world: "", same_for_everyone=True)


def public(url: Callable[[World], str], note: str) -> Case:
    return Case(expected=None, url=url, same_for_everyone=True, notes=note)


def _unique_email(actor: Actor) -> str:
    return f"matrix-signup-{actor}@example.com"


def all_actors(status: int) -> dict[Actor, int]:
    return dict.fromkeys(ACTORS, status)


def authenticated_only(status: int) -> dict[Actor, int]:
    expected = all_actors(status)
    expected["anonymous"] = 401
    return expected


def creator_only(status: int) -> dict[Actor, int]:
    """Anybody signed in may read; only the row's creator may write it.

    The shape the automation rules use (**D-173**). `owner` is the actor that
    created the fixture's rule, so it is the only one that succeeds; the other
    three signed-in actors get 403 rather than 404, because these rows are not
    opportunity-scoped and their existence leaks nothing (D-007's reasoning).
    """
    return {
        "anonymous": 401,
        "unrelated": 403,
        "viewer": 403,
        "editor": 403,
        "owner": status,
    }


def scoped(*, viewer: int, editor: int, owner: int) -> dict[Actor, int]:
    """The shape almost every opportunity-scoped endpoint has."""
    return {
        "anonymous": 401,
        "unrelated": 404,
        "viewer": viewer,
        "editor": editor,
        "owner": owner,
    }


MATRIX: dict[Endpoint, Case] = {
    # --- Authentication -------------------------------------------------
    Endpoint("POST", "/api/v2/auth/signup"): Case(
        expected=all_actors(201),
        url=lambda world: "/api/v2/auth/signup",
        body=lambda world, actor: {
            "email": _unique_email(actor),
            "password": PASSWORD,
            "name": "Matrix Signup",
        },
        notes="Open by design: signing up is how a user comes to exist.",
    ),
    Endpoint("POST", "/api/v2/auth/login"): Case(
        expected=all_actors(200),
        url=lambda world: "/api/v2/auth/login",
        body=lambda world, actor: {"email": world.emails["owner"], "password": PASSWORD},
        notes="Open by design; credentials, not the session, are the control.",
    ),
    Endpoint("POST", "/api/v2/auth/logout"): Case(
        expected=all_actors(200),
        url=lambda world: "/api/v2/auth/logout",
        body=lambda world, actor: None,
        notes=(
            "Deliberately not behind get_current_user: clearing a cookie that is "
            "already absent or expired is a no-op, and answering 401 would leave a "
            "client unable to discard a stale session."
        ),
    ),
    Endpoint("POST", "/api/v2/auth/password"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/auth/password",
        body=lambda world, actor: {
            "current_password": PASSWORD,
            "new_password": "replacement-password-123",
        },
    ),
    Endpoint("GET", "/api/v2/auth/me"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/auth/me",
    ),
    # --- Opportunities ---------------------------------------------------
    Endpoint("GET", "/api/v2/opportunities"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/opportunities",
        notes="Scoped by the query itself: the list only contains what you can see.",
    ),
    Endpoint("POST", "/api/v2/opportunities"): Case(
        expected=authenticated_only(201),
        url=lambda world: "/api/v2/opportunities",
        body=lambda world, actor: {
            "name": "Matrix opportunity",
            "account_name": "Acme",
            "stage": "Prospecting",
        },
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}",
    ),
    Endpoint("PATCH", "/api/v2/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}",
        body=lambda world, actor: {"stage": "Qualification"},
        notes="Opportunity fields are the owner's: require_opportunity_owner.",
    ),
    Endpoint("DELETE", "/api/v2/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}",
    ),
    # --- Sharing and audit log -------------------------------------------
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/shares"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/shares",
    ),
    # Milestone 3.2 (D-123): who is on the deal, for the mention autocomplete.
    # Every role, unlike the share list above it -- a mention only reaches
    # someone who already has access, so a viewer writing a comment needs the
    # same list the owner does. What stays owner-only is the grant: who invited
    # whom and when (tests/test_sharing.py holds both halves).
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/members"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/members",
    ),
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/shares"): Case(
        expected=scoped(viewer=403, editor=403, owner=201),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/shares",
        body=lambda world, actor: {"email": world.emails["unrelated"], "role": "viewer"},
    ),
    Endpoint("PATCH", "/api/v2/opportunities/{opportunity_id}/shares/{user_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: (
            f"/api/v2/opportunities/{world.opportunity_id}/shares/{world.user_ids['viewer']}"
        ),
        body=lambda world, actor: {"role": "editor"},
    ),
    Endpoint("DELETE", "/api/v2/opportunities/{opportunity_id}/shares/{user_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: (
            f"/api/v2/opportunities/{world.opportunity_id}/shares/{world.user_ids['viewer']}"
        ),
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/audit-log"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/audit-log",
        notes="Owner-only forensics (CLAUDE.md, Auditability).",
    ),
    # --- Watchers (milestone 3.3a, D-129) ---------------------------------
    # `docs/FEATURES.md` §7: "follow an opportunity you are not shared on."
    # The three `.../watch` routes check only that the opportunity exists
    # (`require_opportunity_exists`), not who may read it -- so an unrelated,
    # signed-in user gets the same 200/204 a viewer or an owner does, which is
    # `authenticated_only` rather than `scoped`. `tests/test_watchers.py`
    # holds the case this table cannot: the same caller still gets 404 from
    # every other opportunity-scoped route.
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/watch"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/watch",
    ),
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/watch"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/watch",
        body=lambda world, actor: None,
    ),
    Endpoint("DELETE", "/api/v2/opportunities/{opportunity_id}/watch"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/watch",
    ),
    # Who is watching stays owner-only, the same visibility rule as the share
    # list above it.
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/watchers"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/watchers",
    ),
    # --- Timeline ---------------------------------------------------------
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/timeline"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/timeline",
    ),
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/timeline"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/timeline",
        body=lambda world, actor: {
            "type": "call",
            "title": "Matrix entry",
            "body": "",
            "event_timestamp": "2026-09-04T10:00",
        },
    ),
    Endpoint("PATCH", "/api/v2/timeline/{entry_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}",
        body=lambda world, actor: {"title": "Matrix entry, edited"},
        notes="Entry authored by the owner, so the editor is not its author (D-005).",
    ),
    Endpoint("DELETE", "/api/v2/timeline/{entry_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}",
    ),
    Endpoint("POST", "/api/v2/timeline/{entry_id}/notes"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}/notes",
        body=lambda world, actor: {"body": "Matrix note"},
        notes="Editors add freely; only changing an existing item is restricted.",
    ),
    Endpoint("PATCH", "/api/v2/notes/{note_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/notes/{world.note_id}",
        body=lambda world, actor: {
            "body": "Matrix note, edited",
            "updated_at": world.note_updated_at,
        },
        notes=(
            "Carries ADR 0003's edit guard, so the body sends the note's real "
            "updated_at: a stale one is 409 for everybody and would hide the "
            "403s this row exists to check (tests/test_events.py has the "
            "conflict cases)."
        ),
    ),
    Endpoint("DELETE", "/api/v2/notes/{note_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/notes/{world.note_id}",
    ),
    Endpoint("POST", "/api/v2/notes/{note_id}/comments"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/notes/{world.note_id}/comments",
        body=lambda world, actor: {"body": "Matrix comment"},
    ),
    Endpoint("DELETE", "/api/v2/comments/{comment_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/comments/{world.comment_id}",
    ),
    # Resolving a thread is the author-or-owner rule (D-128), so the editor
    # is refused on the owner's thread exactly as they are for deleting it.
    # Both directions are idempotent, which is what lets the matrix call them
    # in any order against one shared world.
    Endpoint("POST", "/api/v2/comments/{comment_id}/resolve"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/comments/{world.comment_id}/resolve",
        body=lambda world, actor: None,
    ),
    Endpoint("POST", "/api/v2/comments/{comment_id}/unresolve"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/comments/{world.comment_id}/unresolve",
        body=lambda world, actor: None,
    ),
    # --- Tasks (milestone 4.1, `docs/FEATURES.md` §8) --------------------
    # Writing one down is adding, so editors may and viewers may not -- the
    # gate entries and notes use. Changing what somebody typed is
    # author-or-owner (D-005), so the editor gets 403 on a task the owner
    # wrote. Completing is the exception (**D-142**): this task is assigned to
    # the editor, and an assignee may close what they did not write.
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/tasks"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/tasks",
        body=lambda world, actor: {"title": f"Task by {actor}"},
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/tasks"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/tasks",
    ),
    # My Tasks is not opportunity-scoped: it answers with the caller's own
    # assignments, so every signed-in reader gets a 200 and an outsider gets an
    # empty page rather than a 404 -- there is no id in the URL whose existence
    # could leak.
    Endpoint("GET", "/api/v2/tasks"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/tasks",
    ),
    Endpoint("PATCH", "/api/v2/tasks/{task_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/tasks/{world.task_id}",
        body=lambda world, actor: {"title": f"Edited by {actor}"},
    ),
    Endpoint("POST", "/api/v2/tasks/{task_id}/complete"): Case(
        expected=scoped(viewer=403, editor=200, owner=200),
        url=lambda world: f"/api/v2/tasks/{world.task_id}/complete",
        body=lambda world, actor: None,
        notes="The editor is this task's assignee (D-142); idempotent, so order is free.",
    ),
    Endpoint("POST", "/api/v2/tasks/{task_id}/reopen"): Case(
        expected=scoped(viewer=403, editor=200, owner=200),
        url=lambda world: f"/api/v2/tasks/{world.task_id}/reopen",
        body=lambda world, actor: None,
    ),
    Endpoint("DELETE", "/api/v2/tasks/{task_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/tasks/{world.task_id}",
    ),
    # Owner-only, like the other three edit histories (D-096): invariant 8 names
    # the opportunity owner, and this app has no admin role.
    Endpoint("GET", "/api/v2/tasks/{task_id}/versions"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/tasks/{world.task_id}/versions",
    ),
    # Owner-only like the history it reads from, and idempotent -- restoring what
    # is already current writes nothing (D-120), so the matrix may call it in any
    # order.
    Endpoint("POST", "/api/v2/tasks/{task_id}/versions/{version_number}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/tasks/{world.task_id}/versions/1/restore",
        body=lambda world, actor: None,
    ),
    Endpoint("POST", "/api/v2/tasks/{task_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/tasks/{world.deleted_task_id}/restore",
        body=lambda world, actor: None,
    ),
    # --- A task's discussion (milestone 4.5) ----------------------------
    # Writing one is adding, so it is the editors-may gate a note comment has;
    # removing one is author-or-owner (D-005), and the matrix's comment is the
    # owner's. There is no PATCH: a comment is immutable (invariant 2).
    Endpoint("POST", "/api/v2/tasks/{task_id}/comments"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/tasks/{world.task_id}/comments",
        body=lambda world, actor: {"body": f"Comment by {actor}"},
    ),
    Endpoint("DELETE", "/api/v2/task-comments/{comment_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/task-comments/{world.task_comment_id}",
    ),
    Endpoint("POST", "/api/v2/task-comments/{comment_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/task-comments/{world.deleted_task_comment_id}/restore",
        body=lambda world, actor: None,
    ),
    # --- Attachments (milestone 4.3) ------------------------------------
    # Uploading is adding, so it is the gate a note already has: editors may,
    # viewers may not. Downloading is a *read* of the opportunity, so a viewer
    # may -- which is the roadmap's acceptance criterion for this phase, and
    # the reason the file never leaves the volume any other way. Removing one
    # is author-or-owner (D-005), and the matrix's attachment is the owner's.
    Endpoint("POST", "/api/v2/timeline/{entry_id}/attachments"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}/attachments",
        files=lambda world, actor: {
            "file": (f"{actor}.txt", f"posted by {actor}".encode(), "text/plain")
        },
    ),
    Endpoint("GET", "/api/v2/attachments/{attachment_id}/download"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/attachments/{world.attachment_id}/download",
    ),
    Endpoint("DELETE", "/api/v2/attachments/{attachment_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/attachments/{world.attachment_id}",
    ),
    Endpoint("POST", "/api/v2/attachments/{attachment_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/attachments/{world.deleted_attachment_id}/restore",
        body=lambda world, actor: None,
    ),
    # Reactions (milestone 3.3a, D-130): any role that may write the timeline
    # may react -- unlike resolve, this is not the author-or-owner rule, since
    # a reaction changes nothing about what anyone wrote. Both routes are
    # idempotent, which is what lets the matrix call them in any order.
    Endpoint("POST", "/api/v2/comments/{comment_id}/reactions"): Case(
        expected=scoped(viewer=403, editor=200, owner=200),
        url=lambda world: f"/api/v2/comments/{world.comment_id}/reactions",
        body=lambda world, actor: {"emoji": "👍"},
    ),
    Endpoint("DELETE", "/api/v2/comments/{comment_id}/reactions/{emoji}"): Case(
        expected=scoped(viewer=403, editor=200, owner=200),
        url=lambda world: f"/api/v2/comments/{world.comment_id}/reactions/%F0%9F%91%8D",
        notes=(
            "URL-encoded 👍. Idempotent, so a role that may write the timeline "
            "gets 200 even though this world's comment carries no reaction yet."
        ),
    ),
    # --- AI agent ---------------------------------------------------------
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/ai/ask"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/ai/ask",
        body=lambda world, actor: {"question": "What happened?"},
        notes="Read-only, so viewers may ask: require_opportunity_access.",
    ),
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/ai/ask/stream"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/ai/ask/stream",
        body=lambda world, actor: {"question": "What happened?"},
        notes=(
            "The same answer as `ask`, arriving sooner (milestone 6.4), so "
            "the same rule: asking a question is a read. The permission is "
            "resolved before the response starts, which is why an outsider "
            "gets a 404 rather than a 200 whose first frame is an error."
        ),
    ),
    Endpoint("POST", "/api/v2/ai/filter"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/ai/filter",
        body=lambda world, actor: {"request": "deals in negotiation over 50k"},
        notes=(
            "Not opportunity-scoped: a filter is over the board and every "
            "signed-in caller has one. No deal content is sent to the model, "
            "and the rows the filter later selects are permission-filtered "
            "by the ordinary list read (**D-186**)."
        ),
    ),
    # --- Export -----------------------------------------------------------
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/export/json"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/export/json",
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/export/csv"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/export/csv",
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/export/pdf"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/export/pdf",
    ),
    # --- Notifications ----------------------------------------------------
    Endpoint("GET", "/api/v2/notifications"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/notifications",
        notes="Scoped by the query: a user only ever reads their own rows.",
    ),
    Endpoint("PATCH", "/api/v2/notifications/{notification_id}/read"): Case(
        expected={
            "anonymous": 401,
            "unrelated": 404,
            "viewer": 404,
            "editor": 404,
            "owner": 200,
        },
        url=lambda world: f"/api/v2/notifications/{world.notification_id}/read",
        body=lambda world, actor: None,
        notes="The fixture's notification belongs to the owner; everyone else 404s.",
    ),
    # --- v2 surface (paginated collection reads) --------------------------
    # Same permission rules as the v1 route each one mirrors: the version
    # boundary carries response shape, not authorization.
    Endpoint("GET", "/api/v2/opportunities"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/opportunities",
        notes="Scoped by the query itself, like its v1 twin.",
    ),
    Endpoint("GET", "/api/v2/stages"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/stages",
        notes="The fixed stage list; no user data, but not offered anonymously.",
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/timeline"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/timeline",
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/shares"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/shares",
    ),
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/audit-log"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/audit-log",
    ),
    # --- Edit history (milestone 2.10) ------------------------------------
    # All three read under the audit log's rule rather than the opportunity's:
    # owner-only, 403 for a viewer or editor who can see the item itself
    # (D-096).
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/versions"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/versions",
    ),
    Endpoint("GET", "/api/v2/timeline/{entry_id}/versions"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}/versions",
    ),
    Endpoint("GET", "/api/v2/notes/{note_id}/versions"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/notes/{world.note_id}/versions",
        notes="Open to every role until 2.10 gave the three histories one rule.",
    ),
    # Restoring a version (milestone 3.1c). The same rule as reading the
    # history it restores from — owner-only, 403 for a viewer or editor who
    # can see the item, 404 for an outsider — and not to be confused with the
    # `/restore` routes below, which undo a soft delete rather than an edit.
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/versions/{version_number}/restore"): (
        Case(
            expected=scoped(viewer=403, editor=403, owner=200),
            url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/versions/1/restore",
            body=lambda world, actor: None,
            notes=(
                "Version 1 is the state the fixture created, and nothing has "
                "edited it since, so the owner's call restores what is already "
                "current and writes nothing (D-120)."
            ),
        )
    ),
    Endpoint("POST", "/api/v2/timeline/{entry_id}/versions/{version_number}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/timeline/{world.entry_id}/versions/1/restore",
        body=lambda world, actor: None,
    ),
    Endpoint("POST", "/api/v2/notes/{note_id}/versions/{version_number}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/v2/notes/{world.note_id}/versions/1/restore",
        body=lambda world, actor: None,
        notes=(
            "Owner-only even though an editor may edit their own note: putting "
            "an old version back is a history operation, and the history is the "
            "owner's (D-096, D-120)."
        ),
    ),
    # Milestone 3.4: ADR 0003's live-update stream. `require_opportunity_access`
    # — the same gate as reading the timeline, because an event says only
    # "read it again". The stream carries no row content, so there is nothing
    # for a role to filter; it closes itself after
    # `settings.sse_max_connection_seconds`, which `conftest.short_event_streams`
    # holds down to a fraction of a second so this row does not hang the suite.
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/events"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/events",
    ),
    # --- Unified activity log (milestone 3.0) -----------------------------
    Endpoint("GET", "/api/v2/opportunities/{opportunity_id}/activity"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/activity",
        notes=(
            "Answered for every role, and the role decides the rows rather "
            "than the status: system entries for anyone with access, the "
            "audit and version halves only for the owner (D-101). "
            "tests/test_activity.py holds which rows each one gets."
        ),
    ),
    Endpoint("GET", "/api/v2/notifications"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/notifications",
        notes="Scoped by the query: a user only ever reads their own rows.",
    ),
    Endpoint("POST", "/api/v2/notifications/mark-all-read"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/notifications/mark-all-read",
        body=lambda world, actor: None,
        notes="Scoped by the query: marks only the caller's own rows.",
    ),
    # The dashboard (milestone 6.2). Like search, a read that spans
    # opportunities: there is no role to resolve, because the rows it
    # aggregates are chosen by `ACCESSIBLE_OPPORTUNITY_IDS_SQL` inside each
    # query. Every signed-in caller gets an answer; what differs is whose
    # deals are in it, which `test_dashboard.py` is where to assert.
    Endpoint("GET", "/api/v2/dashboard"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/dashboard",
        notes="Scoped by the query: six aggregations over the caller's own accessible deals.",
    ),
    # Custom field definitions (milestone 6.1, **D-171**). Global metadata, not
    # a record: `docs/FEATURES.md` §3 says "admin-defined" and this app has no
    # admin role, so the rule is any authenticated caller. Every actor below is
    # therefore identical except anonymous -- which is the point worth pinning,
    # because it is the widest write surface in the app and a future ruling
    # that narrows it should break this test loudly.
    Endpoint("GET", "/api/v2/custom-fields"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/custom-fields",
        notes="A reader has to know what the columns on their screen mean.",
    ),
    Endpoint("POST", "/api/v2/custom-fields"): Case(
        expected=authenticated_only(201),
        url=lambda world: "/api/v2/custom-fields",
        body=lambda world, actor: {
            "entity_type": "opportunity",
            "key": f"matrix_{actor}_field",
            "label": f"Matrix {actor}",
            "type": "text",
        },
        notes=(
            "Any signed-in user may define a field; the key is per-actor "
            "so the runs do not collide."
        ),
    ),
    Endpoint("PATCH", "/api/v2/custom-fields/{field_id}"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/custom-fields/{world.custom_field_id}",
        body=lambda world, actor: {"label": f"Renamed by {actor}", "required": False},
        notes="Label, options, required and position. Never key or type (ADR 0006).",
    ),
    Endpoint("POST", "/api/v2/custom-fields/{field_id}/archive"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/custom-fields/{world.custom_field_id}/archive",
        body=lambda world, actor: None,
        notes="Idempotent, so every actor in turn answers 200 rather than the first one winning.",
    ),
    Endpoint("POST", "/api/v2/custom-fields/{field_id}/restore"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/custom-fields/{world.archived_field_id}/restore",
        body=lambda world, actor: None,
        notes="The undo of archive, against a field the fixture archived.",
    ),
    # --- Automations (milestone 6.3) ------------------------------------
    # Two rules rather than one, and every actor row pins the asymmetry:
    # creating a rule is open to anybody signed in (D-173, the custom-field
    # argument plus a stronger one -- a rule acts with its creator's
    # authority), while changing, running or reading the behaviour of one is
    # the creator's alone, because a rule performs writes attributed to them.
    Endpoint("GET", "/api/v2/automation-rules"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/automation-rules",
        notes=(
            "Open: a reader who finds a stage changing under them should be "
            "able to see which rule did it and whose it is."
        ),
    ),
    Endpoint("POST", "/api/v2/automation-rules"): Case(
        expected=authenticated_only(201),
        url=lambda world: "/api/v2/automation-rules",
        body=lambda world, actor: {
            "name": f"Matrix rule for {actor}",
            "trigger_type": "no_activity",
            "trigger": {"days": 14},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Matrix follow-up"},
        },
        notes="Any signed-in user may write a rule; it can only do what they could.",
    ),
    Endpoint("PATCH", "/api/v2/automation-rules/{rule_id}"): Case(
        expected=creator_only(200),
        url=lambda world: f"/api/v2/automation-rules/{world.automation_rule_id}",
        body=lambda world, actor: {
            "name": f"Renamed by {actor}",
            "trigger_type": "no_activity",
            "trigger": {"days": 21},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Matrix follow-up"},
        },
        notes="Rewritten whole, and only by its creator.",
    ),
    Endpoint("POST", "/api/v2/automation-rules/{rule_id}/archive"): Case(
        expected=creator_only(200),
        url=lambda world: f"/api/v2/automation-rules/{world.automation_rule_id}/archive",
        body=lambda world, actor: None,
        notes="There is no DELETE: the run log points at the row (D-173).",
    ),
    Endpoint("POST", "/api/v2/automation-rules/{rule_id}/run"): Case(
        expected=creator_only(200),
        url=lambda world: f"/api/v2/automation-rules/{world.automation_rule_id}/run",
        body=lambda world, actor: None,
        notes=(
            "Previews by default, and only for the creator -- the preview "
            "names the deals the rule would touch, which are theirs."
        ),
    ),
    Endpoint("GET", "/api/v2/automation-rules/{rule_id}/runs"): Case(
        expected=creator_only(200),
        url=lambda world: f"/api/v2/automation-rules/{world.automation_rule_id}/runs",
        notes="A run row names a deal, so this is the creator's own read.",
    ),
    Endpoint("GET", "/api/v2/job-runs"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/job-runs",
        notes=(
            "The scheduler's log (milestone 6.5). Open to any signed-in "
            "caller: a job name, a status and a time say nothing about "
            "anybody's deals, and 'are the rules being checked at all' is a "
            "question everybody with a rule has (**D-183**)."
        ),
    ),
    Endpoint("POST", "/api/v2/saved-views"): Case(
        expected=authenticated_only(201),
        url=lambda world: "/api/v2/saved-views",
        body=lambda world, actor: {"name": "Matrix new view", "entity": "opportunities"},
        notes="Not opportunity-scoped: any signed-in user may save their own view.",
    ),
    Endpoint("GET", "/api/v2/saved-views"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/saved-views",
        notes="Scoped by the query: own views plus anyone's shared ones.",
    ),
    Endpoint("PATCH", "/api/v2/saved-views/{view_id}"): Case(
        expected={
            "anonymous": 401,
            "unrelated": 404,
            "viewer": 404,
            "editor": 404,
            "owner": 200,
        },
        url=lambda world: f"/api/v2/saved-views/{world.saved_view_id}",
        body=lambda world, actor: {"name": "Matrix view, renamed"},
        notes="The fixture's view belongs to the owner; everyone else 404s (creator-only write).",
    ),
    Endpoint("DELETE", "/api/v2/saved-views/{view_id}"): Case(
        expected={
            "anonymous": 401,
            "unrelated": 404,
            "viewer": 404,
            "editor": 404,
            "owner": 204,
        },
        url=lambda world: f"/api/v2/saved-views/{world.saved_view_id}",
        notes="Same creator-only rule as the PATCH above.",
    ),
    # Undo (milestone 2.4b). Each restore answers exactly what its delete twin
    # answers, because it is the same rule: the author or the opportunity owner.
    Endpoint("POST", "/api/v2/timeline/{entry_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/timeline/{world.deleted_entry_id}/restore",
        body=lambda world, actor: None,
        notes="Entry authored by the owner, so the editor is not its author (D-005).",
    ),
    Endpoint("POST", "/api/v2/notes/{note_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/notes/{world.deleted_note_id}/restore",
        body=lambda world, actor: None,
    ),
    Endpoint("POST", "/api/v2/comments/{comment_id}/restore"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/v2/comments/{world.deleted_comment_id}/restore",
        body=lambda world, actor: None,
    ),
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/restore"): Case(
        expected={
            "anonymous": 401,
            "unrelated": 404,
            "viewer": 404,
            "editor": 404,
            "owner": 204,
        },
        url=lambda world: f"/api/v2/opportunities/{world.deleted_opportunity_id}/restore",
        body=lambda world, actor: None,
        notes=(
            "404 rather than 403 for the shared editor and viewer, unlike DELETE: "
            "deleting the opportunity deleted their share rows with it, so they "
            "can no longer see that the record exists at all."
        ),
    ),
    # Bulk actions (milestone 2.4c). Ids can span opportunities the caller
    # owns and ones they don't, so a single status code cannot carry per-item
    # permission the way the single-item routes do — this answers 200 for
    # anyone signed in and reports ok/error per id in the body instead, the
    # same split `GET /api/v2/search` already uses below.
    # tests/test_bulk_actions.py holds the real per-item cases: owner
    # succeeds, editor/viewer get a "forbidden" item, an unrelated id gets
    # "not found".
    Endpoint("POST", "/api/v2/opportunities/bulk"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/opportunities/bulk",
        body=lambda world, actor: {
            "ids": [world.opportunity_id],
            "action": "set_stage",
            "stage": "Qualification",
        },
    ),
    # Cross-opportunity like search: the ids come from the caller, so the
    # permission filter is inside the query and an id the caller cannot read
    # is absent from the file rather than refused (tests/test_export.py holds
    # the leakage case). Everyone signed in therefore gets 200.
    Endpoint("GET", "/api/v2/opportunities/export/csv"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/opportunities/export/csv?ids={world.opportunity_id}",
    ),
    Endpoint("GET", "/api/v2/opportunities/export/json"): Case(
        expected=authenticated_only(200),
        url=lambda world: f"/api/v2/opportunities/export/json?ids={world.opportunity_id}",
    ),
    Endpoint("GET", "/api/v2/search"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/v2/search?q=discovery",
        notes=(
            "Cross-opportunity, so it answers 200 for anyone signed in and "
            "carries the permission filter inside the query instead "
            "(tests/test_search.py has the leakage cases)."
        ),
    ),
    # --- Identity-independent surfaces ------------------------------------
    Endpoint("GET", "/api/health"): public(
        lambda world: "/api/health",
        "Liveness probe; must answer before anyone can authenticate.",
    ),
    Endpoint("GET", "/api/{path:path}"): public(
        lambda world: "/api/no-such-endpoint",
        "Catch-all so an unknown API path 404s as JSON instead of serving the SPA.",
    ),
    Endpoint("POST", "/api/{path:path}"): public(
        lambda world: "/api/no-such-endpoint", "As above."
    ),
    Endpoint("PUT", "/api/{path:path}"): public(lambda world: "/api/no-such-endpoint", "As above."),
    Endpoint("PATCH", "/api/{path:path}"): public(
        lambda world: "/api/no-such-endpoint", "As above."
    ),
    Endpoint("DELETE", "/api/{path:path}"): public(
        lambda world: "/api/no-such-endpoint", "As above."
    ),
    Endpoint("GET", "/{path:path}"): public(
        lambda world: "/some/client-side/route",
        "Static SPA delivery; the app's own auth screen is what gates the data.",
    ),
}


def _signup(client: TestClient, email: str, name: str) -> int:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["user"]["id"])


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    """A fresh world per test, so the one call that is allowed to mutate state
    cannot reach the next endpoint's expectations.
    """
    from app.database import initialize_database

    settings.database_url = f"sqlite:///{tmp_path / 'matrix.db'}"
    initialize_database()

    monkeypatch.setattr(settings, "openai_api_key", "matrix-test-key")
    monkeypatch.setattr(
        "app.routes_ai.ask_openai",
        lambda **kwargs: "Answer assembled from the timeline.",
    )
    # Milestone 6.4's two new calls, stubbed the same way: the matrix is about
    # who may reach an endpoint, not about what the model says.
    monkeypatch.setattr(
        "app.routes_ai.stream_openai",
        lambda **kwargs: iter(["Answer ", "in pieces."]),
    )
    monkeypatch.setattr(
        "app.routes_ai.ask_openai_for_filter",
        lambda **kwargs: '{"stage": "Negotiation"}',
    )

    clients: dict[Actor, TestClient] = {}
    user_ids: dict[Actor, int] = {}
    emails: dict[Actor, str] = {}

    for actor in ACTORS:
        client = CsrfClient(app)
        client.__enter__()
        clients[actor] = client

    for actor in ("owner", "editor", "viewer", "unrelated"):
        emails[actor] = f"{actor}@example.com"
        user_ids[actor] = _signup(clients[actor], emails[actor], actor.title())

    owner = clients["owner"]
    opportunity_id = owner.post(
        "/api/v2/opportunities",
        json={"name": "Matrix", "account_name": "Acme", "stage": "Prospecting"},
    ).json()["id"]

    for actor, role in (("editor", "editor"), ("viewer", "viewer")):
        assert (
            owner.post(
                f"/api/v2/opportunities/{opportunity_id}/shares",
                json={"email": emails[actor], "role": role},
            ).status_code
            == 201
        )

    entry_id = owner.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "",
            "event_timestamp": "2026-09-04T10:00",
        },
    ).json()["id"]
    note = owner.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": "Owner note"}).json()
    note_id = note["id"]
    comment_id = owner.post(
        f"/api/v2/notes/{note_id}/comments", json={"body": "Owner comment"}
    ).json()["id"]

    # The editor writing to a shared opportunity is what notifies the owner, so
    # this both seeds the notification row and keeps it owned by the owner.
    clients["editor"].post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "email",
            "title": "Editor follow-up",
            "body": "",
            "event_timestamp": "2026-09-05T10:00",
        },
    )
    notifications = owner.get("/api/v2/notifications").json()["items"]
    assert notifications, "expected the owner to be notified of the editor's entry"

    saved_view_id = owner.post(
        "/api/v2/saved-views",
        json={"name": "Matrix view", "entity": "opportunities"},
    ).json()["id"]

    # One of each kind, authored by the owner and then deleted, so the restore
    # endpoints have something to act on. Separate rows from the live ones
    # above: an endpoint's expectations must not depend on another endpoint's
    # test having run.
    deleted_entry_id = owner.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Deleted call",
            "body": "",
            "event_timestamp": "2026-09-06T10:00",
        },
    ).json()["id"]
    deleted_note_id = owner.post(
        f"/api/v2/timeline/{entry_id}/notes", json={"body": "Deleted note"}
    ).json()["id"]
    deleted_comment_id = owner.post(
        f"/api/v2/notes/{note_id}/comments", json={"body": "Deleted comment"}
    ).json()["id"]
    for path in (
        f"/api/v2/timeline/{deleted_entry_id}",
        f"/api/v2/notes/{deleted_note_id}",
        f"/api/v2/comments/{deleted_comment_id}",
    ):
        assert owner.delete(path).status_code == 204, path

    deleted_opportunity_id = owner.post(
        "/api/v2/opportunities",
        json={"name": "Matrix deleted", "account_name": "Acme", "stage": "Prospecting"},
    ).json()["id"]
    for actor, role in (("editor", "editor"), ("viewer", "viewer")):
        assert (
            owner.post(
                f"/api/v2/opportunities/{deleted_opportunity_id}/shares",
                json={"email": emails[actor], "role": role},
            ).status_code
            == 201
        )
    assert owner.delete(f"/api/v2/opportunities/{deleted_opportunity_id}").status_code == 204

    # Tasks (milestone 4.1). The live one is assigned to the **editor**, which
    # is what makes the completion cases meaningful: D-142 lets an assignee
    # close a task they did not write, so an editor completing this one must
    # succeed while editing it must not.
    task_id = owner.post(
        f"/api/v2/opportunities/{opportunity_id}/tasks",
        json={"title": "Matrix task", "assignee_emails": [emails["editor"]]},
    ).json()["id"]
    deleted_task_id = owner.post(
        f"/api/v2/opportunities/{opportunity_id}/tasks",
        json={"title": "Matrix deleted task"},
    ).json()["id"]
    assert owner.delete(f"/api/v2/tasks/{deleted_task_id}").status_code == 204

    # Attachments (milestone 4.3), on the live entry above. `text/plain` has no
    # magic bytes, so the fixture's file is validated by decoding -- the same
    # path a real text attachment takes.
    def attach(filename: str) -> int:
        response = owner.post(
            f"/api/v2/timeline/{entry_id}/attachments",
            files={"file": (filename, b"matrix attachment", "text/plain")},
        )
        assert response.status_code == 201, response.json()
        return int(response.json()["id"])

    def task_comment(body: str) -> int:
        response = owner.post(f"/api/v2/tasks/{task_id}/comments", json={"body": body})
        assert response.status_code == 201, response.json()
        return int(response.json()["id"])

    def custom_field(key: str) -> int:
        response = owner.post(
            "/api/v2/custom-fields",
            json={
                "entity_type": "opportunity",
                "key": key,
                "label": key.replace("_", " ").title(),
                "type": "text",
            },
        )
        assert response.status_code == 201, response.json()
        return int(response.json()["id"])

    def automation_rule() -> int:
        response = owner.post(
            "/api/v2/automation-rules",
            json={
                "name": "Matrix fixture rule",
                "trigger_type": "no_activity",
                "trigger": {"days": 14},
                "conditions": [],
                "action_type": "create_task",
                "action": {"title": "Matrix fixture follow-up"},
            },
        )
        assert response.status_code == 201, response.json()
        return int(response.json()["id"])

    automation_rule_id = automation_rule()

    custom_field_id = custom_field("matrix_field")
    archived_field_id = custom_field("matrix_archived_field")
    assert owner.post(f"/api/v2/custom-fields/{archived_field_id}/archive").status_code == 200

    task_comment_id = task_comment("Matrix task comment")
    deleted_task_comment_id = task_comment("Matrix deleted task comment")
    assert owner.delete(f"/api/v2/task-comments/{deleted_task_comment_id}").status_code == 204

    attachment_id = attach("matrix.txt")
    # A second file with *different* bytes, so deleting it cannot remove the
    # live one's blob: identical content is one file on disk (ADR 0008).
    deleted_attachment_response = owner.post(
        f"/api/v2/timeline/{entry_id}/attachments",
        files={"file": ("matrix-deleted.txt", b"matrix deleted attachment", "text/plain")},
    )
    assert deleted_attachment_response.status_code == 201
    deleted_attachment_id = int(deleted_attachment_response.json()["id"])
    assert owner.delete(f"/api/v2/attachments/{deleted_attachment_id}").status_code == 204

    yield World(
        clients=clients,
        user_ids=user_ids,
        emails=emails,
        opportunity_id=opportunity_id,
        entry_id=entry_id,
        note_id=note_id,
        note_updated_at=note["updated_at"],
        comment_id=comment_id,
        notification_id=notifications[0]["id"],
        saved_view_id=saved_view_id,
        deleted_entry_id=deleted_entry_id,
        deleted_note_id=deleted_note_id,
        deleted_comment_id=deleted_comment_id,
        deleted_opportunity_id=deleted_opportunity_id,
        task_id=task_id,
        deleted_task_id=deleted_task_id,
        attachment_id=attachment_id,
        deleted_attachment_id=deleted_attachment_id,
        task_comment_id=task_comment_id,
        deleted_task_comment_id=deleted_task_comment_id,
        custom_field_id=custom_field_id,
        archived_field_id=archived_field_id,
        automation_rule_id=automation_rule_id,
    )

    for client in clients.values():
        client.__exit__(None, None, None)


def test_every_endpoint_has_a_matrix_entry() -> None:
    """A new route without an authorization expectation fails here.

    This is the guard brief §6.4 asks for: "unregistered routes fail the test".
    """
    served = set(iter_endpoints(app))
    registered = set(MATRIX)

    missing = sorted(str(endpoint) for endpoint in served - registered)
    stale = sorted(str(endpoint) for endpoint in registered - served)

    assert not missing, (
        "These endpoints have no entry in MATRIX. Add one — including the "
        f"status every actor should get — before shipping them: {missing}"
    )
    assert not stale, f"MATRIX describes endpoints the app no longer serves: {stale}"


@pytest.mark.parametrize(
    "endpoint",
    sorted(MATRIX, key=str),
    ids=str,
)
def test_authorization_matrix(endpoint: Endpoint, world: World) -> None:
    case = MATRIX[endpoint]
    url = case.url(world)
    observed: dict[Actor, int] = {}

    for actor in ACTORS:
        client = world.clients[actor]
        kwargs: dict[str, Any] = {}
        if case.body is not None:
            body = case.body(world, actor)
            if body is not None:
                kwargs["json"] = body
        if case.files is not None:
            kwargs["files"] = case.files(world, actor)

        # The unauthorized cases never reach the renderer — require_opportunity_access
        # runs inside routes_export.get_export_data, so a missing native library
        # cannot change a 401/404 into something else. Only the three actors who
        # are expected to get the PDF back can hit the missing-library error, and
        # only on a host without WeasyPrint's native libraries (a laptop, not the
        # container this suite otherwise runs in — see CLAUDE.md's WeasyPrint
        # section). Skipping the whole endpoint here would drop its authorization
        # coverage on every such run while the suite still reported green, so only
        # those three cases are guarded, and only by accepting the same status the
        # container would have returned.
        if (
            endpoint == PDF_EXPORT_ENDPOINT
            and not WEASYPRINT_AVAILABLE
            and case.expected is not None
            and case.expected.get(actor) == 200
        ):
            try:
                observed[actor] = client.request(endpoint.method, url, **kwargs).status_code
            except (ImportError, OSError):
                observed[actor] = 200
            continue

        observed[actor] = client.request(endpoint.method, url, **kwargs).status_code

    if case.same_for_everyone:
        assert len(set(observed.values())) == 1, (
            f"{endpoint} is an identity-independent surface but answered "
            f"differently per caller: {observed}"
        )
        return

    assert case.expected is not None
    assert observed == case.expected, f"{endpoint} authorization changed: {observed}"
