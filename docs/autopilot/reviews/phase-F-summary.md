# Phase F review packet — Foundations

Branch: `autopilot/phase-F`, at commit `a55b306`. No tag exists yet; this packet
puts the phase into `AWAITING_REVIEW`.

Read time budget: 20-30 minutes (brief §3.5).

---

## 1. What changed

Phase F shipped no user-facing features (by brief §4 design). It rebuilt the
ground the roadmap phases will stand on. Milestone-by-milestone detail and
diffs are in `docs/autopilot/PROGRESS.md`; this is the plain-language summary.

- **F.1 Reconnaissance** — full inventory (`docs/autopilot/INVENTORY.md`),
  baseline test run, the roadmap converted into the milestone lists now in
  `PROGRESS.md`, a scope cross-check against the brief's capability list
  (one gap found — dark theme, see D-003 below), and the stale
  `gpt-oss-20b`/OpenRouter reference fixed.
- **F.2 Tooling and structure** — `Makefile` (`dev`, `test`, `check`,
  `check-fast`, `e2e`, `build`, `docker`, `seed`, `migrate`), matching
  pre-commit hooks, permission-check consolidation onto `permissions.py`,
  typed fail-fast settings, structured JSON request logging with request
  IDs, and a consistent JSON error envelope (previously a 500 outside a
  route handler returned plain text, which the frontend's `apiRequest<T>()`
  cannot parse).
- **F.3 API contract** — every response model in OpenAPI is now concretely
  typed (audit-log `detail` and notification `payload` were opaque
  strings/dicts, now 7- and 6-way typed unions); a generated TypeScript
  client (`frontend/lib/api-types.ts`) replaces every hand-written response
  type; the gate fails if the committed client goes stale.
- **F.4 Database** — Alembic adopted with the current schema as the baseline
  revision; the pre-Alembic repair path (`bridge_pre_alembic_database`) runs
  once instead of scanning every boot, closing a data-corruption path this
  same change would otherwise have introduced (D-014); migration tests
  covering upgrade-from-empty and upgrade-from-an-MVP-era snapshot; WAL,
  foreign keys, and a busy timeout confirmed by test, not just set; a
  central `soft_delete.py` replaced ~100 lines of duplicated cascade SQL, and
  a source-scanning test fails the build on any hard delete of user data.
- **F.5 Security** — CSRF (double-submit cookie) on every unsafe method;
  session rotation on login and invalidation on logout and password change
  (new `POST /api/auth/password`, D-018); rate limiting on login/signup;
  upload hardening (`uploads.py`: size ceiling, magic-byte sniffing,
  traversal and symlink tests) and an HTML sanitization framework
  (`sanitize.py`) built ahead of the features that will call them, per
  brief §4.7's explicit instruction; security headers (CSP,
  `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`).
  Also folded in **F.5a**: the human overruled D-005 and editors can now
  edit only their own timeline entries and notes, matching the existing
  delete rule exactly.
- **F.6 AI agent hardening** — the read-only guarantee is now enforced by
  SQLite itself (`PRAGMA query_only = ON`), not just by convention;
  cross-opportunity leakage and prompt-injection tests; a single client
  wrapper with configurable timeout/retry.
- **F.7 Test infrastructure** — every layer named in brief §6.1 now exists:
  frontend unit/component tests (0 → 80, after extracting six testable units
  out of the 1,783-line `page.tsx` with no behavior change); Playwright E2E
  with axe accessibility checks (0 → 13 tests, 7 specs); the authorization
  matrix (38 endpoints × 5 actor types, fails the build if a new route ships
  unregistered); named `test_invariant_*` tests for every brief §2 rule;
  `make seed` demo data; the Docker smoke test defined (verified against the
  running app locally — this sandbox has no Docker socket to run it against
  an image). Two real accessibility bugs were fixed outright (unnamed form
  controls, an unfocusable scrolling region); `color-contrast` is deferred
  to Phase 2/R on a self-tightening ratchet (D-026).
- **F.8 Gap-analysis fixes** — dead code removed (an unused `parse_timestamp`
  was wired up instead of deleted, since a caller should have used it), a
  test-isolation bug in `conftest.py` fixed (and found a real order-dependent
  test hiding behind it), expired sessions now swept on login, `passlib`
  (unmaintained, warned on every run) replaced with direct `bcrypt` calls,
  `prettier --check` added to the gate, frontend dependencies pinned instead
  of tracking `"latest"`, and the authorization matrix guarded against a host
  missing WeasyPrint's native libraries.
- **Gate script fix (a55b306)** — per the D-030(a) ruling, the host half of
  the split gate now runs the backend and frontend suites natively on the
  reviewer's machine before the Docker build, so a platform-specific failure
  (this run hit one — see §4) fails the gate instead of reaching the human
  silently.

---

## 2. How to try it

Everything below runs from a clean checkout of this branch.

```bash
git checkout autopilot/phase-F

cd backend && uv sync
cd ../frontend && npm ci
cd ..

make seed          # prints the seeded users and what each can see
make check-fast    # inner loop: lint, types, unit/integration tests
make check          # full gate: adds pip-audit, npm audit, E2E; prints the
                    # Docker deferral note (see §4)
```

`make seed` output (also asserted true by `tests/test_seed.py`):

```
Sign in with any of these; the password is 'DemoPass123!':
  alex@opptrail.test        Alex Rivera
  blair@opptrail.test       Blair Nakamura
  casey@opptrail.test       Casey Odom
  dana@opptrail.test        Dana Whitfield

  Alex owns four opportunities and can see a fifth (Initech) as a viewer.
  Blair is an editor on Northwind and owns Initech.
  Casey is a viewer on Northwind and Globex - every write is refused.
  Dana has access to nothing, which is the case worth checking by hand.
```

Click paths that exercise this phase's actual changes (there are no new
screens — F ships no features):

- **CSRF / cookies** — sign in as Alex, open dev tools, confirm
  `opptrail_csrf` is set and not `HttpOnly` while the session cookie is.
  Edit any note; the request carries `X-CSRF-Token`.
- **Editor can't edit a colleague's item (F.5a)** — sign in as Blair
  (editor on Northwind), try to edit an entry or note Alex authored: 403,
  and no Edit button is even offered (`canEdit`/`canDelete` in
  `frontend/lib/permissions.ts`).
- **Password change invalidates other sessions** — `POST
  /api/auth/password` with the current session's cookie; a second
  previously-open session for that user now gets 401 on its next call.
- **AI agent is read-only** — ask the AI panel a question as Casey
  (viewer); it answers. There is no way to make it write — there is no
  write tool in its surface at all, and even if there were, the connection
  it queries through has `PRAGMA query_only = ON`.
- **Soft delete** — delete a note; it disappears from the timeline but the
  owner's audit log (`/api/opportunities/{id}/audit-log`) still shows it.
- **Migrations** — `rm backend/app.db*` and start the app; Alembic runs
  `upgrade head` with no manual step (zero-setup preserved).

---

## 3. Decisions needing review

Every `needs human review: Y` entry from this phase's `DECISIONS.md`, in the
order raised. D-003, D-005, D-012 and D-018 were already ruled on mid-phase
(2026-09-16/17) and are listed for completeness only — no action needed on
those four.

| ID | Question | Recommended | Alternative | Status |
|---|---|---|---|---|
| D-003 | Add an explicit dark-theme acceptance criterion? | Add to Phase 2 | Leave implicit | **Ruled: accepted** — added to Phase 2 |
| D-005 | Should editors be allowed to edit a colleague's entry/note? | Keep permissive (matches `AGENTS.md`'s literal wording) | Tighten to author-or-owner | **Ruled: overruled** — tightened (F.5a) |
| D-012 | Write a new ADR for "SQLite fitness for v2"? | Drop — already answered by ADRs 0001/0002/0003/0011 | Write it anyway | **Ruled: accepted** — dropped |
| D-018 | Add `POST /api/auth/password` in a no-new-features phase? | Add it — the §4.5 security requirement is explicit and unimplementable without it | Defer the endpoint and the §4.5 bullet to the account-settings phase | **Ruled: accepted** — kept |
| **D-025** | Journey 12 ("AI answers on accessible data...") can't call a real model under brief §9's no-paid-API rule. Is narrowing the E2E half to failure-handling + no-data-leak acceptable, with the answering half covered by mocked backend tests instead? | **Accept the narrowing** (option b in D-025) — the alternative (a fake-model code path) puts test-only branching into shipped code, which the brief's own coding standards forbid | Add an environment-gated stub model response so E2E can drive a real answer | **Open — needs your ruling** |
| **D-026** | `color-contrast` fails on ~40 nodes (a palette issue, not a Phase F regression). Deferred on a one-entry, self-tightening ratchet (`DEFERRED_AXE_RULES`) rather than fixed here or ignored. Is deferring to Phase 2 (tokens) / R (final polish) the right sequencing? | **Confirm deferral** — repainting the app inside a test-infrastructure milestone would pre-empt Phase 2's token work and exceed Phase F's scope | Fix the palette now, inside Phase F | **Open — needs your ruling** |
| D-030 | Should the split gate grow a host-native test run? | Option (a) — add `make test-host` to `autopilot-gate.sh` | Leave as-is / require per-test platform guards | **Ruled: accepted (a)**, implemented in `a55b306` — see §4, it caught a real bug on the first run |

No decision in this phase changed the stack, and none is a database migration
without an ADR.

---

## 4. Quality evidence

**Sandbox half of the split gate** (`make check`, this session, this commit):
green end to end.

```
ruff check .                      All checks passed!
ruff format --check .             54 files already formatted
mypy --strict app tools           Success: no issues found in 29 source files
frontend typecheck (tsc)          clean
frontend lint (eslint)            clean (1 stray warning, 0 errors — see below)
prettier --check                  All matched files use Prettier code style!
backend pytest                    190 passed, 96.46% combined line+branch coverage
                                   (--cov-fail-under=90)
frontend vitest                   80 passed (6 files), 87.09% stmts / 79.29%
                                   branch / 88.33% funcs / 86.87% line
API-contract check                generated client current
pip-audit                         No known vulnerabilities found
npm audit                         found 0 vulnerabilities
Playwright E2E + axe              13 passed (7 specs, 4 screens under axe)
Docker build + smoke test         deferred to the host (no Docker socket in
                                   this sandbox — sandbox/README.md)
```

**One real environment bug found and fixed while running this gate, not a
code regression:** `frontend/node_modules` in this sandbox session held only
the `darwin-arm64` `@rollup/rollup-*` optional dependency — this is the
well-known npm optional-dependency bug (npm/cli#4828), the same class D-030's
implementation already patched once for a stale lockfile stamp. A
`rm -rf frontend/node_modules && npm ci` (gitignored build output, not user
work) picked up the correct `linux-arm64-gnu` binary and the suite ran clean
afterward. No application or test code changed for this.

The 1 ESLint warning (`no-script-url` unused-disable in
`MarkdownText.test.tsx`) is pre-existing from F.7, not introduced this
session, and does not fail the gate (0 errors).

**Coverage vs. previous phase:** this is Phase F itself — there is no prior
phase to diff against. Within Phase F, coverage moved:

| | F.1 baseline | F.9 (this gate) |
|---|---|---|
| Backend line | 96% | 96.46% (line+branch combined) |
| Backend tests | 39 | 190 |
| Frontend line | 0% (no runner) | 86.87% |
| Frontend tests | 0 | 80 |
| E2E tests | 0 | 13 |

Full history with per-module breakdowns: `docs/autopilot/COVERAGE.md`.

**New invariant / E2E tests this phase:** `tests/test_invariants.py` (10,
named `test_invariant_*`), plus the two that live beside their code
(`test_soft_delete.py::test_invariant_no_hard_deletes_of_user_data`,
`test_ai.py::test_invariant_ai_agent_has_no_write_tools`), plus
`test_invariants.py::test_invariant_ai_agent_data_layer_refuses_writes`
(F.6/D-027, SQLite-enforced). The authorization matrix
(`tests/test_authorization_matrix.py`) is 38 endpoints × 5 actor types and
fails the build on an unregistered route. E2E: 13 tests across 7 specs
covering brief §6.3 journeys 1, 2, 3, 5, 11, and a narrowed 12 (D-025); axe
runs on 4 screens.

**Host half of the split gate:** outstanding. Run
`scripts/autopilot-gate.sh F` against commit `a55b306` — it now runs
`make test-host` (native `pytest` + `npm test` on your machine) before the
Docker build and smoke test, per the D-030(a) ruling implemented in this
same commit. `scripts/autopilot-accept.sh` will refuse to accept without
that receipt.

---

## 5. Risks and known limitations

- **CSP allows inline script/style** (D-019). Forced by `output: "export"`
  emitting Next's hydration payload inline with no render pass to hash
  against. Hashing at build time is named as a Phase R item.
- **`color-contrast` fails axe on ~40 nodes** (D-026, open above). Real,
  pre-existing, not introduced this phase; deferred on a self-tightening
  ratchet rather than silently ignored.
- **Journey 12 is narrowed, not fully E2E'd** (D-025, open above): the
  "answers correctly on accessible data" half is proven only against a
  mocked backend client, not through the browser, because the brief forbids
  a real paid API call from tests.
- **Note revision history has no screen.** The API and table exist; the UI
  doesn't, because building it is a user-facing feature and brief §4 rules
  that out for Phase F. Journey 3's third step is asserted over the API in
  the E2E test instead of by clicking through a UI.
- **Rate limiting and CSRF both assume a single process.** Documented as
  the deliberate scope of D-020/D-017 — correct for ADR 0011's single
  container, and named as the one place to change if that stops being true.
- **`ai_service.py`'s timeout/retry values are exercised only through the
  SDK's own tested behavior**, not against a real slow/failing OpenAI
  endpoint, since brief §9 forbids a live call from tests.
- **The Docker build + smoke test has not run in this session** (no
  Docker socket in the sandbox) and is the one piece of §3.4 not yet
  verified against this exact commit — see §4's "Host half" note.

---

## 6. Out-of-scope items noticed, logged not built

- **Dark theme acceptance criterion** (D-003) — was missing from the
  roadmap entirely; proposed and accepted into Phase 2, not built here.
- **A full routers → services → data-access layer split** (brief §4.2's
  other phrasing) — F.2 closed the specific permission-consolidation gap
  D-004 named, but a full three-tier refactor of every router is a larger
  change than this milestone's budget; not attempted, not claimed done.
- **Synchronizer-token CSRF, hashed CSP, host-aware rate limiting** — all
  named as reversible alternatives inside their respective decisions
  (D-017, D-019, D-020) if the single-container/single-origin assumptions
  ADR 0011 and this stack currently make ever change.

---

## 7. Preview of next phase

Phase 1 — Backbone, Search, Notifications (`autopilot/phase-1`, depends on
the `phase-F-accepted` tag). First milestones per `PROGRESS.md`:

- **1.1** GitHub Actions CI (backend suite, frontend typecheck/lint, Docker
  build, and the backend suite run *inside* the image for WeasyPrint) —
  Blocker B4.
- **1.2** Alembic baseline-stamp / `run_migrations()` → revisions. Note for
  whoever starts this phase: **F.4 already did the Alembic baseline and the
  bridge-not-revisions approach (D-013)** — read that decision before
  treating 1.2 as unstarted; it is likely the roadmap's confirmation of F.4's
  work, not a duplicate.
- **1.3** `/api/v2` pagination envelope and unified error shape.
- **1.4** FTS5 search (ADR 0007).

**Decision to settle before or early in Phase 1:** D-025 and D-026 above.
Neither blocks starting Phase 1 — D-026's ratchet already fails the build if
anything regresses, and D-025's narrowing is documented — but a ruling
either closes them or tells the next session what to change.

---

## Status

`STATUS: AWAITING_REVIEW phase=F`

Per brief §3.3/§3.4: this sandbox's half of the gate is green. The host half
(`scripts/autopilot-gate.sh F` against commit `a55b306`) is required before
`scripts/autopilot-accept.sh` can tag `phase-F-accepted`. Per brief §3.1/§9,
no tag, merge, or push happens from this session — that is the human's step.
