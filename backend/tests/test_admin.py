"""Who administers the deployment (R.1c, **D-215**).

Two writes in this application are not scoped to an opportunity: defining a
**custom field**, which changes the shape of every record of its entity type,
and writing an **automation rule**, which writes to records unattended under
somebody's name. Both were open to any authenticated caller -- D-171 and
D-173, on the reasoning that `docs/FEATURES.md`'s "admin-defined" had no
admin to resolve to in an application with three per-opportunity roles and no
role table.

The reviewer closed that at the Phase R gate: *"both have to be done by the
owner."* An opportunity's owner cannot be the answer, because neither object
has an opportunity in sight, so "the owner" is the deployment's: the
addresses in `ADMIN_EMAILS`.

This file is the pair of tests that holds the gate in both directions, and
the one that holds the *reading* open -- because a gate on the read would
break the column picker, the filter bar and both forms for everybody who is
not an administrator.
"""

import pytest
from fastapi.testclient import TestClient

from app.settings import settings

ADMIN = "owner@example.com"
COLLEAGUE = "editor@example.com"

A_FIELD = {
    "entity_type": "opportunity",
    "key": "region",
    "label": "Region",
    "type": "text",
}

A_RULE = {
    "name": "Nudge me about quiet deals",
    "trigger_type": "no_activity",
    "trigger": {"days": 14},
    "conditions": [],
    "action_type": "notify_user",
    "action": {"title": "This one has gone quiet."},
}


def signup(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text


def test_an_administrator_defines_a_field_and_writes_a_rule(client: TestClient) -> None:
    """`conftest.py` makes `owner@example.com` the administrator, which is the
    same arrangement every feature suite runs under."""
    signup(client, ADMIN)

    assert client.post("/api/v2/custom-fields", json=A_FIELD).status_code == 201
    assert client.post("/api/v2/automation-rules", json=A_RULE).status_code == 201


def test_everybody_else_is_refused_both(client: TestClient) -> None:
    """403 rather than 404, unlike every opportunity-scoped refusal: both
    lists are readable by everyone, so there is no existence to hide and the
    message is the useful part."""
    signup(client, COLLEAGUE)

    field = client.post("/api/v2/custom-fields", json=A_FIELD)
    rule = client.post("/api/v2/automation-rules", json=A_RULE)

    assert field.status_code == 403
    assert rule.status_code == 403
    # The sentence names what an operator has to change, and never who the
    # administrators are.
    for refusal in (field, rule):
        message = refusal.json()["error"]["message"]
        assert "ADMIN_EMAILS" in message
        assert ADMIN not in message


def test_editing_archiving_and_restoring_a_field_are_all_gated(client: TestClient) -> None:
    """The write surface is the four routes, not just the first one: an
    unguarded edit is the same reach as an unguarded create, by way of the
    label everybody reads."""
    signup(client, ADMIN)
    field_id = client.post("/api/v2/custom-fields", json=A_FIELD).json()["id"]
    client.post("/api/v2/auth/logout")

    signup(client, COLLEAGUE)
    assert client.patch(f"/api/v2/custom-fields/{field_id}", json={"label": "R"}).status_code == 403
    assert client.post(f"/api/v2/custom-fields/{field_id}/archive").status_code == 403
    assert client.post(f"/api/v2/custom-fields/{field_id}/restore").status_code == 403


def test_a_non_administrator_still_reads_both_lists(client: TestClient) -> None:
    """The half that must stay open. Three screens read the definitions, and
    "which automations run here, and whose" is answerable by design (D-173)."""
    signup(client, ADMIN)
    client.post("/api/v2/custom-fields", json=A_FIELD)
    client.post("/api/v2/automation-rules", json=A_RULE)
    client.post("/api/v2/auth/logout")

    signup(client, COLLEAGUE)
    fields = client.get("/api/v2/custom-fields")
    rules = client.get("/api/v2/automation-rules")

    assert fields.status_code == 200
    assert [item["key"] for item in fields.json()["items"]] == ["region"]
    assert rules.status_code == 200
    assert [item["name"] for item in rules.json()["items"]] == [A_RULE["name"]]


@pytest.mark.parametrize(
    ("configured", "email", "expected"),
    [
        ("owner@example.com", "owner@example.com", True),
        ("  Owner@Example.com ", "owner@example.com", True),
        ("a@example.com,owner@example.com", "owner@example.com", True),
        ("", "owner@example.com", False),
        ("someone@else.test", "owner@example.com", False),
    ],
)
def test_the_setting_is_read_as_a_list_of_addresses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
    email: str,
    expected: bool,
) -> None:
    """Comma-separated, trimmed and case-insensitive, because an address is
    not case-sensitive and a hand-edited `.env` has spaces in it. **Empty
    means nobody**, which is the safe default for a fresh install."""
    monkeypatch.setattr(settings, "admin_emails", configured)
    signup(client, email)

    allowed = client.post("/api/v2/custom-fields", json=A_FIELD).status_code == 201

    assert allowed is expected
