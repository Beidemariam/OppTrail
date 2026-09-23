"""The seed data has to keep being what its own output claims it is.

`make seed` prints a short tour ("Casey is a viewer on Northwind and Globex",
"Globex renewal is stalled") that a human then follows by hand. Those sentences
are only useful if they stay true, so they are assertions here rather than
prose only.
"""

from conftest import CsrfClient
from fastapi.testclient import TestClient

from app.database import db_connection, initialize_database
from app.settings import settings
from tools.seed import ALEX, BLAIR, CASEY, DANA, DEMO_PASSWORD, seed


def sign_in(client: TestClient, email: str) -> None:
    response = client.post("/api/v2/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text


def seeded_client(email: str) -> CsrfClient:
    from app.main import app

    client = CsrfClient(app)
    client.__enter__()
    sign_in(client, email)
    return client


def test_seed_populates_every_shipped_feature(tmp_path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    initialize_database()

    seed()

    with db_connection() as connection:
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) AS count FROM {table}"  # noqa: S608 - table is a literal
            ).fetchone()["count"]
            for table in (
                "users",
                "opportunities",
                "opportunity_shares",
                "timeline_entries",
                "notes",
                "comments",
                "note_versions",
                "notifications",
                "audit_log_entries",
                "saved_views",
            )
        }
        entry_types = {
            row["type"] for row in connection.execute("SELECT DISTINCT type FROM timeline_entries")
        }
        notification_types = {
            row["type"] for row in connection.execute("SELECT DISTINCT type FROM notifications")
        }
        system_entries = connection.execute(
            "SELECT COUNT(*) AS count FROM timeline_entries WHERE system_generated = 1"
        ).fetchone()["count"]
        soft_deleted_notes = connection.execute(
            "SELECT COUNT(*) AS count FROM notes WHERE deleted_at IS NOT NULL"
        ).fetchone()["count"]
        edited_notes = connection.execute(
            "SELECT COUNT(*) AS count FROM notes WHERE edited = 1"
        ).fetchone()["count"]

    assert counts["users"] == 4
    assert counts["opportunities"] == 5
    assert counts["opportunity_shares"] == 4
    for table in (
        "timeline_entries",
        "notes",
        "comments",
        "note_versions",
        "audit_log_entries",
        "saved_views",
    ):
        assert counts[table] > 0, f"{table} is empty after seeding"

    # Every relationship the demo tour names has to be reachable.
    assert {"call", "email", "meeting", "demo", "proposal", "contract", "other"} <= entry_types
    assert "stage_change" in entry_types and system_entries > 0
    assert {"share_added", "shared_activity", "mention", "comment"} <= notification_types
    assert soft_deleted_notes == 1
    assert edited_notes == 1


def test_seeded_permissions_match_the_printed_tour(tmp_path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    initialize_database()
    seed()

    alex = seeded_client(ALEX)
    blair = seeded_client(BLAIR)
    casey = seeded_client(CASEY)
    dana = seeded_client(DANA)

    try:
        alex_list = alex.get("/api/v2/opportunities").json()["items"]
        by_name = {opportunity["name"]: opportunity for opportunity in alex_list}

        assert set(by_name) == {
            "Northwind platform rollout",
            "Contoso pilot",
            "Globex renewal",
            "Initech expansion",
            "Umbrella discovery",
        }
        assert by_name["Initech expansion"]["current_user_role"] == "viewer"
        assert by_name["Globex renewal"]["stalled"] is True
        assert by_name["Northwind platform rollout"]["stalled"] is False
        assert by_name["Northwind platform rollout"]["stage"] == "Negotiation"

        northwind = by_name["Northwind platform rollout"]["id"]

        # Blair edits Northwind; Casey may only read it; Dana cannot see it.
        assert (
            blair.post(
                f"/api/v2/opportunities/{northwind}/timeline",
                json={
                    "type": "call",
                    "title": "Editor can write",
                    "body": "",
                    "event_timestamp": "2026-09-04T10:00",
                },
            ).status_code
            == 201
        )
        assert casey.get(f"/api/v2/opportunities/{northwind}").status_code == 200
        assert (
            casey.post(
                f"/api/v2/opportunities/{northwind}/timeline",
                json={
                    "type": "call",
                    "title": "Viewer cannot write",
                    "body": "",
                    "event_timestamp": "2026-09-04T10:00",
                },
            ).status_code
            == 403
        )
        assert dana.get(f"/api/v2/opportunities/{northwind}").status_code == 404
        assert dana.get("/api/v2/opportunities").json()["items"] == []

        # The tour's search line: one query, four different answers, because
        # the permission filter lives inside the query (`app/search.py`).
        def finance_hits(session: CsrfClient) -> list[str]:
            page = session.get("/api/v2/search?q=finance")
            assert page.status_code == 200, page.text
            return sorted(item["opportunity_name"] for item in page.json()["items"])

        assert finance_hits(alex) == ["Initech expansion", "Northwind platform rollout"]
        assert finance_hits(blair) == ["Initech expansion", "Northwind platform rollout"]
        assert finance_hits(casey) == ["Northwind platform rollout"]
        assert finance_hits(dana) == []

        # The mention in the demo note notified Alex.
        mentions = [
            notification
            for notification in alex.get("/api/v2/notifications").json()["items"]
            if notification["type"] == "mention"
        ]
        assert mentions, "the seeded @mention did not produce a notification"

        # The inbox rework's tour line (milestone 1.7): one notification
        # already read and still visible in history, next to unread ones —
        # not the v1 dead end where reading one made it disappear.
        alex_inbox = alex.get("/api/v2/notifications?limit=50").json()["items"]
        by_type = {item["type"]: item for item in alex_inbox}
        assert by_type["share_added"]["read_at"] is not None
        assert by_type["mention"]["read_at"] is None
        assert by_type["shared_activity"]["read_at"] is None

        # The saved-views tour line (milestone 2.2): Alex's board view is
        # shared, so Blair sees it beside their own; Blair's is private, so
        # Alex does not see it; and the timeline view is filed under the other
        # entity, so it does not appear in the board's list.
        def view_names(session: CsrfClient, entity: str) -> list[str]:
            page = session.get(f"/api/v2/saved-views?entity={entity}")
            assert page.status_code == 200, page.text
            return sorted(item["name"] for item in page.json()["items"])

        assert view_names(alex, "opportunities") == ["Late-stage pipeline"]
        assert view_names(blair, "opportunities") == [
            "Blair's proposals",
            "Late-stage pipeline",
        ]
        assert view_names(alex, "timeline") == ["Newest first"]
        assert view_names(dana, "opportunities") == ["Late-stage pipeline"]

        # The owner-only audit log is not empty on a fresh seed.
        audit = alex.get(f"/api/v2/opportunities/{northwind}/audit-log")
        assert audit.status_code == 200
        assert audit.json()["items"], "expected share activity in the audit log"
        assert casey.get(f"/api/v2/opportunities/{northwind}/audit-log").status_code == 403

        # The tour says Umbrella holds an undone deletion: both halves in the
        # log, and the entry back on the timeline.
        umbrella = by_name["Umbrella discovery"]["id"]
        actions = [
            row["action"]
            for row in alex.get(f"/api/v2/opportunities/{umbrella}/audit-log").json()["items"]
        ]
        assert "timeline_entry_deleted" in actions
        assert "timeline_entry_restored" in actions
        titles = [
            entry["title"]
            for entry in alex.get(f"/api/v2/opportunities/{umbrella}/timeline").json()["items"]
        ]
        assert "Qualification call" in titles
    finally:
        for client in (alex, blair, casey, dana):
            client.__exit__(None, None, None)
