import csv
import re
import sqlite3
from html import escape
from io import StringIO
from typing import Any

# Excel, LibreOffice and Google Sheets evaluate a cell that opens with one of
# these characters as a formula, so a note body is a live injection vector once
# the export is opened.
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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
) -> dict[str, Any]:
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
        ORDER BY timeline_entries.event_timestamp ASC, timeline_entries.created_at ASC
        """,
        (opportunity_id,),
    ).fetchall()

    entry_ids = [entry["id"] for entry in entries]
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
                  <p>{escape(comment["body"])}</p>
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
                  <p>{escape(note["body"])}</p>
                  <ul class="comments">{comments_html}</ul>
                </li>
                """
            )

        notes_block = (
            f'<ul class="notes">{"".join(notes_html)}</ul>'
            if notes_html
            else '<p class="muted">No notes</p>'
        )
        body = entry["body"] or "No details"
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
              <p>{escape(body)}</p>
              {follow_up}
              <h3>Notes</h3>
              {notes_block}
            </article>
            """
        )

    timeline_html = (
        "".join(entries_html) if entries_html else '<p class="muted">No timeline entries.</p>'
    )

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
              <div class="value">{len(data["entries"])} entries</div></div>
          </div>
        </section>
        {timeline_html}
      </body>
    </html>
    """
