"""Development seed data (brief §4.7, Makefile target `make seed`).

The seed drives the real HTTP API rather than writing rows directly, so every
side effect the application owns — system timeline entries, audit log rows,
notifications, note versions — comes out right without this file restating any
of that logic. That also makes it a standing integration check: if a route's
contract changes, seeding breaks loudly.

It lives outside the `app` package on purpose: it depends on `TestClient`,
which is a development dependency, and nothing in the shipped image should
import it.

Scale here is deliberately small — enough to exercise every shipped feature and
every permission relationship by hand in a minute. The large dataset the
performance budgets need is Phase R's concern (brief §8).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.database import db_connection, initialize_database, sqlite_path_from_url
from app.main import app
from app.security import CSRF_COOKIE_NAME, SAFE_METHODS
from app.settings import settings

DEMO_PASSWORD = "opptrail-demo-123"

ALEX = "alex@opptrail.test"
BLAIR = "blair@opptrail.test"
CASEY = "casey@opptrail.test"
DANA = "dana@opptrail.test"

USERS: list[tuple[str, str]] = [
    (ALEX, "Alex Rivera"),
    (BLAIR, "Blair Osei"),
    (CASEY, "Casey Lindqvist"),
    (DANA, "Dana Whitfield"),
]


class SeedClient(TestClient):
    """Echoes the CSRF cookie the way the browser does (`app/security.py`)."""

    def request(self, method: str, url: Any, **kwargs: Any) -> Any:
        if method.upper() not in SAFE_METHODS:
            if CSRF_COOKIE_NAME not in self.cookies:
                super().request("GET", "/api/health")
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-CSRF-Token", self.cookies[CSRF_COOKIE_NAME])
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@dataclass
class Session:
    client: SeedClient
    user_id: int
    email: str


def days_ago(days: float, hour: int = 10, minute: int = 0) -> str:
    """A `datetime-local` string the API will canonicalize.

    Everything is expressed relative to now so the stalled-opportunity flag and
    the "recent activity" ordering stay true whenever the seed is run, rather
    than going stale against hardcoded dates.
    """
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.replace(hour=hour, minute=minute).strftime("%Y-%m-%dT%H:%M")


def check(response: Any, what: str) -> Any:
    if response.status_code >= 400:
        raise SystemExit(f"Seeding failed at {what}: {response.status_code} {response.text}")
    return response


def sign_up(email: str, name: str) -> Session:
    client = SeedClient(app)
    client.__enter__()
    response = check(
        client.post(
            "/api/v2/auth/signup",
            json={"email": email, "password": DEMO_PASSWORD, "name": name},
        ),
        f"signup for {email}",
    )
    return Session(client=client, user_id=int(response.json()["user"]["id"]), email=email)


def create_opportunity(session: Session, **fields: Any) -> int:
    response = check(
        session.client.post("/api/v2/opportunities", json=fields),
        f"creating {fields.get('name')!r}",
    )
    return int(response.json()["id"])


def add_entry(session: Session, opportunity_id: int, **fields: Any) -> int:
    response = check(
        session.client.post(f"/api/v2/opportunities/{opportunity_id}/timeline", json=fields),
        f"adding an entry to opportunity {opportunity_id}",
    )
    return int(response.json()["id"])


def add_note(session: Session, entry_id: int, body: str) -> dict[str, Any]:
    """The created note, not just its id: an edit needs the `updated_at` it is
    written against (ADR 0003's guard on `PATCH /api/v2/notes/{id}`).
    """
    response = check(
        session.client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": body}),
        f"adding a note to entry {entry_id}",
    )
    note: dict[str, Any] = response.json()
    return note


def edit_note(session: Session, note: dict[str, Any], body: str) -> dict[str, Any]:
    """Rewrite a note, echoing back the `updated_at` the caller last read.

    That is the whole edit guard: the server answers 409 if the note moved in
    between, which is what stops two people on one deal overwriting each other
    (ADR 0003's conflict model).
    """
    response = check(
        session.client.patch(
            f"/api/v2/notes/{note['id']}",
            json={"body": body, "updated_at": note["updated_at"]},
        ),
        f"editing note {note['id']}",
    )
    edited: dict[str, Any] = response.json()
    return edited


def add_comment(
    session: Session,
    note_id: int,
    body: str,
    parent_id: int | None = None,
) -> int:
    payload: dict[str, object] = {"body": body}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = check(
        session.client.post(f"/api/v2/notes/{note_id}/comments", json=payload),
        f"commenting on note {note_id}",
    )
    return int(response.json()["id"])


def resolve_thread(session: Session, comment_id: int) -> None:
    check(
        session.client.post(f"/api/v2/comments/{comment_id}/resolve"),
        f"resolving the thread on comment {comment_id}",
    )


def react(session: Session, comment_id: int, emoji: str) -> None:
    check(
        session.client.post(f"/api/v2/comments/{comment_id}/reactions", json={"emoji": emoji}),
        f"reacting to comment {comment_id}",
    )


def watch(session: Session, opportunity_id: int) -> None:
    check(
        session.client.post(f"/api/v2/opportunities/{opportunity_id}/watch"),
        f"watching opportunity {opportunity_id}",
    )


def share(session: Session, opportunity_id: int, email: str, role: str) -> None:
    check(
        session.client.post(
            f"/api/v2/opportunities/{opportunity_id}/shares",
            json={"email": email, "role": role},
        ),
        f"sharing opportunity {opportunity_id} with {email}",
    )


def save_view(session: Session, **fields: Any) -> int:
    response = check(
        session.client.post("/api/v2/saved-views", json=fields),
        f"saving the view {fields.get('name')!r}",
    )
    return int(response.json()["id"])


def backdate_opportunity(opportunity_id: int, days: float) -> None:
    """Move an opportunity and its auto-generated "created" entry into the past.

    This is the one place the seed writes SQL instead of calling the API, and
    the reason is an invariant rather than an oversight: `created_at` is
    immutable and system timeline entries cannot be edited through any route
    (brief §2.5, §2.6). Without moving them, every seeded opportunity has
    activity stamped "now", so the stalled flag — 14 days without activity,
    `routes_opportunities.is_opportunity_stalled` — could never be demonstrated
    on fresh demo data.
    """
    moment = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_connection() as connection:
        connection.execute(
            "UPDATE opportunities SET created_at = ?, updated_at = ? WHERE id = ?",
            (moment, moment, opportunity_id),
        )
        connection.execute(
            """
            UPDATE timeline_entries
            SET event_timestamp = ?, created_at = ?
            WHERE opportunity_id = ? AND system_generated = 1 AND type = 'other'
            """,
            (moment, moment, opportunity_id),
        )
        connection.commit()


def database_is_empty() -> bool:
    with db_connection() as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    return int(count) == 0


def seed() -> None:
    alex = sign_up(*USERS[0])
    blair = sign_up(*USERS[1])
    casey = sign_up(*USERS[2])
    # Dana has access to nothing: the negative case, by hand. Milestone 3.3a
    # gives them one exception -- watching Northwind below, which is reachable
    # with no share at all (`docs/FEATURES.md` §7).
    dana = sign_up(*USERS[3])

    # 1. The fully populated opportunity: every entry type, both share roles,
    #    an edited note, a threaded comment, and a mention notification.
    northwind = create_opportunity(
        alex,
        name="Northwind platform rollout",
        account_name="Northwind Traders",
        value="185000",
        currency="USD",
        stage="Qualification",
        expected_close_date=days_ago(-45)[:10],
    )
    share(alex, northwind, BLAIR, "editor")
    share(alex, northwind, CASEY, "viewer")

    intro = add_entry(
        alex,
        northwind,
        type="call",
        title="Intro call with the VP of Operations",
        body="Thirty minutes. Current tooling is three spreadsheets and a shared inbox.",
        event_timestamp=days_ago(21, hour=9),
    )
    # Milestone 3.1: a note is written in a rich composer and stored as
    # Markdown, so the demo data carries the structure that composer produces
    # rather than one line of plain text.
    add_note(
        alex,
        intro,
        "Budget holder is the **COO**, not the VP.\n"
        "\n"
        "Next call needs:\n"
        "\n"
        "- the COO in the room\n"
        "- the permissions model written down\n"
        "\n"
        "- [x] recap sent\n"
        "- [ ] security summary",
    )

    demo = add_entry(
        blair,
        northwind,
        type="demo",
        title="Product demo for the operations team",
        body="Eight attendees. Timeline view landed well; they asked about permissions twice.",
        event_timestamp=days_ago(14, hour=14),
        follow_up_date=days_ago(-3)[:10],
    )
    demo_note = add_note(
        blair,
        demo,
        f"Permissions questions came from the security lead. @{ALEX} can you send the model?",
    )
    # Milestone 3.3: the two shapes a discussion has. One thread is answered
    # and closed; one is still open, so the demo shows both states rather
    # than only the tidy one.
    permissions_question = add_comment(
        alex,
        demo_note["id"],
        "Sent the permissions summary. They want viewer-only for finance.",
    )
    add_comment(
        blair,
        demo_note["id"],
        "Confirmed with the security lead - viewer-only is enough.",
        parent_id=permissions_question,
    )
    resolve_thread(alex, permissions_question)
    add_comment(blair, demo_note["id"], "Still open: who signs off on the pilot clause?")

    # Milestone 3.3a: reactions read as toggle state on a comment. Casey is a
    # viewer here and cannot react (require_timeline_write), so it is Alex and
    # Blair who do: both thumbs-up the same comment, and Blair also adds eyes
    # -- one person, two emoji. Dana -- shared on nothing -- follows Northwind
    # anyway, which is the capability `FEATURES.md` §7 names and the rest of
    # the tour's access checks deliberately do not grant her.
    react(alex, permissions_question, "👍")
    react(blair, permissions_question, "👍")
    react(blair, permissions_question, "👀")
    watch(dana, northwind)

    proposal = add_entry(
        alex,
        northwind,
        type="proposal",
        title="Proposal sent",
        body="Three-year term, 185k ARR, 60-day pilot clause.",
        event_timestamp=days_ago(6, hour=16),
    )
    revised = add_note(alex, proposal, "Sent the first cut with list pricing.")
    edit_note(
        alex,
        revised,
        "Sent the first cut with list pricing, then revised to a 8% discount.",
    )

    add_entry(
        blair,
        northwind,
        type="email",
        title="Legal sent redlines",
        body="Two changes to the data-processing addendum.",
        event_timestamp=days_ago(2, hour=11),
    )

    # Milestone 2.6's three new entry types, each with its own icon.
    add_entry(
        alex,
        northwind,
        type="site_visit",
        title="Toured the Northwind warehouse",
        body="Saw the manual intake process the timeline view would replace.",
        event_timestamp=days_ago(17, hour=11),
    )
    add_entry(
        blair,
        northwind,
        type="objection",
        title="Procurement pushed back on price",
        body="Wants a 15% discount for a three-year term instead of two.",
        event_timestamp=days_ago(9, hour=15),
    )
    add_entry(
        alex,
        northwind,
        type="competitor_intel",
        title="Evaluating a rival vendor in parallel",
        body="Their champion mentioned a bake-off against a spreadsheet-plus-CRM combo.",
        event_timestamp=days_ago(5, hour=10),
    )

    # Stage change: the system timeline entry is written by the API, not here.
    check(
        alex.client.patch(f"/api/v2/opportunities/{northwind}", json={"stage": "Negotiation"}),
        "advancing Northwind to Negotiation",
    )

    # Milestone 2.10's edit history, on the case that prompted it: a deal
    # whose value moves with nothing but the history to say what it was.
    check(
        alex.client.patch(f"/api/v2/opportunities/{northwind}", json={"value": "162000"}),
        "revising Northwind's value down after the discount",
    )
    check(
        alex.client.patch(
            f"/api/v2/timeline/{proposal}",
            json={"body": "Three-year term, 162k ARR after the 8% discount, 60-day pilot clause."},
        ),
        "correcting the proposal entry, which keeps the figure it replaced",
    )

    # 2. An ordinary, healthy opportunity with nothing special about it.
    contoso = create_opportunity(
        alex,
        name="Contoso pilot",
        account_name="Contoso",
        value="42000",
        currency="USD",
        stage="Needs Analysis",
        expected_close_date=days_ago(-70)[:10],
    )
    add_entry(
        alex,
        contoso,
        type="meeting",
        title="Discovery workshop",
        body="Mapped their approval chain. Two blockers, both procedural.",
        event_timestamp=days_ago(4, hour=13),
    )

    # 3. Stalled: nothing has happened for well over the 14-day threshold, so
    #    the dashboard flag has something to show.
    globex = create_opportunity(
        alex,
        name="Globex renewal",
        account_name="Globex",
        value="96000",
        currency="EUR",
        stage="Proposal",
        expected_close_date=days_ago(-20)[:10],
    )
    share(alex, globex, CASEY, "viewer")
    add_entry(
        alex,
        globex,
        type="email",
        title="Renewal terms sent",
        body="No reply since.",
        event_timestamp=days_ago(41, hour=10),
    )
    backdate_opportunity(globex, days=64)

    # 4. Owned by someone else and shared back, so Alex's list is not uniform.
    initech = create_opportunity(
        blair,
        name="Initech expansion",
        account_name="Initech",
        value="58000",
        currency="USD",
        stage="Closed Won",
        expected_close_date=days_ago(9)[:10],
    )
    share(blair, initech, ALEX, "viewer")
    won = add_entry(
        blair,
        initech,
        type="contract",
        title="Countersigned",
        body="Two-year term. Kickoff scheduled.",
        event_timestamp=days_ago(9, hour=15),
    )
    add_note(blair, won, "Finance has the PO. Handover call booked for next week.")

    # 5. A deletion, so the owner-only audit log is not empty on a fresh seed.
    umbrella = create_opportunity(
        alex,
        name="Umbrella discovery",
        account_name="Umbrella Corp",
        value="12000",
        currency="USD",
        stage="Prospecting",
    )
    scratch = add_entry(
        alex,
        umbrella,
        type="other",
        title="Inbound form submission",
        body="Came through the website.",
        event_timestamp=days_ago(3, hour=8),
    )
    removed_note = add_note(alex, scratch, "Duplicate of the Contoso lead - removing.")
    check(
        alex.client.delete(f"/api/v2/notes/{removed_note['id']}"),
        "soft-deleting a note",
    )

    # And a deletion that was taken back (milestone 2.4b), so the log shows
    # both halves of an undo and the entry it took is readable again.
    reinstated = add_entry(
        alex,
        umbrella,
        type="call",
        title="Qualification call",
        body="Budget is real; timeline is not.",
        event_timestamp=days_ago(2, hour=11),
    )
    check(
        alex.client.delete(f"/api/v2/timeline/{reinstated}"),
        "soft-deleting a timeline entry",
    )
    check(
        alex.client.post(f"/api/v2/timeline/{reinstated}/restore"),
        "restoring the timeline entry",
    )

    # 6. One of Alex's notifications marked read, so the inbox rework
    #    (milestone 1.7) has both states to show without a click: history
    #    that survives being read, next to what is still unread.
    alex_notifications = check(
        alex.client.get("/api/v2/notifications"), "reading Alex's notifications"
    ).json()["items"]
    share_added = next(n for n in alex_notifications if n["type"] == "share_added")
    check(
        alex.client.patch(f"/api/v2/notifications/{share_added['id']}/read"),
        "marking Alex's share notification read",
    )

    # 7. Saved views (milestone 2.2), so both surfaces that carry a
    #    filter/sort model open with something to apply. The filter keys are
    #    the view state's own field names (`frontend/lib/domain.ts`), which is
    #    also what the URL carries — one shape, no conversion.
    save_view(
        alex,
        name="Late-stage pipeline",
        entity="opportunities",
        filters={"stage": "Negotiation", "sortField": "value", "sortDirection": "desc"},
        group_by="stage",
        is_shared=True,
    )
    save_view(
        alex,
        name="Newest first",
        entity="timeline",
        filters={"order": "desc"},
    )
    save_view(
        blair,
        name="Blair's proposals",
        entity="opportunities",
        filters={"stage": "Proposal"},
        group_by="stage",
    )

    # 8. A curated view (milestone 3.0a): "add to view" on the bulk action
    #    bar writes the selection into the view's filters, because a saved
    #    view is a filter set rather than a folder (D-106). Seeded through
    #    the real endpoint, so what the demo shows is what the button does.
    shortlist = save_view(
        alex,
        name="Alex's shortlist",
        entity="opportunities",
        filters={},
        group_by="stage",
    )
    check(
        alex.client.post(
            "/api/v2/opportunities/bulk",
            json={
                "ids": [northwind, globex],
                "action": "add_to_view",
                "view_id": shortlist,
            },
        ),
        "pinning two opportunities into a saved view",
    )

    for session in (alex, blair, casey):
        session.client.__exit__(None, None, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="seed even though the database already has users (adds a second set)",
    )
    arguments = parser.parse_args(argv)

    database_path = sqlite_path_from_url(settings.database_url)
    initialize_database()

    if not database_is_empty() and not arguments.force:
        print(
            f"{database_path} already has users; refusing to seed on top of it.\n"
            "Delete the file, or pass --force to add a second set of demo data.",
            file=sys.stderr,
        )
        return 1

    seed()

    print(f"Seeded {database_path}.")
    print(f"Sign in with any of these; the password is {DEMO_PASSWORD!r}:")
    for email, name in USERS:
        print(f"  {email:26} {name}")
    print(
        "\n  Alex owns four opportunities and can see a fifth (Initech) as a viewer.\n"
        "  Blair is an editor on Northwind and owns Initech.\n"
        "  Casey is a viewer on Northwind and Globex - every write is refused.\n"
        "  Dana has access to nothing, which is the case worth checking by hand.\n"
        "  Globex renewal is stalled; Northwind has a system stage-change entry,\n"
        "  a mention notification for Alex, an edited note and a soft-deleted note,\n"
        "  plus milestone 2.6's three newest entry types -- site visit, objection,\n"
        "  competitor intel -- each with its own icon on the timeline.\n"
        "  Umbrella discovery holds an undone deletion: its owner-only audit log\n"
        "  has timeline_entry_deleted next to timeline_entry_restored, and the\n"
        "  Qualification call entry is back on the timeline.\n"
        "\n"
        "  Search (GET /api/v2/search?q=finance, or the Search link in the top\n"
        "  bar, which opens /search?q=finance) is scoped to what the caller can\n"
        "  read: Alex and Blair each get two hits in two different opportunities,\n"
        "  Casey gets only the Northwind one, and Dana gets nothing at all.\n"
        "\n"
        "  Alex's notification bell (or GET /api/v2/notifications) shows the\n"
        "  inbox rework: a mention and a shared-activity notification still\n"
        "  unread, next to the Initech share notification already marked read\n"
        "  and still visible — the dead end milestone 1.7 fixed. Filter by\n"
        "  type in the panel, or mark everything read at once.\n"
        "\n"
        "  Saved views (milestone 2.2) sit above the board and above an open\n"
        "  timeline. Alex has 'Late-stage pipeline' over the board, shared, so\n"
        "  Blair sees it too beside their own private 'Blair's proposals';\n"
        "  'Newest first' reverses one opportunity's reading order. Applying\n"
        "  one writes the filter into the URL, so the address bar is the view:\n"
        "  copy it, reload it, or send it to someone with access.\n"
        "\n"
        "  The pipeline (milestone 2.7) draws that same list two ways. Drag\n"
        "  Northwind from Negotiation to Proposal and a stage-change entry\n"
        "  appears on its timeline; the card's stage control and the [ and ]\n"
        "  keys do the same move without a mouse. The Board/List switch beside\n"
        "  the title is in the URL too (?opportunities.view=list), so a saved\n"
        "  view remembers which renderer it was saved in. Alex owns four of\n"
        "  the five, so Initech - where Alex is a viewer - is the card with no\n"
        "  stage control on it.\n"
        "\n"
        "  Edit history (milestone 2.10) is owner-only, so sign in as Alex, and\n"
        "  since milestone 3.1c it is read in one place rather than three\n"
        "  (D-121): open Northwind and press History beside the exports. The\n"
        "  dialog is 'Activity and history' - the creation, the stage change\n"
        "  and the sharing as the timeline records them, with 'changed Value on\n"
        "  this opportunity' and the note and entry edits in the same list.\n"
        "  Open the Value row and it shows 185,000 at Qualification becoming\n"
        "  162,000, with Restore on the version that edit replaced; the\n"
        "  Proposal sent entry and the edited note on it open the same way.\n"
        "  Umbrella discovery shows the audit half - an entry deleted and\n"
        "  restored - in among its own. The button is offered to Blair and\n"
        "  Casey too; what they are given is the events their role may already\n"
        "  read, which is the system entries, and none of the edit rows.\n"
        "\n"
        "  The bulk action bar (milestones 2.4c and 3.0a) appears in place of\n"
        "  the filter bar as soon as something is checked - the checkbox on a\n"
        "  card, x, or shift-click for a range. All five actions are there:\n"
        "  change stage, assign owner, add to view, export and delete. Alex's\n"
        "  shortlist is what 'add to view' leaves behind - Northwind and\n"
        "  Globex pinned into a saved view, which shows only those two until\n"
        "  Show all clears it. Export CSV and Export JSON download the checked\n"
        "  deals as a spreadsheet of records rather than one deal's document.\n"
        "  Assign owner hands them over: type blair@opptrail.test, and Alex\n"
        "  stays on the deal as an editor rather than losing it, with the\n"
        "  handover on the timeline and in the owner-only audit log.\n"
        "\n"
        "  The calendar's follow-up layer (milestone 3.0b) draws beside the\n"
        "  close-date chips: switch the dashboard to Calendar and Northwind's\n"
        "  demo entry shows up three days out, a reminder rather than a deal,\n"
        "  linking back to Northwind's own timeline. GET\n"
        "  /api/v2/timeline/follow-ups is scoped the same way search is -\n"
        "  Casey sees it because they can read Northwind, and Dana sees\n"
        "  nothing at all.\n"
        "\n"
        "  Rich content (milestone 3.1) is on Northwind's first entry: the\n"
        "  note under Intro call renders a bold figure, a bullet list and a\n"
        "  two-item checklist with one box ticked, because it is stored as\n"
        "  Markdown and always was - nothing migrated. Press Edit on it and\n"
        "  the same note opens in the composer as a list rather than as\n"
        "  asterisks; Add note and Add comment open the same editor, one\n"
        "  control until you write in them. Since milestone 3.5 the PDF\n"
        "  export renders these same bodies as markup rather than as\n"
        "  literal asterisks - the other half of requirement 17. It is\n"
        "  the one line of this tour that needs the container, since\n"
        "  WeasyPrint's native libraries are absent on a macOS host.\n"
        "\n"
        "  The composer's three triggers (milestone 3.2) are typed rather than\n"
        "  clicked. In any composer on Northwind, '@bla' offers Blair by name\n"
        "  and writes the address the notification is delivered by - which is\n"
        "  requirement 13's discoverability, since nobody types a colleague's\n"
        "  address from memory; '/' offers the blocks, including the code block\n"
        "  and divider no button carries; and '#procure' offers this deal's own\n"
        "  entries and links to the one chosen, which opens the timeline with\n"
        "  that entry marked. Dana, who shares nothing, is on nobody's '@'\n"
        "  list: GET /api/v2/opportunities/1/members answers the owner and the\n"
        "  shares, and only to someone who can already read the deal.\n"
        "\n"
        "  Threaded comments (milestone 3.3) are on the demo entry's note.\n"
        "  Alex's question about permissions has Blair's answer under it and\n"
        "  is marked resolved, so it reads as one line - 'Resolved by Alex\n"
        "  Rivera' with Show underneath it - while Blair's question about the\n"
        "  pilot clause is still open and still visible. Reply sits on the\n"
        "  thread rather than on each message: replies are one level deep on\n"
        "  purpose. Sign in as Blair and Resolve is offered on their own\n"
        "  thread but not on Alex's, which is the author-or-owner rule the\n"
        "  rest of the timeline already uses; Casey, a viewer, is offered\n"
        "  neither Reply nor Resolve.\n"
        "\n"
        "  Reactions and watchers (milestone 3.3a) are the other half of the\n"
        "  roadmap's line 3.3 split off. Alex's resolved permissions question\n"
        "  carries a thumbs-up from Alex and Blair, plus an eyes reaction from\n"
        "  Blair - GET /api/v2/notes/.../comments returns them on the comment\n"
        "  they belong to, root or reply alike, and reacting twice with the\n"
        "  same emoji is a no-op rather than a second row. Casey, a viewer,\n"
        "  cannot react at all - the same require_timeline_write rule that\n"
        "  keeps them from writing anything else. Dana, shared on nothing,\n"
        "  follows Northwind anyway - POST /api/v2/opportunities/1/watch\n"
        "  answers 200 for them the way it does for anyone signed in, which\n"
        "  is `FEATURES.md` §7's \"follow an opportunity you are not shared\n"
        '  on"; they still get 404 reading Northwind itself, since watching\n'
        "  grants no access. Sign in as Alex and GET\n"
        "  /api/v2/opportunities/1/watchers - owner-only, like the share list\n"
        "  beside it - names Dana as the one watcher.\n"
        "\n"
        "  Live updates and the note edit guard (milestone 3.4) are the one\n"
        "  thing here that needs two windows rather than seeded rows. Open\n"
        "  Northwind as Alex in one and as Blair in the other: an entry\n"
        "  added in either appears in the other within a second, because\n"
        "  GET /api/v2/opportunities/1/events pushes an invalidation and\n"
        "  the client refetches rather than being sent the row. Then press\n"
        "  Edit on the same note in both windows and save in one: the\n"
        "  second save is refused with a 409, keeps the draft, and offers\n"
        "  'Discard my edit' instead of overwriting the first silently."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
