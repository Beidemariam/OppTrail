"""Automations (milestone 6.3, `docs/FEATURES.md` §11).

The authorization matrix covers who may call each route (**D-173**: anybody
signed in may write a rule, only its creator may change or run one). This file
is about what §11's own constraints mean in practice, and the five that carry
the feature are:

- **one hop** -- a rule's write cannot wake a rule, which is why the design
  contains no loop detection at all,
- **a rule acts with its creator's authority**, over the deals its creator can
  read, and is refused per deal when the action needs a role they lack,
- **always dry-runnable**, through the same evaluator the real run uses,
- **every applied action leaves a system entry naming the rule**, which is
  §11's requirement and `AGENTS.md` standard 5's,
- **capped in number**, counted per creator.
"""

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_custom_fields import define
from test_tasks import create_opportunity, login, logout, share, signup
from test_timeline import create_entry

from app.database import db_connection
from app.schemas import MAX_ENABLED_RULES_PER_CREATOR

AUTOMATIONS_SOURCE = Path(__file__).resolve().parent.parent / "app" / "automations.py"


def create_rule(
    client: TestClient,
    name: str = "Nudge the quiet ones",
    trigger_type: str = "no_activity",
    trigger: dict | None = None,
    conditions: list[dict] | None = None,
    action_type: str = "create_task",
    action: dict | None = None,
    enabled: bool = True,
    expect: int = 201,
) -> dict:
    response = client.post(
        "/api/v2/automation-rules",
        json={
            "name": name,
            "trigger_type": trigger_type,
            "trigger": trigger if trigger is not None else {"days": 14},
            "conditions": conditions or [],
            "action_type": action_type,
            "action": action if action is not None else {"title": "Follow up"},
            "enabled": enabled,
        },
    )
    assert response.status_code == expect, response.json()
    return response.json()


def closing_in(days: int) -> str:
    """A close date relative to now, so no assertion depends on today's date.

    `test_timeline.days_ago` read the other way round, and the rule it exists
    for applies just as hard forwards: the first version of
    `test_a_closing_deal_is_found_before_it_closes` hardcoded 2026-10-12 as
    "soon", which stopped being soon the next morning and failed the gate.
    """
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%d")


def silence(opportunity_id: int, days: int = 30) -> None:
    """Backdate everything on a deal so a no-activity rule can see it.

    Every timestamp is moved rather than only the entries': the stalled
    predicate takes the latest of entry, note and comment, so leaving one of
    them at `now` would make the deal look busy. `days` is read as text
    arithmetic in SQLite for the same reason the production query is -- these
    are canonical fixed-width strings.
    """
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE timeline_entries
            SET event_timestamp = datetime(event_timestamp, ?),
                created_at = datetime(created_at, ?)
            WHERE opportunity_id = ?
            """,
            (f"-{days} days", f"-{days} days", opportunity_id),
        )
        connection.commit()


def runs_for(client: TestClient, rule_id: int) -> list[dict]:
    response = client.get(f"/api/v2/automation-rules/{rule_id}/runs")
    assert response.status_code == 200, response.json()
    return response.json()["items"]


def timeline(client: TestClient, opportunity_id: int) -> list[dict]:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline?limit=200")
    assert response.status_code == 200
    return response.json()["items"]


# --- §11's one hop ----------------------------------------------------------


def test_invariant_a_rule_cannot_trigger_a_rule() -> None:
    """**D-174**, and the whole of §11's "no rule may trigger another rule".

    A source scan rather than a behavioural check, for the reason
    `test_soft_delete.py` scans for a hard delete: this is a thing the code
    must not *contain*. If `automations.py` ever calls its own entry points,
    an automated write could wake a rule and the design would need loop
    detection it deliberately does not have.

    The definitions themselves are excluded -- `def fire_event(` is not a
    call -- as is the module docstring, which names both functions while
    explaining why they are not called.
    """
    source = AUTOMATIONS_SOURCE.read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    calls = [
        line.strip()
        for line in body.splitlines()
        if re.search(r"(?<!def )\b(fire_event|run_rule)\(", line)
        and not line.strip().startswith(("#", "def ", "*"))
        and "fire_event(connection, trigger, opportunity_id, event)" not in line
    ]
    assert calls == [], (
        "automations.py must not invoke its own entry points: an automated "
        f"write that wakes a rule is a chain, not one hop. Found: {calls}"
    )


def test_a_rules_own_write_does_not_wake_a_rule(client: TestClient) -> None:
    """The behavioural half, against the pair that would chain if anything did.

    A rule that changes the stage, and a rule triggered *by* a stage change.
    Running the first by hand moves the deal and writes a `stage_change`
    entry; the second must stay unfired, because the write came from an
    automation and not from a person.
    """
    signup(client, "ruth@example.com", "Ruth")
    opportunity = create_opportunity(client, "Chain test")
    mover = create_rule(
        client,
        name="Advance it",
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="change_stage",
        action={"stage": "Qualification"},
    )
    watcher = create_rule(
        client,
        name="React to the move",
        trigger_type="stage_changed",
        trigger={},
        action_type="add_entry",
        action={"title": "Stage moved"},
    )
    silence(opportunity["id"])

    applied = client.post(f"/api/v2/automation-rules/{mover['id']}/run?dry_run=false")
    assert applied.status_code == 200
    assert [run["outcome"] for run in applied.json()["runs"]] == ["applied"]

    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["stage"] == (
        "Qualification"
    )
    assert runs_for(client, watcher["id"]) == []


# --- The triggers -----------------------------------------------------------


def test_a_stage_change_by_a_person_fires_the_rule_watching_it(client: TestClient) -> None:
    signup(client, "sam@example.com", "Sam")
    opportunity = create_opportunity(client, "Stage watch")
    rule = create_rule(
        client,
        name="Negotiation handoff",
        trigger_type="stage_changed",
        trigger={"to_stage": "Negotiation"},
        action_type="create_task",
        action={"title": "Prepare the paperwork", "due_in_days": 2},
    )

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Qualification"})
    assert runs_for(client, rule["id"]) == []

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Negotiation"})
    runs = runs_for(client, rule["id"])
    assert [run["outcome"] for run in runs] == ["applied"]

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert [task["title"] for task in tasks] == ["Prepare the paperwork"]
    assert tasks[0]["due_date"] is not None


def test_an_entry_of_the_watched_type_fires_the_rule(client: TestClient) -> None:
    signup(client, "ingrid@example.com", "Ingrid")
    opportunity = create_opportunity(client, "Entry watch")
    rule = create_rule(
        client,
        name="Log objections",
        trigger_type="entry_created",
        trigger={"entry_type": "objection"},
        action_type="notify_user",
        action={"title": "An objection was raised"},
    )

    create_entry(client, opportunity["id"], entry_type="call")
    assert runs_for(client, rule["id"]) == []

    create_entry(client, opportunity["id"], title="Procurement pushback", entry_type="objection")
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == ["applied"]

    inbox = client.get("/api/v2/notifications?type=automation").json()["items"]
    assert [item["payload"]["rule_name"] for item in inbox] == ["Log objections"]
    assert inbox[0]["payload"]["title"] == "An objection was raised"


def test_a_field_changed_trigger_ignores_a_patch_that_moved_something_else(
    client: TestClient,
) -> None:
    """The route reports which fields its `PATCH` actually moved, so a rule
    watching the value is not woken by a rename."""
    signup(client, "fiona@example.com", "Fiona")
    opportunity = create_opportunity(client, "Field watch")
    rule = create_rule(
        client,
        name="Value moved",
        trigger_type="field_changed",
        trigger={"field": "value"},
        action_type="add_entry",
        action={"title": "Value was revised"},
    )

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"name": "Renamed"})
    assert runs_for(client, rule["id"]) == []

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"value": "90000"})
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == ["applied"]


def test_a_resent_custom_value_is_not_a_change(client: TestClient) -> None:
    """A JSON column is written whole, so a form resending a value unchanged
    would look like a change to anything comparing the submitted set against
    nothing."""
    signup(client, "carla@example.com", "Carla")
    define(client, "region", "select", options=["EMEA", "APAC"])
    opportunity = create_opportunity(client, "Custom watch")
    rule = create_rule(
        client,
        name="Region moved",
        trigger_type="field_changed",
        trigger={"field": "custom:region"},
        action_type="add_entry",
        action={"title": "Region was revised"},
    )

    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"custom_values": {"region": "EMEA"}},
    )
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == ["applied"]

    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"custom_values": {"region": "EMEA"}},
    )
    assert len(runs_for(client, rule["id"])) == 1

    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"custom_values": {"region": "APAC"}},
    )
    assert len(runs_for(client, rule["id"])) == 2


def test_the_no_activity_rule_is_the_feature_requests_own_example(client: TestClient) -> None:
    """§11's opening line: *"if nothing has happened in two weeks, remind me"*.

    And the phase's acceptance criterion: the rule fires once, creates a task,
    and leaves a system entry naming the rule.
    """
    signup(client, "nina@example.com", "Nina")
    quiet = create_opportunity(client, "Gone quiet")
    busy = create_opportunity(client, "Still moving")
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="create_task",
        action={"title": "Chase this deal", "due_in_days": 1},
    )
    silence(quiet["id"])

    response = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert [(run["opportunity_id"], run["outcome"]) for run in runs] == [(quiet["id"], "applied")]

    tasks = client.get(f"/api/v2/opportunities/{quiet['id']}/tasks").json()["items"]
    assert [task["title"] for task in tasks] == ["Chase this deal"]
    assert client.get(f"/api/v2/opportunities/{busy['id']}/tasks").json()["items"] == []

    trace = [entry for entry in timeline(client, quiet["id"]) if entry["system_generated"]]
    named = [entry for entry in trace if rule["name"] in entry["body"]]
    assert len(named) == 1, "§11: an automated write must leave an entry naming the rule"
    assert named[0]["id"] == runs[0]["entry_id"]


def test_a_closing_deal_is_found_before_it_closes(client: TestClient) -> None:
    signup(client, "clive@example.com", "Clive")
    soon = create_opportunity(client, "Closing soon")
    late = create_opportunity(client, "Closing later")
    client.patch(
        f"/api/v2/opportunities/{soon['id']}",
        json={"expected_close_date": closing_in(3)},
    )
    client.patch(
        f"/api/v2/opportunities/{late['id']}",
        json={"expected_close_date": closing_in(300)},
    )
    rule = create_rule(
        client,
        name="Close date is near",
        trigger_type="close_date_approaching",
        trigger={"days": 7},
        action_type="notify_user",
        action={"title": "This one closes this week"},
    )

    runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").json()["runs"]
    assert [run["opportunity_id"] for run in runs] == [soon["id"]]


# --- Conditions -------------------------------------------------------------


def test_conditions_are_anded_and_a_failed_one_is_not_logged(client: TestClient) -> None:
    """A non-match writes no run row: a rule asked about four hundred deals
    would otherwise log four hundred rows a tick saying nothing happened."""
    signup(client, "aiden@example.com", "Aiden")
    big = create_opportunity(client, "Big and quiet")
    small = create_opportunity(client, "Small and quiet")
    client.patch(f"/api/v2/opportunities/{big['id']}", json={"value": "80000"})
    client.patch(f"/api/v2/opportunities/{small['id']}", json={"value": "900"})
    rule = create_rule(
        client,
        name="Chase the big quiet ones",
        trigger_type="no_activity",
        trigger={"days": 14},
        conditions=[
            {"field": "value", "op": "gte", "value": "50000"},
            {"field": "stage", "op": "ne", "value": "Closed Won"},
        ],
        action_type="create_task",
        action={"title": "Chase it"},
    )
    silence(big["id"])
    silence(small["id"])

    runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").json()["runs"]
    assert [run["opportunity_id"] for run in runs] == [big["id"]]


def test_a_number_is_compared_as_a_number(client: TestClient) -> None:
    """`"900" > "50000"` is true as text and false as money. The condition on
    `value` is the one place this project compares a stored number that is
    held as `NUMERIC` and read back as a string."""
    signup(client, "nate@example.com", "Nate")
    opportunity = create_opportunity(client, "Nine hundred")
    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"value": "900"})
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        conditions=[{"field": "value", "op": "gt", "value": "50000"}],
    )
    silence(opportunity["id"])

    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"] == []


def test_archiving_a_custom_field_disarms_the_rules_that_read_it(client: TestClient) -> None:
    """ADR 0006's never-trust-the-column-on-read, applied to a rule.

    The value stays in the JSON, so a rule reading the raw column would keep
    acting on a field nobody can see on screen any more.
    """
    signup(client, "archie@example.com", "Archie")
    field = define(client, "tier", "select", options=["Gold", "Silver"])
    opportunity = create_opportunity(client, "Gold account")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"custom_values": {"tier": "Gold"}},
    )
    rule = create_rule(
        client,
        name="Gold accounts get a nudge",
        trigger_type="no_activity",
        trigger={"days": 14},
        conditions=[{"field": "custom:tier", "op": "eq", "value": "Gold"}],
    )
    silence(opportunity["id"])

    assert len(client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"]) == 1

    assert client.post(f"/api/v2/custom-fields/{field['id']}/archive").status_code == 200
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"] == []


# --- A rule acts with its creator's authority (D-173) -----------------------


def test_a_rule_only_sees_the_deals_its_creator_can_read(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    hidden = create_opportunity(client, "Not shared")
    silence(hidden["id"])
    logout(client)

    signup(client, "outsider@example.com", "Outsider")
    rule = create_rule(client, name="Everything quiet", trigger_type="no_activity")
    response = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    assert response.json() == {"dry_run": False, "considered": 0, "runs": []}


def test_a_rule_may_not_do_what_its_creator_could_not_do_by_hand(client: TestClient) -> None:
    """An editor's rule asking for an owner-only action is a logged skip, not
    a write -- which is what makes open rule creation safe (D-173)."""
    signup(client, "editor@example.com", "Editor")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client, "Owned elsewhere")
    share(client, opportunity["id"], "editor@example.com", "editor")
    silence(opportunity["id"])
    logout(client)

    login(client, "editor@example.com")
    rule = create_rule(
        client,
        name="Editor moves a stage",
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="change_stage",
        action={"stage": "Negotiation"},
    )
    runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").json()["runs"]

    assert [(run["outcome"], run["reason"]) for run in runs] == [
        ("skipped", "Editor may not change stage here")
    ]
    assert runs[0]["entry_id"] is None
    logout(client)

    login(client, "owner@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["stage"] == (
        "Prospecting"
    )


def test_an_editors_rule_may_still_add_an_entry(client: TestClient) -> None:
    """The same rule-acts-as-creator check, passing: adding to a timeline is
    the editor's own write (`require_timeline_write`), so the rule may."""
    signup(client, "editor@example.com", "Editor")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client, "Shared deal")
    share(client, opportunity["id"], "editor@example.com", "editor")
    silence(opportunity["id"])
    logout(client)

    login(client, "editor@example.com")
    rule = create_rule(
        client,
        name="Editor logs a nudge",
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="add_entry",
        action={"title": "Still waiting on procurement", "entry_type": "other"},
    )
    runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").json()["runs"]

    assert [run["outcome"] for run in runs] == ["applied"]
    titles = [entry["title"] for entry in timeline(client, opportunity["id"])]
    assert "Still waiting on procurement" in titles


def test_an_automated_entry_cannot_be_edited(client: TestClient) -> None:
    """It is `system_generated`, so the API's existing rule covers it: nobody
    rewrites the record of what an automation did. Deleting one is a different
    question and a different answer (D-181, below)."""
    signup(client, "sylvia@example.com", "Sylvia")
    opportunity = create_opportunity(client, "Automated entry")
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="add_entry",
        action={"title": "Automated note"},
    )
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    written = next(
        entry for entry in timeline(client, opportunity["id"]) if entry["title"] == "Automated note"
    )
    assert written["system_generated"] is True
    assert written["automation_rule_id"] == rule["id"]
    assert (
        client.patch(f"/api/v2/timeline/{written['id']}", json={"title": "Mine now"}).status_code
        == 403
    )


# --- The owner can clear up after a mistaken rule (6.3a, D-181) -------------


def test_the_owner_can_delete_an_entry_a_rule_wrote(client: TestClient) -> None:
    """The human's own request at the 6.3 review: *"the owner of the deal
    should have a delete power over rule entries, in case a mistaken rule
    action had occured."* Before this nobody at all could remove them --
    every system entry answered 403 to everybody."""
    signup(client, "ruleauthor@example.com", "Rule Author")
    logout(client)
    signup(client, "dealowner@example.com", "Deal Owner")
    opportunity = create_opportunity(client, "Owned by me")
    share(client, opportunity["id"], "ruleauthor@example.com", "editor")
    silence(opportunity["id"])
    logout(client)

    # The rule is somebody else's, which is the case that makes this matter.
    login(client, "ruleauthor@example.com")
    rule = create_rule(
        client,
        name="A rule that misfires",
        action_type="add_entry",
        action={"title": "Written by mistake"},
    )
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")
    logout(client)

    login(client, "dealowner@example.com")
    written = next(
        entry
        for entry in timeline(client, opportunity["id"])
        if entry["title"] == "Written by mistake"
    )
    assert client.delete(f"/api/v2/timeline/{written['id']}").status_code == 204
    assert "Written by mistake" not in [
        entry["title"] for entry in timeline(client, opportunity["id"])
    ]

    # Soft, audited and undoable like every other delete in this project.
    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()["items"]
    assert "timeline_entry_deleted" in [row["action"] for row in audit]
    assert client.post(f"/api/v2/timeline/{written['id']}/restore").status_code == 204
    assert "Written by mistake" in [entry["title"] for entry in timeline(client, opportunity["id"])]


def test_the_rules_author_can_delete_what_their_rule_wrote(client: TestClient) -> None:
    """Author-or-owner (D-005) with no second permission shape: an automated
    entry's `created_by` is the rule's creator, whose authority it ran with."""
    signup(client, "cleanup@example.com", "Cleanup")
    opportunity = create_opportunity(client, "My own deal")
    rule = create_rule(
        client,
        action_type="add_entry",
        action={"title": "Remove me"},
    )
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    written = next(
        entry for entry in timeline(client, opportunity["id"]) if entry["title"] == "Remove me"
    )
    assert client.delete(f"/api/v2/timeline/{written['id']}").status_code == 204


def test_a_viewer_still_cannot_delete_what_a_rule_wrote(client: TestClient) -> None:
    """The exception is one entry kind, not one permission rule: a viewer is
    neither the author nor the owner, so they get the ordinary 403."""
    signup(client, "looker@example.com", "Looker")
    logout(client)
    signup(client, "holder@example.com", "Holder")
    opportunity = create_opportunity(client, "Shared read-only")
    share(client, opportunity["id"], "looker@example.com", "viewer")
    silence(opportunity["id"])
    rule = create_rule(client, action_type="add_entry", action={"title": "Not yours"})
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")
    written = next(
        entry for entry in timeline(client, opportunity["id"]) if entry["title"] == "Not yours"
    )
    logout(client)

    login(client, "looker@example.com")
    assert client.delete(f"/api/v2/timeline/{written['id']}").status_code == 403


def test_a_system_entry_a_person_caused_is_still_undeletable(client: TestClient) -> None:
    """The exception is for what a rule did *to* somebody, not for what a
    person did. "Opportunity created" and a stage somebody moved are the
    record of their own actions, and nobody edits or deletes those."""
    signup(client, "history@example.com", "History")
    opportunity = create_opportunity(client, "Ordinary history")
    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Proposal"})

    for title in ("Opportunity created", "Stage changed to Proposal"):
        entry = next(item for item in timeline(client, opportunity["id"]) if item["title"] == title)
        assert entry["automation_rule_id"] is None, title
        assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 403, title


def test_a_stage_a_rule_moved_is_not_put_back_by_deleting_its_entry(client: TestClient) -> None:
    """Deleting the entry removes the *record*, not the change -- which is why
    the version history matters (D-178): that is where the stage goes back."""
    signup(client, "undo@example.com", "Undo")
    opportunity = create_opportunity(client, "Moved wrongly")
    rule = create_rule(
        client,
        name="Wrong move",
        action_type="change_stage",
        action={"stage": "Closed Lost"},
    )
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    written = next(
        entry
        for entry in timeline(client, opportunity["id"])
        if entry["title"] == "Stage changed to Closed Lost"
    )
    assert client.delete(f"/api/v2/timeline/{written['id']}").status_code == 204
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["stage"] == (
        "Closed Lost"
    )

    restored = client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore")
    assert restored.status_code == 200
    assert restored.json()["stage"] == "Prospecting"


# --- Dry run ----------------------------------------------------------------


def test_a_dry_run_writes_nothing_and_says_what_it_would_have_done(client: TestClient) -> None:
    """§11's "always dry-runnable", and the reason `dry_run` defaults to true:
    a preview is what somebody writing a rule wants, and the other default's
    failure mode is two hundred deals changed by mistake."""
    signup(client, "dana@example.com", "Dana")
    opportunity = create_opportunity(client, "Preview me")
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="create_task",
        action={"title": "Would chase this"},
    )
    silence(opportunity["id"])

    preview = client.post(f"/api/v2/automation-rules/{rule['id']}/run")
    assert preview.status_code == 200
    body = preview.json()
    assert body["dry_run"] is True
    assert [(run["outcome"], run["dry_run"]) for run in body["runs"]] == [("applied", True)]
    assert body["runs"][0]["entry_id"] is None

    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"] == []
    assert [entry["title"] for entry in timeline(client, opportunity["id"])] == [
        "Opportunity created"
    ]


def test_a_rule_that_would_change_nothing_is_a_skip(client: TestClient) -> None:
    """The server's half of D-114, applied to a writer that fires on a timer:
    a deal already in the target stage must not collect a `stage_change` entry
    on every run saying nothing changed."""
    signup(client, "stan@example.com", "Stan")
    opportunity = create_opportunity(client, "Already there")
    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Negotiation"})
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="change_stage",
        action={"stage": "Negotiation"},
    )
    silence(opportunity["id"])

    runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").json()["runs"]
    assert [(run["outcome"], run["reason"]) for run in runs] == [
        ("skipped", "already in Negotiation")
    ]


# --- Writing a rule ---------------------------------------------------------


def test_a_config_key_the_chosen_kind_does_not_take_is_refused(client: TestClient) -> None:
    """Accepting and ignoring the key would store a rule that does not mean
    what the person who wrote it read on screen."""
    signup(client, "val@example.com", "Val")
    create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14, "to_stage": "Negotiation"},
        expect=422,
    )
    create_rule(client, trigger_type="no_activity", trigger={}, expect=422)
    create_rule(
        client,
        trigger_type="stage_changed",
        trigger={},
        action_type="change_stage",
        action={"title": "Not a stage"},
        expect=422,
    )


def test_a_rule_cannot_forge_a_stage_change_entry(client: TestClient) -> None:
    """The dashboard's time-in-stage reads `type = 'stage_change'` (milestone
    6.2), so an `add_entry` action naming that type would feed it a stage
    change that never happened. The `change_stage` action writes one properly,
    having actually moved the deal."""
    signup(client, "forge@example.com", "Forge")
    create_rule(
        client,
        action_type="add_entry",
        action={"title": "Pretend move", "entry_type": "stage_change"},
        expect=422,
    )


def test_a_condition_can_only_name_a_field_a_rule_is_about(client: TestClient) -> None:
    signup(client, "cora@example.com", "Cora")
    create_rule(client, conditions=[{"field": "owner_id", "op": "eq", "value": "1"}], expect=422)
    create_rule(client, conditions=[{"field": "value", "op": "contains", "value": "5"}], expect=422)
    create_rule(client, conditions=[{"field": "value", "op": "gt", "value": "lots"}], expect=422)
    create_rule(
        client, conditions=[{"field": "custom:Region", "op": "eq", "value": "x"}], expect=422
    )


def test_rules_are_capped_per_creator(client: TestClient) -> None:
    """§11: "capped in number". Per creator, because a rule acts with its
    creator's authority -- a global cap would let one person's twenty rules
    lock everybody else out."""
    signup(client, "capped@example.com", "Capped")
    for index in range(MAX_ENABLED_RULES_PER_CREATOR):
        create_rule(client, name=f"Rule {index}")

    create_rule(client, name="One too many", expect=409)
    # A disabled rule does not count, so a shelf of experiments is allowed.
    create_rule(client, name="Parked", enabled=False)


def test_only_the_creator_can_change_or_run_a_rule(client: TestClient) -> None:
    """D-173's second half. Everybody may *read* the list, because "what
    automations run here" is a question a colleague has a stake in; a rule
    performs writes attributed to its creator, so changing somebody else's is
    not open."""
    signup(client, "author@example.com", "Author")
    rule = create_rule(client, name="Author's rule")
    logout(client)

    signup(client, "other@example.com", "Other")
    listed = client.get("/api/v2/automation-rules").json()["items"]
    assert [item["name"] for item in listed] == ["Author's rule"]
    assert listed[0]["creator_name"] == "Author"

    assert (
        client.patch(
            f"/api/v2/automation-rules/{rule['id']}",
            json={
                "name": "Mine now",
                "trigger_type": "no_activity",
                "trigger": {"days": 14},
                "conditions": [],
                "action_type": "create_task",
                "action": {"title": "Hijacked"},
                "enabled": True,
            },
        ).status_code
        == 403
    )
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/archive").status_code == 403
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run").status_code == 403
    assert client.get(f"/api/v2/automation-rules/{rule['id']}/runs").status_code == 403


def test_an_archived_rule_stops_firing_and_keeps_its_history(client: TestClient) -> None:
    """There is no DELETE: `automation_runs.rule_id` points at the row, and a
    log saying "rule 4 changed this deal's stage" is worthless if rule 4 can
    vanish."""
    signup(client, "ariel@example.com", "Ariel")
    opportunity = create_opportunity(client, "Archive test")
    rule = create_rule(
        client,
        name="Will be archived",
        trigger_type="stage_changed",
        trigger={},
        action_type="add_entry",
        action={"title": "Moved"},
    )
    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Qualification"})
    assert len(runs_for(client, rule["id"])) == 1

    archived = client.post(f"/api/v2/automation-rules/{rule['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert archived.json()["enabled"] is False
    # Idempotent, like `archive_custom_field`.
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/archive").status_code == 200

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Proposal"})
    assert len(runs_for(client, rule["id"])) == 1
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").status_code == (
        409
    )
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run").status_code == 200


def test_a_disabled_rule_does_not_fire(client: TestClient) -> None:
    signup(client, "dee@example.com", "Dee")
    opportunity = create_opportunity(client, "Disabled test")
    rule = create_rule(
        client,
        name="Parked rule",
        trigger_type="stage_changed",
        trigger={},
        action_type="add_entry",
        action={"title": "Moved"},
        enabled=False,
    )

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Qualification"})
    assert runs_for(client, rule["id"]) == []


# --- The operators, and the shapes a custom value can take -----------------


def test_every_operator_compares_the_way_a_reader_would_expect(client: TestClient) -> None:
    """One rule per operator over one deal, which is the cheapest way to pin a
    comparison ladder. `contains` is case-insensitive and the orderings are
    numeric on `value` and textual everywhere else."""
    signup(client, "ops@example.com", "Ops")
    opportunity = create_opportunity(client, "Contoso renewal")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"value": "25000", "account_name": "Contoso"},
    )
    silence(opportunity["id"])

    cases: list[tuple[dict, bool]] = [
        ({"field": "account_name", "op": "contains", "value": "contos"}, True),
        ({"field": "account_name", "op": "contains", "value": "northwind"}, False),
        ({"field": "value", "op": "lt", "value": "30000"}, True),
        ({"field": "value", "op": "lte", "value": "25000"}, True),
        ({"field": "value", "op": "gt", "value": "25000"}, False),
        ({"field": "account_name", "op": "eq", "value": "Contoso"}, True),
        ({"field": "expected_close_date", "op": "lt", "value": "2027-01-01"}, True),
    ]
    for index, (condition, expected) in enumerate(cases):
        rule = create_rule(client, name=f"Operator {index}", conditions=[condition])
        runs = client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"]
        assert bool(runs) is expected, condition
        # Twenty enabled rules is the cap, so each case parks its own rule.
        assert client.post(f"/api/v2/automation-rules/{rule['id']}/archive").status_code == 200


def test_a_checkbox_and_a_multi_select_compare_as_text(client: TestClient) -> None:
    """A custom value is not always a string. A checkbox reads as
    `true`/`false` and a multi-select as its joined options, because a
    condition's own value is typed by a person into one text box."""
    signup(client, "shapes@example.com", "Shapes")
    define(client, "follow_up", "checkbox")
    define(client, "regions", "multi_select", options=["EMEA", "APAC"])
    opportunity = create_opportunity(client, "Shaped values")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"custom_values": {"follow_up": True, "regions": ["EMEA", "APAC"]}},
    )
    silence(opportunity["id"])

    flagged = create_rule(
        client,
        name="Follow ups",
        conditions=[{"field": "custom:follow_up", "op": "eq", "value": "true"}],
    )
    assert len(client.post(f"/api/v2/automation-rules/{flagged['id']}/run").json()["runs"]) == 1

    listed = create_rule(
        client,
        name="Any APAC",
        conditions=[{"field": "custom:regions", "op": "contains", "value": "apac"}],
    )
    assert len(client.post(f"/api/v2/automation-rules/{listed['id']}/run").json()["runs"]) == 1


def test_an_unset_field_fails_its_condition_rather_than_matching(client: TestClient) -> None:
    signup(client, "unset@example.com", "Unset")
    opportunity = create_opportunity(client, "No close date")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"expected_close_date": None},
    )
    silence(opportunity["id"])
    rule = create_rule(
        client,
        conditions=[{"field": "expected_close_date", "op": "lt", "value": "2027-01-01"}],
    )

    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"] == []


# --- The trigger filters ----------------------------------------------------


def test_a_stage_rule_can_watch_the_stage_a_deal_left(client: TestClient) -> None:
    signup(client, "left@example.com", "Left")
    opportunity = create_opportunity(client, "Leaving Prospecting")
    rule = create_rule(
        client,
        name="Left prospecting",
        trigger_type="stage_changed",
        trigger={"from_stage": "Qualification"},
        action_type="add_entry",
        action={"title": "Out of qualification"},
    )

    # Prospecting -> Qualification is a change *to* the watched stage, not from.
    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Qualification"})
    assert runs_for(client, rule["id"]) == []

    client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Proposal"})
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == ["applied"]


def test_an_action_can_be_aimed_at_the_rules_author_instead_of_the_owner(
    client: TestClient,
) -> None:
    """`recipient` is the answer to "whose list grows": a rep writing a rule
    over their own pipeline wants the owner, a manager watching a team's deals
    wants themselves."""
    signup(client, "manager@example.com", "Manager")
    logout(client)
    signup(client, "rep@example.com", "Rep")
    opportunity = create_opportunity(client, "Rep's deal")
    share(client, opportunity["id"], "manager@example.com", "editor")
    silence(opportunity["id"])
    logout(client)

    login(client, "manager@example.com")
    rule = create_rule(
        client,
        name="My own follow-ups",
        action_type="create_task",
        action={"title": "Look at this", "recipient": "rule_creator"},
    )
    assert client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false").status_code == (
        200
    )

    mine = client.get("/api/v2/tasks").json()["items"]
    assert [task["title"] for task in mine] == ["Look at this"]


# --- The routes' own answers -----------------------------------------------


def test_a_rule_that_does_not_exist_is_a_404(client: TestClient) -> None:
    signup(client, "missing@example.com", "Missing")
    assert client.get("/api/v2/automation-rules/9999/runs").status_code == 404
    assert client.post("/api/v2/automation-rules/9999/archive").status_code == 404


def test_the_list_can_be_narrowed_to_the_callers_own_rules(client: TestClient) -> None:
    signup(client, "theirs@example.com", "Theirs")
    create_rule(client, name="Theirs")
    logout(client)
    signup(client, "mine@example.com", "Mine")
    create_rule(client, name="Mine")

    everybodys = client.get("/api/v2/automation-rules").json()["items"]
    assert sorted(rule["name"] for rule in everybodys) == ["Mine", "Theirs"]

    own = client.get("/api/v2/automation-rules?mine_only=true").json()["items"]
    assert [rule["name"] for rule in own] == ["Mine"]


def test_the_list_and_the_log_page(client: TestClient) -> None:
    """Keyset over `(created_at, id)` like every other collection read here,
    which is what the cursor walk proves rather than the page size."""
    signup(client, "pager@example.com", "Pager")
    for index in range(3):
        create_rule(client, name=f"Rule {index}")

    first = client.get("/api/v2/automation-rules?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = client.get(f"/api/v2/automation-rules?limit=2&cursor={first['next_cursor']}").json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    assert {rule["id"] for rule in first["items"]}.isdisjoint(
        {rule["id"] for rule in second["items"]}
    )


def test_an_archived_rule_cannot_be_edited_and_an_archived_list_includes_it(
    client: TestClient,
) -> None:
    signup(client, "frozen@example.com", "Frozen")
    rule = create_rule(client, name="Frozen rule")
    client.post(f"/api/v2/automation-rules/{rule['id']}/archive")

    assert client.get("/api/v2/automation-rules").json()["items"] == []
    listed = client.get("/api/v2/automation-rules?include_archived=true").json()["items"]
    assert [item["name"] for item in listed] == ["Frozen rule"]

    refused = client.patch(
        f"/api/v2/automation-rules/{rule['id']}",
        json={
            "name": "Frozen rule",
            "trigger_type": "no_activity",
            "trigger": {"days": 14},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Follow up"},
            "enabled": True,
        },
    )
    assert refused.status_code == 409


def test_re_enabling_a_rule_counts_against_the_cap(client: TestClient) -> None:
    """The cap counts enabled rules, so the write that has to be refused is
    the one that *turns one on* -- not only the one that creates one."""
    signup(client, "recap@example.com", "Recap")
    parked = create_rule(client, name="Parked", enabled=False)
    for index in range(MAX_ENABLED_RULES_PER_CREATOR):
        create_rule(client, name=f"Live {index}")

    turned_on = client.patch(
        f"/api/v2/automation-rules/{parked['id']}",
        json={
            "name": "Parked",
            "trigger_type": "no_activity",
            "trigger": {"days": 14},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Follow up"},
            "enabled": True,
        },
    )
    assert turned_on.status_code == 409

    # Editing it while leaving it disabled is fine.
    kept_off = client.patch(
        f"/api/v2/automation-rules/{parked['id']}",
        json={
            "name": "Still parked",
            "trigger_type": "no_activity",
            "trigger": {"days": 21},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Follow up"},
            "enabled": False,
        },
    )
    assert kept_off.status_code == 200
    assert kept_off.json()["trigger"]["days"] == 21


# --- The two paths a well-behaved database never takes ----------------------


def test_a_non_numeric_value_compares_as_text_rather_than_raising(client: TestClient) -> None:
    """`opportunities.value` is a `NUMERIC` column and SQLite will store text
    in one. Nothing the API accepts can put it there, but an imported or
    hand-edited database can -- and a rule firing is not where that should be
    discovered, because the 500 would land on somebody else's write."""
    signup(client, "odd@example.com", "Odd")
    opportunity = create_opportunity(client, "Hand edited")
    with db_connection() as connection:
        connection.execute(
            "UPDATE opportunities SET value = 'to be confirmed' WHERE id = ?",
            (opportunity["id"],),
        )
        connection.commit()
    silence(opportunity["id"])

    rule = create_rule(
        client,
        conditions=[{"field": "value", "op": "gte", "value": "50000"}],
    )
    response = client.post(f"/api/v2/automation-rules/{rule['id']}/run")

    assert response.status_code == 200
    # "to be confirmed" >= "50000" as text, which is a meaningless answer to a
    # meaningless question -- the point is that it is an answer and not a 500.
    assert len(response.json()["runs"]) == 1


def test_a_failing_rule_does_not_fail_the_write_that_triggered_it(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A person renamed a deal; whether somebody else's automation managed to
    act on that is not their problem."""
    signup(client, "resilient@example.com", "Resilient")
    opportunity = create_opportunity(client, "Still editable")
    create_rule(
        client,
        name="Will fail",
        trigger_type="stage_changed",
        trigger={},
        action_type="add_entry",
        action={"title": "Moved"},
    )

    def explode(*args: object, **kwargs: object) -> list[int]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("app.automations.fire_event", explode)
    moved = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Qualification"},
    )

    assert moved.status_code == 200
    assert moved.json()["stage"] == "Qualification"


def test_the_run_log_pages(client: TestClient) -> None:
    signup(client, "logpager@example.com", "Log Pager")
    for index in range(3):
        create_opportunity(client, f"Deal {index}")
    rule = create_rule(client)
    for index in range(1, 4):
        silence(index)
    assert len(client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"]) == 3

    first = client.get(f"/api/v2/automation-rules/{rule['id']}/runs?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    second = client.get(
        f"/api/v2/automation-rules/{rule['id']}/runs?limit=2&cursor={first['next_cursor']}"
    ).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


# --- Invariant 8, read against a writer nobody is watching ------------------


def test_a_stage_a_rule_moved_is_recoverable_from_the_history(client: TestClient) -> None:
    """`AGENTS.md` invariant 8: every user-editable field keeps its previous
    value, attributed to who changed it, and "quietly rewriting one must be
    [traceable] too" -- which is what an unattended writer does. So a rule's
    stage change records a version like every other write to an opportunity,
    and the owner can put the previous stage back."""
    signup(client, "recover@example.com", "Recover")
    opportunity = create_opportunity(client, "Moved by a rule")
    rule = create_rule(
        client,
        name="Advance it",
        action_type="change_stage",
        action={"stage": "Proposal"},
    )
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["stage"] == "Proposal"

    versions = client.get(f"/api/v2/opportunities/{opportunity['id']}/versions").json()["items"]
    assert [version["stage"] for version in versions] == ["Prospecting", "Proposal"]
    # Attributed to the rule's creator, who is who the rule acts as (D-173).
    assert versions[-1]["edited_by"] == versions[0]["edited_by"]

    restored = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore",
    )
    assert restored.status_code == 200
    assert restored.json()["stage"] == "Prospecting"


def test_a_task_a_rule_created_opens_its_history_with_what_it_said(client: TestClient) -> None:
    """Version 1 at creation (milestone 4.2a). A version is the state *after* a
    write, so a task with no version 1 would lose its original wording to its
    own first edit."""
    signup(client, "firstdraft@example.com", "First Draft")
    opportunity = create_opportunity(client, "Task from a rule")
    rule = create_rule(client, action={"title": "Original wording"})
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    task = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"][0]
    assert (
        client.patch(
            f"/api/v2/tasks/{task['id']}",
            json={"title": "Edited by hand"},
        ).status_code
        == 200
    )

    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [version["title"] for version in versions] == ["Original wording", "Edited by hand"]
    # The assignee set is the canonical string `version_is_current` compares,
    # so restoring what is already current is still a no-op (D-120).
    assert versions[0]["assignees"] == versions[1]["assignees"]


def test_a_rules_stage_change_appears_once_in_the_activity_log(client: TestClient) -> None:
    """The system entry is the event's one appearance: `activity.py` drops an
    opportunity version whose only changed field is the stage, so recording
    the version does not put the same change on the feed twice."""
    signup(client, "once@example.com", "Once")
    opportunity = create_opportunity(client, "Counted once")
    rule = create_rule(
        client,
        name="Advance it",
        action_type="change_stage",
        action={"stage": "Proposal"},
    )
    silence(opportunity["id"])
    client.post(f"/api/v2/automation-rules/{rule['id']}/run?dry_run=false")

    feed = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity?limit=50").json()
    details = [row["detail"] for row in feed["items"]]

    # One mention of the move, and it is the system entry.
    moves = [detail for detail in details if "Proposal" in str(detail)]
    assert len(moves) == 1, details
    assert moves[0]["source"] == "system_entry"

    # And no edit row at all: version 1 is the creation baseline (D-097) and
    # version 2 moved only the stage, which `activity.py` drops because the
    # system entry above is that event's one appearance.
    assert [detail for detail in details if detail["source"] == "version"] == []


def test_a_close_date_rule_may_change_a_stage(client: TestClient) -> None:
    """**D-179.** This combination used to be refused by a rule that is
    nowhere in `docs/FEATURES.md` §11 -- I invented it -- and the refusal
    reached the human at the 6.3 review as the generic 422 message with no
    reason attached. Two faults in one, and this is the half about the
    prohibition: it is gone. A rule that moves a deal as its close date
    approaches is odd rather than harmful, and it is idempotent, because
    `_would_change_nothing` skips a deal already in the target stage."""
    signup(client, "closing@example.com", "Closing")
    rule = create_rule(
        client,
        name="Closing this week",
        trigger_type="close_date_approaching",
        trigger={"days": 7},
        action_type="change_stage",
        action={"stage": "Negotiation"},
    )

    assert rule["trigger_type"] == "close_date_approaching"
    assert rule["action_type"] == "change_stage"


def test_a_refused_rule_says_which_part_was_wrong(client: TestClient) -> None:
    """The other half of the same finding: the 422 envelope carries `fields`
    so a form can mark the input (`docs/REVIEW.md` M4, the property milestone
    6.1 was careful about). The API was already right; nothing on the client
    read it, which is what made the refusal mute.

    Two shapes, and the form has to render both: a **field** error keys on the
    input (`trigger.days`), while a **cross-field** one keys on `_`, because a
    rule whose action does not match its trigger is wrong as a whole and there
    is no single input to mark. `errors.py`'s `validation_fields` is what
    decides that, from the location Pydantic reports.
    """
    signup(client, "named@example.com", "Named")

    def refuse(**overrides: object) -> dict:
        payload = {
            "name": "Refused",
            "trigger_type": "no_activity",
            "trigger": {"days": 14},
            "conditions": [],
            "action_type": "create_task",
            "action": {"title": "Chase it"},
            "enabled": True,
        }
        payload.update(overrides)
        response = client.post("/api/v2/automation-rules", json=payload)
        assert response.status_code == 422, response.json()
        fields: dict = response.json()["error"]["fields"]
        return fields

    # A value this field cannot hold: keyed on the input.
    assert "trigger.days" in refuse(trigger={"days": 9999})
    # A rule that is wrong as a whole: keyed on `_`.
    whole = refuse(action={"title": None})
    assert list(whole) == ["_"]
    assert whole["_"] == "A 'create_task' action needs 'title'"
    # And the reason is the sentence itself: Pydantic prefixes a custom
    # `ValueError` with "Value error, ", which says nothing to the person
    # reading the form the reason now lands in.
    condition = refuse(conditions=[{"field": "value", "op": "gte", "value": "lots"}])
    assert condition == {"conditions.0": "'lots' is not a number"}
