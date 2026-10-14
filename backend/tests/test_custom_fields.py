"""Custom fields (milestone 6.1, ADR 0006, `docs/FEATURES.md` §3).

The authorization matrix covers who may call each route (**D-171**: anybody
signed in, because this app has no admin role). This file is about what the
feature does, and the properties that carry it are the ADR's own:

- values are **validated on write** against the live definition set, with a
  422 that names the field so a form can mark the input,
- the JSON column is **never trusted on read**, so archiving a field hides
  its values everywhere without rewriting a single row -- and restoring the
  definition brings them back,
- a `key` and a `type` cannot be edited, which is what makes
  archive-and-recreate the only route to a type change,
- a write that does not mention custom fields **keeps** them, because a JSON
  column is written whole and there is no partial merge to express.
"""

import json

from fastapi.testclient import TestClient
from test_tasks import create_opportunity, login, logout, share, signup
from test_timeline import create_entry

from app.custom_fields import stored_values, visible_values
from app.database import db_connection


def define(
    client: TestClient,
    key: str,
    field_type: str = "text",
    entity_type: str = "opportunity",
    **extra: object,
) -> dict:
    response = client.post(
        "/api/v2/custom-fields",
        json={
            "entity_type": entity_type,
            "key": key,
            "label": extra.pop("label", key.title()),
            "type": field_type,
            **extra,
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_a_field_appears_on_the_record_it_was_defined_for(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    define(client, "region", "select", options=["EMEA", "APAC"])
    define(client, "sentiment", entity_type="entry")

    opportunity = client.post(
        "/api/v2/opportunities",
        json={"name": "Acme", "account_name": "Acme", "custom_values": {"region": "EMEA"}},
    ).json()
    assert opportunity["custom_values"] == {"region": "EMEA"}

    entry = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "visibility": "shared",
            "type": "call",
            "title": "Call",
            "event_timestamp": "2026-09-01T10:00:00",
            "custom_values": {"sentiment": "warm"},
        },
    ).json()
    assert entry["custom_values"] == {"sentiment": "warm"}

    # The field sets are per entity type, so an opportunity's field is not
    # offered on an entry and vice versa.
    refused = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "visibility": "shared",
            "type": "call",
            "title": "Wrong field",
            "event_timestamp": "2026-09-01T10:00:00",
            "custom_values": {"region": "EMEA"},
        },
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["fields"] == {
        "custom_values.region": "is not a field on this record"
    }


def test_a_refused_value_names_the_field_that_was_wrong(client: TestClient) -> None:
    """The half of a 422 that matters (`docs/REVIEW.md` M4): a flat "Request
    failed" leaves a form with no input to mark."""
    signup(client, "owner@example.com", "Owner")
    define(client, "region", "select", options=["EMEA", "APAC"])
    define(client, "headcount", "number")
    define(client, "renews_on", "date")
    define(client, "is_strategic", "checkbox")

    for values, expected in [
        ({"region": "ANTARCTICA"}, {"custom_values.region": "must be one of the field's options"}),
        ({"headcount": "many"}, {"custom_values.headcount": "must be a number"}),
        ({"headcount": True}, {"custom_values.headcount": "must be a number"}),
        (
            {"renews_on": "not a date"},
            {"custom_values.renews_on": "Enter a valid date as YYYY-MM-DD"},
        ),
        ({"is_strategic": "yes"}, {"custom_values.is_strategic": "must be true or false"}),
        ({"nope": 1}, {"custom_values.nope": "is not a field on this record"}),
    ]:
        response = client.post(
            "/api/v2/opportunities",
            json={"name": "Acme", "account_name": "Acme", "custom_values": values},
        )
        assert response.status_code == 422, (values, response.json())
        assert response.json()["error"]["fields"] == expected


def test_a_required_field_is_required_when_values_are_submitted(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    define(client, "region", "select", options=["EMEA"], required=True)

    refused = client.post(
        "/api/v2/opportunities",
        json={"name": "Acme", "account_name": "Acme", "custom_values": {}},
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["fields"] == {"custom_values.region": "is required"}

    # And a create that does not mention custom fields at all is still
    # allowed: making a field required must not make every existing screen
    # that posts without it start failing.
    allowed = client.post("/api/v2/opportunities", json={"name": "Acme", "account_name": "Acme"})
    assert allowed.status_code == 201
    assert allowed.json()["custom_values"] == {}


def test_a_patch_that_does_not_mention_fields_keeps_them(client: TestClient) -> None:
    """A JSON column is written whole, so "leave them alone" has to be the
    quiet default or renaming a deal would clear its custom values."""
    signup(client, "owner@example.com", "Owner")
    define(client, "region", "select", options=["EMEA", "APAC"])
    opportunity = client.post(
        "/api/v2/opportunities",
        json={"name": "Acme", "account_name": "Acme", "custom_values": {"region": "EMEA"}},
    ).json()

    renamed = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}", json={"name": "Acme Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["custom_values"] == {"region": "EMEA"}

    changed = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}", json={"custom_values": {"region": "APAC"}}
    )
    assert changed.json()["custom_values"] == {"region": "APAC"}

    # Submitting an empty set is how a value is cleared -- it is a whole set,
    # not a patch.
    cleared = client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"custom_values": {}})
    assert cleared.json()["custom_values"] == {}


def test_archiving_hides_values_without_rewriting_any_row(client: TestClient) -> None:
    """ADR 0006's load-bearing property: "unknown keys are ignored, so
    archiving a field does not require rewriting rows"."""
    signup(client, "owner@example.com", "Owner")
    field = define(client, "region", "select", options=["EMEA", "APAC"])
    opportunity = client.post(
        "/api/v2/opportunities",
        json={"name": "Acme", "account_name": "Acme", "custom_values": {"region": "EMEA"}},
    ).json()

    assert client.post(f"/api/v2/custom-fields/{field['id']}/archive").status_code == 200
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["custom_values"] == {}

    # The value is still in the column. This is the assertion that makes
    # archiving reversible rather than destructive, so it reads the database
    # directly rather than the API that is deliberately hiding it.
    with db_connection() as connection:
        raw = connection.execute(
            "SELECT custom_values FROM opportunities WHERE id = ?",
            (opportunity["id"],),
        ).fetchone()["custom_values"]
    assert json.loads(raw) == {"region": "EMEA"}

    assert client.post(f"/api/v2/custom-fields/{field['id']}/restore").status_code == 200
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["custom_values"] == {
        "region": "EMEA"
    }


def test_an_archived_key_can_be_reused_and_then_blocks_the_restore(client: TestClient) -> None:
    """The partial unique index allows reuse once a field is retired, which is
    what makes archive-and-recreate a workable answer to a type change -- and
    it is also the one way `restore` can fail."""
    signup(client, "owner@example.com", "Owner")
    text_field = define(client, "region")
    assert client.post(f"/api/v2/custom-fields/{text_field['id']}/archive").status_code == 200

    # The same key, now as a select: the type change ADR 0006 asks the UI to
    # express this way rather than by mutating a definition.
    define(client, "region", "select", options=["EMEA"])

    clash = client.post(f"/api/v2/custom-fields/{text_field['id']}/restore")
    assert clash.status_code == 409


def test_a_key_and_a_type_cannot_be_edited(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    field = define(client, "region", "select", options=["EMEA", "APAC"])

    # Not refused: ignored, because `CustomFieldUpdate` does not carry them.
    # The field's identity and the shape of every stored value are what would
    # need a data migration, which is the thing the ADR avoids.
    updated = client.patch(
        f"/api/v2/custom-fields/{field['id']}",
        json={
            "label": "Sales region",
            "options": ["EMEA", "APAC", "AMER"],
            "required": True,
            "position": 2,
            "key": "something_else",
            "type": "text",
            "entity_type": "entry",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["label"] == "Sales region"
    assert body["options"] == ["EMEA", "APAC", "AMER"]
    assert body["required"] is True
    assert (body["key"], body["type"], body["entity_type"]) == ("region", "select", "opportunity")


def test_a_duplicate_key_is_refused_while_the_field_is_live(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    define(client, "region")
    clash = client.post(
        "/api/v2/custom-fields",
        json={"entity_type": "opportunity", "key": "region", "label": "Other", "type": "text"},
    )
    assert clash.status_code == 409
    # Same key, different entity type: a different field set, so it is allowed.
    assert define(client, "region", entity_type="entry")["key"] == "region"


def test_a_definition_must_make_sense_for_its_type(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    for payload, reason in [
        ({"key": "tier", "label": "Tier", "type": "select"}, "a select needs options"),
        (
            {"key": "flag", "label": "Flag", "type": "checkbox", "options": ["a"]},
            "only selects carry options",
        ),
        ({"key": "Bad Key", "label": "Bad", "type": "text"}, "the key pattern"),
        ({"key": "ok", "label": "   ", "type": "text"}, "a blank label"),
        (
            {"key": "dupes", "label": "Dupes", "type": "select", "options": ["a", "a"]},
            "distinct options",
        ),
    ]:
        response = client.post(
            "/api/v2/custom-fields", json={"entity_type": "opportunity", **payload}
        )
        assert response.status_code == 422, (reason, response.json())


def test_a_multi_select_stores_a_set_in_the_definitions_own_order(client: TestClient) -> None:
    """Two writes of the same choices have to produce the same JSON, or a
    version snapshot comparing them as text would see a change that is not
    one -- the reasoning `task_versions.assignee_ids` already follows."""
    signup(client, "owner@example.com", "Owner")
    define(client, "products", "multi_select", options=["Core", "Addon", "Support"])

    first = client.post(
        "/api/v2/opportunities",
        json={
            "name": "Acme",
            "account_name": "Acme",
            "custom_values": {"products": ["Support", "Core", "Core"]},
        },
    ).json()
    assert first["custom_values"]["products"] == ["Core", "Support"]

    refused = client.post(
        "/api/v2/opportunities",
        json={"name": "Nope", "account_name": "X", "custom_values": {"products": ["Nonsense"]}},
    )
    assert refused.status_code == 422


def test_every_role_reads_the_values_and_the_definitions(client: TestClient) -> None:
    """A field is global metadata, so a viewer has to be able to read it --
    otherwise the columns on their screen have no labels."""
    owner = signup(client, "owner@example.com", "Owner")
    assert owner
    define(client, "region", "select", options=["EMEA"])
    opportunity = create_opportunity(client)
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}", json={"custom_values": {"region": "EMEA"}}
    )
    signup(client, "viewer@example.com", "Viewer")
    logout(client)
    login(client, "owner@example.com")
    share(client, opportunity["id"], "viewer@example.com", "viewer")
    logout(client)
    login(client, "viewer@example.com")

    assert client.get("/api/v2/custom-fields").json()["items"][0]["key"] == "region"
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["custom_values"] == {
        "region": "EMEA"
    }


def test_the_read_tolerates_a_column_it_cannot_parse() -> None:
    """The column is `NOT NULL DEFAULT '{}'` with a `json_valid` check, so
    this should be unreachable -- but an unparseable value stored in a column
    the dashboard renders is exactly how `event_timestamp` once produced a 500
    for every user sharing an opportunity (`CLAUDE.md`, "Timestamps")."""
    definitions = [{"key": "region", "required": False, "type": "text"}]
    assert stored_values(None) == {}
    assert stored_values("") == {}
    assert stored_values("not json") == {}
    assert stored_values("[1, 2]") == {}
    assert visible_values("not json", definitions) == {}
    assert visible_values('{"region": "EMEA", "gone": 1}', definitions) == {"region": "EMEA"}


def test_a_field_is_listed_for_one_entity_type_and_archived_on_request(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    define(client, "region")
    entry_field = define(client, "sentiment", entity_type="entry")

    assert [f["key"] for f in client.get("/api/v2/custom-fields").json()["items"]] == [
        "region",
        "sentiment",
    ]
    assert [
        f["key"] for f in client.get("/api/v2/custom-fields?entity_type=entry").json()["items"]
    ] == ["sentiment"]

    client.post(f"/api/v2/custom-fields/{entry_field['id']}/archive")
    assert [f["key"] for f in client.get("/api/v2/custom-fields").json()["items"]] == ["region"]
    archived = client.get("/api/v2/custom-fields?include_archived=true").json()["items"]
    assert [f["key"] for f in archived] == ["region", "sentiment"]

    # Archiving twice is the same answer: the first archiver is recorded.
    first = client.post(f"/api/v2/custom-fields/{entry_field['id']}/archive").json()
    again = client.post(f"/api/v2/custom-fields/{entry_field['id']}/archive").json()
    assert first["archived_at"] == again["archived_at"]

    # An archived field cannot be edited -- create a new one (ADR 0006).
    assert (
        client.patch(
            f"/api/v2/custom-fields/{entry_field['id']}",
            json={"label": "Nope", "required": False},
        ).status_code
        == 409
    )


def test_an_entrys_values_survive_an_edit_of_something_else(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    define(client, "sentiment", entity_type="entry")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    client.patch(f"/api/v2/timeline/{entry['id']}", json={"custom_values": {"sentiment": "warm"}})

    retitled = client.patch(f"/api/v2/timeline/{entry['id']}", json={"title": "Retitled"})
    assert retitled.status_code == 200
    assert retitled.json()["custom_values"] == {"sentiment": "warm"}
    assert retitled.json()["title"] == "Retitled"
