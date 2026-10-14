import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v2/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200


def create_opportunity(client: TestClient) -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": "Expansion",
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
    event_timestamp: str,
    body: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "visibility": "shared",
            "type": "call",
            "title": title,
            "body": body if body is not None else f"{title} details",
            "event_timestamp": event_timestamp,
        },
    )
    assert response.status_code == 201
    return response.json()


def share_opportunity(opportunity_id: int, user_id: int, invited_by: int, role: str) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO opportunity_shares (opportunity_id, user_id, invited_by, role)
            VALUES (?, ?, ?, ?)
            """,
            (opportunity_id, user_id, invited_by, role),
        )
        connection.commit()


def add_note_and_comment(client: TestClient, entry_id: int) -> tuple[dict, dict]:
    note_response = client.post(
        f"/api/v2/timeline/{entry_id}/notes",
        json={"body": "Procurement follow-up needed"},
    )
    assert note_response.status_code == 201
    note = note_response.json()
    comment_response = client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "Loop in legal before Friday"},
    )
    assert comment_response.status_code == 201
    return note, comment_response.json()


def test_export_json_csv_and_pdf_for_owner(client: TestClient, monkeypatch) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    later_entry = create_entry(
        client,
        opportunity["id"],
        "Later call",
        "2026-09-04T13:00:00",
    )
    earlier_entry = create_entry(
        client,
        opportunity["id"],
        "Earlier call",
        "2026-09-01T09:00:00",
    )
    note, comment = add_note_and_comment(client, later_entry["id"])
    hidden_entry = create_entry(
        client,
        opportunity["id"],
        "Hidden call",
        "2026-09-02T09:00:00",
    )
    assert client.delete(f"/api/v2/timeline/{hidden_entry['id']}").status_code == 204

    json_response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json")
    assert json_response.status_code == 200
    assert "attachment" in json_response.headers["content-disposition"]
    data = json_response.json()
    titles = [entry["title"] for entry in data["entries"]]
    timestamps = [entry["event_timestamp"] for entry in data["entries"]]
    assert "Hidden call" not in titles
    # Newest first by default since milestone 4.4b: the export follows the
    # timeline's own default reading order (D-137) rather than contradicting
    # the screen it was exported from.
    assert timestamps == sorted(timestamps, reverse=True)
    exported_later = next(entry for entry in data["entries"] if entry["id"] == later_entry["id"])
    assert exported_later["notes"][0]["id"] == note["id"]
    assert exported_later["notes"][0]["comments"][0]["id"] == comment["id"]

    csv_response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(csv_response.text)))
    assert {row["row_type"] for row in rows} >= {"entry", "note", "comment"}
    note_row = next(row for row in rows if row["row_type"] == "note")
    comment_row = next(row for row in rows if row["row_type"] == "comment")
    assert note_row["parent_entry_id"] == str(later_entry["id"])
    assert comment_row["parent_note_id"] == str(note["id"])

    monkeypatch.setattr("app.routes_export.export_data_to_pdf", lambda data: b"%PDF-1.7")
    pdf_response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")
    assert earlier_entry["title"] in titles


def test_the_export_reads_in_the_order_the_timeline_does(client: TestClient) -> None:
    """Milestone 4.4b, from the human's note on check T6: *"the export comes in
    reverse chronology than the timeline for which I chose descending ... make
    it the same as the timeline view"*. The link carries the order the reader
    is in; a bare link gets the timeline's default.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Later call", "2026-09-04T13:00:00")
    create_entry(client, opportunity["id"], "Earlier call", "2026-09-01T09:00:00")

    def titles(query: str) -> list[str]:
        response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json{query}")
        assert response.status_code == 200
        return [entry["title"] for entry in response.json()["entries"]]

    newest_first = titles("")
    oldest_first = titles("?order=asc")

    assert newest_first.index("Later call") < newest_first.index("Earlier call")
    assert oldest_first == list(reversed(newest_first))
    # An order the API does not know is refused rather than guessed at.
    assert (
        client.get(
            f"/api/v2/opportunities/{opportunity['id']}/export/json?order=sideways"
        ).status_code
        == 422
    )


def test_a_discussion_is_never_read_backwards(client: TestClient) -> None:
    """Only the entries turn. A note's comments are a conversation, and the
    reading order is a question about which event you meet first."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Discovery call", "2026-09-04T13:00:00")
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "First note"}).json()
    client.post(f"/api/v2/notes/{note['id']}/comments", json={"body": "First comment"})
    client.post(f"/api/v2/notes/{note['id']}/comments", json={"body": "Second comment"})

    exported = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/export/json?order=desc"
    ).json()
    # By title, not by position: newest-first puts the "Opportunity created"
    # system entry first, which is exactly the assumption this change breaks.
    discovery = next(item for item in exported["entries"] if item["title"] == "Discovery call")
    comments = discovery["notes"][0]["comments"]

    assert [item["body"] for item in comments] == ["First comment", "Second comment"]


def test_shared_users_can_export_and_unshared_user_cannot(
    client: TestClient,
    monkeypatch,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Shared call", "2026-09-04T10:00:00")
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    other = signup(client, "other@example.com", "Other")
    client.post("/api/v2/auth/logout")

    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    monkeypatch.setattr("app.routes_export.export_data_to_pdf", lambda data: b"%PDF-1.7")

    login(client, "editor@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/export/csv").status_code == 200
    client.post("/api/v2/auth/logout")

    login(client, "viewer@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json").status_code == 200
    client.post("/api/v2/auth/logout")

    login(client, "other@example.com")
    assert other["email"] == "other@example.com"
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json").status_code == 404
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/export/csv").status_code == 404
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/export/pdf").status_code == 404


def test_csv_export_neutralizes_spreadsheet_formulas(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Discovery", "2026-09-01T09:00:00")
    client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": '=HYPERLINK("https://attacker.example","Click")'},
    )

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    note_row = next(row for row in rows if row["row_type"] == "note")
    assert note_row["body"].startswith("'=")

    for row in rows:
        for value in row.values():
            assert not (value or "").startswith(("=", "+", "@"))


def test_pdf_html_renders_timeline_in_the_readers_order_and_escapes_bodies(
    client: TestClient,
) -> None:
    from app.export_service import fetch_export_data, render_export_html

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Second call", "2026-09-04T13:00:00")
    first = create_entry(client, opportunity["id"], "First call", "2026-09-01T09:00:00")
    client.post(
        f"/api/v2/timeline/{first['id']}/notes",
        json={"body": "<script>alert(1)</script> follow up"},
    )

    with db_connection() as connection:
        data = fetch_export_data(connection, opportunity["id"], 1)
    html = render_export_html(data)

    # Newest first, which is what the reader's timeline shows by default
    # (milestone 4.4b).
    assert html.index("Second call") < html.index("First call")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Expansion" in html and "Acme" in html


def test_pdf_html_renders_markdown_instead_of_escaping_it(client: TestClient) -> None:
    """The other half of `docs/code_review.md` finding 9: a note reading
    `**Budget approved**` used to appear in the PDF with literal asterisks
    (`export_service.py` escaped every body as plain text). Milestone 3.5
    renders Markdown through the same node set the browser does, sanitizing
    the result rather than trusting it (`app/sanitize.py`).
    """
    from app.export_service import fetch_export_data, render_export_html

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(
        client,
        opportunity["id"],
        "Discovery call",
        "2026-09-01T09:00:00",
        body="**Budget confirmed**\n\n- champion identified\n- next step scheduled",
    )
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Approved by [finance](javascript:alert(1))."},
    ).json()
    client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "Confirmed, ~~pending~~ done."},
    )

    with db_connection() as connection:
        data = fetch_export_data(connection, opportunity["id"], 1)
    html = render_export_html(data)

    # The entry body's bold and list render as markup, not literal syntax.
    assert "<strong>Budget confirmed</strong>" in html
    assert "**Budget confirmed**" not in html
    assert "<li>champion identified</li>" in html

    # A `javascript:` link is refused by the Markdown parser itself (the same
    # scheme guard `lib/markdown.ts`'s composer applies): it is left as
    # unparsed literal text rather than becoming a clickable anchor — this
    # body was posted straight to the API, bypassing the composer entirely, so
    # the parser and the sanitizer beneath it are the only things standing in
    # the way. What must never appear is an `href` carrying the scheme.
    assert 'href="javascript' not in html

    # A comment's Markdown renders too.
    assert "<s>pending</s>" in html


def test_pdf_html_sanitizes_raw_html_even_if_the_markdown_parser_let_it_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`render_markdown_to_safe_html` has two layers against a hostile body:
    the parser's own `html: False` option (pinned by the two tests above) and
    `sanitize_html` underneath it. This test forces the first layer off — the
    same as `commonmark`'s own default — to prove the second still holds, so a
    future change to the parser's options cannot reopen the hole silently.
    """
    import app.export_service as export_service

    monkeypatch.setattr(
        export_service,
        "_markdown",
        export_service.MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"]),
    )

    html = export_service.render_markdown_to_safe_html("<script>alert(1)</script>ok")

    assert "<script>" not in html
    assert "ok" in html


# --- The attachment manifest (milestone 4.4, `docs/FEATURES.md` §6) ---------


def attach(client: TestClient, entry_id: int, filename: str, data: bytes) -> dict:
    response = client.post(
        f"/api/v2/timeline/{entry_id}/attachments",
        files={"file": (filename, data, "application/pdf")},
    )
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.mark.parametrize(
    ("byte_size", "expected"),
    [
        (0, "0 bytes"),
        (512, "512 bytes"),
        (1024, "1.0 KB"),
        (2_411_724, "2.3 MB"),
        (10 * 1024 * 1024, "10.0 MB"),
    ],
)
def test_a_file_size_reads_the_way_the_screen_reads_it(byte_size: int, expected: str) -> None:
    """The same answers `lib/domain.ts`'s `formatBytes` gives, deliberately as a
    second implementation: nothing travels between WeasyPrint and the browser
    except `byte_size` itself, which is why the API sends a number."""
    from app.export_service import format_byte_size

    assert format_byte_size(byte_size) == expected


def test_the_pdf_lists_each_file_under_its_own_entry(client: TestClient) -> None:
    """§6: "Attachments appear in PDF export as a listed manifest with filename,
    size and uploader -- **not** embedded, which would make exports unbounded."

    Both halves are asserted, and so is the placement the human ruled for after
    reading a real export (milestone 4.4a, overruling D-154): the file is under
    the entry it belongs to, not in a section at the end.
    """
    from app.export_service import fetch_export_data, render_export_html

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent", "2026-09-04T13:00:00")
    contents = b"%PDF-1.7 " + b"x" * 3000
    attach(client, entry["id"], "quarterly proposal.pdf", contents)

    with db_connection() as connection:
        data = fetch_export_data(connection, opportunity["id"], 1)
    html = render_export_html(data)

    # The file is inside its entry's own article, which is what "next to its
    # entry" means in a document with no columns to put it beside.
    entry_html = html[html.index("Proposal sent") :]
    listing = entry_html[entry_html.index('<ul class="files">') :]
    assert "quarterly proposal.pdf" in listing
    assert "2.9 KB" in listing
    assert "Owner" in listing
    # Nothing is left at the end of the document (4.4a removed that section).
    assert '<section class="manifest">' not in html
    # Not embedded: nothing of the file's own bytes reaches the document, which
    # is the half of §6 that keeps an export's size bounded -- and the summary
    # says so once, where a reader meets the document.
    assert "xxxxxxxxxx" not in html
    assert "1 attachments" in html
    assert "are not included in this file" in html


def test_the_manifest_is_absent_when_there_are_no_files(client: TestClient) -> None:
    """A section announcing that there are no documents is the clutter the
    Design bar rules out -- the same reason `TaskSummary` draws nothing when
    nothing is due."""
    from app.export_service import fetch_export_data, render_export_html

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Discovery call", "2026-09-04T13:00:00")

    with db_connection() as connection:
        data = fetch_export_data(connection, opportunity["id"], 1)
    html = render_export_html(data)

    assert '<ul class="files">' not in html
    assert "0 attachments" in html
    # And the sentence about files is absent too, because there are none to
    # explain.
    assert "are not included in this file" not in html


def test_a_filename_cannot_carry_markup_into_the_export(client: TestClient) -> None:
    """The filename is the one field in the manifest a person chose, and it
    reaches the document as typed by design -- `uploads.safe_filename` strips
    paths, not markup -- so escaping it here is the boundary.

    The payload has no `/` in it on purpose. A tag with a closing half loses its
    front to the path stripping (`</script>` contains a separator, so
    `<script>alert(1)</script>.pdf` is *recorded* as `script>.pdf`), which is a
    real property of that function and not the one this test is about.
    """
    from app.export_service import fetch_export_data, render_export_html

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent", "2026-09-04T13:00:00")
    attach(client, entry["id"], "<img src=x onerror=alert(1)>.pdf", b"%PDF-1.7 payload")

    with db_connection() as connection:
        data = fetch_export_data(connection, opportunity["id"], 1)
    html = render_export_html(data)

    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;.pdf" in html


def test_the_csv_and_json_carry_the_files_too(client: TestClient) -> None:
    """One read feeds all three formats (`fetch_export_data`), so leaving the
    files out of two of them would make "export this deal" mean three different
    things. The CSV's new columns are appended, so a reader of the old file
    keeps every column where it was."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent", "2026-09-04T13:00:00")
    attachment = attach(client, entry["id"], "proposal.pdf", b"%PDF-1.7 payload")

    exported = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json").json()
    rows = list(
        csv.DictReader(
            StringIO(client.get(f"/api/v2/opportunities/{opportunity['id']}/export/csv").text)
        )
    )

    entry_json = next(item for item in exported["entries"] if item["id"] == entry["id"])
    assert [item["filename"] for item in entry_json["attachments"]] == ["proposal.pdf"]
    assert entry_json["attachments"][0]["sha256"] == attachment["sha256"]

    attachment_row = next(row for row in rows if row["row_type"] == "attachment")
    assert attachment_row["filename"] == "proposal.pdf"
    assert attachment_row["byte_size"] == str(attachment["byte_size"])
    assert attachment_row["parent_entry_id"] == str(entry["id"])
    assert attachment_row["author_name"] == "Owner"


def test_a_deleted_file_is_not_in_the_export(client: TestClient) -> None:
    """The export reads through the same helper the timeline does, so the
    `deleted_at` filter is the same one -- this is what pins that, since a
    second copy of the query is exactly where the filter goes missing."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent", "2026-09-04T13:00:00")
    kept = attach(client, entry["id"], "kept.pdf", b"%PDF-1.7 kept")
    removed = attach(client, entry["id"], "removed.pdf", b"%PDF-1.7 removed")
    assert client.delete(f"/api/v2/attachments/{removed['id']}").status_code == 204

    exported = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/json").json()
    entry_json = next(item for item in exported["entries"] if item["id"] == entry["id"])

    assert [item["id"] for item in entry_json["attachments"]] == [kept["id"]]


def test_pdf_export_produces_a_real_pdf(client: TestClient) -> None:
    # WeasyPrint needs native libraries that are only installed in the container;
    # missing them surfaces as an OSError from cffi, not an ImportError.
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"WeasyPrint native libraries unavailable: {exc}")

    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Discovery", "2026-09-01T09:00:00")

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/export/pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000


# --- Exporting a selection (milestone 3.0a, D-107) --------------------------


def create_named_opportunity(client: TestClient, name: str, account: str = "Acme") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": account,
            "value": "1000",
            "currency": "USD",
            "stage": "Prospecting",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_selection_export_writes_one_row_per_opportunity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_named_opportunity(client, "First")
    second = create_named_opportunity(client, "Second")
    create_named_opportunity(client, "Unselected")

    response = client.get(f"/api/v2/opportunities/export/csv?ids={first['id']},{second['id']}")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="opportunities.csv"'

    rows = list(csv.DictReader(StringIO(response.text)))
    # The record, not its timeline: a selection export is a spreadsheet of
    # deals, which is a different question from one deal's document (D-107).
    assert sorted(row["name"] for row in rows) == ["First", "Second"]
    assert rows[0]["owner_name"] == "Owner"
    assert set(rows[0]) == {
        "id",
        "name",
        "account_name",
        "value",
        "currency",
        "stage",
        "owner_name",
        "expected_close_date",
        "created_at",
        "updated_at",
    }


def test_selection_export_json_carries_the_same_records(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_named_opportunity(client, "First")

    response = client.get(f"/api/v2/opportunities/export/json?ids={opportunity['id']}")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="opportunities.json"'

    body = response.json()
    assert body["exported_at"].endswith("Z")
    assert [item["name"] for item in body["opportunities"]] == ["First"]
    assert body["opportunities"][0]["value"] == "1000"


def test_selection_export_omits_what_the_caller_cannot_read(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    shared = create_named_opportunity(client, "Shared")
    hidden = create_named_opportunity(client, "Hidden")
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    share_opportunity(shared["id"], viewer["id"], owner["id"], "viewer")

    response = client.get(f"/api/v2/opportunities/export/csv?ids={shared['id']},{hidden['id']}")
    # Absent rather than refused: a 404 naming one id out of a selection would
    # say whether it exists, which is what the 404-not-403 rule avoids.
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["name"] for row in rows] == ["Shared"]


def test_selection_export_neutralizes_spreadsheet_formulas(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_named_opportunity(client, '=HYPERLINK("https://attacker.example")')

    response = client.get(f"/api/v2/opportunities/export/csv?ids={opportunity['id']}")
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert rows[0]["name"].startswith("'=")


def test_selection_export_rejects_ids_it_cannot_read(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")

    assert client.get("/api/v2/opportunities/export/csv?ids=one,two").status_code == 400
    assert client.get("/api/v2/opportunities/export/csv?ids=").status_code == 400
    assert client.get("/api/v2/opportunities/export/csv").status_code == 422

    too_many = ",".join(str(number) for number in range(1, 402))
    assert client.get(f"/api/v2/opportunities/export/json?ids={too_many}").status_code == 400


def test_selection_export_needs_a_session(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_named_opportunity(client, "First")
    client.post("/api/v2/auth/logout")

    assert (
        client.get(f"/api/v2/opportunities/export/csv?ids={opportunity['id']}").status_code == 401
    )
