import csv
import re
import sqlite3
from html import escape
from io import StringIO
from typing import Any

from markdown_it import MarkdownIt

from .attachment_utils import attachments_by_entry_id
from .permissions import ACCESSIBLE_OPPORTUNITY_IDS_SQL
from .sanitize import sanitize_html

# Excel, LibreOffice and Google Sheets evaluate a cell that opens with one of
# these characters as a formula, so a note body is a live injection vector once
# the export is opened.
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# The same node set `lib/markdown.ts`'s composer writes and `MarkdownText.tsx`
# renders (`table` and `strikethrough` cover content written before the
# composer existed, or posted straight to the API). `commonmark`'s own default
# is `html: True` -- raw HTML passed through untouched, on the assumption that
# whatever renders the output will sanitize it -- so `html: False` is set
# explicitly here to make a raw `<script>` in a body come out as escaped text
# rather than a tag; `sanitize_html` beneath it is the same allowlist the
# frontend's `rehype-sanitize` pass uses, so a hostile body is stopped twice —
# once by the parser, once by the sanitizer — rather than trusting either
# alone (brief §4.5, `app/sanitize.py`'s own docstring on why it existed
# before any feature called it).
_markdown = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def render_markdown_to_safe_html(text: str) -> str:
    """A stored Markdown body, rendered and sanitized for embedding in the
    PDF export. This is the same content `MarkdownText.tsx` renders in the
    browser; WeasyPrint gets no other protection against what a body
    contains, so sanitizing here is the boundary (`app/sanitize.py`).
    """
    return sanitize_html(_markdown.render(text))


def format_byte_size(byte_size: int) -> str:
    """A file size as a reader of the document reads it (milestone 4.4).

    The same job `lib/domain.ts`'s `formatBytes` does for the screen, and
    deliberately a second implementation rather than a shared one: there is no
    code path between the browser and WeasyPrint, and what travels between them
    is `byte_size` itself (`AttachmentPublic`), which is why the API sends a
    number and never a formatted string.
    """
    size = float(byte_size)
    for unit in ("bytes", "KB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"


def escape_csv_value(value: object) -> object:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def safe_export_filename(name: str, extension: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return f"{slug or 'opportunity'}-timeline.{extension}"


def fetch_export_data(
    connection: sqlite3.Connection,
    opportunity_id: int,
    order: str = "desc",
) -> dict[str, Any]:
    """Everything one deal is made of, in the order the reader asked for.

    **The order is a parameter because the export was contradicting the
    screen** (milestone 4.4b): entries came out oldest-first whatever the
    timeline was set to, so a reader working newest-first got a document that
    ran the other way. The caller passes what the timeline is showing, and the
    default is `desc` — the timeline's own default (D-137), so a bare link
    matches what most readers see.

    **Only the entries turn.** A note's comments and an entry's notes stay
    chronological inside it either way: the reading order is a question about
    which event you meet first, not about reading a conversation backwards.
    """
    opportunity = connection.execute(
        """
        SELECT opportunities.*, users.name AS owner_name
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id = ? AND opportunities.deleted_at IS NULL
        """,
        (opportunity_id,),
    ).fetchone()
    # Callers resolve access through `require_opportunity_access` before reaching
    # here, which already forecloses a missing or soft-deleted opportunity.
    assert opportunity is not None

    entries = connection.execute(
        """
        SELECT timeline_entries.*, users.name AS author_name
        FROM timeline_entries
        LEFT JOIN users ON users.id = timeline_entries.created_by
        WHERE timeline_entries.opportunity_id = ?
            AND timeline_entries.deleted_at IS NULL
        ORDER BY timeline_entries.event_timestamp {direction},
                 timeline_entries.created_at {direction}
        """.format(direction="ASC" if order == "asc" else "DESC"),
        (opportunity_id,),
    ).fetchall()

    entry_ids = [entry["id"] for entry in entries]
    # The entry's files (milestone 4.4), through the same helper the timeline
    # read uses rather than a second copy of the query -- so an export cannot
    # disagree with the screen about which files are on a deal. `model_dump`
    # because this module answers with plain dicts (it is the JSON export's
    # payload as well as the PDF's input), which is the one conversion needed.
    attachments_by_entry: dict[int, list[dict[str, Any]]] = {
        entry_id: [attachment.model_dump() for attachment in attachments]
        for entry_id, attachments in attachments_by_entry_id(connection, entry_ids).items()
    }
    notes_by_entry_id: dict[int, list[dict[str, Any]]] = {}
    comments_by_note_id: dict[int, list[dict[str, Any]]] = {}
    if entry_ids:
        placeholders = ",".join("?" for _ in entry_ids)
        notes = connection.execute(
            f"""
            SELECT notes.*, users.name AS author_name
            FROM notes
            JOIN users ON users.id = notes.created_by
            WHERE notes.entry_id IN ({placeholders})
                AND notes.deleted_at IS NULL
            ORDER BY notes.created_at ASC, notes.id ASC
            """,
            entry_ids,
        ).fetchall()
        note_ids = [note["id"] for note in notes]

        if note_ids:
            note_placeholders = ",".join("?" for _ in note_ids)
            comments = connection.execute(
                f"""
                SELECT comments.*, users.name AS author_name
                FROM comments
                JOIN users ON users.id = comments.created_by
                WHERE comments.note_id IN ({note_placeholders})
                    AND comments.deleted_at IS NULL
                ORDER BY comments.created_at ASC, comments.id ASC
                """,
                note_ids,
            ).fetchall()
            for comment in comments:
                comments_by_note_id.setdefault(comment["note_id"], []).append(
                    {
                        "id": comment["id"],
                        "note_id": comment["note_id"],
                        "body": comment["body"],
                        "created_by": comment["created_by"],
                        "author_name": comment["author_name"],
                        "created_at": comment["created_at"],
                    }
                )

        for note in notes:
            notes_by_entry_id.setdefault(note["entry_id"], []).append(
                {
                    "id": note["id"],
                    "entry_id": note["entry_id"],
                    "body": note["body"],
                    "created_by": note["created_by"],
                    "author_name": note["author_name"],
                    "created_at": note["created_at"],
                    "updated_at": note["updated_at"],
                    "edited": bool(note["edited"]),
                    "comments": comments_by_note_id.get(note["id"], []),
                }
            )

    return {
        "opportunity": {
            "id": opportunity["id"],
            "name": opportunity["name"],
            "account_name": opportunity["account_name"],
            "value": str(opportunity["value"]),
            "currency": opportunity["currency"],
            "stage": opportunity["stage"],
            "owner_id": opportunity["owner_id"],
            "owner_name": opportunity["owner_name"],
            "expected_close_date": opportunity["expected_close_date"],
            "created_at": opportunity["created_at"],
            "updated_at": opportunity["updated_at"],
        },
        "entries": [
            {
                "id": entry["id"],
                "opportunity_id": entry["opportunity_id"],
                "type": entry["type"],
                "title": entry["title"],
                "body": entry["body"],
                "event_timestamp": entry["event_timestamp"],
                "follow_up_date": entry["follow_up_date"],
                "created_by": entry["created_by"],
                "author_name": entry["author_name"],
                "system_generated": bool(entry["system_generated"]),
                "created_at": entry["created_at"],
                "notes": notes_by_entry_id.get(entry["id"], []),
                "attachments": attachments_by_entry.get(entry["id"], []),
            }
            for entry in entries
        ],
    }


def export_data_to_csv(data: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "row_type",
        "opportunity_id",
        "opportunity_name",
        "account_name",
        "entry_id",
        "note_id",
        "comment_id",
        "parent_entry_id",
        "parent_note_id",
        "entry_type",
        "title",
        "body",
        "event_timestamp",
        "follow_up_date",
        "created_by",
        "author_name",
        "created_at",
        "updated_at",
        "edited",
        "system_generated",
        # Attachments (milestone 4.4). Appended rather than slotted in beside
        # `title`, so a reader whose spreadsheet or script already reads this
        # file keeps every column where it was -- and `filename` is its own
        # column rather than borrowed from `title`, because a file's name is
        # not an entry's title and a formula guard has to apply to both.
        "filename",
        "content_type",
        "byte_size",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    def write_row(row: dict[str, Any]) -> None:
        writer.writerow({key: escape_csv_value(value) for key, value in row.items()})

    opportunity = data["opportunity"]
    for entry in data["entries"]:
        base = {
            "opportunity_id": opportunity["id"],
            "opportunity_name": opportunity["name"],
            "account_name": opportunity["account_name"],
        }
        write_row(
            {
                **base,
                "row_type": "entry",
                "entry_id": entry["id"],
                "entry_type": entry["type"],
                "title": entry["title"],
                "body": entry["body"],
                "event_timestamp": entry["event_timestamp"],
                "follow_up_date": entry["follow_up_date"] or "",
                "created_by": entry["created_by"] or "",
                "author_name": entry["author_name"] or "System",
                "created_at": entry["created_at"],
                "system_generated": int(entry["system_generated"]),
            }
        )
        for attachment in entry["attachments"]:
            write_row(
                {
                    **base,
                    "row_type": "attachment",
                    "entry_id": entry["id"],
                    "parent_entry_id": entry["id"],
                    "created_by": attachment["uploaded_by"],
                    "author_name": attachment["uploader_name"],
                    "created_at": attachment["created_at"],
                    "filename": attachment["filename"],
                    "content_type": attachment["content_type"],
                    "byte_size": attachment["byte_size"],
                }
            )
        for note in entry["notes"]:
            write_row(
                {
                    **base,
                    "row_type": "note",
                    "entry_id": entry["id"],
                    "note_id": note["id"],
                    "parent_entry_id": entry["id"],
                    "body": note["body"],
                    "created_by": note["created_by"],
                    "author_name": note["author_name"],
                    "created_at": note["created_at"],
                    "updated_at": note["updated_at"],
                    "edited": int(note["edited"]),
                }
            )
            for comment in note["comments"]:
                write_row(
                    {
                        **base,
                        "row_type": "comment",
                        "entry_id": entry["id"],
                        "note_id": note["id"],
                        "comment_id": comment["id"],
                        "parent_entry_id": entry["id"],
                        "parent_note_id": note["id"],
                        "body": comment["body"],
                        "created_by": comment["created_by"],
                        "author_name": comment["author_name"],
                        "created_at": comment["created_at"],
                    }
                )

    return output.getvalue()


def export_data_to_pdf(data: dict[str, Any]) -> bytes:
    from weasyprint import HTML

    html = render_export_html(data)
    pdf_bytes: bytes = HTML(string=html).write_pdf()
    return pdf_bytes


def attachment_count(data: dict[str, Any]) -> int:
    return sum(len(entry["attachments"]) for entry in data["entries"])


def render_entry_attachments(entry: dict[str, Any]) -> str:
    """One entry's files, listed under the entry they belong to (milestone
    4.4, moved here by **4.4a**).

    **A list, not the files** -- embedding them would make an export unbounded,
    which is the one thing `docs/FEATURES.md` §6 says about this explicitly.
    Each line is what a person needs to go and find the document: its name, its
    size, and who put it there.

    **Beside the entry rather than in a section at the end.** D-154 chose the
    end of the document, on the argument that a manifest answers a question
    about the whole file; the human ruled for that **against a description of
    it** and then reversed on the document itself -- *"better to keep each file
    next to its entry"* -- which is the stronger evidence and the one this
    follows. Nothing is lost in the other direction: the summary still counts
    them, so "does this deal have documents at all" is answered on page one.

    Absent entirely on an entry with no files, for the reason `TaskSummary`
    draws nothing when nothing is due.
    """
    if not entry["attachments"]:
        return ""
    items = "".join(
        f"""
        <li>
          <strong>{escape(attachment["filename"])}</strong>
          <span>{escape(format_byte_size(attachment["byte_size"]))}</span>
          <span>{escape(attachment["uploader_name"])}</span>
        </li>
        """
        for attachment in entry["attachments"]
    )
    return f"""
      <h3>Attachments</h3>
      <ul class="files">{items}</ul>
    """


def render_export_html(data: dict[str, Any]) -> str:
    opportunity = data["opportunity"]
    entries_html = []
    for entry in data["entries"]:
        notes_html = []
        for note in entry["notes"]:
            comments_html = "".join(
                f"""
                <li>
                  <strong>{escape(comment["author_name"])}</strong>
                  <span>{escape(comment["created_at"])}</span>
                  <div class="rendered">{render_markdown_to_safe_html(comment["body"])}</div>
                </li>
                """
                for comment in note["comments"]
            )
            edited = " edited" if note["edited"] else ""
            notes_html.append(
                f"""
                <li>
                  <strong>{escape(note["author_name"])}</strong>
                  <span>{escape(note["created_at"])}{edited}</span>
                  <div class="rendered">{render_markdown_to_safe_html(note["body"])}</div>
                  <ul class="comments">{comments_html}</ul>
                </li>
                """
            )

        notes_block = (
            f'<ul class="notes">{"".join(notes_html)}</ul>'
            if notes_html
            else '<p class="muted">No notes</p>'
        )
        body_html = (
            render_markdown_to_safe_html(entry["body"])
            if entry["body"]
            else '<p class="muted">No details</p>'
        )
        follow_up = (
            f"<p><strong>Follow up:</strong> {escape(entry['follow_up_date'])}</p>"
            if entry["follow_up_date"]
            else ""
        )
        entries_html.append(
            f"""
            <article class="entry">
              <div class="entry-meta">
                <span>{escape(entry["event_timestamp"])}</span>
                <span>{escape(entry["type"].replace("_", " ").title())}</span>
                <span>{escape(entry["author_name"] or "System")}</span>
              </div>
              <h2>{escape(entry["title"])}</h2>
              <div class="rendered">{body_html}</div>
              {follow_up}
              {render_entry_attachments(entry)}
              <h3>Notes</h3>
              {notes_block}
            </article>
            """
        )

    timeline_html = (
        "".join(entries_html) if entries_html else '<p class="muted">No timeline entries.</p>'
    )
    files = attachment_count(data)

    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          @page {{ margin: 24mm 18mm; }}
          body {{
            color: #0b2540;
            font-family: Arial, "DejaVu Sans", sans-serif;
            font-size: 12px;
            line-height: 1.5;
          }}
          h1, h2, h3 {{ margin: 0; }}
          h1 {{ font-size: 26px; }}
          h2 {{ font-size: 17px; margin-top: 8px; }}
          h3 {{ font-size: 12px; margin-top: 14px; text-transform: uppercase; }}
          .summary {{
            border-bottom: 2px solid #0f9d8c;
            margin-bottom: 18px;
            padding-bottom: 14px;
          }}
          .grid {{
            display: grid;
            gap: 8px 20px;
            grid-template-columns: repeat(2, 1fr);
            margin-top: 14px;
          }}
          .label {{ color: #6b7280; font-size: 10px; text-transform: uppercase; }}
          .value {{ font-weight: 700; }}
          .entry {{
            border-left: 3px solid #0f9d8c;
            margin: 0 0 16px;
            padding: 0 0 0 12px;
            break-inside: avoid;
          }}
          .entry-meta {{
            color: #6b7280;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            font-size: 11px;
            font-weight: 700;
          }}
          .notes, .comments {{ margin: 8px 0 0 18px; padding: 0; }}
          .notes li, .comments li {{ margin-bottom: 8px; }}
          .comments {{ color: #24364a; }}
          .muted {{ color: #6b7280; }}
          .rendered p {{ margin: 0 0 6px; }}
          .rendered p:last-child {{ margin-bottom: 0; }}
          .rendered ul, .rendered ol {{ margin: 0 0 6px 18px; padding: 0; }}
          .rendered blockquote {{
            border-left: 2px solid #d1d5db;
            color: #4b5563;
            margin: 0 0 6px;
            padding-left: 10px;
          }}
          .rendered code {{
            background: #f3f4f6;
            font-family: "DejaVu Sans Mono", monospace;
            padding: 1px 4px;
          }}
          .rendered pre {{
            background: #f3f4f6;
            padding: 8px;
            white-space: pre-wrap;
          }}
          .rendered pre code {{ background: none; padding: 0; }}
          .files {{ margin: 6px 0 0 18px; padding: 0; }}
          .files li {{ margin-bottom: 4px; }}
          .files span {{ color: #6b7280; margin-left: 8px; }}
          .rendered table {{ border-collapse: collapse; margin: 0 0 6px; }}
          .rendered th, .rendered td {{
            border: 1px solid #d1d5db;
            padding: 3px 6px;
          }}
        </style>
      </head>
      <body>
        <section class="summary">
          <p class="label">Opportunity Timeline Export</p>
          <h1>{escape(opportunity["name"])}</h1>
          <div class="grid">
            <div><div class="label">Account</div>
              <div class="value">{escape(opportunity["account_name"])}</div></div>
            <div><div class="label">Value</div>
              <div class="value">
                {escape(opportunity["currency"])} {escape(opportunity["value"])}
              </div></div>
            <div><div class="label">Stage</div>
              <div class="value">{escape(opportunity["stage"])}</div></div>
            <div><div class="label">Owner</div>
              <div class="value">{escape(opportunity["owner_name"])}</div></div>
            <div><div class="label">Expected Close</div>
              <div class="value">
                {escape(opportunity["expected_close_date"] or "Not set")}
              </div></div>
            <div><div class="label">Exported Rows</div>
              <div class="value">
                {len(data["entries"])} entries, {files} attachments
              </div></div>
          </div>
          {
        '<p class="muted">Attachments are listed on the entry they belong to,'
        " and are not included in this file.</p>"
        if files
        else ""
    }
        </section>
        {timeline_html}
      </body>
    </html>
    """


# --- Exporting a selection (milestone 3.0a) ---------------------------------

# One row per opportunity, in the order a reader scans them. Deliberately the
# record and not its timeline: `fetch_export_data` above answers "give me
# everything about this deal" and is a document per opportunity, while the
# action bar's export answers "give me the deals I just selected", which is a
# spreadsheet (**D-107**). The two are different questions, so they are
# different shapes rather than one shape asked twice.
OPPORTUNITY_EXPORT_FIELDS = (
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
)


def fetch_opportunity_list_export(
    connection: sqlite3.Connection,
    opportunity_ids: list[int],
    user_id: int,
) -> list[dict[str, Any]]:
    """The selected opportunities the caller may read, newest activity first.

    The permission filter is inside the query rather than a pass over its
    results (`permissions.ACCESSIBLE_OPPORTUNITY_IDS_SQL`), the same way
    `search.py` does it: this is the second read in the app that spans
    opportunities, so there is no single role to resolve first. An id the
    caller cannot read is absent rather than refused -- a 404 naming one id
    out of a selection would say whether it exists.
    """
    if not opportunity_ids:
        return []

    placeholders = ",".join("?" for _ in opportunity_ids)
    rows = connection.execute(
        f"""
        SELECT opportunities.*, users.name AS owner_name
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id IN ({placeholders})
            AND opportunities.id IN ({ACCESSIBLE_OPPORTUNITY_IDS_SQL})
        ORDER BY opportunities.updated_at DESC, opportunities.id DESC
        """,
        (*opportunity_ids, user_id, user_id),
    ).fetchall()

    return [
        {
            field: (str(row["value"]) if field == "value" else row[field])
            for field in OPPORTUNITY_EXPORT_FIELDS
        }
        for row in rows
    ]


def opportunity_list_to_csv(opportunities: list[dict[str, Any]]) -> str:
    """The same formula-injection guard the timeline export uses: a deal name
    beginning `=` is a live spreadsheet formula once the file is opened."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(OPPORTUNITY_EXPORT_FIELDS))
    writer.writeheader()
    for opportunity in opportunities:
        writer.writerow({key: escape_csv_value(value) for key, value in opportunity.items()})
    return output.getvalue()
