"""Attachments on a timeline entry (milestone 4.3, ADR 0008, `FEATURES.md` §6).

The authorization matrix covers who may call each route; this file is about
what the routes do. Five properties carry the milestone, and they are the
roadmap's own acceptance criteria plus the two decisions this milestone took:

- a viewer on a shared deal can download, and somebody not on it gets 404,
- a `.exe` renamed `.pdf` is refused on its bytes, not on its name,
- identical uploads are one file on disk (**D-147**, ADR 0008's dedupe),
- an attachment is content, so deleting one is soft, audited and undoable --
  and the **bytes stay** when the row goes (**D-149**),
- the blobs are never reachable as static files; this route is the only way
  out of the volume.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_tasks import create_opportunity, login, logout, share, signup
from test_timeline import create_entry

from app.attachment_utils import attachments_by_entry_id
from app.database import db_connection
from app.settings import settings
from app.uploads import attachments_dir, content_digest

PDF = b"%PDF-1.7\n" + b"proposal" * 8
EXECUTABLE = b"MZ\x90\x00" + b"\x00" * 32


def upload(
    client: TestClient,
    entry_id: int,
    data: bytes = PDF,
    filename: str = "proposal.pdf",
    content_type: str = "application/pdf",
) -> dict:
    response = client.post(
        f"/api/v2/timeline/{entry_id}/attachments",
        files={"file": (filename, data, content_type)},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def timeline_entry(client: TestClient, opportunity_id: int, entry_id: int) -> dict:
    items = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline").json()["items"]
    return next(item for item in items if item["id"] == entry_id)


def stored_files() -> list[Path]:
    root = attachments_dir()
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.exists() else []


def test_a_file_is_read_with_the_entry_it_is_attached_to(client: TestClient) -> None:
    """An entry's attachments travel with it, the way a note's comments do: no
    list route of its own, so drawing a page of entries is one read."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    attachment = upload(client, entry["id"], filename="  Q3 proposal.pdf")

    assert attachment["filename"] == "Q3 proposal.pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["byte_size"] == len(PDF)
    assert attachment["sha256"] == content_digest(PDF)
    assert attachment["uploader_name"] == "Owner"

    entry_read_back = timeline_entry(client, opportunity["id"], entry["id"])
    assert [item["id"] for item in entry_read_back["attachments"]] == [attachment["id"]]


def test_the_bytes_decide_the_type_not_the_name(client: TestClient) -> None:
    """The roadmap's acceptance criterion: a `.exe` renamed `.pdf` and posted
    as `application/pdf` is refused. Nothing the client declared is consulted.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    response = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("report.pdf", EXECUTABLE, "application/pdf")},
    )

    assert response.status_code == 415
    assert stored_files() == []


def test_a_refusal_names_itself_in_the_envelope(client: TestClient, monkeypatch) -> None:
    """413 and 415 are the two statuses this app had never answered before it
    took a file, so `errors.ERROR_CODES` had no name for either and both came
    back as `internal_error` -- telling the client the server broke when the
    file was simply too big or of the wrong type. `lib/api.ts` branches on
    `code`, which is why the name matters as much as the status.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    wrong_type = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("report.pdf", EXECUTABLE, "application/pdf")},
    )
    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    too_big = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("big.pdf", PDF + b"\x00" * 256, "application/pdf")},
    )

    assert wrong_type.status_code == 415
    assert wrong_type.json()["error"]["code"] == "unsupported_media_type"
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "payload_too_large"


def test_an_oversized_file_is_refused(client: TestClient, monkeypatch) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    monkeypatch.setattr(settings, "max_upload_bytes", 64)

    response = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("big.pdf", PDF + b"\x00" * 256, "application/pdf")},
    )

    assert response.status_code == 413


def test_identical_uploads_are_one_file_and_two_attachments(client: TestClient) -> None:
    """Content addressing (ADR 0008): the same contract attached to two entries
    is two rows and one file on disk. The digest is deliberately not the row's
    identity, which is why the table carries no unique index on it."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    first_entry = create_entry(client, opportunity["id"], title="Proposal sent")
    second_entry = create_entry(client, opportunity["id"], title="Contract sent")

    first = upload(client, first_entry["id"])
    second = upload(client, second_entry["id"], filename="signed-contract.pdf")

    assert first["id"] != second["id"]
    assert first["sha256"] == second["sha256"]
    assert [path.name for path in stored_files()] == [first["sha256"]]
    # The stored path is the digest sharded by its first two characters, and
    # nothing in it comes from either filename.
    assert stored_files()[0].parent.name == first["sha256"][:2]


def test_a_viewer_can_download_and_an_outsider_cannot(client: TestClient) -> None:
    """The roadmap's other acceptance criterion. Downloading is a read of the
    opportunity, so a viewer may; absence of access is 404, not 403."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "viewer@example.com", "Viewer")
    signup(client, "outsider@example.com", "Outsider")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])
    share(client, opportunity["id"], "viewer@example.com", "viewer")
    logout(client)

    login(client, "viewer@example.com")
    allowed = client.get(f"/api/v2/attachments/{attachment['id']}/download")
    logout(client)
    login(client, "outsider@example.com")
    refused = client.get(f"/api/v2/attachments/{attachment['id']}/download")

    assert allowed.status_code == 200
    assert allowed.content == PDF
    assert refused.status_code == 404


def test_a_download_is_forced_and_never_sniffed(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"], filename="réunion.pdf")

    response = client.get(f"/api/v2/attachments/{attachment['id']}/download")

    assert response.headers["content-disposition"].startswith("attachment; ")
    assert "filename*=UTF-8''r%C3%A9union.pdf" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"] == "application/pdf"


def test_a_viewer_cannot_attach_a_file(client: TestClient) -> None:
    """Uploading is adding, which is the gate a note and a comment already
    have: editors may, viewers may not.

    The file here is a *valid* one, which is the point: the permission answer
    comes before the bytes are looked at, so a reader with no write access is
    told about their access rather than about their file.
    """
    signup(client, "owner@example.com", "Owner")
    signup(client, "viewer@example.com", "Viewer")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    share(client, opportunity["id"], "viewer@example.com", "viewer")
    logout(client)
    login(client, "viewer@example.com")

    response = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 403
    assert stored_files() == []


def test_the_deal_is_told_a_document_arrived(client: TestClient) -> None:
    """A file landing on a shared deal is activity on it, told the way a note
    is -- one `shared_activity` notification naming the file."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    share(client, opportunity["id"], "editor@example.com", "editor")
    logout(client)

    login(client, "editor@example.com")
    upload(client, entry["id"])
    logout(client)
    login(client, "owner@example.com")
    notifications = client.get("/api/v2/notifications?type=shared_activity").json()["items"]

    assert [
        item["payload"]["title"]
        for item in notifications
        if item["payload"]["source_type"] == "attachment"
    ] == ["New attachment: proposal.pdf"]


def test_deleting_an_attachment_keeps_the_file_and_offers_it_back(client: TestClient) -> None:
    """Soft, audited and undoable like every other delete -- and the bytes stay
    on disk (**D-149**), because the row can come back and the digest may be
    another entry's attachment as well."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])

    assert client.delete(f"/api/v2/attachments/{attachment['id']}").status_code == 204

    assert timeline_entry(client, opportunity["id"], entry["id"])["attachments"] == []
    assert client.get(f"/api/v2/attachments/{attachment['id']}/download").status_code == 404
    assert [path.name for path in stored_files()] == [attachment["sha256"]]
    with db_connection() as connection:
        row = connection.execute(
            "SELECT deleted_at FROM attachments WHERE id = ?",
            (attachment["id"],),
        ).fetchone()
    assert row["deleted_at"] is not None

    assert client.post(f"/api/v2/attachments/{attachment['id']}/restore").status_code == 204

    restored = timeline_entry(client, opportunity["id"], entry["id"])["attachments"]
    assert [item["id"] for item in restored] == [attachment["id"]]
    assert client.get(f"/api/v2/attachments/{attachment['id']}/download").content == PDF

    actions = [
        item["action"]
        for item in client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()[
            "items"
        ]
    ]
    assert actions == ["attachment_deleted", "attachment_restored"]


def test_only_the_uploader_or_the_owner_can_remove_a_file(client: TestClient) -> None:
    """D-005's rule, the one every other delete follows: an editor may attach
    freely and may not remove a colleague's document."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])
    share(client, opportunity["id"], "editor@example.com", "editor")
    logout(client)

    login(client, "editor@example.com")
    refused = client.delete(f"/api/v2/attachments/{attachment['id']}")
    own = upload(client, entry["id"], data=b"editor notes", filename="notes.txt")
    own_delete = client.delete(f"/api/v2/attachments/{own['id']}")

    assert refused.status_code == 403
    assert own_delete.status_code == 204


def test_a_refused_caller_is_told_about_their_access_not_their_file(
    client: TestClient,
) -> None:
    """A viewer posting something the allowlist would refuse gets 403, not 415.

    Order of checks, asserted rather than assumed: the role is resolved first,
    so nothing is hashed or stored for somebody who may not write, and the
    answer does not depend on what they sent.
    """
    signup(client, "owner@example.com", "Owner")
    signup(client, "viewer@example.com", "Viewer")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    share(client, opportunity["id"], "viewer@example.com", "viewer")
    logout(client)
    login(client, "viewer@example.com")

    response = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("setup.pdf", EXECUTABLE, "application/pdf")},
    )

    assert response.status_code == 403


def test_restoring_something_that_is_not_deleted_is_a_404(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])

    assert client.post(f"/api/v2/attachments/{attachment['id']}/restore").status_code == 404


@pytest.mark.parametrize("level", ["entry", "opportunity"])
def test_an_attachment_is_a_level_of_the_delete_cascade(client: TestClient, level: str) -> None:
    """A file is read through its entry and has nowhere else to appear, so it
    goes with the entry and with the deal -- and comes back with either.

    Asserted against the row's own `deleted_at` rather than against the file
    being absent from a read: every read filters the deleted parent too, so
    that assertion would pass with the cascade removed (the mistake 4.1's first
    cascade test made).
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])
    path = (
        f"/api/v2/timeline/{entry['id']}"
        if level == "entry"
        else f"/api/v2/opportunities/{opportunity['id']}"
    )

    assert client.delete(path).status_code == 204
    assert deleted_at_of(attachment["id"]) is not None

    assert client.post(f"{path}/restore").status_code == 204
    assert deleted_at_of(attachment["id"]) is None


def deleted_at_of(attachment_id: int) -> str | None:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT deleted_at FROM attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
    return row["deleted_at"]


def test_a_file_the_volume_has_lost_answers_404(client: TestClient) -> None:
    """A real state, not a hypothetical one: the database is backed up (ADR
    0011) and the blobs are not yet (Phase R, R.5), so a restored database can
    name files this volume has never held. Saying so beats a 500 from a
    response that has already begun.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])
    stored_files()[0].unlink()

    response = client.get(f"/api/v2/attachments/{attachment['id']}/download")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Attachment file is missing"


def test_an_entry_on_another_deal_cannot_be_attached_to(client: TestClient) -> None:
    """A 404 rather than a 403: an entry the caller has no access to is one
    they may not know exists."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "outsider@example.com", "Outsider")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    logout(client)
    login(client, "outsider@example.com")

    response = client.post(
        f"/api/v2/timeline/{entry['id']}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404
    assert stored_files() == []


def test_an_entry_that_does_not_exist_is_a_404(client: TestClient) -> None:
    """Checked before the role is resolved, because there is no opportunity to
    resolve a role against -- and it is the same 404 a deleted entry gets."""
    signup(client, "owner@example.com", "Owner")
    create_opportunity(client)

    response = client.post(
        "/api/v2/timeline/9999/attachments",
        files={"file": ("notes.txt", b"nowhere to go", "text/plain")},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Timeline entry not found"


def test_asking_about_no_entries_asks_the_database_nothing(client: TestClient) -> None:
    """`attachments_by_entry_id` is read by the timeline, which never calls it
    with an empty page -- and by the export, which may. An empty `IN ()` is a
    SQL syntax error rather than an empty result, so the guard is the
    function's contract and not a defensive branch."""
    signup(client, "owner@example.com", "Owner")

    with db_connection() as connection:
        assert attachments_by_entry_id(connection, []) == {}


def test_the_blobs_are_never_reachable_as_static_files(client: TestClient) -> None:
    """ADR 0008's rule, and the roadmap's acceptance criterion: `/data` is
    never a static path, so this route is the only way bytes leave the volume.
    Every one of these paths is answered by the SPA fallback or a 404, never
    by the file.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    attachment = upload(client, entry["id"])
    digest = attachment["sha256"]

    for path in (
        f"/attachments/{digest[:2]}/{digest}",
        f"/data/attachments/{digest[:2]}/{digest}",
        f"/api/v2/attachments/{digest[:2]}/{digest}",
        f"/_next/../attachments/{digest[:2]}/{digest}",
    ):
        response = client.get(path)
        assert PDF not in response.content, f"{path} served the stored file"
