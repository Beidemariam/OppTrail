"""Full-text search over entries, notes and comments (ADR 0007).

The index is the `search_index` FTS5 table created by revision
`0002_search_index` and kept current by that revision's triggers, so nothing
here writes to it during an ordinary request: a write to `timeline_entries`,
`notes` or `comments` is indexed by the same statement that performs it, inside
the same transaction.

Two consequences of the index being *contentless* shape this module:

- It stores no text, so `snippet()` and `highlight()` are unavailable. A match
  is resolved back to its row and `build_snippet` produces the excerpt, which
  is cheap for a page of 50 (ADR 0007).
- It cannot be scanned without `MATCH`, so every query here starts from one.

The rowid carries the document's identity — `source id * 4 + kind code` — which
is why the index needs no mapping table beside it. The encoding is repeated by
the migration's triggers, and `tests/test_search.py` pins the two together.
"""

import re
import sqlite3

from .pagination import PageRequest, cursor_clause, split_page
from .permissions import ACCESSIBLE_OPPORTUNITY_IDS_SQL
from .schemas import SearchKind, SearchResultPublic, SearchSnippet, SnippetMatch

# Kind codes, and the base that separates them from the source row id.
#
# The base was 4 until milestone 4.8, which both added the fourth kind and
# widened it to 8 (**D-167**) -- the action the 1.4 review's note asked the
# first milestone needing a fourth type to take, rather than spending the last
# code and leaving v3's email to pay for a rowid rewrite. Four codes are free.
# It is interpolated into the queries below: it was a constant that did not
# govern them until this milestone, because `/ 4` and `% 4` were written out
# literally in four places.
DOCUMENT_BASE = 8
KIND_CODES: dict[SearchKind, int] = {
    "entry": 0,
    "note": 1,
    "comment": 2,
    # The filename, indexed as a title (milestone 4.8). There is no body: the
    # file's contents are not read, here or anywhere (**D-158**).
    "attachment": 3,
}


def document_id(kind: SearchKind, source_id: int) -> int:
    """The `search_index` rowid for one source row."""
    return source_id * DOCUMENT_BASE + KIND_CODES[kind]


# `\w+` rather than an escape function: the user's text is never handed to
# FTS5's query parser, it is taken apart into tokens and rebuilt. A quoted
# token cannot contain a quote, so nothing the user types can turn into an
# operator (`AND`, `NEAR`, `title:`) or a syntax error.
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)

# The excerpt returned with each result, in characters.
SNIPPET_LENGTH = 200
# How much of the excerpt sits before the first match, so the match is visible
# with the words that lead into it.
SNIPPET_LEAD = 60
ELLIPSIS = "…"


def query_tokens(query: str) -> list[str]:
    return TOKEN_PATTERN.findall(query)


def match_expression(query: str) -> str | None:
    """The user's words as an FTS5 MATCH expression, or None if there are none.

    Every token is a prefix term, so "proc" still finds "procurement" the way
    the `LIKE '%…%'` filter this replaced did. Tokens are implicitly ANDed by
    FTS5, which is what a search box is expected to do.
    """
    tokens = query_tokens(query)
    if not tokens:
        return None
    return " ".join(f'"{token}"*' for token in tokens)


def build_snippet(text: str, tokens: list[str]) -> SearchSnippet:
    """An excerpt around the first matching word, with the match offsets.

    The offsets are returned instead of markup: the API's contract is plain
    text, so nothing here can turn into markup the client forgets to escape.

    Stemming is why a match list can be empty on a row FTS5 matched — the index
    matched "objection" for the typed "objections" and this literal pass does
    not. The excerpt is still the head of the text, which is the same thing the
    user would see with no highlight, so the result is never dropped for it.
    """
    pattern = matches_pattern(tokens)
    first = pattern.search(text) if pattern else None
    start = max(0, first.start() - SNIPPET_LEAD) if first else 0
    excerpt = text[start : start + SNIPPET_LENGTH]

    prefix = ELLIPSIS if start > 0 else ""
    suffix = ELLIPSIS if start + SNIPPET_LENGTH < len(text) else ""

    # Offsets are into the returned text, leading ellipsis included, so a
    # client highlights by slicing what it was given and nothing else.
    matches = (
        [
            SnippetMatch(start=found.start() + len(prefix), length=len(found.group()))
            for found in pattern.finditer(excerpt)
        ]
        if pattern
        else []
    )
    return SearchSnippet(text=f"{prefix}{excerpt}{suffix}", matches=matches)


def matches_pattern(tokens: list[str]) -> re.Pattern[str] | None:
    """Word-prefix matches for the typed tokens, mirroring `match_expression`."""
    if not tokens:
        return None
    alternatives = "|".join(re.escape(token) for token in tokens)
    return re.compile(rf"\b(?:{alternatives})\w*", re.IGNORECASE)


# One FTS5 scan, then the matched rowids are decoded back to the three source
# tables. Each branch carries the same columns so the union is one result set,
# and each filters `deleted_at IS NULL` at every level it joins through, like
# every other read in the app -- the triggers already keep deleted rows out of
# the index, and a read that depends on that is a read that trusts a cache.
SEARCH_DOCUMENTS_SQL = f"""
    WITH matches AS (
        SELECT rowid AS document_id, bm25(search_index) AS rank
        FROM search_index
        WHERE search_index MATCH ?
    ),
    documents AS (
        SELECT
            'entry' AS kind,
            timeline_entries.id AS source_id,
            timeline_entries.id AS entry_id,
            NULL AS note_id,
            timeline_entries.opportunity_id AS opportunity_id,
            timeline_entries.type AS entry_type,
            timeline_entries.created_by AS author_id,
            timeline_entries.event_timestamp AS timestamp,
            timeline_entries.title AS title,
            timeline_entries.body AS body,
            matches.document_id AS document_id,
            matches.rank AS rank
        FROM matches
        JOIN timeline_entries
            ON timeline_entries.id = matches.document_id / {DOCUMENT_BASE}
            AND matches.document_id % {DOCUMENT_BASE} = 0
        WHERE timeline_entries.deleted_at IS NULL

        UNION ALL

        SELECT
            'note',
            notes.id,
            notes.entry_id,
            notes.id,
            timeline_entries.opportunity_id,
            timeline_entries.type,
            notes.created_by,
            notes.created_at,
            NULL,
            notes.body,
            matches.document_id,
            matches.rank
        FROM matches
        JOIN notes
            ON notes.id = matches.document_id / {DOCUMENT_BASE}
            AND matches.document_id % {DOCUMENT_BASE} = 1
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL

        UNION ALL

        SELECT
            'comment',
            comments.id,
            notes.entry_id,
            comments.note_id,
            timeline_entries.opportunity_id,
            timeline_entries.type,
            comments.created_by,
            comments.created_at,
            NULL,
            comments.body,
            matches.document_id,
            matches.rank
        FROM matches
        JOIN comments
            ON comments.id = matches.document_id / {DOCUMENT_BASE}
            AND matches.document_id % {DOCUMENT_BASE} = 2
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL

        UNION ALL

        -- A file, found by its name (milestone 4.8). `title` is the filename
        -- and there is no body, so the snippet `result_from_row` builds falls
        -- back to the title -- which is the whole document. The entry it hangs
        -- off is what the result links to, so a filename hit lands on the
        -- conversation it belongs to rather than on the deal.
        SELECT
            'attachment',
            attachments.id,
            attachments.entry_id,
            NULL,
            timeline_entries.opportunity_id,
            timeline_entries.type,
            attachments.uploaded_by,
            attachments.created_at,
            attachments.filename,
            '',
            matches.document_id,
            matches.rank
        FROM matches
        JOIN attachments
            ON attachments.id = matches.document_id / {DOCUMENT_BASE}
            AND matches.document_id % {DOCUMENT_BASE} = 3
        JOIN timeline_entries ON timeline_entries.id = attachments.entry_id
        WHERE attachments.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
    )
    SELECT
        documents.*,
        opportunities.name AS opportunity_name,
        users.name AS author_name
    FROM documents
    JOIN opportunities ON opportunities.id = documents.opportunity_id
    LEFT JOIN users ON users.id = documents.author_id
"""


# The timeline's keyword filter, reimplemented against the index (ADR 0007): an
# entry matches when it matches itself, or one of its notes or comments does.
MATCHING_ENTRY_IDS_SQL = f"""
    WITH matches(document_id) AS (
        SELECT rowid FROM search_index WHERE search_index MATCH ?
    )
    SELECT matches.document_id / {DOCUMENT_BASE}
    FROM matches
    WHERE matches.document_id % {DOCUMENT_BASE} = 0

    UNION

    SELECT notes.entry_id
    FROM matches
    JOIN notes
        ON notes.id = matches.document_id / {DOCUMENT_BASE}
        AND matches.document_id % {DOCUMENT_BASE} = 1
    WHERE notes.deleted_at IS NULL

    UNION

    SELECT notes.entry_id
    FROM matches
    JOIN comments
        ON comments.id = matches.document_id / {DOCUMENT_BASE}
        AND matches.document_id % {DOCUMENT_BASE} = 2
    JOIN notes ON notes.id = comments.note_id
    WHERE comments.deleted_at IS NULL
        AND notes.deleted_at IS NULL
"""


def search(
    connection: sqlite3.Connection,
    user_id: int,
    query: str,
    page: PageRequest,
    *,
    entry_type: str | None = None,
    author_id: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> tuple[list[SearchResultPublic], str | None]:
    """Ranked matches across every opportunity the user can read.

    Permissions are part of the query rather than a filter applied to its
    result: a page of 50 is 50 rows the caller may read, not 50 rows of which
    some are then dropped.
    """
    expression = match_expression(query)
    if expression is None:
        return [], None

    where = [f"documents.opportunity_id IN ({ACCESSIBLE_OPPORTUNITY_IDS_SQL})"]
    params: list[object] = [expression, user_id, user_id]

    if entry_type:
        # The type of the entry the result sits under, so a note on a call is
        # found by `type=call` exactly as the timeline filter has it.
        where.append("documents.entry_type = ?")
        params.append(entry_type)
    if author_id is not None:
        where.append("documents.author_id = ?")
        params.append(author_id)
    if from_date:
        where.append("documents.timestamp >= ?")
        params.append(from_date)
    if to_date:
        where.append("documents.timestamp <= ?")
        params.append(to_date)

    # bm25() is negative and better matches are more negative, so ascending is
    # best first. The document id breaks ties, as every v2 cursor needs.
    continuation, cursor_values = cursor_clause(
        page,
        "documents.rank",
        "documents.document_id",
        descending=False,
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)

    rows = connection.execute(
        f"""
        {SEARCH_DOCUMENTS_SQL}
        WHERE {" AND ".join(where)}
        ORDER BY documents.rank ASC, documents.document_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["rank"], row["document_id"]))
    tokens = query_tokens(query)
    return [result_from_row(row, tokens) for row in rows], next_cursor


def result_from_row(row: sqlite3.Row, tokens: list[str]) -> SearchResultPublic:
    return SearchResultPublic(
        kind=row["kind"],
        id=row["source_id"],
        opportunity_id=row["opportunity_id"],
        opportunity_name=row["opportunity_name"],
        entry_id=row["entry_id"],
        note_id=row["note_id"],
        title=row["title"],
        snippet=build_snippet(row["body"] or row["title"] or "", tokens),
        timestamp=row["timestamp"],
        author_id=row["author_id"],
        author_name=row["author_name"],
    )


# Repeated by revision 0002_search_index's own backfill, which cannot import
# this module (a revision is frozen in time). The rebuild-matches-migration
# test in tests/test_search.py is what keeps the two identical.
INDEX_SOURCES = (
    f"""
    INSERT INTO search_index(rowid, title, body)
    SELECT id * {DOCUMENT_BASE} + 0, title, body FROM timeline_entries WHERE deleted_at IS NULL
    """,
    f"""
    INSERT INTO search_index(rowid, title, body)
    SELECT id * {DOCUMENT_BASE} + 1, '', body FROM notes WHERE deleted_at IS NULL
    """,
    f"""
    INSERT INTO search_index(rowid, title, body)
    SELECT id * {DOCUMENT_BASE} + 2, '', body FROM comments WHERE deleted_at IS NULL
    """,
    # The fourth kind (milestone 4.8): the filename as the title, no body.
    f"""
    INSERT INTO search_index(rowid, title, body)
    SELECT id * {DOCUMENT_BASE} + 3, filename, '' FROM attachments WHERE deleted_at IS NULL
    """,
)


def rebuild_search_index(connection: sqlite3.Connection) -> int:
    """Discard the index and build it again from the source tables.

    ADR 0007 asks for this for corruption or a schema change; changing the
    tokenizer, or adding a document kind, needs it too. It is a plain rebuild
    rather than FTS5's `'rebuild'` command, which only works on an
    external-content table. Returns the number of documents indexed.
    """
    connection.execute("INSERT INTO search_index(search_index) VALUES ('delete-all')")
    return sum(connection.execute(statement).rowcount for statement in INDEX_SOURCES)
