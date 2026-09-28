import re
import sqlite3

from openai import OpenAI

from .timeline_utils import ENTRY_SEQUENCE_SQL

SYSTEM_PROMPT = """
You are OppTrail's read-only sales opportunity analyst.
Answer only from the supplied opportunity timeline context.
Never claim that you changed, created, edited, deleted, shared, or notified anything.
When using timeline evidence, cite entries using [Entry #number, date].
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

    # `sequence` is the number the timeline prints on each card, from the one
    # expression both sides read (milestone 3.9, **D-139**) -- so an answer
    # citing "Entry #7" names the card the reader can see. Ordered by the same
    # `(event_timestamp, id)` pair that numbering counts, rather than by
    # `created_at`, so the context reads in ascending number order and two
    # entries stamped in the same second cannot swap between the two.
    entries = connection.execute(
        f"""
        SELECT
            timeline_entries.*,
            users.name AS author_name,
            {ENTRY_SEQUENCE_SQL} AS sequence
        FROM timeline_entries
        LEFT JOIN users ON users.id = timeline_entries.created_by
        WHERE timeline_entries.opportunity_id = ?
            AND timeline_entries.deleted_at IS NULL
        ORDER BY timeline_entries.event_timestamp ASC, timeline_entries.id ASC
        """,
        (opportunity_id,),
    ).fetchall()
    # The numbers this context actually cites, which is what an answer's
    # citations are checked against (milestone 3.9, **D-140**). They are the
    # per-deal sequence, not the row ids: `#7` in an answer means the card
    # printed `#7`, and validating it against ids would both reject a real
    # citation and accept a number that happens to match an unrelated row.
    entry_numbers = [int(entry["sequence"]) for entry in entries]

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
                    f"[Entry #{entry['sequence']}, {entry['event_timestamp']}] "
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
                # Threading and resolve state are part of what the discussion
                # says (milestone 3.3): a reply read as a fresh comment turns
                # an answer into a second question, and a settled thread read
                # as an open one makes the agent report a concern that the
                # deal has already dealt with.
                kind = "Reply" if comment["parent_id"] else "Comment"
                resolved = " (thread resolved)" if comment["resolved_at"] else ""
                lines.append(
                    f"    {kind} by {comment['author_name']} at "
                    f"{comment['created_at']}{resolved}: {comment['body']}"
                )
        lines.append("")

    if not entries:
        lines.append("No timeline entries yet.")

    return "\n".join(lines), entry_numbers


def extract_referenced_entry_numbers(answer: str, available_entry_numbers: list[int]) -> list[int]:
    """Which entries an answer cited, as the numbers the timeline prints.

    Renamed from `extract_referenced_entry_ids` in milestone 3.9 (**D-140**),
    and it is the rename that matters rather than the code: the model cites
    `[Entry #number, date]` now, so validating those numbers against row ids
    silently produced a list that was wrong in both directions. The answer's
    numbers and the reader's cards are the same numbering, and this checks one
    against the other.
    """
    available = set(available_entry_numbers)
    referenced = []
    for match in re.findall(r"Entry\s+#(\d+)", answer):
        entry_number = int(match)
        if entry_number in available and entry_number not in referenced:
            referenced.append(entry_number)
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
