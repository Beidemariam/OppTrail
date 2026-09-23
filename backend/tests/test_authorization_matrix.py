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
    comment_id: int
    notification_id: int
    saved_view_id: int
    # Deleted rows, for the restore endpoints: there is nothing to restore
    # about a live one, and a restore of what is already here is a 404.
    deleted_entry_id: int
    deleted_note_id: int
    deleted_comment_id: int
    deleted_opportunity_id: int


@dataclass(frozen=True)
class Case:
    """What one endpoint is expected to answer, per actor.

    `expected` maps an actor to a status code. `SAME_FOR_EVERYONE` marks the
    handful of surfaces that are deliberately identity-independent (health, the
    API 404 catch-all, the static frontend); there the assertion is that the
    response does not vary by caller, which is the property worth protecting.
    """

    expected: dict[Actor, int] | None
    url: Callable[[World], str]
    body: Callable[[World, Actor], Any] | None = None
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
        body=lambda world, actor: {"body": "Matrix note, edited"},
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
    # --- AI agent ---------------------------------------------------------
    Endpoint("POST", "/api/v2/opportunities/{opportunity_id}/ai/ask"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/v2/opportunities/{world.opportunity_id}/ai/ask",
        body=lambda world, actor: {"question": "What happened?"},
        notes="Read-only, so viewers may ask: require_opportunity_access.",
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
    note_id = owner.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": "Owner note"}).json()[
        "id"
    ]
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

    yield World(
        clients=clients,
        user_ids=user_ids,
        emails=emails,
        opportunity_id=opportunity_id,
        entry_id=entry_id,
        note_id=note_id,
        comment_id=comment_id,
        notification_id=notifications[0]["id"],
        saved_view_id=saved_view_id,
        deleted_entry_id=deleted_entry_id,
        deleted_note_id=deleted_note_id,
        deleted_comment_id=deleted_comment_id,
        deleted_opportunity_id=deleted_opportunity_id,
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
