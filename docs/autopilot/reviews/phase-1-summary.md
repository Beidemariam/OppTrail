# Phase 1 review packet — Backbone, Search, Notifications

Branch: `autopilot/phase-1`, at commit `83d2aeb`. Depends on the
`phase-F-accepted` tag (present). This packet puts the phase into
`AWAITING_REVIEW`.

Read time budget: 20-30 minutes (brief §3.5).

---

## 1. What changed

Phase 1's stated goal (`docs/ROADMAP.md`): put the non-negotiable foundations
in while shipping the two features whose current implementations were dead
ends rather than extensions. User-visible outcome: global ranked search with
highlighted snippets across every opportunity, and a notification inbox that
keeps history instead of erasing it. All seven milestones are done.
Milestone-by-milestone detail and diffs are in `docs/autopilot/PROGRESS.md`;
this is the plain-language summary.

- **1.1 GitHub Actions CI** (Blocker B4) — `.github/workflows/ci.yml`, two
  jobs, not pushed to any remote (guardrail). `checks` runs `make
  check-fast`; `docker` (gated on `checks` passing first) runs `make docker`,
  `make docker-test` (a new Dockerfile stage that runs the backend suite
  *inside* the image, where WeasyPrint's native libraries live) and `make
  docker-smoke`. **1.1a** narrowed the trigger to `branches: [main]`, matching
  R.6's wording exactly, once raised at review.
- **1.2 Alembic confirmation** (Blocker B2, ADR 0002) — re-verified line by
  line against ADR 0002's six-step plan; Phase F's `database.py` already
  satisfied it in full. No code changed — confirmation only, recorded rather
  than rebuilt, per the "no unnecessary defensive branches" standard.
- **1.3 `/api/v2` pagination envelope and error shape** (Blocker B3) — seven
  new v2 endpoints (`opportunities`, `stages`, per-opportunity `timeline`,
  `shares`, `audit-log`, note `versions`, `notifications`), each mirroring
  its v1 twin's rows, filters and permissions exactly. Keyset pagination
  (`{"items", "next_cursor"}`, opaque cursors over `(sort value, id)` so
  inserts/deletes between two page requests never skip or duplicate a row),
  and a `{"error": {"code","message","fields"?}}` envelope for v2 failures
  while v1 keeps `{"detail": ...}` byte-for-byte. The authorization matrix
  grew from 38 to 45 endpoints.
- **1.4 FTS5 search index, triggers, `/api/v2/search`** (ADR 0007, feature:
  Search §13) — a contentless FTS5 table indexing entries, notes and
  comments, maintained by nine triggers (including the soft-delete
  transitions), ranked and snippeted cross-opportunity search with
  permissions resolved inside the query rather than filtered after. The v1
  timeline `?q=` filter was reimplemented against the same index (word-prefix
  matching replaces substring matching — a deliberate, documented behaviour
  change, D-037). `make reindex` rebuilds the index from source tables.
- **1.5 React Router, TanStack Query, search page** (ADR 0005) — `AppRoot`
  now renders nothing until it is running in a browser (so the static export
  stays an empty shell, avoiding a hydration mismatch), routing `/` to the
  existing `Home.tsx` unchanged and `/search` to a new page built on
  TanStack Query's `useInfiniteQuery` over the v2 cursor. `Home.tsx` itself
  is deliberately untouched except for one link — its decomposition is
  Phase 2's milestone 2.1, not this one (D-038).
- **1.6 Structured logging, `/api/health` detail, backups** (ADR 0011) —
  `/api/health` now reports `schema_version`, `database_writable` (a `BEGIN
  IMMEDIATE` probe) and `last_backup_at`, with the whole check wrapped
  against a database that fails before any query runs (D-042, caught by its
  own test first). `app/backup.py`'s `VACUUM INTO` snapshots without locking
  out writers; `make backup` / `make restore` with retention and a real
  round-trip test (back up, write more, restore, confirm the write is gone).
  No scheduler wired yet — deliberately deferred to ADR 0004 in Phase 5
  (D-041), not built early.
- **1.7 Notifications inbox rework** (§9, minus digests) — the `WHERE read =
  0` dead end is fixed: `GET /api/v2/notifications` answers full history with
  an optional `?type=` filter, while v1 stays exactly as shipped (unread-only)
  per the roadmap's breaking-changes table — the one deliberate exception to
  "a v2 route mirrors its v1 twin" (D-043). New `read_at` column is the
  source of truth; `read` stays for v1, kept in sync by one shared helper so
  the two columns cannot drift. New `POST /api/v2/notifications/mark-all-read`.
  Frontend inbox panel now shows history, a type filter, and a mark-all-read
  button.

---

## 2. How to try it

Everything below runs from a clean checkout of this branch.

```bash
git checkout autopilot/phase-1

cd backend && uv sync
cd ../frontend && npm ci
cd ..

make seed          # prints the seeded users and what each can see
make check-fast    # inner loop: lint, types, unit/integration tests
make check          # full gate: adds pip-audit, npm audit, E2E; prints the
                    # Docker deferral note (see §4)
```

Click paths that exercise this phase's new capabilities:

- **Global search** — sign in as Alex, go to `/search`, search a rare term
  that appears in an opportunity Alex can read; results are ranked with the
  matched term highlighted. Try the same term as Casey (viewer on
  Northwind/Globex only, per the seed tour) — only matches inside their
  accessible opportunities appear. A deep link straight to `/search?q=...`
  loads and runs the search without visiting `/` first.
- **Search reacts to deletion** — delete a note containing the searched
  term; it drops out of the results (the FTS5 triggers fire on the same
  soft-delete transition every other read already filters on).
- **Notification history** — sign in as Alex, open the bell. A read
  notification (Alex's `share_added` from the Initech share, marked read by
  `make seed`) is still visible, not gone — filter by type to confirm it is
  still findable. Click "Mark all read"; the unread badge clears and a
  second click is a no-op (idempotent).
- **v1 still works unchanged** — the existing dashboard, timeline, sharing
  panel and single mark-read button (`PATCH /api/notifications/{id}/read`)
  behave exactly as before this phase; nothing in `Home.tsx` besides the new
  notification controls and one `/search` link changed.
- **`/api/health`** — `curl http://localhost:8000/api/health` (or the
  equivalent behind the running container) shows `schema_version`,
  `database_writable: true`, `last_backup_at`. Run `make backup`, check the
  timestamp advances.
- **CI, locally inspectable** — `.github/workflows/ci.yml`; not run here
  (never pushed), but its two jobs mirror `make check-fast` and the new
  `make docker-test`/`make docker-smoke` targets, both runnable by hand.

---

## 3. Decisions needing review

Every `needs human review: Y` decision raised during this phase was already
resolved mid-phase, before this gate — none is open now.

| ID | Question | Recommended | Status |
|---|---|---|---|
| D-033 | v1's ~20 remaining endpoints (mutations, single-resource reads) have no shape change to make in 1.3 — mirror them anyway, or scope 1.3 to the seven paginated collection reads plus the error envelope? | Scope narrowly (a); flag the consequence for Phase 2's plan | **Ruled: accepted.** Milestone **2.9** added to `PROGRESS.md`'s Phase 2 list to finish the port and retire v1, so the roadmap's "v1 removed at the end of Phase 2" stays true. |
| D-036 | Phase 1's acceptance line asks for search latency "at seeded scale" (~800k rows per `AGENTS.md`), but building that seed is Phase R's own milestone (R.7) — assert the budget at a smaller, affordable corpus now, or defer the whole criterion to R.3? | Assert at a documented bounded corpus (24,000 documents) *and* assert the query-plan property that makes the number hold as the corpus grows | **Ruled: accepted.** `test_search_reads_the_index_and_never_scans_a_source_table` (the plan test) was confirmed to catch a regression the latency test alone missed; the 800k re-measurement stays R.3's, against ADR 0001's already-recorded 294 ms figure. |

No decision this phase changed the stack, and no database migration shipped
without an accepted ADR.

---

## 4. Quality evidence

**Sandbox half of the split gate** (brief §3.4), re-run this session at
commit `83d2aeb` (no application code changed since milestone 1.7's own
gate — this is a fresh run, not a copied-forward number):

```
ruff check .                      All checks passed!
ruff format --check .             67 files already formatted
mypy app tools                    Success: no issues found in 36 source files
frontend typecheck (tsc)          clean
frontend lint (eslint)            clean (1 pre-existing warning, 0 errors)
prettier --check                  All matched files use Prettier code style!
backend pytest                    258 passed, 97.28% combined line+branch
                                   coverage (--cov-fail-under=90 enforced)
frontend vitest                   102 passed (9 files), 88.64% stmts /
                                   80.86% branch / 90.54% funcs / 88.38% line
API-contract check                generated client (lib/api-types.ts) current
pip-audit                         No known vulnerabilities found
npm audit                         found 0 vulnerabilities
Playwright E2E + axe              18 passed (7 specs), axe clean on every
                                   screen exercised, including search and the
                                   reworked notification panel; the deferred
                                   color-contrast ratchet (D-026) still fails
                                   on cue, confirming the gate still tightens
Docker build + smoke test         deferred to the host — no Docker socket in
                                   this sandbox (sandbox/README.md)
```

The 1 ESLint warning (`no-script-url` unused-disable in
`MarkdownText.test.tsx`) predates this phase (Phase F) and does not fail the
gate (0 errors).

Coverage floors (brief §6.2) all met: backend ≥ 90% line / ≥ 80% branch
(97.28% combined, unchanged from milestone 1.7's own gate); frontend ≥ 80%
line (88.38%); the ≥95%-branch modules (`permissions.py`, `audit_utils.py`,
`auth.py`, `soft_delete.py`, `routes_ai.py`) all still at or above 95%.

**Coverage vs. previous phase** (Phase F's F.9 gate → this gate):

| | Phase F gate | Phase 1 gate |
|---|---|---|
| Backend tests | 190 | 258 |
| Backend coverage | 96.46% | 97.28% |
| Frontend tests | 80 | 102 |
| Frontend line coverage | 86.87% | 88.38% |
| E2E tests | 13 (7 specs) | 18 (7 specs) |
| Authorization-matrix endpoints | 38 | 47 |

Full per-milestone history and module breakdowns: `docs/autopilot/COVERAGE.md`.

**New invariant / E2E tests this phase:** the authorization matrix grew from
38 to 47 endpoints (the seven v2 collection routes plus mark-all-read), with
the registry guard confirmed to fail first when a new route was left
unregistered. `tests/test_search.py` carries a query-plan assertion
(`test_search_reads_the_index_and_never_scans_a_source_table`) confirmed to
fail against a mutation that defeats the rowid lookups — the guard for D-036.
No brief §6.3 journey was newly completed end-to-end this phase (journey 6,
search, is close but click-through into a result is deferred to 2.1 per
D-039); `08-search.spec.ts`'s four specs cover the access-scoping half of it.

**Host half of the split gate:** outstanding. Run
`scripts/autopilot-gate.sh 1` against commit `83d2aeb` — it builds the image
from this branch, runs `make docker-test` (the backend suite inside the
image, where WeasyPrint's native libraries are present) and `make
docker-smoke`. `scripts/autopilot-accept.sh` will refuse to accept without
that receipt.

---

## 5. Risks and known limitations

- **A search result has no click-through into the timeline** (D-039). The
  timeline is still rendered by `Home.tsx` from in-memory selection state
  with no URL, so a result can name its opportunity and matched text but not
  link into it yet. Deferred to milestone 2.1, which gives the timeline a
  route to link to — building it now would mean teaching `Home.tsx` to read
  a selection from the URL without making the URL follow it, a half-built
  version of the property 2.1 owns end to end.
- **v1's timeline `?q=` filter now matches word prefixes, not substrings**
  (D-037): "proc" still finds "procurement", "curement" no longer does. A
  deliberate fix (ADR 0007 names substring matching as a defect), not a
  regression in the response *shape*, but a real behaviour change on an
  endpoint the shipped frontend still calls.
- **v1 endpoints beyond the seven v2 collection reads have not moved.**
  ~20 mutation/single-resource endpoints stay v1-only until milestone 2.9
  (added this phase, per D-033) ports them and retires v1.
- **`color-contrast` still fails axe** on the same nodes named at the Phase F
  gate (D-026) — unchanged this phase, deferred to Phase 2's token work
  (2.5) on the same self-tightening ratchet; confirmed still enforced (§4).
- **No scheduler drives `make backup` yet** (D-041) — it is a script/cron
  target until ADR 0004's APScheduler instance lands in milestone 5.1;
  building a throwaway scheduler now would risk becoming de facto
  infrastructure nobody designed for the other four phases' periodic jobs.
- **The search index has a hard ceiling of four document types**
  (`source id * 4 + kind code` — see the 2026-09-18 human note in
  `DECISIONS.md`). Not a defect — the index is rebuildable from source by
  construction — but Phase 4 (attachments) or Phase 5 (inbound email),
  whichever needs a fourth type first, must widen the encoding as part of
  that milestone.
- **The Docker build + smoke test has not run in this session** (no Docker
  socket in the sandbox) — the one piece of §3.4 not yet verified against
  this exact commit; see §4's "Host half" note.

---

## 6. Out-of-scope items noticed, logged not built

- Nothing new surfaced this phase beyond what Phase F's gate already logged
  (dark theme → accepted into Phase 2 as D-003; the full routers → services
  → data-access refactor remains larger than any one milestone's budget).
  No new capability-list gap (brief §7) was found during Phase 1's work.

---

## 7. Preview of next phase

Phase 2 — Pipeline Views and Keyboard Navigation (`autopilot/phase-2`,
depends on the `phase-1-accepted` tag). First milestones per `PROGRESS.md`:

- **2.1** Decompose `Home.tsx` into routed views on TanStack Query — the
  rewrite Phase 1 deliberately deferred here (D-038), and the file milestone
  2.9's v1→v2 port will also touch.
- **2.9** (added this phase per the D-033 ruling) — port the remaining ~20
  v1 endpoints to `/api/v2`, move the frontend off v1, delete v1 and the
  shared-SQL constants that exist only to keep the two surfaces from
  drifting, regenerate the client, update the authorization matrix.
- Board/table views, saved filtered views, and the design-token work that
  closes D-026's `color-contrast` ratchet (2.5).

**Decision to settle before or early in Phase 2:** none outstanding — both
of this phase's `needs human review: Y` items are already resolved (§3).
Worth confirming at the gate: that 2.9's placement inside Phase 2 (rather
than as its own phase) still reads right now that 2.1's decomposition and
2.9's v1 removal will touch overlapping files, per D-033's own reasoning for
sequencing it there.

---

## Status

`STATUS: AWAITING_REVIEW phase=1`

Per brief §3.3/§3.4: this sandbox's half of the gate is green. The host half
(`scripts/autopilot-gate.sh 1` against commit `83d2aeb`) is required before
`scripts/autopilot-accept.sh` can tag `phase-1-accepted`. Per brief §3.1/§9,
no tag, merge, or push happens from this session — that is the human's step.
