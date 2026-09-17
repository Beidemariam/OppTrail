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

PDF_EXPORT_ENDPOINT = Endpoint("GET", "/api/opportunities/{opportunity_id}/export/pdf")

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
    Endpoint("POST", "/api/auth/signup"): Case(
        expected=all_actors(201),
        url=lambda world: "/api/auth/signup",
        body=lambda world, actor: {
            "email": _unique_email(actor),
            "password": PASSWORD,
            "name": "Matrix Signup",
        },
        notes="Open by design: signing up is how a user comes to exist.",
    ),
    Endpoint("POST", "/api/auth/login"): Case(
        expected=all_actors(200),
        url=lambda world: "/api/auth/login",
        body=lambda world, actor: {"email": world.emails["owner"], "password": PASSWORD},
        notes="Open by design; credentials, not the session, are the control.",
    ),
    Endpoint("POST", "/api/auth/logout"): Case(
        expected=all_actors(200),
        url=lambda world: "/api/auth/logout",
        body=lambda world, actor: None,
        notes=(
            "Deliberately not behind get_current_user: clearing a cookie that is "
            "already absent or expired is a no-op, and answering 401 would leave a "
            "client unable to discard a stale session."
        ),
    ),
    Endpoint("POST", "/api/auth/password"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/auth/password",
        body=lambda world, actor: {
            "current_password": PASSWORD,
            "new_password": "replacement-password-123",
        },
    ),
    Endpoint("GET", "/api/auth/me"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/auth/me",
    ),
    # --- Opportunities ---------------------------------------------------
    Endpoint("GET", "/api/opportunities"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/opportunities",
        notes="Scoped by the query itself: the list only contains what you can see.",
    ),
    Endpoint("POST", "/api/opportunities"): Case(
        expected=authenticated_only(201),
        url=lambda world: "/api/opportunities",
        body=lambda world, actor: {
            "name": "Matrix opportunity",
            "account_name": "Acme",
            "stage": "Prospecting",
        },
    ),
    Endpoint("GET", "/api/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}",
    ),
    Endpoint("PATCH", "/api/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}",
        body=lambda world, actor: {"stage": "Qualification"},
        notes="Opportunity fields are the owner's: require_opportunity_owner.",
    ),
    Endpoint("DELETE", "/api/opportunities/{opportunity_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}",
    ),
    # --- Sharing and audit log -------------------------------------------
    Endpoint("GET", "/api/opportunities/{opportunity_id}/shares"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/shares",
    ),
    Endpoint("POST", "/api/opportunities/{opportunity_id}/shares"): Case(
        expected=scoped(viewer=403, editor=403, owner=201),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/shares",
        body=lambda world, actor: {"email": world.emails["unrelated"], "role": "viewer"},
    ),
    Endpoint("PATCH", "/api/opportunities/{opportunity_id}/shares/{user_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: (
            f"/api/opportunities/{world.opportunity_id}/shares/{world.user_ids['viewer']}"
        ),
        body=lambda world, actor: {"role": "editor"},
    ),
    Endpoint("DELETE", "/api/opportunities/{opportunity_id}/shares/{user_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: (
            f"/api/opportunities/{world.opportunity_id}/shares/{world.user_ids['viewer']}"
        ),
    ),
    Endpoint("GET", "/api/opportunities/{opportunity_id}/audit-log"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/audit-log",
        notes="Owner-only forensics (CLAUDE.md, Auditability).",
    ),
    # --- Timeline ---------------------------------------------------------
    Endpoint("GET", "/api/opportunities/{opportunity_id}/timeline"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/timeline",
    ),
    Endpoint("POST", "/api/opportunities/{opportunity_id}/timeline"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/timeline",
        body=lambda world, actor: {
            "type": "call",
            "title": "Matrix entry",
            "body": "",
            "event_timestamp": "2026-09-04T10:00",
        },
    ),
    Endpoint("PATCH", "/api/timeline/{entry_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/timeline/{world.entry_id}",
        body=lambda world, actor: {"title": "Matrix entry, edited"},
        notes="Entry authored by the owner, so the editor is not its author (D-005).",
    ),
    Endpoint("DELETE", "/api/timeline/{entry_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/timeline/{world.entry_id}",
    ),
    Endpoint("POST", "/api/timeline/{entry_id}/notes"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/timeline/{world.entry_id}/notes",
        body=lambda world, actor: {"body": "Matrix note"},
        notes="Editors add freely; only changing an existing item is restricted.",
    ),
    Endpoint("GET", "/api/notes/{note_id}/versions"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/notes/{world.note_id}/versions",
    ),
    Endpoint("PATCH", "/api/notes/{note_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=200),
        url=lambda world: f"/api/notes/{world.note_id}",
        body=lambda world, actor: {"body": "Matrix note, edited"},
    ),
    Endpoint("DELETE", "/api/notes/{note_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/notes/{world.note_id}",
    ),
    Endpoint("POST", "/api/notes/{note_id}/comments"): Case(
        expected=scoped(viewer=403, editor=201, owner=201),
        url=lambda world: f"/api/notes/{world.note_id}/comments",
        body=lambda world, actor: {"body": "Matrix comment"},
    ),
    Endpoint("DELETE", "/api/comments/{comment_id}"): Case(
        expected=scoped(viewer=403, editor=403, owner=204),
        url=lambda world: f"/api/comments/{world.comment_id}",
    ),
    # --- AI agent ---------------------------------------------------------
    Endpoint("POST", "/api/opportunities/{opportunity_id}/ai/ask"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/ai/ask",
        body=lambda world, actor: {"question": "What happened?"},
        notes="Read-only, so viewers may ask: require_opportunity_access.",
    ),
    # --- Export -----------------------------------------------------------
    Endpoint("GET", "/api/opportunities/{opportunity_id}/export/json"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/export/json",
    ),
    Endpoint("GET", "/api/opportunities/{opportunity_id}/export/csv"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/export/csv",
    ),
    Endpoint("GET", "/api/opportunities/{opportunity_id}/export/pdf"): Case(
        expected=scoped(viewer=200, editor=200, owner=200),
        url=lambda world: f"/api/opportunities/{world.opportunity_id}/export/pdf",
    ),
    # --- Notifications ----------------------------------------------------
    Endpoint("GET", "/api/notifications"): Case(
        expected=authenticated_only(200),
        url=lambda world: "/api/notifications",
        notes="Scoped by the query: a user only ever reads their own rows.",
    ),
    Endpoint("PATCH", "/api/notifications/{notification_id}/read"): Case(
        expected={
            "anonymous": 401,
            "unrelated": 404,
            "viewer": 404,
            "editor": 404,
            "owner": 200,
        },
        url=lambda world: f"/api/notifications/{world.notification_id}/read",
        body=lambda world, actor: None,
        notes="The fixture's notification belongs to the owner; everyone else 404s.",
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
        "/api/auth/signup",
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
        "/api/opportunities",
        json={"name": "Matrix", "account_name": "Acme", "stage": "Prospecting"},
    ).json()["id"]

    for actor, role in (("editor", "editor"), ("viewer", "viewer")):
        assert (
            owner.post(
                f"/api/opportunities/{opportunity_id}/shares",
                json={"email": emails[actor], "role": role},
            ).status_code
            == 201
        )

    entry_id = owner.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "",
            "event_timestamp": "2026-09-04T10:00",
        },
    ).json()["id"]
    note_id = owner.post(f"/api/timeline/{entry_id}/notes", json={"body": "Owner note"}).json()[
        "id"
    ]
    comment_id = owner.post(
        f"/api/notes/{note_id}/comments", json={"body": "Owner comment"}
    ).json()["id"]

    # The editor writing to a shared opportunity is what notifies the owner, so
    # this both seeds the notification row and keeps it owned by the owner.
    clients["editor"].post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "email",
            "title": "Editor follow-up",
            "body": "",
            "event_timestamp": "2026-09-05T10:00",
        },
    )
    notifications = owner.get("/api/notifications").json()["notifications"]
    assert notifications, "expected the owner to be notified of the editor's entry"

    yield World(
        clients=clients,
        user_ids=user_ids,
        emails=emails,
        opportunity_id=opportunity_id,
        entry_id=entry_id,
        note_id=note_id,
        comment_id=comment_id,
        notification_id=notifications[0]["id"],
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
