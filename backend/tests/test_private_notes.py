"""A notebook of one's own (milestone R.1b).

The half of the human's ruling that keeps something out of the deal's history
altogether, rather than sealing a moment inside it.
"""

from fastapi.testclient import TestClient

from app.database import db_connection
from tests.test_entry_visibility import create_opportunity, login, shared_deal, signup


def note(client: TestClient, opportunity_id: int) -> dict:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/private-note")
    assert response.status_code == 200
    return response.json()


def write(client: TestClient, opportunity_id: int, body: str) -> dict:
    response = client.put(
        f"/api/v2/opportunities/{opportunity_id}/private-note",
        json={"body": body},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_an_unwritten_notebook_reads_as_empty_rather_than_missing(client: TestClient) -> None:
    signup(client, "solo@example.com", "Solo")
    opportunity = create_opportunity(client)

    assert note(client, opportunity["id"]) == {
        "opportunity_id": opportunity["id"],
        "body": "",
        "updated_at": None,
    }


def test_it_is_written_whole_and_read_back(client: TestClient) -> None:
    signup(client, "solo@example.com", "Solo")
    opportunity = create_opportunity(client)

    write(client, opportunity["id"], "Their procurement lead is the blocker.")
    write(client, opportunity["id"], "Their procurement lead is the blocker. Call Dave.")

    held = note(client, opportunity["id"])
    assert held["body"] == "Their procurement lead is the blocker. Call Dave."
    assert held["updated_at"] is not None
    # One notebook per person per deal, not one per write.
    with db_connection() as connection:
        rows = connection.execute("SELECT COUNT(*) AS n FROM private_notes").fetchone()
    assert rows["n"] == 1


def test_two_people_on_one_deal_keep_two_notebooks(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    write(client, opportunity["id"], "What the owner thinks.")

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")

    # The colleague's own is empty, not the owner's.
    assert note(client, opportunity["id"])["body"] == ""
    write(client, opportunity["id"], "What the colleague thinks.")
    assert note(client, opportunity["id"])["body"] == "What the colleague thinks."

    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")
    assert note(client, opportunity["id"])["body"] == "What the owner thinks."


def test_somebody_with_no_access_to_the_deal_gets_the_usual_404(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    signup(client, "stranger@example.com", "Stranger")

    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/private-note").status_code == 404
    assert (
        client.put(
            f"/api/v2/opportunities/{opportunity['id']}/private-note",
            json={"body": "Reading over your shoulder"},
        ).status_code
        == 404
    )


def test_clearing_it_empties_it_and_keeps_the_row(client: TestClient) -> None:
    signup(client, "solo@example.com", "Solo")
    opportunity = create_opportunity(client)
    write(client, opportunity["id"], "Something")

    write(client, opportunity["id"], "")

    assert note(client, opportunity["id"])["body"] == ""
    with db_connection() as connection:
        rows = connection.execute("SELECT COUNT(*) AS n FROM private_notes").fetchone()
    assert rows["n"] == 1


def test_a_notebook_is_in_no_other_read(client: TestClient) -> None:
    """The property that makes this safe is structural: no query outside
    `routes_private_notes.py` mentions the table. This asserts the two reads a
    leak would most plausibly come through."""
    _, _, opportunity = shared_deal(client)
    write(client, opportunity["id"], "Procurement lead is the blocker")

    found = client.get("/api/v2/search", params={"q": "procurement"}).json()["items"]
    exported = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json")

    assert found == []
    assert "procurement" not in exported.text.lower()
