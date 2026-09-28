"""Watchers: follow an opportunity you are not shared on (milestone 3.3a,
`docs/FEATURES.md` §7, D-129).

The rest of this app answers 404 to anyone without a share, so existence
never leaks. Watching is the one deliberate exception: `require_opportunity_exists`
checks only that the id names a live opportunity, because the whole point of
the feature is to be reachable by someone the access model would otherwise
turn away at the door. `test_soft_delete.py` and `docs/autopilot/DECISIONS.md`
D-130 cover why `watchers` rows are hard-deleted; this file covers watching's
own behavior.
"""

from fastapi.testclient import TestClient
from test_comment_threads import post_comment
from test_timeline import create_entry, create_opportunity, login, share_opportunity, signup


def test_watching_is_available_with_no_share_at_all(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    signup(client, "outsider@example.com", "Outsider")

    # The outsider cannot read the opportunity at all.
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 404

    status_before = client.get(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert status_before.status_code == 200
    assert status_before.json() == {"watching": False}

    watched = client.post(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert watched.status_code == 200
    assert watched.json() == {"watching": True}

    # Watching grants no read access -- it is additive, not a weaker share.
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 404

    status_after = client.get(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert status_after.json() == {"watching": True}

    unwatched = client.delete(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert unwatched.status_code == 200
    assert unwatched.json() == {"watching": False}


def test_watching_twice_is_idempotent(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    first = client.post(f"/api/v2/opportunities/{opportunity['id']}/watch")
    second = client.post(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert first.status_code == second.status_code == 200

    with_owner = client.get(f"/api/v2/opportunities/{opportunity['id']}/watchers")
    assert with_owner.status_code == 200
    assert len(with_owner.json()["items"]) == 1


def test_unwatching_something_never_watched_is_a_no_op(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.delete(f"/api/v2/opportunities/{opportunity['id']}/watch")
    assert response.status_code == 200
    assert response.json() == {"watching": False}


def test_watch_routes_404_a_deleted_or_unknown_opportunity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204

    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 404
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 404
    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 404
    assert client.get("/api/v2/opportunities/9999/watch").status_code == 404


def test_watchers_list_is_owner_only(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 200
    refused = client.get(f"/api/v2/opportunities/{opportunity['id']}/watchers")
    assert refused.status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    allowed = client.get(f"/api/v2/opportunities/{opportunity['id']}/watchers")
    assert allowed.status_code == 200
    assert [item["user_email"] for item in allowed.json()["items"]] == ["editor@example.com"]


def test_a_watcher_who_is_not_shared_is_still_notified_of_shared_activity(
    client: TestClient,
) -> None:
    """`notify_shared_activity` is additive: a watcher is unioned into the
    recipients an accessible user already gets, not a filter over them."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    signup(client, "watcher@example.com", "Watcher")
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 200
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    create_entry(client, opportunity["id"])
    client.post("/api/v2/auth/logout")

    login(client, "watcher@example.com")
    inbox = client.get("/api/v2/notifications?type=shared_activity").json()["items"]
    assert len(inbox) == 1
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 404


def test_watching_does_not_widen_the_member_list_or_the_mention_autocomplete(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "Note"}).json()
    post_comment(client, note["id"], "Anything to add?")
    client.post("/api/v2/auth/logout")

    signup(client, "watcher@example.com", "Watcher")
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/watch").status_code == 200
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    members = client.get(f"/api/v2/opportunities/{opportunity['id']}/members").json()["items"]
    assert "watcher@example.com" not in {member["email"] for member in members}
