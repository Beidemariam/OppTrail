"""The `/api/v2` surface: the pagination envelope and the unified error shape.

Milestone 1.3 (`docs/ROADMAP.md` Phase 1, review blocker B3). Two properties
carry the whole milestone and are asserted here rather than assumed:

- a client can walk a collection to its end through cursors and see every row
  exactly once, whatever happens to the table between requests;
- every v2 failure — validation, permission, unknown path, CSRF, unhandled
  exception — arrives in one envelope, while v1 keeps the `{"detail": ...}`
  shape the shipped frontend reads (Phase 1 acceptance: "v1 endpoints still
  serve the existing frontend").
"""

import contextlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import routes_opportunities
from app.pagination import encode_cursor
from app.settings import settings


def signup(client: TestClient, email: str = "owner@example.com", name: str = "Owner") -> dict:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200


def create_opportunity(client: TestClient, name: str = "Expansion") -> dict:
    response = client.post(
        "/api/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_entry(
    client: TestClient,
    opportunity_id: int,
    title: str,
    event_timestamp: str = "2026-09-01T10:00:00",
) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": title,
            "body": "Budget discussed",
            "event_timestamp": event_timestamp,
        },
    )
    assert response.status_code == 201
    return response.json()


def walk(client: TestClient, url: str, limit: int) -> tuple[list[dict], int]:
    """Follow `next_cursor` to the end, returning every item and the page count."""
    items: list[dict] = []
    pages = 0
    cursor: str | None = None
    while True:
        query = f"{url}?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        response = client.get(query)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"items", "next_cursor"}
        assert len(body["items"]) <= limit
        items.extend(body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return items, pages
        assert pages < 20, "cursor walk did not terminate"


@contextlib.contextmanager
def server_exceptions_not_raised(client: TestClient) -> Iterator[None]:
    """See `tests/test_error_handling.py` — same reason, same mechanism."""
    transport = client._transport  # type: ignore[attr-defined]
    original = transport.raise_server_exceptions
    transport.raise_server_exceptions = False
    try:
        yield
    finally:
        transport.raise_server_exceptions = original


# --- The envelope ------------------------------------------------------------


def test_opportunity_pages_return_every_row_exactly_once(client: TestClient) -> None:
    signup(client)
    created = [create_opportunity(client, f"Opportunity {index}")["id"] for index in range(5)]

    items, pages = walk(client, "/api/v2/opportunities", limit=2)

    assert pages == 3
    assert [item["id"] for item in items] == sorted(created, reverse=True)


def test_a_full_page_is_not_followed_by_an_empty_one(client: TestClient) -> None:
    """The `limit + 1` probe is what makes this true: a collection whose size
    is an exact multiple of the limit must still end with `next_cursor: null`,
    not with a cursor that resolves to nothing.
    """
    signup(client)
    for index in range(4):
        create_opportunity(client, f"Opportunity {index}")

    items, pages = walk(client, "/api/v2/opportunities", limit=2)

    assert pages == 2
    assert len(items) == 4


def test_the_last_page_of_a_single_page_collection_has_no_cursor(client: TestClient) -> None:
    signup(client)
    create_opportunity(client)

    body = client.get("/api/v2/opportunities?limit=50").json()

    assert body["next_cursor"] is None
    assert len(body["items"]) == 1


def test_a_row_added_between_pages_does_not_duplicate_one(client: TestClient) -> None:
    """The keyset argument for cursors over OFFSET: page two continues after a
    known row rather than after a count, so a row inserted at the head of the
    order cannot push a row the client already saw onto the next page.
    """
    signup(client)
    for index in range(4):
        create_opportunity(client, f"Opportunity {index}")

    first = client.get("/api/v2/opportunities?limit=2").json()
    create_opportunity(client, "Inserted between pages")
    second = client.get(f"/api/v2/opportunities?limit=2&cursor={first['next_cursor']}").json()

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert not set(first_ids) & set(second_ids)


def test_a_soft_deleted_row_leaves_the_page(client: TestClient) -> None:
    signup(client)
    kept = create_opportunity(client, "Kept")["id"]
    removed = create_opportunity(client, "Removed")["id"]

    assert client.delete(f"/api/opportunities/{removed}").status_code == 204

    items, _ = walk(client, "/api/v2/opportunities", limit=50)
    assert [item["id"] for item in items] == [kept]


def test_limit_outside_its_range_is_a_validation_error(client: TestClient) -> None:
    signup(client)

    for limit in (0, 201):
        response = client.get(f"/api/v2/opportunities?limit={limit}")

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "limit" in error["fields"]


def test_an_unreadable_cursor_is_rejected(client: TestClient) -> None:
    signup(client)

    for cursor in ("not-base64!", encode_cursor(["only-one-value"])):
        response = client.get(f"/api/v2/opportunities?cursor={cursor}")

        assert response.status_code == 400
        assert response.json() == {
            "error": {"code": "bad_request", "message": "Invalid pagination cursor"}
        }


def test_stages_are_served_as_their_own_collection(client: TestClient) -> None:
    """v1 carried the fixed stage list on the opportunity list response; the v2
    envelope has no room for it, so it moves here rather than disappearing.
    """
    signup(client)

    body = client.get("/api/v2/stages").json()

    assert body["next_cursor"] is None
    assert body["items"] == client.get("/api/opportunities").json()["stages"]


# --- Every collection endpoint ----------------------------------------------


def test_timeline_pages_carry_whole_entries(client: TestClient) -> None:
    owner = signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Discovery call", "2026-09-02T10:00:00")
    note = client.post(f"/api/timeline/{entry['id']}/notes", json={"body": "Note body"})
    assert note.status_code == 201
    comment = client.post(f"/api/notes/{note.json()['id']}/comments", json={"body": "Comment body"})
    assert comment.status_code == 201

    items, pages = walk(client, f"/api/v2/opportunities/{opportunity['id']}/timeline", limit=1)

    # Two entries: the one created above and the auto-generated "Opportunity
    # created", which is stamped with the current time and so sorts last.
    assert pages == 2
    assert [item["title"] for item in items] == ["Discovery call", "Opportunity created"]
    assert items[0]["notes"][0]["body"] == "Note body"
    assert items[0]["notes"][0]["comments"][0]["body"] == "Comment body"
    assert items[0]["notes"][0]["author_name"] == owner["name"]


def test_timeline_pages_apply_the_v1_filters(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Pricing call", "2026-09-02T10:00:00")
    create_entry(client, opportunity["id"], "Renewal call", "2026-09-03T10:00:00")

    filtered = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/timeline?q=renewal&type=call"
    ).json()

    assert [item["title"] for item in filtered["items"]] == ["Renewal call"]

    windowed = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/timeline"
        "?from=2026-09-03T00:00:00Z&to=2026-09-04T00:00:00Z"
    ).json()

    assert [item["title"] for item in windowed["items"]] == ["Renewal call"]


def walk_with_order(client: TestClient, url: str, limit: int, order: str) -> list[dict]:
    """Like `walk`, but for a query that already needs its own `order` param —
    `walk` always appends `?limit=`, so it cannot be reused once the URL
    itself needs a `?`.
    """
    items: list[dict] = []
    cursor: str | None = None
    pages = 0
    while True:
        query = f"{url}?order={order}&limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        response = client.get(query)
        assert response.status_code == 200, response.text
        body = response.json()
        items.extend(body["items"])
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            return items
        assert pages < 20, "cursor walk did not terminate"


def test_timeline_pages_reverse_with_order_desc(client: TestClient) -> None:
    """D-051: the timeline's reading order is a URL parameter like any other,
    and reversing it has to reverse the cursor's comparison direction, not
    just the `ORDER BY` — walking `order=desc` one row at a time is what would
    repeat or skip a row at the boundary if only the `ORDER BY` flipped.
    """
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Pricing call", "2026-09-02T10:00:00")
    create_entry(client, opportunity["id"], "Renewal call", "2026-09-03T10:00:00")

    url = f"/api/v2/opportunities/{opportunity['id']}/timeline"
    ascending = walk_with_order(client, url, limit=1, order="asc")
    descending = walk_with_order(client, url, limit=1, order="desc")

    assert [item["title"] for item in descending] == list(
        reversed([item["title"] for item in ascending])
    )
    assert len(ascending) == 3  # the two calls above, plus "Opportunity created"


def test_share_pages_are_ordered_by_name(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    for name, email in (("Zoe", "zoe@example.com"), ("Adam", "adam@example.com")):
        assert (
            client.post(
                "/api/auth/signup",
                json={"email": email, "password": "password123", "name": name},
            ).status_code
            == 201
        )
        login(client, "owner@example.com")
        assert (
            client.post(
                f"/api/opportunities/{opportunity['id']}/shares",
                json={"email": email, "role": "viewer"},
            ).status_code
            == 201
        )

    items, pages = walk(client, f"/api/v2/opportunities/{opportunity['id']}/shares", limit=1)

    assert pages == 2
    assert [item["name"] for item in items] == ["Adam", "Zoe"]


def test_audit_log_pages_read_forwards(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Discovery call")
    assert client.delete(f"/api/timeline/{entry['id']}").status_code == 204
    note_owner = client.post(
        "/api/auth/signup",
        json={"email": "viewer@example.com", "password": "password123", "name": "Viewer"},
    )
    assert note_owner.status_code == 201
    login(client, "owner@example.com")
    assert (
        client.post(
            f"/api/opportunities/{opportunity['id']}/shares",
            json={"email": "viewer@example.com", "role": "viewer"},
        ).status_code
        == 201
    )

    items, _ = walk(client, f"/api/v2/opportunities/{opportunity['id']}/audit-log", limit=1)
    v1_items = client.get(f"/api/opportunities/{opportunity['id']}/audit-log").json()

    assert [item["action"] for item in items] == ["timeline_entry_deleted", "share_added"]
    assert items == v1_items


def test_note_version_pages_read_forwards(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Discovery call")
    note = client.post(f"/api/timeline/{entry['id']}/notes", json={"body": "First"})
    note_id = note.json()["id"]
    for body in ("Second", "Third"):
        assert client.patch(f"/api/notes/{note_id}", json={"body": body}).status_code == 200

    items, pages = walk(client, f"/api/v2/notes/{note_id}/versions", limit=1)

    assert pages == 3
    assert [item["version_number"] for item in items] == [1, 2, 3]
    assert [item["body"] for item in items] == ["First", "Second", "Third"]


def test_notification_pages_carry_the_same_rows_as_v1_in_the_v2_shape(client: TestClient) -> None:
    """Milestone 1.7: unlike every other v2 collection, notifications is a
    deliberate exception to "the boundary carries shape, not behaviour" — v2
    answers full history in the `read_at`/`grouped_key` shape, v1 keeps
    answering unread-only in the old `read` shape (`docs/ROADMAP.md`'s
    breaking-changes table). Both still describe the same underlying row.
    """
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.post(
            "/api/auth/signup",
            json={"email": "viewer@example.com", "password": "password123", "name": "Viewer"},
        ).status_code
        == 201
    )
    login(client, "owner@example.com")
    assert (
        client.post(
            f"/api/opportunities/{opportunity['id']}/shares",
            json={"email": "viewer@example.com", "role": "viewer"},
        ).status_code
        == 201
    )

    login(client, "viewer@example.com")
    items, _ = walk(client, "/api/v2/notifications", limit=1)
    v1_items = client.get("/api/notifications").json()["notifications"]

    assert [item["type"] for item in items] == ["share_added"]
    assert [item["id"] for item in items] == [item["id"] for item in v1_items]
    assert [item["payload"] for item in items] == [item["payload"] for item in v1_items]
    assert items[0]["read_at"] is None
    assert items[0]["grouped_key"] is None


def test_v2_notification_history_survives_being_read_and_can_be_filtered_by_type(
    client: TestClient,
) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    viewer_signup = client.post(
        "/api/auth/signup",
        json={"email": "viewer@example.com", "password": "password123", "name": "Viewer"},
    )
    assert viewer_signup.status_code == 201
    viewer_id = viewer_signup.json()["user"]["id"]

    login(client, "owner@example.com")
    client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    client.patch(
        f"/api/opportunities/{opportunity['id']}/shares/{viewer_id}",
        json={"role": "editor"},
    )

    login(client, "viewer@example.com")
    before = walk(client, "/api/v2/notifications", limit=1)[0]
    assert {item["type"] for item in before} == {"share_added", "share_role_changed"}

    # Marking one read through the v1 endpoint (the only mark-read route)
    # must not remove it from the v2 history -- that dead end is exactly
    # what this milestone fixes.
    unread_id = next(item["id"] for item in before if item["type"] == "share_added")
    marked = client.patch(f"/api/notifications/{unread_id}/read")
    assert marked.status_code == 200
    assert marked.json()["read"] is True

    after = walk(client, "/api/v2/notifications", limit=1)[0]
    assert {item["id"] for item in after} == {item["id"] for item in before}
    read_item = next(item for item in after if item["id"] == unread_id)
    assert read_item["read_at"] is not None

    filtered_response = client.get("/api/v2/notifications?type=share_role_changed&limit=50")
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()["items"]
    assert {item["type"] for item in filtered} == {"share_role_changed"}


def test_v2_mark_all_notifications_read_is_scoped_to_the_caller(client: TestClient) -> None:
    owner = signup(client)
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    client.patch(
        f"/api/opportunities/{opportunity['id']}/shares/{viewer['id']}",
        json={"role": "editor"},
    )
    client.post("/api/auth/logout")

    login(client, "viewer@example.com")
    response = client.post("/api/v2/notifications/mark-all-read")
    assert response.status_code == 200
    assert response.json() == {"marked": 2}

    items = walk(client, "/api/v2/notifications", limit=50)[0]
    assert all(item["read_at"] is not None for item in items)

    # A second call marks nothing new -- everything is already read.
    assert client.post("/api/v2/notifications/mark-all-read").json() == {"marked": 0}

    client.post("/api/auth/logout")
    login(client, "owner@example.com")
    assert walk(client, "/api/v2/notifications", limit=50)[0] == []
    assert owner["id"] == opportunity["owner_id"]


# --- The error envelope ------------------------------------------------------


def test_a_permission_failure_uses_the_envelope(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.post(
            "/api/auth/signup",
            json={"email": "viewer@example.com", "password": "password123", "name": "Viewer"},
        ).status_code
        == 201
    )
    login(client, "owner@example.com")
    assert (
        client.post(
            f"/api/opportunities/{opportunity['id']}/shares",
            json={"email": "viewer@example.com", "role": "viewer"},
        ).status_code
        == 201
    )

    login(client, "viewer@example.com")
    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares")

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "forbidden", "message": "Only the owner can manage this opportunity"}
    }


def test_an_anonymous_caller_gets_the_envelope(client: TestClient) -> None:
    response = client.get("/api/v2/opportunities")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_an_unknown_v2_path_gets_the_envelope(client: TestClient) -> None:
    response = client.get("/api/v2/no-such-collection")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "API endpoint not found"}}


def test_a_csrf_rejection_on_a_v2_path_gets_the_envelope(client: TestClient) -> None:
    """The CSRF middleware answers before routing, so it is the one v2 error no
    exception handler can shape (`app/security.py`).
    """
    plain = TestClient(client.app)
    response = plain.post("/api/v2/opportunities", json={})

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "forbidden", "message": "CSRF token missing or invalid"}
    }


def test_an_unhandled_exception_on_a_v2_path_gets_the_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)
    create_opportunity(client)

    def explode(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes_opportunities, "is_opportunity_stalled", explode)

    with server_exceptions_not_raised(client):
        response = client.get("/api/v2/opportunities")

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "boom"}}

    monkeypatch.setattr(settings, "environment", "production")
    with server_exceptions_not_raised(client):
        hidden = client.get("/api/v2/opportunities")

    assert hidden.json()["error"]["message"] == "Internal server error"


# --- v1 is untouched ---------------------------------------------------------


def test_v1_keeps_its_own_shapes(client: TestClient) -> None:
    """Phase 1 acceptance: v1 endpoints still serve the existing frontend."""
    signup(client)
    create_opportunity(client)

    listing = client.get("/api/opportunities").json()
    assert set(listing) == {"stages", "opportunities"}

    not_found = client.get("/api/opportunities/999")
    assert not_found.status_code == 404
    assert not_found.json() == {"detail": "Opportunity not found"}

    unknown = client.get("/api/no-such-endpoint")
    assert unknown.json() == {"detail": "API endpoint not found"}

    invalid = client.post("/api/opportunities", json={"account_name": "Acme"})
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)

    plain = TestClient(client.app)
    assert plain.post("/api/opportunities", json={}).json() == {
        "detail": "CSRF token missing or invalid"
    }
