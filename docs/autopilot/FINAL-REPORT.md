# Final report

Milestone R.9. What shipped, what it costs, what is not reversible, what is
still open, and what I would do next. Written to be read once, at the gate,
by the person who has to decide whether this is finished.

Branch `autopilot/phase-R`, nine milestones plus R.1c. **Accepted and tagged
`phase-R-accepted` on 2026-10-21**, then merged to `main` and pushed. This
report was written at R.9, before the two review rounds and before acceptance;
what those rounds and the maintenance since have changed is corrected in
place, dated, and attributed to a decision.

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
| R | 2026-10-21 | The layout pass, privacy, accessibility, performance, the container, data safety, CI, seed data, documentation |

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

Measured on 2026-10-29 at `e67b1fb`, which is eight days past the accepted
commit; the R.9/R.1c figures and what moved them are below the table.

| Suite | Count | Coverage |
|---|---|---|
| Backend (`pytest`), host | **772** passed, 1 skipped | 97% combined |
| Backend (`pytest`), in-image | **773** passed, **no skips** | 97.58% combined |
| Frontend unit (`vitest`) | **777** passed, 46 files | 96.23% statements, 90.03% branches |
| End-to-end (Playwright) | **113** passed, 1 skipped | 30 spec files |

**The in-image row is the one that covers the PDF export**, and it is here
because the host row structurally cannot: `make docker-test` runs the same
suite inside the image, where `weasyprint` imports, so the 773rd test is the
772 plus the one skip. Any change to the PDF path gets checked there.

**The frontend count moved 778 -> 777** and that is a test deliberately
removed, not one lost: D-219's fix made the sticky padding measure itself
instead of carrying a literal, so `AppShell.test.tsx`'s "tells the document
which sticky stack the screen has" had no literal left to assert against
(commit `41ce749`).

**The e2e row in the version of this report written at R.9 said 112 passed,
and that was not true** (**D-213**). The suite was red on the committed phase:
milestone R.7's seed wrote Alex a notebook, and a spec written four milestones
earlier in R.1b waits for the empty-state notebook trigger, so it timed out
deterministically. It was found by running the suite at the review rather than
by trusting this table — which is the same way the other two corrections below
were found, and the reason this row now carries a measured number and a date.

Two more claims from R.9 that needed correcting, both recorded as decisions
rather than quietly edited:

- **The documented restore never reached the deployment** (**D-214**). It
  overwrote a scratch file beside the code and reported success.
- **"axe clean at WCAG 2.2 AA" was narrower than it sounded** (**D-219**):
  clean at one viewport, at rest. Both criteria 2.2 added that this project
  can check had something wrong — `--sticky-deal` was 66px short of the real
  sticky chrome at 1024, which is a focused control two thirds hidden under a
  band, and the audit that would have caught it only ever ran at 1280.

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

**No known advisory, and the allowlist is empty** (updated 2026-10-29,
**D-223**). R.6's one entry was **GHSA-vfj7-8cjw-p6xm** (`braces`, high, no fix
published anywhere) — allowlisted because it was lint-time only, over this
repository's own configuration, and absent from the shipped artifact entirely.
It stopped being reported while `braces@3.0.3` sat unchanged in the tree, so
the advisory was withdrawn upstream rather than fixed here, and D-207's second
failure mode — an allowlisted advisory that no longer appears also fails —
is what reported it. The entry is removed; the mechanism stays, with nothing
in it.

**Dependency advisories have gone red three times since R.6 locked the
lockfiles**, every time within days and every time after a gate had passed
green (D-220, D-223). None was a code defect and all had fixes available. It is
the one recurring maintenance cost this project has, and §7 item 6 is the
answer to it.

---

## 6. What needed you, and what you decided

All three are answered, in two review rounds. The record matters because each
was a product judgement I could not make from the requirements.

1. **The default for a new entry** stays **private** (**D-196**). Ruled at the
   R.1b round after using it, which is what was asked for.
2. **The three R.1b checks passed** — a sealed entry from both sides, the
   notification withdrawal ("yes it does take it away"), and the notebook,
   which neither the export nor the AI picks up. Both shapes stay. And the
   check produced a reversal: *"better not to mention anything instead of
   saying it is kept private"* — so a sealed entry is now **absent** from a
   colleague's timeline rather than standing there emptied, and the numbering
   counts per reader so no gap is left where it was (**D-209**).
3. **Both wide write surfaces are narrowed** (**D-215**): *"both have to be
   done by the owner."* Defining a custom field and writing an automation rule
   are an administrator's, named in `ADMIN_EMAILS`. Reading stays open.

Two more things the rounds settled:

- **Backups need a schedule outside the application** — a cron line, chosen at
  the gate. The in-process job had fired **zero** times in six days against
  154 automation ticks, because an interval's first firing is one interval
  after boot and the machine sleeps. Built as a **`launchd` LaunchAgent**
  instead (**D-221**), raised with the reviewer rather than substituted
  silently: cron skips a job it sleeps through and keeps no record of having
  skipped it, which is precisely how the in-process scheduler came to take no
  backups at all. `docs/operations.md` carries both forms, and the offsite copy
  is live.
- **The sign-in screen** opened on *Create account*. It opens on sign-in now,
  with the account link under the form.

### What the review rounds found that no test did

Worth keeping, because it is the fourth time running on this project:

- The **documented restore never reached the deployment** (**D-214**). It
  copied a real snapshot over a scratch file beside the code and reported
  success. Every test in `test_backup.py` points the database at its own
  temporary directory, so the snapshot and the live database were the same
  database by construction and the defect was invisible to the design of the
  tests.
- The **activity log still announced a sealed entry** to the deal's owner
  (**D-210**) — existence, author, time, which fields changed.
- The **14-day rule had a fourth copy** in the one feature named after it
  (**D-211**): 112 ms a tick against under 1 ms.
- The **end-to-end suite was red** on the committed phase (**D-213**), which
  is the one claim in §3 of this report that was not true when it was written.
- The **scale corpus belonged to the wrong user** (**D-212**), so a person
  following R.7's own tour could not find any of the 805,000 rows they had
  just built.

## 7. What I would do next

In the order I would do it, with the reason. **The first two are done**, both
after acceptance; they are kept rather than deleted so the list stays readable
against the two review rounds that produced it.

1. ~~**Answer §6's three.**~~ **Done** — all three were ruled on across the two
   rounds, and §6 records each answer.
2. ~~**Copy backups off the box.**~~ **Done** (**D-221**), as a `launchd`
   LaunchAgent to iCloud Drive rather than the cron line named at the gate,
   because cron would have reproduced the very defect it was installed to fix.
   This was called "the single largest gap between 'this works' and 'this is
   safe'" and it is closed: the offsite snapshot verifies with
   `integrity_check ok` and every attachment digest its live rows reference
   present in the mirror, which is R.5's own requirement (D-205) rather than
   merely the presence of a file.
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
6. **A dependency bot** — now the highest-value item on this list rather than
   the sixth, on evidence this report did not have when it was written.
   Advisories have taken `make check` red **three times** since R.6 locked the
   lockfiles (D-220, D-223), each within days, each found by hand, and each
   after a gate had passed green. It would also make `D-204`'s base-image
   decision obsolete: with something to refresh a digest, pinning both base
   images by digest becomes the better answer than pinning by tag. The related
   half is giving **`pip-audit` the ratchet `npm audit` has** — D-220 named
   that the right long-term shape and declined it that day because a fix
   existed; it is a bare wall until somebody builds it, so the first Python
   advisory with no upgrade available takes the build red with nowhere to
   record why it is safe in this deployment.
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
