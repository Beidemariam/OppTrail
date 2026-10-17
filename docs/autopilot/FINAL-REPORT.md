# Final report

Milestone R.9. What shipped, what it costs, what is not reversible, what is
still open, and what I would do next. Written to be read once, at the gate,
by the person who has to decide whether this is finished.

Branch `autopilot/phase-R`, nine milestones, nothing pushed to a remote.

---

## 1. What shipped

Sixteen scope items in `AGENTS.md`; **fifteen shipped, one deferred** (email,
item 5, deferred to v3 by **D-141** with ADR 0009 kept as the record of how it
would be built). `CHANGELOG.md` is the per-phase summary;
`docs/autopilot/PROGRESS.md` is the milestone detail with the reasoning inline.

| Phase | Accepted | What it was |
|---|---|---|
| F | 2026-09-16 | Reconnaissance: one authorization boundary, the canonical timestamp, soft deletes with an audit row per deletion |
| 1 | 2026-09-20 | Alembic, request security, structured logging, notifications, FTS5 search, health, backups, CI |
| 2 | 2026-09-23 | Four views over one dataset, linkable view state, saved views, design tokens in both themes, keyboard map, bulk actions, undo, the v2 API boundary |
| 3 | 2026-09-29 | One Markdown composer with three typed triggers, threaded comments, reactions, watchers, SSE live updates, one activity log, editing where content is read |
| 4 | 2026-10-09 | Tasks with several assignees and their own discussion, attachments, exports carrying them, search landing on the match, the labelled AI context |
| 6 | 2026-10-13 | Custom fields, six live reports, automations, the AI expansion, the scheduler |
| R | *awaiting this review* | The layout pass, privacy, accessibility, performance, the container, data safety, CI, seed data, documentation |

Phase 5 is email and is the deferred one; the numbering is kept so every
reference to a phase by number stays true.

### Phase R in one line each

- **R.1 / R.1b** — the layout the human chose from four drawn options, then
  privacy in two shapes at their request mid-phase.
- **R.2** — the accessibility audit had been measuring WCAG 2.1 while the bar
  said 2.2; now 2.2, with six unaudited screens added and a real 2.4.11 failure
  fixed.
- **R.3** — measured at 805,220 rows; one read was slow and it was not the one
  the plan expected.
- **R.4** — ADR 0011's healthcheck, which three documents described and nothing
  implemented.
- **R.5** — backups now carry the uploads, which was the other half of ADR 0011
  item 2.
- **R.6** — `make check` in CI, and an `npm audit` ratchet because the one
  advisory this tree carries has no fix anywhere.
- **R.7** — the seed covers Phase 6 and R.1b, and `make seed-scale` layers the
  confirmed scale on top of the demo data.
- **R.8** — eight documents, one per audience.

---

## 2. What it costs to run

Measured on a laptop against the corpus `AGENTS.md` specifies — 400 deals,
80,000 entries, **805,220 rows** — through the real HTTP stack
(`tests/test_performance.py`, `make seed-scale` builds the same corpus):

| Read | Owner | Shared reader |
|---|---|---|
| Board, first page | 2.5 ms | 2.5 ms |
| Whole board (8 pages, what the client reads) | 18.7 ms | — |
| A deal's timeline, first page | 3.6 ms | 3.4 ms |
| Activity log | 2.9 ms | — |
| My tasks | 7.2 ms | — |
| Inbox | 9.2 ms | — |
| Search | 182.4 ms | 24.7 ms |
| Export one deal (JSON) | 5.1 ms | — |
| Six dashboard aggregates | 20.1 ms | — |
| `/api/health` | 1.2 ms | — |

Search is the slowest read and the only one above 25 ms; the owner's is slower
because they can read every deal, so more rows are ranked and more snippets
built. It is less than half its 400 ms budget. The six aggregates each hold
inside §10's own 300 ms criterion with an order of magnitude spare.

ADR 0001's bet — SQLite, one container, no broker — holds at the confirmed
scale with room to spare. Its revisit triggers are unchanged: multiple
writers, or no local disk.

---

## 3. Coverage and the test suites

| Suite | Count | Coverage |
|---|---|---|
| Backend (`pytest`) | **757** passed, 1 skipped | 97.3% statements |
| Frontend unit (`vitest`) | **770** passed, 46 files | 96.3% statements, 90.2% branches |
| End-to-end (Playwright) | **112** passed, 1 skipped | 30 spec files |

Both skips are the documented WeasyPrint gap: PDF rendering needs native
libraries absent on a macOS host, so one backend test and one e2e test skip
here and run in the container, which is where `make docker-smoke` proves the
PDF path (9,944 bytes, `%PDF` verified).

Floors (brief §6.2, never lowered): backend ≥ 90% line / ≥ 80% branch, ≥ 95%
branch on auth, permissions, soft-delete, audit and AI modules; frontend ≥ 80%
line. `docs/autopilot/COVERAGE.md` is the history, including what each
milestone's tests *found* rather than only what they cover.

### The suites that carry rules rather than features

Four, and they should not be treated as ordinary tests:

- **`test_authorization_matrix.py`** — every endpoint × {owner, editor, viewer,
  unrelated, anonymous}, with the endpoint list read out of the running app.
  **A new route with no entry fails the build.** 105 tests.
- **`test_invariants.py` and its three outposts** — 17 `test_invariant_*`
  tests for the rules the product may not break: the AI has no write tools and
  its data layer refuses writes, no comment edit route exists, resolving a
  thread writes no body, an edit keeps its previous version, deleting leaves
  the row, `event_timestamp` is editable and `created_at` is not, the stage
  list is fixed, untrusted content is labelled, no hard deletes of user data,
  a rule cannot trigger a rule, and a sealed entry is in nobody else's AI
  context.
- **`test_soft_delete.py`** — fails the build if any module in `app/` contains
  a `DELETE FROM` against a user-data table. This is the test that caught R.1b
  hard-deleting notifications.
- **`test_seed.py`** — keeps `make seed`'s printed tour true. This is the test
  that caught R.7's missing private entry.

### The e2e suite, by what it protects

30 specs. Four earn their keep in ways a unit test cannot:

- **`07-accessibility.spec.ts`** — axe on every screen, in both themes, at
  WCAG 2.2 AA.
- **`23-responsive.spec.ts`** — eight widths from 1440 to 420 across eight
  screens, failing on any control taller than wide or any page that scrolls
  sideways. Nothing in this project measured a rendered box before it, which
  is how a defect visible at three gates survived three phases.
- **`30-focus-and-keyboard.spec.ts`** — the half of 2.2 AA axe cannot answer:
  focus never entirely hidden (walked forwards *and backwards*, which is the
  direction that fails), the skip link actually moving the keyboard, and a
  single-pointer alternative on every draggable card.
- **`22-live-updates.spec.ts`** — two browsers on one deal.

---

## 4. Decisions that cannot be undone

218 decisions are recorded in `docs/autopilot/DECISIONS.md`. These are the ones
that would be expensive or impossible to reverse, and the reason each was
taken:

1. **22 Alembic revisions** (ADR 0002). The schema is append-only in practice:
   every revision has a `downgrade()`, but data written under a later schema
   does not survive going back. Two columns are deliberately frozen rather than
   dropped — `notifications.read` (**D-095**) and `tasks.assignee_id`
   (4.6) — because dropping a column nothing reads is a migration with no
   client-visible benefit.
2. **v1 of the API is gone** (milestone 2.9). Every client calls `/api/v2/*`;
   the old paths 404 and a parametrized test keeps them doing so.
3. **Attachments are content addressed** (**D-147**, amending ADR 0008). A
   file's name is its SHA-256, which deduplicates and makes the backup mirror
   sound — and means the stored name cannot be derived from anything else.
   Nothing prunes a blob (**D-149**), so the only safe predicate for deleting
   one would have to consider a soft-deleted row and a restorable backup.
4. **The FTS5 index is contentless** (ADR 0007) and its rowid encoding —
   `source id * 8 + kind code` — is written twice, as constants in `search.py`
   and arithmetic in a migration's triggers. A fifth document kind needs the
   base widened again, as **D-167** did for the fourth.
5. **`opportunities.last_activity_at` is maintained by triggers** (**D-201**).
   A derived value stored in the schema: `tests/test_stalled.py` is what makes
   it trustworthy, and a new write path to entries, notes or comments inherits
   the triggers rather than having to remember a call.
6. **New entries are private by default** (**D-196**). One constant, so the
   default is reversible — but entries already written under it are not
   retroactively shared, and the suites now state the visibility they mean.
   **This is the open ruling in §6.**
7. **Timestamps are fixed-width UTC text**, compared lexicographically. A
   different format does not look wrong, it *sorts* wrong, and there are now
   ~800,000 rows written in the canonical one.
8. **Soft deletes everywhere.** No purge exists in the application; a real
   deletion is a database-admin action outside it. That is the MVP's ruling and
   the whole audit story rests on it.

---

## 5. Open blockers

**None.** `docs/autopilot/BLOCKERS.md` records one standing constraint rather
than a blocker: the autopilot sandbox has no Docker socket, so the image build,
the in-image backend suite and the smoke test are deferred to the host. All
three were run on the host for Phase R and pass — the smoke test now also
covers R.4's two probes and the container reaching `healthy`.

One known-and-accepted advisory: **GHSA-vfj7-8cjw-p6xm** (`braces`, high, no
fix published anywhere). It is allowlisted in `scripts/audit-gate.mjs` with the
reason — lint-time only, over this repository's own configuration, and absent
from the shipped artifact entirely — and the gate fails if it ever stops
appearing, so the entry cannot outlive the problem.

---

## 6. What needs you

Three things, in the order they matter:

1. **The default for a new entry** (**D-196**). Private-by-default is running
   because you asked for it. Flipping it broke 132 backend tests, every one a
   scenario where one person writes and another reads — that is the honest
   measure of how much of this app assumes a shared timeline, not an argument
   either way. It is one constant. Use it for a few days and rule.
2. **The three R.1b checks** on the shakedown page — a sealed entry from both
   sides, the notification withdrawal, and the notebook. They are the only part
   of R.1b a test cannot answer.
3. **Two write surfaces you may want narrower.** Defining a custom field
   (**D-171**) is open to any signed-in person, because `FEATURES.md` says
   "admin-defined" and this app has no admin role; creating an automation rule
   (**D-173**) is likewise open, though a rule can only ever act with its
   creator's own authority. Both are recorded as the widest surfaces in the
   application, both are pinned by the authorization matrix, and neither is a
   ruling I can make from the requirements.

---

## 7. What I would do next

In the order I would do it, with the reason:

1. **Answer §6's three.** Two are rulings and one is twenty minutes of
   clicking; everything below is cheaper once they are settled.
2. **Copy backups off the box.** `docs/operations.md` says plainly that
   `backups/` is on the same volume as the database, which protects against a
   bad write and not against losing the disk. A `cron` line and a destination
   is the whole job, and it is the single largest gap between "this works" and
   "this is safe".
3. **Email (scope item 5, ADR 0009)** if it is still wanted. It is the one
   deferred item, it is the highest-risk thing left — the first untrusted input
   path into a shared record and into the AI's context — and ADR 0009 plus
   Phase 5's nine milestones in `PROGRESS.md` are a complete plan for it.
4. **A scripted real-model check for the AI.** The read-only guarantee is
   structural and proven; the model's *obedience* to "you cannot read inside an
   attachment" is behaviour, and the test suite forbids the live call that
   would prove it (**D-169**). One script, run by hand before a release, closes
   the only honest gap in §3 of `docs/ARCHITECTURE.md`'s AI section.
5. **Digest batching** (scope item 9's last clause). `notifications.grouped_key`
   exists and is deliberately unpopulated so this is a query change rather than
   a migration — "3 new comments on Acme Expansion, not three emails".
6. **A dependency bot**, which would make `D-204`'s base-image decision
   obsolete: with something to refresh a digest, pinning both base images by
   digest becomes the better answer than pinning by tag.
7. **Two deferred UI judgements**, both small and both yours: a Details card in
   the deal's rail (**D-188**, dropped because the record band already carries
   those fields), and widening the activity log so a non-owner can see that an
   edit happened (**D-102**).

## What I would not do

- **Add infrastructure.** Every measurement in §2 says the single container is
  not the constraint. ADR 0001 names what would change that.
- **Move the board's filtering into SQL** (**D-202**). Measured: it would save
  at most 16 ms on a read that happens once per visit, while splitting one
  tested pure function across two languages and costing the keyboard cursor,
  the bulk selection and the calendar their shared list.
- **Drop the two frozen columns** without a reason to touch those tables
  anyway. The migration has no client-visible effect and the risk is not zero.
