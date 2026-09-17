import re
import sqlite3

from openai import OpenAI

SYSTEM_PROMPT = """
You are OppTrail's read-only sales opportunity analyst.
Answer only from the supplied opportunity timeline context.
Never claim that you changed, created, edited, deleted, shared, or notified anything.
When using timeline evidence, cite entries using [Entry #id, date].
If the context is thin, say what is known and what is missing.
Keep the answer concise and useful for a sales teammate.
Use plain text only; do not use Markdown formatting such as bold markers.
""".strip()


def build_timeline_context(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> tuple[str, list[int]]:
    opportunity = connection.execute(
        """
        SELECT opportunities.*, users.name AS owner_name
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id = ? AND opportunities.deleted_at IS NULL
        """,
        (opportunity_id,),
    ).fetchone()
    if not opportunity:
        return "Opportunity not found.", []

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
    entry_ids = [int(entry["id"]) for entry in entries]

    lines = [
        "Opportunity:",
        f"- Name: {opportunity['name']}",
        f"- Account: {opportunity['account_name']}",
        f"- Value: {opportunity['currency']} {opportunity['value']}",
        f"- Stage: {opportunity['stage']}",
        f"- Owner: {opportunity['owner_name']}",
        f"- Expected close: {opportunity['expected_close_date'] or 'Not set'}",
        "",
        "Timeline:",
    ]

    for entry in entries:
        lines.extend(
            [
                (
                    f"[Entry #{entry['id']}, {entry['event_timestamp']}] "
                    f"{entry['type']} - {entry['title']}"
                ),
                f"Author: {entry['author_name'] or 'System'}",
                f"Details: {entry['body'] or 'No details'}",
            ]
        )
        if entry["follow_up_date"]:
            lines.append(f"Follow up: {entry['follow_up_date']}")

        notes = connection.execute(
            """
            SELECT notes.*, users.name AS author_name
            FROM notes
            JOIN users ON users.id = notes.created_by
            WHERE notes.entry_id = ? AND notes.deleted_at IS NULL
            ORDER BY notes.created_at ASC, notes.id ASC
            """,
            (entry["id"],),
        ).fetchall()
        for note in notes:
            edited = " edited" if note["edited"] else ""
            lines.append(
                f"  Note by {note['author_name']} at {note['created_at']}{edited}: {note['body']}"
            )
            comments = connection.execute(
                """
                SELECT comments.*, users.name AS author_name
                FROM comments
                JOIN users ON users.id = comments.created_by
                WHERE comments.note_id = ? AND comments.deleted_at IS NULL
                ORDER BY comments.created_at ASC, comments.id ASC
                """,
                (note["id"],),
            ).fetchall()
            for comment in comments:
                lines.append(
                    f"    Comment by {comment['author_name']} at "
                    f"{comment['created_at']}: {comment['body']}"
                )
        lines.append("")

    if not entries:
        lines.append("No timeline entries yet.")

    return "\n".join(lines), entry_ids


def extract_referenced_entry_ids(answer: str, available_entry_ids: list[int]) -> list[int]:
    available = set(available_entry_ids)
    referenced = []
    for match in re.findall(r"Entry\s+#(\d+)", answer):
        entry_id = int(match)
        if entry_id in available and entry_id not in referenced:
            referenced.append(entry_id)
    return referenced


def normalize_ai_answer(answer: str) -> str:
    return answer.replace("**", "").strip()


def ask_openai(
    api_key: str,
    model: str,
    timeline_context: str,
    question: str,
    timeout: float,
    max_retries: int,
) -> str:
    client = OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=f"Timeline context:\n{timeline_context}\n\nQuestion:\n{question}",
        store=False,
    )
    return normalize_ai_answer(response.output_text)
