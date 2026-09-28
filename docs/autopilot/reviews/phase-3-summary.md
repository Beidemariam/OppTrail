# Phase 3 review packet — Rich Content and Live Collaboration

Branch: `autopilot/phase-3`. Depends on the `phase-2-accepted` tag (present).
This packet puts the phase into `AWAITING_REVIEW`.

Read time budget: 20-30 minutes (brief §3.5).

---

## 1. What changed

Phase 3's stated goal (`docs/ROADMAP.md`): *make the timeline worth writing
in, and make two people on one deal see each other.* User-visible outcome: a
real editor with `@`, `/` and `#` triggers; comments that thread and resolve;
a colleague's entry appearing without a refresh; and a PDF that renders the
bold and the bullets instead of printing asterisks.

Fourteen milestones are done (3.0, 3.0a, 3.0b, 3.1, 3.1a, 3.1b, 3.1c, 3.2,
3.3, 3.3a, 3.4, 3.5, and 3.6 which resolved to N/A). Three of them — 3.0,
3.0a and 3.0b — are work the **human's own rulings at the Phase 2 gate**
scheduled here (D-101, D-070, D-088) rather than roadmap lines. Two — 3.1a
and 3.1b — are corrections from the mid-phase editor checkpoint. Per-milestone
detail, diffs and test lists are in `docs/autopilot/PROGRESS.md`; this is the
plain-language summary.

**The four collaboration features the roadmap names**

- **3.1 One composer, storing Markdown** — every place a person writes
  content (an entry body, a note, a note edit, a comment) is now one TipTap
  editor serializing to Markdown, and **nothing migrated**: these bodies have
  been Markdown text since the MVP, which is the payoff ADR 0005 predicted.
  `lib/markdown.ts` declares the node set once and it is *the renderer's*
  (D-108) — a document cannot be written that `app/MarkdownText.tsx` will not
  read back, and `linkProtocols` is shared by the editor's link validation
  and the sanitizer's `href` allowlist, so the editor cannot produce a
  `javascript:` link the renderer would silently strip. The sanitizer's
  allowlist is otherwise unchanged, which is what `FEATURES.md` §4 requires
  and what the roadmap named as this phase's risk. Entry bodies became
  Markdown too (D-109, open — see §3): they used to print as plain text, so a
  list typed into the one field a call gets logged into showed its dashes.
  The composer is collapsed to a control until you write in it (D-110, open).
- **3.2 The three typed triggers** — `@` (who to notify), `/` (which block to
  start) and `#` (which earlier entry to point at) are one
  `@tiptap/suggestion` mechanism with three declarations in
  `lib/suggestions.ts`, which is why 3.1 shipped none of them (D-111, open).
  This is requirement 13's discoverability fix: a mention needed a full email
  address typed from memory. A mention is still plain `@email` text (D-122) —
  no new node, no storage change, `notification_service.MENTION_RE`
  untouched. One new read backs the `@` list, `GET
  /api/v2/opportunities/{id}/members`, open to every role rather than the
  owner (D-123, open — see §3), because a viewer writing a comment mentions
  the same people.
- **3.3 Threaded comments that resolve** — `comments` gains `parent_id`,
  `resolved_at` and `resolved_by` (revision `20260924_0007_comment_threads`),
  no new table. Replies are **one level, enforced in the route** (D-127): a
  reply's parent must be a thread root on the same note, and anything else is
  a 400 or a 404 rather than a silent reparenting. Resolving is
  author-or-owner through the existing `require_edit_permission` (D-128) and
  is `POST .../resolve` / `.../unresolve` rather than a PATCH, because a
  comment PATCH is the route `AGENTS.md` invariant 2 says must not exist. A
  thread is a level of the delete cascade, so one Undo restores the thread.
- **3.3a Reactions and watchers** — the other half of the roadmap's single
  "threaded comments with reactions ... watchers" line, split off by D-126.
  Two new tables (`20260925_0008_reactions_watchers`). A reaction is one row
  per (comment, person, emoji) over a fixed seven-item set, on roots and
  replies alike, and any role that may write the timeline may react. A
  **watcher is the one deliberate exception to "absence of access is a 404"**
  (D-129, open — see §3): `FEATURES.md` §7 names "follow an opportunity you
  are not shared on", which the ordinary role-resolving gate would 404 for
  exactly the caller the feature exists for. Neither table is soft-deleted
  (D-130) — both are "I am currently doing this", the same reasoning
  `soft_delete.py` already applies to `sessions`.
- **3.4 Live updates and the note edit guard** (ADR 0003) — `GET
  /api/v2/opportunities/{id}/events` is the app's only `text/event-stream`
  route, and it carries **invalidations, never payloads**: the server says
  `{"type": "timeline.changed", "opportunity_id": 7}` and the client refetches
  through `lib/queries.ts`, so neither what a row looks like nor who may read
  it is decided twice. Publishing happens after `commit()`, a write that wrote
  nothing publishes nothing, each subscriber's queue de-duplicates (which is
  what bounds it), and a stream ends itself after 300s having advertised a
  `retry:` so the browser reopens it. The guard is the other half of ADR
  0003's conflict model: `PATCH /api/v2/notes/{id}` now takes a **required**
  `updated_at` and answers 409 if the note has moved. Required, not optional,
  because the client that omits it is exactly the one that clobbers — which
  makes it this phase's one client-visible API break (D-132, open — see §3,
  and `docs/ROADMAP.md`'s breaking-changes table).
- **3.5 PDF export renders Markdown** — `export_service.render_export_html`
  renders every entry, note and comment body through `markdown-it-py` instead
  of escaping it as plain text, closing the half of requirement 17 that
  `docs/code_review.md` finding 9 recorded as still open (3.1 closed the other
  half). Two independent layers, deliberately: `html: False` is set
  explicitly because `commonmark`'s own preset default is `html: True`, and
  the rendered HTML still goes through `app/sanitize.py`'s allowlist before
  WeasyPrint sees it — a body reaching this path may have been posted straight
  to the API rather than through the composer that refuses a bad link. This is
  `sanitize.py`'s first caller from application code, the module brief §4.5
  asked Phase F to stand up "ready for rich text".

**The three milestones the human's Phase 2 rulings put here**

- **3.0 One activity log per opportunity** (D-101) — the reviewer asked for
  *"one place where the whole history of every event to the opportunity
  resides"*. `GET /api/v2/opportunities/{id}/activity` merges the three
  mechanisms that never met — system timeline entries, audit rows, version
  rows — and **adds no table**: every row it returns already existed. The
  design question inside it was who sees what; **a row keeps the visibility of
  the source it came from** (D-102, open — see §3), so the route is
  `require_opportunity_access` and the *rows* are what the role decides. An
  editor asking what happened is answered with the events they may read
  rather than refused. The reviewer's second question — whether auditable
  events are defined to exclude some — is answered in PROGRESS.md: they are,
  deliberately, and nothing was missing; `AGENTS.md` invariant 7 scopes the
  audit log to deletions and sharing while invariant 8 puts edits in version
  tables.
- **3.0a The three bulk actions 2.4c did not build** (D-070's ruling) —
  assign owner, add to view and export, each gated by a different rule
  because each writes to a different thing. **An ownership transfer leaves the
  previous owner behind as an editor** (D-105, open — see §3): it is the one
  action with no undo available to the person performing it. "Add to view"
  writes the selection into the saved view's own `filters` as an `ids` filter
  (D-106, open) rather than building a membership table — a pinned selection
  *is* a filter, so it serialises to `?opportunities.ids=3,7` and is
  shareable and reloadable for free. Export is a `GET` with the ids in the
  query string rather than a fourth bulk action (D-107, open), because a file
  has no room for per-item outcomes; CSV and JSON of the *records*,
  deliberately not PDF.
- **3.0b Follow-up dates on the calendar** (D-088's ruling) — one new
  permission-filtered, paginated read (`GET /api/v2/timeline/follow-ups`) and
  the calendar's second layer, closing the half of `FEATURES.md` §1 that 2.8
  shipped without.

**The corrections and the reworks**

- **3.1a Four corrections from the editor checkpoint** (D-115) — the timeline
  defaults to newest-first (the control had shipped in 2.2 and the default hid
  it); one export control per opportunity instead of two; the timeline is the
  first thing read on the opportunity screen, with the record's fields moved
  to the right column; and a one-row version history says it is the baseline
  rather than looking broken.
- **3.1b Rework: 3.1a committed on an unverified gate** (D-118) — 3.1a
  changed three E2E specs it could not execute in the sandbox and deferred
  them to the phase gate. Run on the host, two were real regressions from
  3.1a's own default flip and one was the documented WeasyPrint-on-macOS
  limitation. Both regressions are fixed. **The process lesson is recorded in
  PROGRESS.md and is the more important half:** an unexecuted gate is not a
  green one, and when the E2E suite cannot run, the milestone is not complete.
  The cause (an empty `node_modules` volume, not a missing browser) was
  established rather than assumed; every milestone since has run the full
  Playwright suite in the sandbox.
- **3.1c Restore a previous version, and one place to read history** (D-116,
  requested at the checkpoint) — `POST /api/v2/<kind>/{id}/versions/{n}/restore`
  writes a chosen version back over the parent row and then records a version
  for having done it, so history stays append-only and a restore is itself
  restorable. Owner-only, matching D-096. And the human's other request:
  **the activity log is now the only destination** (D-121, open — see §3). The
  per-item History buttons and the sharing panel's audit disclosure are gone;
  an edit row in the feed expands to the before/after they used to answer, and
  offers Restore on the version that edit replaced. `GET .../audit-log` and
  the three `GET .../versions` reads all remain — what moved is where a person
  reads them. The button is "History" and the dialog "Activity and history",
  so the three words the reviewer used land on one screen.
- **3.6 Table/calendar views** — N/A, condition false. `docs/ROADMAP.md`'s
  Phase 2 risk note allowed both to slip here; milestone 2.8 shipped them
  inside Phase 2 and this was reconfirmed against the current tree rather
  than trusted from the earlier note.

**One fix this gate produced.** The `make seed` tour still said *"PDF export
still renders these bodies as plain text — milestone 3.5 is the other half of
requirement 17"*, which 3.5 made false and did not update, and 3.4 had shipped
with no tour line at all. `backend/tools/seed.py`'s printed tour now states
what 3.5 actually does and names the two-window check for 3.4's stream and
409 guard. `test_seed.py` asserts the *data* behind the tour, not its prose,
which is why nothing caught this — worth knowing, because the printed tour is
what §2 below sends the reviewer to.

---

## 2. How to try it

Everything below runs from a clean checkout of this branch.

```bash
git checkout autopilot/phase-3

cd backend && uv sync
cd ../frontend && npm ci
cd ..

make seed          # prints the seeded users and a tour of every shipped feature
make check-fast    # inner loop: lint, types, unit/integration tests
make check         # full gate: adds pip-audit, npm audit, E2E; prints the
                   # Docker deferral note (see §4)
```

To use the app rather than the tests, either build the container
(`./scripts/start_mac.sh`) or run `npm run build` in `frontend/` and then
`uv run uvicorn app.main:app` from `backend/` — `npm run dev` alone cannot
reach the API (`output: "export"`, no rewrites; see `CLAUDE.md`).

Seeded users (password printed by `make seed`): **Alex** owns four
opportunities and views a fifth (Initech); **Blair** edits Northwind and owns
Initech; **Casey** views Northwind and Globex only (every write refused);
**Dana** has access to nothing — and, since 3.3a, watches Northwind anyway.

Click paths for this phase's new capabilities:

- **Type a bullet list in a note** (the roadmap's first acceptance line, and
  what was impossible before). Open Northwind as Alex, press **Add note** on
  any entry — the composer is one control until you write in it — and type
  `- ` then three items. The toolbar carries bold through quote; a link
  (`[text](url)`) and a heading (`### `) are typed, because a button for
  either has to open a dialog out of a composer. The note under **Intro call**
  is already seeded with a bold figure, a bullet list and a two-item
  checklist, so there is something to read before you write anything.
- **The three triggers**, in any composer on Northwind. Type `@bla` — Blair is
  offered by name and the address the notification is delivered by gets
  written, which is requirement 13's fix. Type `/` for the blocks, including
  the code block and divider no toolbar button carries. Type `#procure` for
  this deal's own entries; choosing one inserts a relative Markdown link
  (D-124) that opens the timeline with that entry scrolled to and marked. All
  three are keyboard-driven with the editable keeping focus — arrow keys to
  move, Enter to choose, `Escape` to close the menu **without** closing the
  composer or losing the draft.
- **@mention notifies** (the second acceptance line). Mention Blair, post,
  then sign in as Blair: the bell carries it. Dana, who shares nothing, is on
  nobody's `@` list — `GET /api/v2/opportunities/1/members` answers the owner
  and the live shares, and 404s anyone who cannot already read the deal.
- **Threaded comments.** The demo entry's note carries two threads: Alex's
  question about permissions, answered by Blair and **marked resolved** so it
  reads as one line ("Resolved by Alex Rivera" with Show beside it), and
  Blair's question about the pilot clause, still open. Reply sits on the
  thread rather than on each message, because a control on a reply would ask
  for what the API refuses. Sign in as Blair: Resolve is offered on their own
  thread but not on Alex's (author-or-owner). Sign in as Casey, a viewer:
  neither Reply nor Resolve.
- **Reactions.** Alex's resolved thread carries a thumbs-up from Alex and
  Blair plus an eyes reaction from Blair, as count pills with a "React"
  trigger revealing the fixed seven behind progressive disclosure. Reacting
  twice with the same emoji is a no-op, not a second row. Casey cannot react
  at all.
- **Watchers** — the one place existence is knowingly not hidden. Sign in as
  **Dana** and open `/opportunities/1`: the screen says the opportunity is not
  available *and offers a Watch toggle*, which is the only place
  watching-with-no-access has to render. Dana already watches Northwind in the
  seed data. `POST /api/v2/opportunities/1/watch` answers 200 for anyone
  signed in; reading Northwind itself still 404s, because watching grants no
  access. As Alex, the sharing panel's read-only "Watching" list names Dana —
  `GET .../watchers` is owner-only like the share list beside it.
- **Two browsers, live** (the third acceptance line: < 2 s). Open Northwind as
  Alex in one window and as Blair in the other. Add an entry in either; it
  appears in the other within a second, because the stream pushed an
  invalidation and the client refetched. Nothing about the row travelled the
  push path.
- **Concurrent note edits produce a 409** (the fourth acceptance line). With
  those two windows still open, press Edit on the same note in both. Save in
  one. Save in the other: it is **refused, keeps your draft**, and renames
  Cancel to "Discard my edit" — which is the "offer to reload" ADR 0003 asks
  for, rather than a silent clobber. Worth knowing why it works: the editor
  captures `updated_at` **when it opens**, not on save, because the live
  stream refetches the note underneath an open editor and reading the prop at
  save time would hand back the *other* person's write and pass the guard.
- **Exported PDF renders bold and lists** (the fifth acceptance line). Open an
  opportunity's export control and choose PDF. **This one needs the
  container** — WeasyPrint's native libraries are absent on a macOS host, and
  that single skip is the one test the suite runs fewer of on a laptop.
- **One activity log.** As Alex, open Northwind and press **History** beside
  the exports. The dialog is "Activity and history": the creation, the stage
  change and the sharing as the timeline records them, with "changed Value on
  this opportunity" and the note and entry edits in the same list. Open the
  Value row — 185,000 at Qualification becoming 162,000 — and **Restore** is
  offered on the version that edit replaced. Umbrella discovery shows the
  audit half, an entry deleted and restored. The button is offered to Blair
  and Casey too, and what they get is the events their role may already read:
  the system entries, and none of the edit rows.
- **The five bulk actions.** Check two cards (the checkbox, `x`, or
  shift-click for a range). All five are there now: change stage, assign
  owner, add to view, export, delete. **Assign owner**: type
  `blair@opptrail.test` — Alex stays on the deal as an editor rather than
  losing it, with the handover on the timeline, in the owner-only audit log,
  and as a notification to Blair, who did not ask to be given a deal.
  **Add to view** is what Alex's shortlist already holds — Northwind and
  Globex pinned, shown until Show all clears it, and `?opportunities.ids=`
  in the address bar. **Export CSV/JSON** downloads the checked deals as a
  spreadsheet of records, not one deal's document; an id the caller cannot
  read is absent from the file rather than refused.
- **The calendar's follow-up layer.** Switch the dashboard to Calendar:
  Northwind's demo entry shows up three days out as a reminder rather than a
  deal, linking back to its own timeline. `GET /api/v2/timeline/follow-ups` is
  scoped the way search is — Casey sees it, Dana sees nothing.
- **What 3.1a moved.** The timeline is now the first thing on the opportunity
  screen and reads newest-first by default; the record's fields sit in the
  right column beneath the AI panel; and there is one export control per
  opportunity with a format choice rather than two links.

**Left for the human's own judgment** (D-053's non-automatable half,
unchanged): timestamps read correctly in your own timezone, rendered Markdown
is readable, a PDF export is something you would actually send, and an AI
answer is grounded in the timeline it was asked about. The PDF one carries
more weight this phase than last, since 3.5 changed what it contains.

---

## 3. Decisions needing review

Every decision below is still flagged `needs human review: Y` in
`DECISIONS.md` as of this gate. Phase 3 recorded D-101 through D-135; eleven
need a ruling. The seven Phase 2 decisions the last packet raised are not
repeated — three were ruled at that gate and became milestones 3.0, 3.0a and
3.0b (D-101, D-070, D-088); the rest (D-078, D-090, D-093, D-096, D-097)
were accepted as shipped.

| ID | Question | Recommended | Alternative |
|---|---|---|---|
| D-102 | Who sees what in the merged activity log. The audit half and the version half are owner-only; system entries are visible to anyone with access. A view that merges all three has to answer per row. | **Filter per row by the rule of the source it came from** — changes no existing permission rule, so an editor asking what happened is answered with what they may read rather than refused. | **Widen**: show every reader with access *that* an edit happened, since a note already carries a visible "edited" marker and the feed reports the occurrence rather than the snapshot D-096 restricts. This is the better product and is genuinely defensible — recommended for a later milestone if the reviewer wants a shared deal's collaborators to see each other's edits, which is this phase's stated goal. A one-line change to `fetch_activity_page` plus its matrix row. Owner-only in full was the third option and is rejected: it would make "who did what when" available to one person per deal. |
| D-105 | Ownership transfer: who may, and what becomes of the previous owner. | **Owner-only, and the previous owner stays on as an editor.** Owner-only because every other write to an opportunity row is (name, value, stage, sharing, deletion) and giving the record away is the largest of them. Editor-after because a transfer is the one destructive-feeling action with no undo available to the person performing it: a mis-typed address would otherwise remove the deal from their board with no way back. | **The clean break** — the previous owner loses the deal entirely, which is what a reader who expects "transfer" to mean "it is no longer mine" would predict. Dropping the leftover grant is one line and one test. (Leaving them a *viewer* was considered and rejected as the worst of both.) |
| D-106 | What "add to view" adds to. A saved view is a filter/sort spec, not a curated set of ids. | **Write the selection into the view's `filters` as an `ids` filter**, read by the client like every other filter. This is the shape the app already has — `filters` is literally a saved `URLSearchParams` — so a pinned selection survives a reload, is shareable by URL, and is permission-filtered per reader, with no migration. | **Build view membership** (a `saved_view_opportunities` table, a membership read, and a rule for how members and filters combine). That is a Phase 6-sized feature and should be scheduled as one if the human wants folders rather than filters. The consequence of what shipped, stated plainly: nothing "belongs to" a view, and a pinned deal still shows even if it stops matching the view's other filters. |
| D-107 | Multi-record export: the action bar has a selection, but `routes_export.py` generates one document per opportunity. | **A `GET` of its own with the ids in the query string** (`/opportunities/export/{csv,json}?ids=`), answering with a file — so the action stays a plain `<a href>` like the three links on an opportunity's own screen, with the permission filter inside the query. CSV and JSON of the opportunities' own fields; **PDF deliberately not offered**, because a list of deals is a spreadsheet. | A fourth action on `POST .../bulk` cannot work (that endpoint answers per-id results and a file has no room for them). If the reviewer wants a selection to export as one PDF per deal in an archive, that is a Phase 4 item beside the attachment work, not a formatter change. |
| D-109 | Which surfaces the rich composer replaces. Finding 10 names notes and comments; a timeline entry's body was a textarea *printed as plain text*. | **All three content surfaces** — one composer, one renderer. Requirement 17 is "sanitized Markdown rich text", not "in notes", and an entry body is the field a call gets logged into. It is also what makes 3.5 coherent: rendering notes as Markdown while escaping entry bodies is half a fix. | **Notes and comments only** (one line). Cost of what shipped, stated plainly: an existing entry body containing a Markdown character now renders as Markdown — `*` around a word becomes emphasis. That is the same exposure notes and comments have had since the MVP, and no stored text changed. |
| D-110 | Whether a composer is open on arrival. The old ones were a single-line `<input>`, always on screen, one per entry and one per note. An editor is a ProseMirror view with its own document and plugins. | **Collapse each composer to the control that opens it**, mounting the editor when someone writes in it — which is what `docs/UX.md` already specifies for the entry composer, generalised. The draft lives in the `Composer`, so `Esc` or Cancel keeps what was written. | **Mount the editor everywhere the input used to be** — reads as "the composer is already open", at the cost of one editor per entry plus one per note on a fifty-entry timeline. Two visible consequences of what shipped: adding a note takes a click before typing, and posting closes the composer rather than clearing it. |
| D-111 | Slash commands. The roadmap's Phase 3 outcome names "slash commands and @mention autocomplete" together; 3.1 was the editor and 3.2 the mention autocomplete. | **Build the slash menu in 3.2 beside the mention autocomplete** — they are one `@tiptap/suggestion` mechanism with two triggers, and building it twice is the duplication `AGENTS.md`'s standards rule out. Nothing was lost in between: every block the menu inserts is on the toolbar or has a Markdown input rule. | **Build it in 3.1**, where a reader of the roadmap would expect it. Both shipped inside this phase either way; the ruling asked for is whether moving a roadmap-named capability one milestone sideways is acceptable. |
| D-121 | Milestone 3.1c's other half: what is actually removed when an activity row can expand, and whether the before/after ships with the feed or is fetched on expand. | **Remove the three History buttons and the sharing panel's audit disclosure**, leaving the activity log as the only destination, **and have the opened row read the item's existing `GET .../versions`.** Nothing a reader could see is lost: deletions and restores already reach an owner as sentences, and access changes carry the person and the role in words on the system entry beside them, so requirement 18 still holds — on one screen instead of three. Fetching on expand also means a forty-edit timeline opens with zero history requests. | Keep the History buttons and only add audit rows to the feed; or send a `changes` array with the feed. The second is the one worth naming as rejected: a version's fields render through per-kind read functions (`value` becomes "USD 485,000" using `currency` from the same snapshot), which a per-field before/after cannot supply — it would have meant a visible regression in how history reads, or a second formatting path built for this screen only. **This retires two surfaces the human used at the 3.1 checkpoint**, which is why it wants an explicit confirmation. |
| D-123 | The `@` list needs the people a mention can reach, and no route answered it. `GET .../shares` is owner-only and has no row for the owner. | **A new `GET .../members`** (owner + live shares), `require_opportunity_access`. The set has to be the one a mention actually reaches, since `notify_mentions` only notifies a user in `get_accessible_user_ids` — an autocomplete over anything else offers people whose mention silently does nothing. | Widen `GET .../shares` to every role (it carries who invited whom and when, which is the sharing panel's owner-only business), or keep it owner-only and leave two thirds of the roles typing addresses by hand. **What shipped does widen something deliberately:** an editor or viewer can now read the other participants' names *and email addresses* on one deal they can already read. The names are already on every entry and comment; the addresses are new. The reviewer's call is whether that visibility is acceptable at 20 known internal users. |
| D-129 | `FEATURES.md` §7 names "follow an opportunity you are not shared on." Every other opportunity-scoped route 404s an outsider so existence never leaks. Watching cannot go through that gate. | **A new `require_opportunity_exists` check — presence only, no role — used by the three `.../watch` routes and nowhere else**, accepting that any authenticated caller learns whether an id is live. What leaks is narrow (that an id exists, not its content, owner or anything a share reveals), and a caller could already infer liveness from any endpoint's 404 one call later. `GET .../watchers` stays owner-only, so the exception does not widen who reads the *result*. | Require a share to watch — which keeps existence hidden but ships a different feature than the one named, a "follow" role indistinguishable from a viewer share with no read rights. **This is the one place in the app where existence is knowingly not hidden behind access**, which is why it is here even though invariant 7 itself is untouched. Narrowing it later is a `permissions.py` change plus a migration, not a data-model change. |
| D-132 | The note edit guard: is `updated_at` optional or required, and is it the right token given second-resolution timestamps? | **Required, and `updated_at` as ADR 0003 words it.** An optional guard is no guard — the client that omits the field is precisely the one that clobbers. The break is fully absorbed inside this repo (one client, the value already on `NotePublic`, and the seed tool and test suite echo back what they read), and it is recorded in `docs/ROADMAP.md`'s breaking-changes table. | Optional (enforce when sent), or use the note's latest `note_versions.version_number`, which is exact and monotonic but adds a field whose only purpose is this comparison and deviates from the ADR. The imprecision accepted: two edits inside one second carry the same `updated_at`, the same window D-067 already accepted for undo's delete stamp — and inside it the ADR's own fallback applies (last-write-wins with full version history, so a clobbered edit is recoverable rather than lost). Documented on `update_note` and pinned by a deterministic clock. **This is the phase's one client-visible API break**, which is what the breaking-changes table exists to surface at a gate. |

Two ADR-level notes. **No ADR was written this phase** because none was
needed: ADR 0003 already fixed the real-time transport (SSE), the
invalidation-not-payload rule and the conflict model, and 3.4 implements it —
the decisions it left open are D-131 through D-134, of which only D-132 needs
a ruling. No decision changed the stack, and both migrations
(`20260924_0007`, `20260925_0008`) are ordinary schema additions under ADR
0002's Alembic ownership, with `tests/data/expected_schema.sql` updated.

---

## 4. Quality evidence

**Sandbox half of the split gate** (brief §3.4), run in full this session
after the seed-tour fix in §1:

```
ruff check .                      All checks passed!
ruff format --check .             88 files already formatted
mypy app tools                    Success: no issues found in 42 source files
frontend typecheck (tsc)          clean
frontend lint (eslint)            clean (0 errors, 3 warnings — see below)
prettier --check                  All matched files use Prettier code style!
backend pytest                    458 passed, 98.08% combined line+branch
                                   coverage (--cov-fail-under=90 enforced);
                                   the ≥95%-branch modules all at 100%
                                   (permissions, audit_utils, auth,
                                   soft_delete, routes_ai, versioning), and
                                   this phase's new modules at 100% too
                                   (activity.py, events.py, routes_events.py)
frontend vitest                    530 passed (34 files), 97.13% statements /
                                   91.35% branch / 95.71% functions / 97.09%
                                   line (thresholds 96/96/95/90 all met)
API-contract check                generated client (lib/api-types.ts) current
pip-audit                         No known vulnerabilities found
npm audit                         found 0 vulnerabilities
Playwright E2E + axe              69 passed (22 specs), axe clean on every
                                   screen in both light and dark
                                   (prefers-color-scheme emulation);
                                   DEFERRED_AXE_RULES still empty
Docker build + smoke test         deferred to the host — no Docker socket in
                                   this sandbox (sandbox/README.md)
```

**The three eslint warnings, named rather than left for the reviewer to
find** (0 errors; eslint exits clean, so the gate is green):
`MarkdownText.test.tsx:58` an unused eslint-disable directive and
`VirtualList.tsx:43` the React Compiler's "incompatible library" skip on
`useVirtualizer` are both pre-existing and were in the Phase 2 packet.
The third is new in 3.1: `MarkdownText.tsx:71` reports `'_node' is defined
but never used` for `input: ({ node: _node, ...props })`, where the
destructure exists precisely to keep `node` out of the DOM spread. It is
informational, and left rather than fixed at the gate because changing code
during the gate session would invalidate the run it is evidenced by.

**Coverage vs. previous phase** (Phase 2's gate → this gate):

| | Phase 1 gate | Phase 2 gate | Phase 3 gate |
|---|---|---|---|
| Backend tests | 258 | 338 | 458 |
| Backend coverage | 97.28% | 97.27% | 98.08% |
| Frontend tests | 102 | 429 | 530 |
| Frontend line coverage | 88.38% | 97.07% | 97.09% |
| Frontend coverage thresholds | 85/85/85/78 | 96/96/95/90 | 96/96/95/90 |
| E2E tests | 18 (7 specs) | 57 (17 specs) | 69 (22 specs) |
| Authorization-matrix endpoints | 47 | 52 | 69 |

Coverage floors (brief §6.2) all met with room: backend ≥ 90% line / ≥ 80%
branch (98.08% combined), frontend ≥ 80% line (97.09%), and the
auth/permissions/soft-delete/audit/AI modules ≥ 95% branch (all at 100%).
Full per-milestone history and module breakdowns: `docs/autopilot/COVERAGE.md`.

**New invariant and authorization tests this phase.** The authorization
matrix grew from 52 to **69 endpoints** — the activity log, the members read,
the follow-ups read, bulk export, the two multi-record export routes, three
version-restore routes, resolve/unresolve, reactions, the three watch routes,
the watchers read, and the event stream — and every one landed with its
milestone, because a route with no matrix entry fails the build. One new
`test_invariant_*`: `test_invariant_resolving_a_thread_writes_no_body`
(3.3), which pins that resolving a comment changes no `body` and so does not
become the comment PATCH invariant 2 forbids. `test_soft_delete.py`'s
hard-delete scanner was extended rather than relaxed: `reactions` and
`watchers` are deliberately outside `USER_DATA_TABLES` (D-130), for the same
reason `sessions` is.

**Five new E2E specs** (`18` through `22`): rich text typing and the Markdown
input rules, the three suggestion triggers, threaded comments, reactions and
watchers, and live updates in two real browser contexts. Of brief §6.3's
journeys, **journey 5 (@mention → recipient notified)** is now the
autocomplete path as well as the typed one (`04-mentions.spec.ts`,
`19-suggestions.spec.ts`); **journey 3 (edit note → edit marker → revision
history)** was rewritten for 3.1c's single destination. No journey was newly
completed this phase: **journey 11** (export respects permissions) has been
present since Phase F in `05-export.spec.ts` with its PDF case guarded on
WeasyPrint being importable, and **journey 7** is still the adapted half the
Phase 2 packet described (custom fields are Phase 6). What remains is
**journey 4** (attachments — Phase 4), **journey 9** (stalled flag → reminder
notification) and **journey 10** (automation on stage change — Phase 6). The
stalled flag itself has existed since the MVP; what journey 9 still needs is
the *delivery* of a reminder, which no phase has built — the nearest roadmap
line is Phase 6's "a rule that pings you when a deal goes quiet", so that is
where it should land unless the human would rather see it with Phase 5's
notification preferences.

**Host half of the split gate: outstanding.** Run
`scripts/autopilot-gate.sh 3` against this branch's tip commit — it builds the
image from the branch, runs `make docker-test` (the backend suite inside the
image, where the WeasyPrint PDF test actually executes) and
`make docker-smoke`. `scripts/autopilot-accept.sh` will refuse to accept
without that receipt. **This matters more this phase than last**: 3.5 changed
the PDF renderer, and the one test that renders a real PDF is the one test
that cannot run in this sandbox.

---

## 5. Risks and known limitations

- **The PDF renderer changed and its end-to-end test runs only in the
  container** (3.5). `render_export_html` is covered directly in the sandbox —
  including a hostile body posted straight to the API and a forced
  `html: True` proving the sanitizer underneath — but the WeasyPrint render
  itself is the single skip on a non-Linux host. Verify a PDF you would
  actually send, in Docker.
- **The note edit guard is a client-visible API break** (D-132). Any caller of
  `PATCH /api/v2/notes/{id}` that omits `updated_at` now gets a 422. There is
  one client and it was updated in the same milestone, but this is the row in
  `docs/ROADMAP.md`'s breaking-changes table.
- **Two edits inside one second share an `updated_at`** and the guard cannot
  tell them apart (D-132). Bounded, documented on `update_note`, and inside
  that window ADR 0003's stated fallback applies: last-write-wins with full
  version history, so the clobbered edit is recoverable.
- **A revoked role does not close an open stream.** `routes_events.py` checks
  access at the handshake and never re-checks; a reader whose share is removed
  mid-connection keeps receiving invalidations, and the refetch each one
  provokes is the read that answers 404. No content travels this path either
  way, so nothing leaks — but the stream outliving the grant is worth knowing.
- **Watching tells any signed-in caller whether an opportunity id is live**
  (D-129) — the one deliberate exception to "absence of access is a 404", and
  the item in §3 most worth a ruling.
- **Every role on a deal can now read the other participants' email
  addresses** (D-123), where before that was the owner's view. Scoped to one
  opportunity the caller can already read.
- **Entry bodies that contain Markdown characters now render as Markdown**
  (D-109). No stored text changed, and this is the exposure notes and comments
  have had since the MVP, but an old entry body with a stray `*` will look
  different.
- **Two surfaces the human used at the 3.1 checkpoint are gone** (D-121): the
  per-item History dialogs and the sharing panel's audit disclosure. The
  information is all on the activity log, and both endpoints still exist —
  but if the replacement does not read as well as what it replaced, that is a
  reject-worthy judgment call and the packet is the place to make it.
- **A non-owner's activity log is a smaller answer than an owner's** (D-102) —
  correct per row, and possibly not the product the phase's goal implies.
- **The activity log merges five queries in Python**, each asked for
  `limit + 1` rows past the cursor. Exact, and untested above a few hundred
  rows per opportunity; the performance budget work is Phase R.
- **`grouped_key` and the boolean `notification.read` column are still
  carried unread** (D-095) — unchanged this phase, listed because Phase 5's
  digest work is what retires them.
- **The Docker build and smoke test have not run against this commit** — the
  one piece of §3.4 outstanding; see §4's host-half note.

---

## 6. Out-of-scope items noticed, logged not built

- **Nothing new was proposed or built outside `docs/ROADMAP.md`'s Phase 3
  scope plus the three milestones the human's own Phase 2 rulings added**
  (D-101 → 3.0, D-070 → 3.0a, D-088 → 3.0b). No CRM contact database, lead
  scoring, outbound pipeline, general project management, billing or SSO
  surface was introduced, consistent with brief §2 invariant 8.
- Several decisions this phase are scope *narrowings* inside planned
  milestones rather than newly noticed capability gaps, and are in §3 rather
  than here: D-107 (bulk export is CSV and JSON of records, not PDF and not
  whole timelines), D-106 (a pinned view is a filter, not a membership model),
  D-111 (slash commands moved from 3.1 to 3.2), D-127 (replies are one level
  deep, though the column could hold a tree).
- Two capabilities were touched at their edge and deliberately left where the
  roadmap puts them: inline attachments in the composer (Phase 4, where
  attachments exist at all) and digest batching over `grouped_key` (Phase 5).
- **D-128 records one thing not added to the audit log**: resolving a thread
  is read where it happened — the thread names who closed it and when — and
  putting it in the audit log would widen `AGENTS.md` invariant 7 past
  deletions and sharing. Flagged `needs human review: N` because the
  permission rule is the existing one, and noted here because it is a
  deliberate gap in an auditability mechanism.

---

## 7. Preview of next phase

Phase 4 — Tasks and Attachments (`autopilot/phase-4`, depends on the
`phase-3-accepted` tag). Goal: capture the two artifacts a deal actually
produces — the next action and the document. Milestones per `PROGRESS.md`:

- **4.1** Task model scoped to an opportunity; My Tasks across opportunities;
  overdue and upcoming surfaces on the dashboard. Schema: `tasks`.
- **4.2** Migrate `timeline_entries.follow_up_date` into tasks, keeping the
  column until the UI has moved (dropped in Phase 5 per the breaking-changes
  table).
- **4.3** Attachments: content-addressed storage, magic-byte validation,
  streamed authorized download, `Content-Disposition: attachment` and
  `nosniff` (ADR 0008). Schema: `attachments`. This is what Phase F's
  `uploads.py` was stood up for.
- **4.4** PDF export gains an attachment manifest.

Decisions worth settling before Phase 4 begins, because they shape what it
builds rather than only how this phase reads:

- **D-102** (who sees edit rows in the activity log). Phase 4 adds tasks and
  attachments, both of which will want activity rows of their own; whether a
  non-owner sees them is the same question, and answering it once now is
  cheaper than answering it per feature.
- **D-129** (watching as the existence-leak exception). 4.3's attachment
  downloads are the next route family where "404 for an outsider" is
  load-bearing, and ADR 0008's threat model assumes it holds everywhere.
  If the reviewer wants watching narrowed, narrowing it before another route
  family is written against the norm is the cheap moment.
- **D-107** (bulk export's formats). 4.4 adds an attachment manifest to the
  per-opportunity PDF; if a selection should also export as PDFs in an
  archive, that belongs beside 4.4 rather than as a later formatter change.

3.0b's follow-up calendar layer is also worth a second look during 4.2:
it reads `timeline_entries.follow_up_date` directly, so the migration into
`tasks` is where that read moves rather than a second source of truth.
