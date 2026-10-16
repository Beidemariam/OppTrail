# Coverage History

Coverage floors (brief §6.2, never lowered): backend ≥ 90% line / ≥ 80% branch;
auth, permissions, soft-delete, audit, and AI-agent modules ≥ 95% branch; frontend
≥ 80% line. `AGENTS.md`'s own bar (backend integration ≥ 90%, frontend unit ≥ 70%)
is looser than the brief's; the brief's floor governs per the source-of-truth
hierarchy (higher item wins — but note the brief is item 6, lowest-ranked, so
where `AGENTS.md` sets a *stricter* number than the brief, as it does for backend
line coverage — 90% either way here, no conflict — the stricter of the two always
applies; call out any future case where they actually diverge).

## Phase F — baseline (pre-milestone-work), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-report=term-missing`,
run inside the sandbox (WeasyPrint's native libraries are present here, unlike a
macOS host — see `CLAUDE.md`).

```
39 passed in 14.62s
TOTAL: 1032 stmts, 44 miss, 96% line coverage
```

No branch-coverage figure yet — `pytest-cov` was run without `--cov-branch`; add
it once `make check` exists (Phase F milestone F.2) so branch coverage is
tracked from the same baseline going forward.

| Module | Line % | Notes |
|---|---|---|
| `permissions.py` | 100% | already meets the ≥95% floor for permission-critical modules |
| `audit_utils.py` | 100% | already meets the ≥95% floor |
| `timeline_utils.py` | 100% | |
| `routes_ai.py` | 100% | |
| `routes_auth.py` | 100% | |
| `routes_export.py` | 100% | |
| `routes_notifications.py` | 100% | |
| `schemas.py` | 98% | |
| `export_service.py` | 99% | |
| `routes_sharing.py` | 95% | |
| `auth.py` | 97% | auth-critical module; already at the ≥95% floor, keep it there as sessions/rotation/CSRF work lands in F.5 |
| `notification_service.py` | 97% | |
| `database.py` | 94% | |
| `main.py` | 93% | |
| `routes_timeline.py` | 94% | |
| `routes_opportunities.py` | 92% | |
| `time_utils.py` | 86% | `parse_timestamp` (lines 22-23) is unreferenced by any current caller |
| `ai_service.py` | 82% | the live `ask_openai` call itself and a couple of context-building edge branches are unexercised (mocked in tests by design, per brief §4.6) |

Frontend: no test runner exists yet (0% by absence, not by failing tests).
Standing one up is Phase F milestone F.7.

Full detail: `docs/autopilot/INVENTORY.md` §7.

## Phase F — after milestone F.2 (Tooling and structure), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`
(now wired into `make check-fast` / `make check`), run inside the sandbox.

```
47 passed in 15.87s
TOTAL: 1126 stmts, 43 miss, 172 branches, 34 partial, 94% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 94.07%
```

47 tests, up from 39: +1 permission-consolidation regression test
(`test_shared_editor_can_view_but_not_mutate_opportunity`), +2 error-envelope
tests (`test_error_handling.py`), +2 auth-branch tests (expired-session,
logout-without-cookie), +3 settings fail-fast-validation tests
(`test_settings.py`). All new tests were confirmed to fail against the
pre-fix code first, per brief §6.5's guard-test rule.

`--cov-branch` is now part of the standard command (COVERAGE.md's prior baseline
noted this as a to-do for F.2 — done). The `Cover` column below is combined
statement+branch coverage (pytest-cov does not report a branch-only percentage
separately); it is the practical proxy used for the brief §6.2 branch floors.

| Module | Combined line+branch % | Notes |
|---|---|---|
| `auth.py` | 100% | was 93% before this milestone (missing the expired/unknown-session branch and the no-cookie logout branch) — now closes brief §6.2's ≥95% floor for auth-critical modules |
| `permissions.py` | 100% | already met the ≥95% floor; unchanged |
| `audit_utils.py` | 100% | already met the ≥95% floor; unchanged |
| `errors.py` | 100% | new module (F.2) |
| `logging_utils.py` | 100% | new module (F.2) |
| `routes_ai.py` | 100% | new `logger.warning` call on OpenAI failure (F.2) is exercised by the existing `test_ai_returns_helpful_errors` |
| `routes_export.py` | 100% | |
| `routes_auth.py` | 100% | |
| `routes_notifications.py` | 100% | |
| `export_service.py` | 97% | |
| `notification_service.py` | 96% | |
| `schemas.py` | 98% | |
| `routes_timeline.py` | 91% | mostly 404 branches for missing entries/notes/comments |
| `main.py` | 91% | |
| `routes_sharing.py` | 90% | |
| `database.py` | 88% | |
| `time_utils.py` | 88% | `parse_timestamp` still unreferenced — candidate for F.8 |
| `settings.py` | 100% | both fail-fast validators' error branches now covered (`test_settings.py`) |
| `routes_opportunities.py` | 89% | |
| `ai_service.py` | 79% | **below the ≥95% floor brief §6.2 sets for AI-agent modules.** The live `ask_openai` call and several context-building edge branches are unexercised by design (mocked in tests, brief §4.6) — closing this is Phase F milestone F.6's explicit scope ("Single OpenAI client wrapper with timeouts, retries, and graceful failure... always mocked in tests"), not F.2's. Logged here so the gap is visible rather than silently carried forward. |

Frontend: still 0% (no test runner) — unchanged from baseline; F.7's scope.

New tooling this milestone: `ruff check`, `ruff format --check`, and `mypy
--strict app/` are now all green (`backend/pyproject.toml` `[tool.ruff]` /
`[tool.mypy]`), and `pip-audit` / `npm audit` both report zero known
vulnerabilities (weasyprint bumped 69.0 → 70.0 to clear PYSEC-2026-3940, a
`url_fetcher`-bypass finding that does not apply to OppTrail's usage — no
`xmp_metadata=`/`stylesheets=` arguments are ever passed — but the fix was a
trivial, safe version bump so it was taken anyway).

## Phase F — after milestone F.3 (API contract), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`
(via `make check-fast`), run inside the sandbox.

```
48 passed in 16-34s (timing varies with sandbox load)
TOTAL: 1210 stmts, 44 miss, 174 branches, 35 partial, 94% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 94.29%
```

48 tests, up from 47: +1 (`test_export_openapi.py::test_main_prints_the_openapi_schema_as_json`,
covering the new `app/export_openapi.py` CLI shim used by
`scripts/generate-api-client.sh`). Two existing tests were adjusted to match
the tightened response contract, not weakened — both changes are direct
consequences of `AuditLogEntryPublic.detail` and `NotificationPublic.payload`
moving from opaque `str`/`dict[str, Any]` to typed unions (see this session's
DECISIONS.md entry): `test_deletions_are_recorded_in_the_audit_log`
(`test_timeline.py`) now asserts the structured `detail.entry_id` field
instead of a substring match on a JSON-as-string blob, and
`test_user_can_mark_only_own_notification_read` (`test_notifications.py`)'s
raw-SQL notification fixture now inserts a complete `mention` payload instead
of a partial one, since the payload is now schema-validated on read.

| Module | Combined line+branch % | Notes |
|---|---|---|
| `audit_utils.py` | 100% | now includes `parse_audit_detail`; unchanged floor |
| `notification_service.py` | 97% | now includes `parse_notification_payload` |
| `schemas.py` | 98% | +14 new typed models (7 audit-detail variants, 6 notification-payload variants, plus `CurrentUserRole`); untouched lines are validator branches already noted as thin in F.2 |
| `export_openapi.py` | 75% | new module (6 statements); the untested line is the standard `if __name__ == "__main__":` guard, not application logic |
| `routes_sharing.py` | 90% | unchanged — only the audit-log read path changed, already covered |
| `routes_notifications.py` | 100% | unchanged |

Frontend: still 0% (no test runner) — unchanged from baseline; F.7's scope.
`npm run typecheck`, `npm run lint`, and `npm run build` all pass against the
generated `frontend/lib/api-types.ts` and the `page.tsx` types now sourced
from it — these are compile-time checks, not a substitute for F.7's Vitest
component-test floor.

## Phase F — after milestone F.4 (database), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`
(via `make check-fast`), run inside the sandbox.

```
60 passed in 17.21s
TOTAL: 1261 stmts, 42 miss, 178 branches, 35 partial, 95% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 94.65%
```

60 tests, up from 48: +13 new, -1 relocated.

- `tests/test_migrations.py` (+6) — upgrade from empty, idempotence, upgrade
  from an MVP-era database, the backfill running once, the legacy repair *not*
  running on every startup, and canonical timestamps written into a bridged
  legacy database. Brief §6.1's migration layer; `make check` no longer prints
  a deferral for it.
- `tests/test_soft_delete.py` (+4) — the hard-delete source scan, the scanner's
  own self-check against a file that does contain one, the `sessions` exclusion,
  and a behavioral check that deleting a populated opportunity retains every row
  across five tables.
- `tests/test_database.py` (+3) — WAL, `foreign_keys`, and the busy timeout,
  each confirmed to fail with the corresponding pragma removed from
  `get_connection()`.
- `tests/test_opportunities.py` (-1) — `test_schema_init_backfills_created_system_entries`
  removed; the same guarantee is now asserted by
  `test_mvp_backfill_creates_one_system_entry_per_opportunity` against a real
  pre-Alembic database instead of a hand-built row. Justified in DECISIONS.md
  D-016, per brief §6.5's rule on removed tests.

Coverage moved 94.29% → 94.65% on a larger codebase (1210 → 1261 statements).

| Module | Combined line+branch % | Notes |
|---|---|---|
| `soft_delete.py` | 100% | new module; every cascade helper is exercised through the API by `test_invariant_deleting_an_opportunity_retains_every_row` and the existing delete tests |
| `database.py` | 94% | new module content (Alembic wiring, the bridge, `table_exists`). The four uncovered branches are the bridge's two `column_exists` guards in their already-migrated direction (a legacy database that happens to have one of the two columns), plus the non-sqlite `ValueError` that `settings.py`'s validator forecloses |
| `auth.py` | 100% | unchanged floor; touched by D-014's explicit-timestamp writes |
| `audit_utils.py` | 100% | unchanged |
| `notification_service.py` | 97% | unchanged |
| `timeline_utils.py` | 100% | unchanged |
| `routes_timeline.py` | 91% | ~60 lines of cascade SQL replaced by `soft_delete` calls; uncovered lines unchanged from F.3 |

Brief §6.2's ≥95% branch floor for critical modules: `auth.py`, `permissions.py`
and `soft_delete.py` are at 100%; `audit_utils.py` 100%. `ai_service.py` stays
at 79% and remains knowingly deferred to F.6, which owns the timeout/retry
wrapper that makes its error branches testable without a live API call.

Frontend: still 0% (no test runner) — unchanged; F.7's scope.

---

## F.5 — Security (§4.5)

```
129 passed in 22.99s
TOTAL: 1451 stmts, 41 miss, 222 branches, 35 partial, 95% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 95.46%
```

129 tests, up from 60: +69 (no test removed; one rewritten in place under D-005,
one moved onto `CsrfClient`).

- `tests/test_uploads.py` (+23) — sniffing per allowed type, three rejected
  binary shapes, the declared type being ignored entirely, the size ceiling,
  generated-name randomness and shape, seven traversal shapes, a symlink planted
  inside the upload root, and three disposition-header cases including CRLF and
  non-ASCII filenames.
- `tests/test_sanitize.py` (+16) — five hostile element classes, event-handler
  attributes, four rejected URL schemes against three allowed ones, forced
  `rel`, and a round-trip proving ordinary Markdown output survives byte for
  byte.
- `tests/test_security.py` (+11) — cookie issuance, four CSRF rejection shapes
  (no header, mismatched token, header without a cookie, and the matching pair
  succeeding), headers on API/page/rejection responses, cookie flags in and out
  of production, session rotation, and logout.
- `tests/test_rate_limit.py` (+9) — the cap, the window sliding rather than
  resetting, per-caller and per-endpoint isolation, reset, the memory sweep, the
  no-peer fallback, both endpoints end to end, and the ordering check that
  bcrypt is never reached by a limited caller.
- `tests/test_auth.py` (+5) — password change: wrong current password, no
  authentication, short new password, every other session invalidated, and the
  new password being the one that works.
- `tests/test_settings.py` (+3) — the three new settings must be positive.
- `tests/test_timeline.py` (+1, one rewritten) — owner edits an editor's entry
  and note; the editor test now asserts 403 on both edit paths (D-005).

Coverage moved 94.65% → 95.46% while the codebase grew 1261 → 1451 statements.

| Module | Combined line+branch % | Notes |
|---|---|---|
| `security.py` | 100% | new; every branch of the CSRF decision and both cookie-flag directions are exercised |
| `rate_limit.py` | 100% | new; includes the sweep path and the `request.client is None` fallback |
| `uploads.py` | 100% | new |
| `sanitize.py` | 100% | new |
| `permissions.py` | 100% | unchanged floor; `require_author_or_owner` is reached from both wrappers |
| `auth.py` | 100% | rotation and `delete_user_sessions` both covered |
| `routes_auth.py` | 100% | includes every branch of the new endpoint |
| `settings.py` | 100% | was 95%; the new positive-value validator is tested |
| `main.py` | 93% | unchanged; the two uncovered lines are the frontend-build-missing fallbacks |

Brief §6.2's ≥95% branch floor for critical modules: `auth.py`, `permissions.py`,
`soft_delete.py` and `audit_utils.py` remain at 100%. `ai_service.py` stays at
79% and is still F.6's, which owns the client wrapper that makes its error
branches testable without a live API call.

Frontend: still 0% (no test runner) — unchanged; F.7's scope.

---

## F.6 — AI agent hardening (§4.6)

```
138 passed in 23.69s
TOTAL: 1465 stmts, 34 miss, 226 branches, 30 partial, 96% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 96.22%
```

138 tests, up from 129: +9 (no test removed or weakened).

- `tests/test_ai.py` (+7):
  - `test_invariant_ai_agent_has_no_write_tools` — drives `ask_openai` directly
    against a fake `OpenAI` class and asserts `"tools"` is never a key in the
    `responses.create(...)` call, `store=False` is always sent, and the client
    is constructed with the configured `timeout`/`max_retries` (brief §2.1,
    §6.4 naming).
  - `test_ai_context_never_includes_another_opportunitys_data` — the positive
    half of cross-opportunity leakage that F.6 named as missing: a second
    opportunity with distinctive name/account/body text exists, and asking
    about the first opportunity proves none of that text reaches the model.
  - `test_ai_treats_hostile_note_content_as_inert_data` — an
    instruction-shaped hostile note body reaches the model only as quoted
    timeline text; even a simulated answer that *claims* to have deleted and
    shared the opportunity produces no row-count change and no new share row,
    because there is no tool surface to act through.
  - `test_build_timeline_context_reports_a_missing_opportunity`,
    `test_build_timeline_context_reports_no_entries_yet`,
    `test_build_timeline_context_includes_follow_up_dates_and_comments`,
    `test_extract_referenced_entry_ids_deduplicates_and_ignores_unknown_ids` —
    close `ai_service.py`'s remaining branch gaps (the defensive
    opportunity-not-found path, the no-entries path, the follow-up-date and
    comment-rendering branches, and the dedupe/unknown-id branch in
    `extract_referenced_entry_ids`), unrelated to the client wrapper but
    needed to clear the module's ≥95% branch floor.
- `tests/test_settings.py` (+2) — `openai_timeout_seconds` must be positive,
  `openai_max_retries` must not be negative.

Coverage moved 95.46% → 96.22% while the codebase grew 1451 → 1465 statements.
`ai_service.py` moved 79% → **100%**, closing the floor gap F.5's log entry
named. `routes_ai.py` and `settings.py` stay at 100%.

Brief §6.2's ≥95% branch floor for critical modules: `auth.py`, `permissions.py`,
`soft_delete.py`, `audit_utils.py`, and now `ai_service.py` are all at 100%.

Frontend: still 0% (no test runner) — unchanged; F.7's scope.

---

## F.7 — Test infrastructure (§4.7)

### Backend

```
189 passed in 57.71s
TOTAL: 1472 stmts, 32 miss, 226 branches, 30 partial
Required test coverage of 90% reached. Total coverage: 96.35%
```

189 tests, up from 138: **+51**, no test removed or weakened.

- `tests/test_authorization_matrix.py` (+39) — every endpoint the app serves,
  against all five actors. One parametrized test per endpoint plus
  `test_every_endpoint_has_a_matrix_entry`, which reads the endpoint list out
  of the running app (`tests/route_registry.py`) and fails when a route ships
  without an expectation. Both halves were confirmed to fail against mutated
  code before being trusted (brief §6.5): adding an unregistered route fails
  the completeness test, and replacing `require_edit_permission` with
  `require_timeline_write` in `routes_timeline.update_timeline_entry` fails
  `PATCH /api/timeline/{entry_id}`. This is also where F.5's carried-over
  "authorization-matrix entries with the tightened expectations" lands.
- `tests/test_invariants.py` (+10) — brief §2, under the §6.4 naming. AI data
  layer refuses writes; the AI route is wired to that connection; no comment
  edit route exists at any path shape and `PATCH`/`PUT` are refused over HTTP;
  editing a note marks it and keeps the history; every delete endpoint stamps
  rather than removes; `event_timestamp` is editable; `created_at` cannot be
  set or moved through any endpoint that takes a body; the stage list is fixed
  and anything outside it is a 422. Two were confirmed to fail against mutated
  code (pragma removed, an eighth stage added).
- `tests/test_seed.py` (+2) — the demo data is what `make seed` prints that it
  is, including the permission relationships and the stalled flag.

Per-module, against brief §6.2's ≥95% branch floor for critical modules:

| Module | Coverage | Note |
|---|---|---|
| `auth.py` | 100% | |
| `permissions.py` | 100% | |
| `soft_delete.py` | 100% | |
| `audit_utils.py` | 100% | |
| `ai_service.py` | 100% | |
| `routes_ai.py` | 100% | |
| `database.py` | 94% | the one new miss is `read_only_connection`'s cleanup on an unused branch; not a permission-critical module |

### Frontend — first measurement (was 0%: no runner existed)

```
Test Files  6 passed (6)
     Tests  80 passed (80)
Statements : 87.09% ( 405/465 )
Branches   : 79.29% ( 226/285 )
Functions  : 88.33% ( 106/120 )
Lines      : 86.81% ( 395/455 )
```

Vitest + React Testing Library, jsdom, `@vitest/coverage-v8`, over `app/` and
`lib/` (`lib/api-types.ts` is generated and excluded — the contract check in
`scripts/generate-api-client.sh` is what guards it; `app/test-api.ts` is test
infrastructure).

| File | Line % |
|---|---|
| `lib/time.ts` | 100% |
| `lib/api.ts` | 100% |
| `lib/permissions.ts` | 100% |
| `lib/notifications.ts` | 100% |
| `app/MarkdownText.tsx` | 100% |
| `app/page.tsx` | 85.4% |

Brief §6.2's frontend floor is ≥80% line. The enforced thresholds in
`frontend/vitest.config.ts` are set **above** it — lines 85, statements 85,
functions 85, branches 78 — so the measured value is what has to be kept, not
the brief's minimum. Never lowered; raising them is how a future gain is held.

The suite was confirmed to catch a real regression rather than merely execute
code: inverting `canChangeItem` in `lib/permissions.ts` fails three tests
across the unit and component suites.

### E2E

13 Playwright tests, 0 before. Brief §6.3 journeys 1, 2, 3, 5, 11 and 12 (12
adapted — see **D-025**), plus axe on four screens. Journeys 4, 6, 7, 8, 9, 10
and 13 depend on features no phase has shipped yet (attachments, search,
custom fields, board view, reminders, automations, command palette) and are
added in the phases that build them.

Coverage moved 96.22% → 96.35% on the backend while the codebase grew
1465 → 1472 statements, and 0% → 86.81% on the frontend.

## F.8 — Gap-analysis fixes not covered above

No new production code paths — this milestone is fixes and cleanup, not
features — so coverage is reported to show it did not regress, not to show
growth.

```
190 passed
TOTAL   1469 stmts   30 miss   96% line   96%-line-branch combined coverage
Required test coverage of 90% reached. Total coverage: 96.46%
```

Frontend, after the repository-wide Prettier reformat (whitespace-only, no
statements added or removed):

```
Test Files  6 passed (6)
     Tests  80 passed (80)
Statements : 87.09% ( 405/465 )
Branches   : 79.29% ( 226/285 )
Functions  : 88.33% ( 106/120 )
Lines      : 86.87% ( 397/457 )
```

Unchanged from F.7's measurement to three significant figures — expected,
since no `app/`/`lib/` behavior changed, only formatting.

One new test (`test_login_purges_expired_sessions`, `tests/test_auth.py`)
covers the new sweep in `auth.create_session`; one existing test
(`test_ai.py::test_build_timeline_context_reports_a_missing_opportunity`)
gained the `client` fixture it should always have had, which is a
test-isolation fix, not new coverage.

## F.9 — Phase F gate (full `make check`, sandbox half)

No production code changed this milestone — this is the gate run, not a
feature. Numbers confirm no regression since F.8's measurement.

```
backend:  190 passed, 96.46% combined line+branch coverage
          (--cov-fail-under=90 enforced)
frontend: 6 files / 80 passed
          Statements 87.09%  Branches 79.29%  Functions 88.33%  Lines 86.87%
          (thresholds in vitest.config.ts: 85/85/85/78 — met)
e2e:      13 passed (7 specs), axe on 4 screens
```

Identical to F.8's measurement to the figures reported there — expected,
since F.9 added no application code, only the review packet and this
history entry.

## Phase F summary (F.1 baseline → F.9 gate)

| | F.1 baseline | F.9 gate |
|---|---|---|
| Backend tests | 39 | 190 |
| Backend coverage | 96% line (no branch figure yet) | 96.46% line+branch combined |
| Frontend tests | 0 (no runner) | 80 |
| Frontend coverage | 0% | 86.87% line |
| E2E tests | 0 | 13 |
| Invariant tests | 0 named | 10 named `test_invariant_*`, plus 2 living beside their code |
| Authorization matrix | none | 38 endpoints × 5 actor types |

---

## Phase 1 — milestone 1.1 (GitHub Actions CI)

No application code changed — this milestone is a workflow file, a Dockerfile
stage, and Makefile/script plumbing. Reported to show no regression, not
growth.

```
backend:  190 passed, 96.46% combined line+branch coverage (unchanged from F.9)
frontend: 80 passed, 86.87% line (unchanged from F.9)
```

`make docker-test`'s in-image pytest run uses the same `--cov-fail-under=90`
command as `check-fast`; it has no separate coverage report here because
building and running it needs the Docker socket this sandbox does not have —
it is the host gate's job (`scripts/autopilot-gate.sh 1`), same as the image
build and smoke test always have been.

## Phase 1 — milestones 1.1a + 1.2

No application code changed — 1.1a is a one-line CI trigger filter
(`.github/workflows/ci.yml`), and 1.2 (Alembic baseline/one-shot bridge) was
confirmed already satisfied by Phase F milestone F.4, so there was nothing to
re-implement.

```
backend:  190 passed, 96.46% combined line+branch coverage (unchanged from 1.1)
frontend: 80 passed, 86.87% line (unchanged from 1.1)
```

## Phase 1 — milestone 1.3 (`/api/v2`: pagination envelope, error shape)

First milestone of Phase 1 to add application code. Seven new endpoints, two
new modules (`app/pagination.py`, the rewritten `app/errors.py`), one new test
file (`tests/test_api_v2.py`, 20 tests) and 7 new authorization-matrix entries.

```
backend:  217 passed (was 190), 96.82% combined line+branch coverage
          (was 96.46%; --cov-fail-under=90 enforced)
          app/pagination.py  100% line, 100% branch
          app/errors.py      100% line, 100% branch
frontend: 80 passed, 86.87% line (unchanged — no frontend source changed;
          lib/api-types.ts is generated and carries no executable code)
```

Coverage rose rather than held because both new modules are fully exercised
and the v2 handlers reuse the v1 row-mapping code that was already covered.

Authorization matrix: 38 endpoints → 45, each v2 entry carrying the same
expectations as the v1 route it mirrors.

## Phase 1 — milestone 1.4 (FTS5 search index, triggers, `/api/v2/search`)

Two new modules (`app/search.py`, `app/routes_search.py`), one migration
(`alembic/versions/20260917_0002_search_index.py`), one new tool
(`tools/reindex.py`), one new test file (`tests/test_search.py`, 30 tests) and
one new authorization-matrix entry. `routes_timeline.py`'s keyword filter was
reimplemented against the index, so its existing tests cover changed code.

```
backend:  247 passed (was 217), 97.11% combined line+branch coverage
          (was 96.82%; --cov-fail-under=90 enforced)
          app/search.py        100% line, 100% branch
          app/routes_search.py 100% line, 100% branch
          app/permissions.py   100% line, 100% branch (unchanged; brief §6.2's
                               95%-branch floor for permissions modules holds)
frontend: 80 passed, 86.87% line (unchanged — no frontend source changed; the
          search UI is milestone 1.5's, see D-035. lib/api-types.ts is
          generated and carries no executable code)
```

Authorization matrix: 45 endpoints → 46.

The one branch that needed a test written for it rather than falling out of the
feature tests is `search.matches_pattern`'s empty-token guard: `search()`
returns early on a query with no words, so no request reaches it, but
`build_snippet` is a public helper and without the guard its alternation would
be empty and match at every position. `test_build_snippet_with_no_tokens_marks_
nothing` pins that.

## Phase 1 — milestone 1.5 (React Router, TanStack Query, the search page)

The first milestone since F.7 to add frontend source: three new components and
modules with tests (`app/AppRoot.tsx`, `app/SearchPage.tsx`, `lib/query.ts`,
`lib/snippet.ts`), two new test files, and `lib/api.ts` extended to raise the
v2 error envelope's message.

```
backend:  247 passed, 97.11% combined line+branch coverage (unchanged — the
          only backend change is the printed seed tour, which test_seed.py
          already covers)
frontend: 101 passed (was 80), 88.21% line (was 86.87%), 81.79% branch,
          90% functions
          app/AppRoot.tsx    100% line, 100% branch
          app/SearchPage.tsx 100% line, 94.73% branch
          lib/query.ts       100% line, 100% branch
          lib/snippet.ts     100% line, 100% branch
          app/Home.tsx       85.43% line (unchanged file, renamed from page.tsx)
e2e:      18 passed (was 13) — journey 6 lands with the search page
```

The thresholds in `frontend/vitest.config.ts` are unchanged (lines 85,
statements 85, functions 85, branches 78) and the measured values are now
further above them. They are not raised here because `app/Home.tsx`, which
dominates the total, is rewritten in milestone 2.1; ratcheting on a number that
is about to move would fail the gate for a reason unrelated to test quality.

`SearchPage.tsx`'s two uncovered branches are the `?? ""` fallback for a form
field that cannot be absent, and the `isFetchingNextPage` label swap, which
needs a request held open mid-flight to observe.

The two guard tests here were both confirmed to fail first (brief §6.5): the
empty-export-shell assertion in `app/AppRoot.test.tsx` reports the rendered
sign-in markup when the browser-only gate is removed, and the v2 envelope test
in `lib/api.test.ts` reports "Request failed" against the old `detail`-only
wrapper.

## Phase 1 — milestone 1.6 (`/api/health` detail, `VACUUM INTO` backups and restore)

Backend-only: one new module (`app/backup.py`), `/api/health` rewritten from a
bare `{"status": "ok"}` to a typed `HealthStatus`, two new CLI tools
(`tools/backup.py`, `tools/restore.py`), no frontend source touched.

```
backend:  255 passed (was 247), 97.23% combined line+branch coverage
          (was 97.11%; --cov-fail-under=90 enforced)
          app/backup.py  100% line, 100% branch
          app/main.py    97% line (was 93% before this milestone's own new
                         code; app/main.py:122 pre-existing, unrelated to
                         this change)
frontend: 101 passed, 88.21% line, 81.79% branch (unchanged — no frontend
          source changed; frontend/lib/api-types.ts regenerated for the new
          HealthStatus schema, generated code carries no executable coverage)
e2e:      18 passed (unchanged — no user-facing surface added)
```

Authorization matrix: unchanged at 46 endpoints (`/api/health` was already
registered as a public, identity-independent surface; its response body
changed shape but not its authorization behavior).

The one branch that needed a dedicated test rather than falling out of the
feature tests is `main.py`'s health-check failure path: `database.
get_connection()` asserts WAL mode on every call, which is itself a write, so
a database that is genuinely unwritable can fail before the explicit
`BEGIN IMMEDIATE` probe ever runs (D-042). `test_health_reports_unwritable_
when_the_database_file_is_read_only` makes the file *and* its `-wal` sidecar
*and* the containing directory read-only — WAL means a write can land in the
sidecar without ever touching the main file's bytes — and was confirmed to
reproduce the uncaught `sqlite3.OperationalError` against the pre-fix code
(only the probe wrapped in `try`/`except`) before the fix was applied, per
brief §6.5.

`tests/test_backup.py::test_restore_recovers_data_written_after_a_backup` is
the test ADR 0011 asks for by name ("a restore procedure must be written and
actually exercised"): back up, write more data through the real API, restore,
and assert the write is gone and the backed-up state is back — not just that
`restore_backup` runs without raising.

## Phase 1 — milestone 1.7 (notifications inbox rework)

New migration (`20260920_0003_notification_history.py`), the v2 notifications
route rewritten from a v1 mirror into the real inbox, one new v2 endpoint
(`mark-all-read`), and the first frontend change to the notification panel
since the MVP shipped it.

```
backend:  258 passed (was 255), 97.28% combined line+branch coverage
          (was 97.23%; --cov-fail-under=90 enforced)
          app/routes_notifications.py    100% line, 100% branch (was 96%/—)
          app/notification_service.py    97% line, 97% branch — the one
                                          uncovered branch (line 129) is
                                          notify_mentions' "actor mentioning
                                          themselves" skip, pre-existing and
                                          untouched by this milestone
frontend: 102 passed (was 101), 88.38% line (was 88.21%), 80.86% branch
          (was 81.79% — still above the configured floor of 78%), 90.54%
          functions
          app/Home.tsx  85.74% line (was 85.43%) — the notification panel's
                        new controls are exercised by the two notification
                        tests; the drop in the overall branch percentage
                        (81.79% -> 80.86%) is this file picking up branches
                        (the empty-state ternary, the disabled-button
                        condition) faster than the two new tests cover them,
                        not a regression anywhere already covered
e2e:      18 passed (unchanged) — 04-mentions.spec.ts and the notification
          panel a11y test in 07-accessibility.spec.ts both re-run against the
          rewritten panel (same button name, same `.notification-panel`
          class, same displayed text) rather than needing new assertions
```

Authorization matrix: 46 → 47 endpoints. `POST /api/v2/notifications/
mark-all-read` is `authenticated_only(200)`, the same shape as every other
self-scoped-by-the-query surface (`GET /api/notifications`,
`GET /api/v2/notifications`).

The thresholds in `frontend/vitest.config.ts` (lines 85, statements 85,
functions 85, branches 78) are unchanged and still comfortably cleared;
not raised here for the same reason milestone 1.5 gave — `app/Home.tsx`
dominates the total and is rewritten in milestone 2.1.

The guard test for this milestone (brief §6.5: confirmed to fail against the
unfixed code first) is `test_v2_notification_history_survives_being_read_
and_can_be_filtered_by_type` in `backend/tests/test_api_v2.py`: run against
the pre-milestone `list_notifications_page` (unread-only, no `read_at` field),
the "after" assertion — that a notification marked read is still in the v2
page — fails with a `KeyError` on `read_at`, which is the exact dead end this
milestone closes.

## Phase 1 — gate (end of phase, all milestones 1.1–1.7 done)

No application code changed in this session — it re-ran the full sandbox
half of the split gate (brief §3.4) at the commit milestone 1.7 left, to
confirm the phase is ready for `AWAITING_REVIEW`. Figures are unchanged from
the 1.7 gate above, run fresh rather than copied forward:

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          258 passed, 97.28% combined line+branch coverage
          (--cov-fail-under=90 enforced)
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (1 pre-existing eslint warning, 0 errors — see phase-1-summary.md)
          102 passed, 88.38% line / 80.86% branch / 90.54% functions
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
e2e:      18 passed (7 specs), axe clean on every screen it runs against,
          including the deferred color-contrast ratchet still failing on cue
docker:   deferred to the host half — scripts/autopilot-gate.sh 1
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend ≥ 90% line / ≥ 80% branch
(97.28% combined); frontend ≥ 80% line (88.38%); the five ≥95%-branch modules
(`permissions.py`, `audit_utils.py`, plus `auth.py`/`soft_delete.py`/
`routes_ai.py`, all still at or above 95% per their per-milestone entries
above) unchanged since Phase F.

Full detail and the try-it steps: `docs/autopilot/reviews/phase-1-summary.md`.


## Phase 2 — milestone 2.1 (decompose `Home.tsx`, routed views, query cache)

No backend code changed. The whole frontend changed: `app/Home.tsx` is gone and
thirteen components plus `lib/queries.ts` and `lib/domain.ts` stand where it
was.

```
backend:  258 passed (unchanged), 97.28% combined line+branch coverage
          (--cov-fail-under=90 enforced). No application file touched;
          scripts/e2e-server.sh gained one exported environment variable.
frontend: 110 passed (was 102), 95.76% line (was 88.38%), 88.32% branch
          (was 80.86%), 94.42% functions (was 90.54%)
          thresholds raised 85/85/85/78 -> 93/93/92/85 (D-058)
          lib/queries.ts    100% line, 95% branch
          lib/domain.ts     100% line
          every app/ component at or above 75% line, the lowest being
          TimelineFilterBar (75%: its type, to and author-id inputs are typed
          by no test yet) and TimelineEntryForm (80%: the follow-up date and
          the type select)
e2e:      19 passed (was 18), axe clean on every screen, the deferred
          color-contrast ratchet still failing on cue
```

The jump is not new tests chasing coverage; it is the same assertions reaching
code that was previously unreachable behind one 1,863-line component. The two
milestones that declined to raise the thresholds (1.5, 1.7) both named this as
the reason, so the raise lands here.

Authorization matrix: 47 endpoints, unchanged — this milestone adds no route.

The guard test for this milestone (brief §6.5: confirmed to fail against the
unfixed code first) is `keeps the conversation when the reader looks at another
opportunity` in `app/OpportunityPanel.test.tsx`. Run against an `AiSidebar`
holding its transcript in `useState` — the obvious way to write it once the
panel is per-route — it fails on the return trip, which is the behaviour
`Home.tsx` had and D-055 keeps.


## Phase 2 — milestone 2.2 (URL view state, saved views, timeline order)

One new table and one new router (`saved_views`,
`app/routes_saved_views.py`), the timeline's `order` parameter on both
timeline routes, and the frontend's two view states moved into the URL.

```
backend:  274 passed (was 258), 97.40% combined line+branch coverage
          (was 97.28%, --cov-fail-under=90 enforced)
          app/routes_saved_views.py   100% line, 100% branch
          app/soft_delete.py          100% line (the new saved-view helper
                                      keeps the module's ≥95% branch floor)
          app/schemas.py               99% line
frontend: 138 passed (was 110), 96.60% line (was 95.76%), 88.21% branch
          (was 88.32%), 95.22% functions (was 94.42%)
          thresholds unchanged at 93/93/92/85 (raised in 2.1, D-058)
          lib/viewState.ts     100% line, 100% branch
          lib/domain.ts        100% line, 92.85% branch
          app/SavedViewsMenu.tsx       100% line, 86.2% branch
          app/OpportunityFilterBar.tsx 100% line, 75% branch
e2e:      24 passed (was 19), axe clean on every screen including the newly
          filtered board, the deferred color-contrast ratchet still failing
          on cue
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Branch coverage dipped 0.11 points against 2.1 while line coverage rose: the
two new filter bars each carry a small number of select-option branches no
test exercises individually (`OpportunityFilterBar` at 75% branch), and the
saved-views menu has error branches only its failure test reaches. Both stay
well above the 85% threshold, and the floor is unchanged rather than lowered.

Authorization matrix: 47 → 51 endpoints. The four new ones are the saved-view
routes (`POST`/`GET /api/v2/saved-views`, `PATCH`/`DELETE
/api/v2/saved-views/{id}`); the registry guard fails on any route without an
entry, so they were added with the routes.

The guard test for this milestone (brief §6.5, confirmed to fail against the
unfixed code first) is `keeps the board's keyword filter out of the open
timeline's query` in `app/DashboardPage.test.tsx`. Before D-059's
entity-namespaced parameters, filtering the board sent
`GET /api/opportunities/10/timeline?q=northwind` — the board's keyword
silently filtering the open timeline, because both states were reading the
same query-string field names.

## Phase 2 — milestone 2.3 (`VirtualList` for the 400-opportunity scale)

No backend code touched — this milestone windows DOM rendering over data the
app already fetches the same way (D-063: the switch to `/api/v2/opportunities`'s
pagination stays 2.9's).

```
backend:  274 passed (unchanged), 97.40% combined line+branch coverage
          (unchanged, --cov-fail-under=90 enforced)
frontend: 143 passed (was 138), 96.74% line (was 96.60%), 88.25% branch
          (was 88.21%), 95.3% functions (was 95.22%)
          thresholds unchanged at 93/93/92/85 (raised in 2.1, D-058)
          app/VirtualList.tsx   100% line, 100% branch, 100% functions
          app/StageBoard.tsx    100% line, 100% branch, 100% functions
e2e:      24 passed (unchanged — no new journey; seeded demo data is nowhere
          near 400 rows, so these exercise the virtualized board without
          hitting its windowing), axe clean including the dashboard spec
          against the now-virtualized board
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization matrix unchanged (51 endpoints) — no new route.

New dependency: `@tanstack/react-virtual` 3.14.13. `pip-audit`: no known
vulnerabilities. `npm audit`: 0 vulnerabilities.

The guard test for this milestone (brief §6.5, confirmed to fail against the
unfixed code first) is `does not mount every row for a 400-item list` in
`app/VirtualList.test.tsx`: run against a non-virtualized stand-in
implementation, it renders all 400 rows and fails the `toBeLessThan(50)`
assertion.

One test-infrastructure change with no production effect: jsdom never lays
anything out, so a virtualized container's real `offsetHeight` is 0 and the
virtualizer (correctly) renders nothing into what it measures as a
zero-height viewport. Every existing test that renders `StageBoard` failed
this way until `vitest.setup.ts` stubbed `offsetHeight`/`offsetWidth` to a
plausible constant for the whole suite — confirmed against the unfixed setup
file before adding the stub, matching brief §6.5's "confirm a guard fails
first" for the test infrastructure itself, not just the guard test above.

## Phase 2 — milestone 2.4a (command palette and keyboard map)

No backend code touched — this milestone is navigation and input, entirely in
`frontend/`. The backend suite is re-run by the gate unchanged, as evidence
that it is unchanged.

```
backend:  274 passed (unchanged), 97.40% combined line+branch coverage
          (unchanged, --cov-fail-under=90 enforced)
frontend: 192 passed (was 143), 97.04% line (was 96.74%), 89.63% branch
          (was 88.25%), 95.67% functions (was 95.3%)
          thresholds raised 93/93/92/85 -> 94/94/93/87 (D-058's ratchet,
          applied again: a coverage gain is kept by raising the floor)
          lib/keyboard.ts          98.27% line, 97.95% branch, 100% functions
          lib/palette.ts           100%   line, 100%   branch, 100% functions
          app/CommandPalette.tsx   100%   line, 100%   branch, 100% functions
          app/Modal.tsx            95.83% line, 77.77% branch, 100% functions
          app/ShortcutsProvider.tsx 94.11% line, 100%  branch, 83.33% functions
e2e:      27 passed (was 24), axe clean, including two new surfaces — the open
          command palette and the keyboard reference dialog
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization matrix unchanged (51 endpoints) — no new route. No new
dependency: the palette and both dialogs are plain React, because 2.5 is the
milestone that brings Radix and would otherwise have two implementations to
replace. `pip-audit`: no known vulnerabilities. `npm audit`: 0
vulnerabilities.

**Critical journey 13** (brief §6.3, "keyboard-only: command palette →
opportunity → add note") lands here, in `e2e/10-keyboard.spec.ts`. Every step
after sign-in is keystrokes alone, and the note composer is reached by a
bounded Tab walk that fails with a sentence rather than hanging if the control
stops being reachable.

The guard test for this milestone (brief §6.5, confirmed to fail against the
unfixed code first) is `does not treat what the reader types as commands` in
`app/Keyboard.test.tsx`. With `isTypingTarget` removed from `chordFor`, typing
"check jack's expiry date?" into a note composer fires `c`, `e`, `j`, `k` and
`?` as commands: the dialog opens, the edit form opens, the board's cursor
moves, and the note never gets typed.

One defect the suite did not catch and the journey did (D-066): `Modal`
returned focus on unmount, so a palette jump put focus back into the form on
the screen the reader had just left. Visible only in a real browser, because
the component tests start from a body that holds no focus. Recorded here
because it is the second time in this phase that an E2E journey found
something no unit test could (2.1's D-057 was the first) — the ratio is worth
watching rather than assuming more component tests would have done it.

---

## Phase 2 — milestone 2.4b (optimistic mutations and undo toasts)

```
backend:  290 passed (was 274), 97.41% combined line+branch coverage
          (was 97.40%, --cov-fail-under=90 enforced)
          app/soft_delete.py       100%   line, 100%  branch (the four new
                                   restore cascades)
          app/routes_timeline.py   100%   line,  97%  branch
          app/routes_opportunities.py 100% line, 100% branch
frontend: 201 passed (was 192), 97.09% line (was 97.04%), 89.71% branch
          (was 89.63%), 95.66% functions (was 95.67%)
          thresholds unchanged at 94/94/93/87 — the measurement is flat
          (+0.05 line, +0.08 branch, -0.01 functions), so there is no gain to
          ratchet. D-058's rule is that a gain is kept, not that the floor
          moves every milestone.
          app/Toasts.tsx           100%   line, 100%  branch, 95.45% functions
          lib/queries.ts           98.75% line, 80.76% branch, 98.52% functions
e2e:      29 passed (was 27), axe clean, including the timeline with an undo
          toast open (the live region is a new surface)
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization matrix: 51 → 55 endpoints, the four restore routes. Each one's
expectations are its delete twin's, because it is the same rule — except the
opportunity restore, where a former editor and viewer get 404 rather than 403:
deleting the opportunity deleted the share rows that made it visible to them.
`World` gained four deleted fixtures, since there is nothing to restore about a
live row. No new dependency; no migration. `pip-audit`: no known
vulnerabilities. `npm audit`: 0 vulnerabilities.

The guard test for this milestone (brief §6.5, confirmed to fail against the
unfixed code first) is `removes what was deleted before the server has
answered` in `app/Undo.test.tsx`. It holds the DELETE response open — a new
`pending` option on the fake API, since an optimistic update is only
observable while its request is still in flight — and asserts the comment has
already left the DOM. With `onMutate` removed from `useDeleteComment` it fails.

Two things the tests found rather than the design:

- The undo toast outlives the control that raised it, so per-call mutation
  callbacks are the wrong mechanism: deleting a note unmounts the note, and
  TanStack Query drops `mutate(vars, { onSuccess })` when the observer has no
  listeners left. `mutateAsync` resolves either way.
- A delete writes an audit row, and the audit panel was showing a list fetched
  before it. Fixed by invalidating the `["audit-log"]` prefix from every
  delete and restore, which is also the only way those mutations can express
  it — they know the id of the thing they removed, not the opportunity it
  hung under.

---

## Phase 2 — milestone 2.4c (bulk actions)

```
backend:  302 passed (was 290), 97.47% combined line+branch coverage
          (was 97.41%, --cov-fail-under=90 enforced)
          app/routes_opportunities.py  bulk_opportunity_action: 100% line,
                                        100% branch (both actions, the
                                        per-item error branch, the
                                        same-id-twice branch, the
                                        set-stage-to-current-stage no-op)
          app/schemas.py                99% line (unchanged; the new
                                        BulkOpportunityAction/BulkAction
                                        Response/BulkActionResultItem models
                                        add no uncovered branch)
frontend: 208 passed (was 201), 96.6% statements (was ~97%), 96.47% line,
          95.35% functions, 88.73% branch — thresholds unchanged at
          94/94/93/87, all four still clear the floor
          app/BulkActionBar.tsx    100% line, 100% branch
          app/StageBoard.tsx       100% line, 100% branch (was 84.37%/88% —
                                    the checkbox and its onChange branch)
          app/DashboardPage.tsx    ~91% line — the bulk handlers' error
                                    paths (network failure on the mutation
                                    itself, not a per-item result) are the
                                    remaining gap, same shape as the
                                    pre-existing uncovered lines in the
                                    single-delete path
e2e:      30 passed (was 29), axe clean on the open action bar
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization matrix: 55 → 56 endpoints, the one new bulk route. It answers
`authenticated_only(200)` in the matrix rather than a scoped owner/editor/
viewer split, because ids in one request can span
ownership boundaries and a single status code cannot represent that — the same
reasoning `GET /api/v2/search` already carries. The real per-item authorization
(owner succeeds, editor/viewer get a "forbidden" item, an unrelated id gets
"not found") is `tests/test_bulk_actions.py`'s, not the matrix's. No migration:
`delete` and `set_stage` are the existing `opportunities` table's existing
columns. `pip-audit`: no known vulnerabilities. `npm audit`: 0 vulnerabilities.

Two things found rather than assumed, both recorded at the milestone in
`PROGRESS.md`:

- The checkbox's shift-click detection moved from `onClick` +
  `preventDefault` to `onChange` reading `nativeEvent.shiftKey`, after the
  `onClick` version passed every Vitest/jsdom test and then failed in real
  Chromium — a controlled checkbox's native toggle and React's own
  checkbox-change wiring did not agree on which event should win once
  `preventDefault` was in the mix. Found by running the E2E spec, not by the
  unit suite, which is the same category of gap 2.4a's D-066 named (a defect
  only visible in a real browser).
- Playwright's own `.click()` on a board checkbox this far down the page
  intermittently completed without the change handler firing, confirmed via
  a raw CDP mouse sequence at the same coordinates (which worked every time)
  to be Playwright's scroll-then-click sequencing rather than an application
  defect before writing `e2e/12-bulk-actions.spec.ts`'s retrying `check`
  helper around it.

## Phase 2 — milestone 2.5 (design tokens, Radix dialogs, light and dark themes)

```
backend:  302 passed (unchanged), 97% combined line+branch coverage
          (--cov-fail-under=90 enforced) — no backend change in this
          milestone: tokens, dialogs and themes are all client-side
frontend: 298 passed (was 280), 96.75% statements, 96.74% line, 95.11%
          functions, 89.32% branch — thresholds raised 94/94/93/87 ->
          96/96/94/88 and all four still clear the floor
          lib/contrast.ts          100% line, 100% branch (new)
          lib/theme.ts             100% line, 100% branch (new)
          app/ConfirmDialog.tsx    100% line, 100% branch (new)
          app/Theme.tsx            93% line — the `useSyncExternalStore`
                                    server snapshot (`() => false`) is the
                                    export pass's answer and no browser test
                                    reaches it
          app/Modal.tsx            100% line (unchanged; the internals moved
                                    to Radix behind the same two rules)
e2e:      42 passed (was 30) — the axe screens now run twice, once per
          colour scheme, plus the search page, the three dialogs, and
          13-theme.spec.ts for the switch itself
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

`DEFERRED_AXE_RULES` is now **empty**. It held `color-contrast` from Phase F
(D-026) against exactly this milestone; `07-accessibility.spec.ts` audits
every screen under both `prefers-color-scheme` values with contrast included,
and the ratchet's own guard test still stands for whatever might be added
next. `lib/contrast.test.ts` measures 28 text pairs and 6 non-text pairs in
each palette — 72 assertions — straight out of `app/globals.css`, so a token
edited to an unreadable value fails the unit suite before axe sees a page.

No migration, no new route, so the authorization matrix is unchanged at 56
endpoints. `pip-audit`: no known vulnerabilities. `npm audit`: 0
vulnerabilities, with two dependencies added (`@radix-ui/react-dialog`,
`@radix-ui/react-alert-dialog`).

Two things found rather than assumed:

- **Two axe failures the palette work exposed rather than caused.**
  `.notification-row.is-read` faded read rows with `opacity: 0.6`, which
  multiplies a measured ratio into an unmeasured one; it now recedes with the
  sunken surface and secondary text role, both pairs the contrast test holds
  to AA. Colour was never the only carrier there — an unread row is the one
  with a "Mark read" button.
- **A real interaction defect, found by the E2E suite going red** (D-072):
  focusing a card by clicking a control inside it moved the board's keyboard
  cursor, which made the virtualized column scroll to it — out from under the
  pointer, between the mousedown and the mouseup. Eight journeys failed on it
  once the token work changed where cards sit; the fix is that the column
  follows the cursor only when the keyboard moved it.

## Phase 2 — milestone 2.6 (three new entry types, entry-type icons)

```
backend:  304 passed (was 302), 97.47% combined line+branch coverage
          (--cov-fail-under=90 enforced) — the two new tests exercise the
          rebuilt CHECK constraint end-to-end: the three new types accepted
          and filterable, an unrecognized type still rejected with a 422
frontend: 316 passed (was 298), 96.76% statements, 96.75% line, 95.13%
          functions, 89.32% branch — thresholds unchanged at 96/96/94/88,
          not raised this milestone (small, well-covered addition; the
          measured value moved only fractionally)
          app/EntryTypeBadge.tsx   100% line, 100% branch (new)
e2e:      unchanged this milestone (deferred to the phase-end full gate,
          brief §3.4) — no new journey, no existing one touches the badge
          markup in a way its own text content wouldn't still satisfy
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

One migration this milestone — the project's first table rebuild rather than
an additive column, since SQLite has no `ALTER TABLE ... ADD CHECK`
(`backend/alembic/versions/20260921_0005_entry_types.py`). No new route, so
the authorization matrix is unchanged. `pip-audit`/`npm audit`: not re-run
this milestone (`make check-fast` only; deferred to the phase-end `make
check` per brief §3.4).

Found rather than assumed: `docs/DESIGN-SYSTEM.md` already commits to "never
colour alone" for entry types and lists `EntryTypeBadge` as an unbuilt domain
component — scoping icons to only the three new types (the roadmap
sentence's literal reading) would have left 8 of 11 types colour-only.
Logged as **D-078** (needs human review) and built for all eleven.

## Phase 2 — milestone 2.7 (board drag, list view, dashboard layout)

```
backend:  305 passed (was 304), 97.47% combined line+branch coverage
          (--cov-fail-under=90 enforced) — one new test, for the exact
          request a drag sends: a stage-only PATCH logs the system entry and
          leaves every other field alone
frontend: 344 passed (was 316), 96.74% statements, 96.71% line, 95.54%
          functions, 89.16% branch — thresholds unchanged at 96/96/94/88
          app/StageBoard.tsx        93.0% line, 90.6% branch (rewritten)
          app/OpportunityList.tsx   80.0% line, 75.0% branch (new)
          app/MoveToStage.tsx       100%  line, 100%  branch (new)
          app/ViewSwitcher.tsx      100%  line, 100%  branch (new)
          app/useOpportunityItem.ts 100%  line, 100%  branch (new)
e2e:      44 passed (was 41) — run in full for this milestone rather than
          deferred, because the layout work moved selectors thirteen other
          specs use. New: e2e/14-board-views.spec.ts, critical journey 8
          (brief §6.3) — a real pointer drag between stage columns and the
          system entry it writes, the keyboard move, and the list view.
          axe clean on every screen in both themes; DEFERRED_AXE_RULES
          stays empty.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

No migration and no new route this milestone, so the authorization matrix is
unchanged: a drag is `PATCH /api/opportunities/{id}` with one field, already
owner-only through `require_opportunity_owner` and already in the matrix.
`pip-audit`/`npm audit`: not re-run (`make check-fast` plus E2E; the audits
belong to the phase-end `make check` per brief §3.4). No new dependency —
the drag is the browser's own (D-080).

Two coverage notes worth keeping. `OpportunityList.tsx`'s uncovered lines are
the virtualizer's own render callbacks, the same shape already uncovered in
`StageBoard.tsx`. And the board's empty-list branch was deleted rather than
tested: `DashboardPage` answers an empty view itself, with two different
answers ("there are none yet" and "your filters removed them all"), so the
view components can never be asked to draw nothing.

## Phase 2 — milestone 2.13 (saved-view sharing, view management, labelled controls)

```
backend:  unchanged — 305 passed, 97.47% combined line+branch
          (--cov-fail-under=90 enforced). No schema and no route change:
          PATCH /api/v2/saved-views/{id} shipped with 2.2 and this is its
          first caller, so it was already in the authorization matrix.
frontend: 354 passed (was 344), 96.54% statements, 96.51% line, 95.22%
          functions, 89.23% branch — thresholds unchanged at 96/96/94/88
          app/SavedViewsMenu.tsx     94.7% line, 92.3% branch (rewritten)
          app/ManageSavedViews.tsx   new
          app/SavedViewFields.tsx    new
          lib/domain.ts              100%  line, 95%   branch
e2e:      46 passed (was 44). New in e2e/09-saved-views.spec.ts: a view
          saved for everyone and read back by the colleague it reaches, and
          the manage-dialog rename/delete round trip with axe over the open
          dialog. axe clean; DEFERRED_AXE_RULES stays empty.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

`pip-audit` and `npm audit` were run for this milestone (full `make check`,
not just `check-fast`) and are clean. No new dependency.

One finding worth keeping, because it is a rule rather than a fix: nesting
`app/ConfirmDialog.tsx` (Radix `AlertDialog`) inside `app/Modal.tsx` (Radix
`Dialog`) does not stack. The two focus traps pull focus from each other, and
the vitest worker aborted with SIGABRT after 165,066 `Maximum call stack size
exceeded` errors in `HTMLButtonElement.focus`. The delete confirmation moved
into the row instead (**D-083**); `useConfirm` is for a question raised from
the page, not from inside another dialog.

## Phase 2 — milestone 2.8 (table and calendar views, density modes)

```
backend:  unchanged — 305 passed, 97.47% combined line+branch
          (--cov-fail-under=90 enforced). No schema, no route, no new
          authorization-matrix entry: both views are renderers over the list
          GET /api/opportunities already returns whole (D-061), so nothing
          on the server moved.
frontend: 391 passed (was 354), 96.88% statements, 96.85% line, 95.59%
          functions, 90.18% branch. Thresholds raised 96/96/94/88 ->
          96/96/95/89.
          app/OpportunityTable.tsx    100%   line, 94.4% branch (new)
          app/OpportunityCalendar.tsx 100%   line, 100%  branch (new)
          app/ColumnPicker.tsx        92.3%  line, 87.5% branch (new)
          app/Density.tsx             100%   line (new)
          lib/density.ts              100%   line, 100%  branch (new)
          lib/domain.ts               100%   line, 98.2% branch
e2e:      49 passed (was 46). New in e2e/15-table-calendar.spec.ts: the
          table's column picker and header sorting surviving a reload,
          compact density surviving one, and the calendar placing a deal on
          its close month, listing what it cannot place, and walking months
          through the URL. axe clean on both new views;
          DEFERRED_AXE_RULES stays empty.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

`pip-audit` and `npm audit` were run for this milestone (full `make check`,
not just `check-fast`) and are clean. No new dependency: the calendar is a CSS
grid and the table reuses `app/VirtualList.tsx`.

One defect found and fixed inside the milestone rather than worked around: the
bulk selection was derived from the *reading order of the current view*
(`ordered`), which is every filtered opportunity on the board, the list and the
table — but only the drawn month in the calendar. Switching to the calendar
therefore shrank a live selection to whatever that month happened to show. It
now derives from the filtered set (`visibleOpportunities`), which is identical
for the three views that were already shipping and correct for the fourth. The
guard test is `keeps a selection made in another view, even when the month
hides it` in `app/DashboardPage.test.tsx`, confirmed to fail against the
unfixed code first (brief §6.5): `0 selected` where `1 selected` was expected.

## Phase 2 — milestone 2.9a (reset view state on sign-out, D-091)

```
backend:  unchanged — 305 passed, 97.47% combined line+branch. No route, no
          schema, no permission touched: this is a frontend-only navigation
          fix.
frontend: 393 passed (was 391), 96.89% statements, 96.85% line, 95.60%
          functions, 90.18% branch — against the 96/96/95/89 floor 2.8 set;
          no threshold change needed for two call sites and two tests.
          app/TopBar.tsx               100%   line (unchanged; new branch)
          app/CommandPalette.tsx       97.3%  line, 90.9% branch
e2e:      unchanged at 49 — no new route, no new journey; sign-out is not one
          of brief §6.3's critical journeys.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

`make check-fast` only for this milestone (ruff, ruff format, mypy, eslint,
tsc, prettier, backend suite, frontend suite, contract check) — a two-file
frontend fix with no schema or route change does not need `pip-audit`,
`npm audit`, E2E or Docker re-run; the previous milestone's full `make check`
already covers everything else at this commit's ancestor.

Two things found and fixed inside the milestone rather than worked around,
per brief §6.5, both confirmed against the unfixed code first:

1. The reviewer-reported symptom itself (D-091): after the fix, signing out
   from a URL carrying `?opportunities.view=table` and signing back in as
   another user now lands on the default Board view, not Table. Guard tests:
   `resets the view state in the URL on sign-out, for the next reader in this
   tab` (`app/DashboardPage.test.tsx`) and `resets the view state in the URL
   when signing out from the palette` (`app/Keyboard.test.tsx`), each
   confirmed to fail with `aria-pressed="false"` on the Board button against
   the pre-fix code.
2. A second, independent bug in the first draft of the fix itself (D-092):
   `app/CommandPalette.tsx`'s "Sign out" command unmounts the palette
   (`onClose()`) before its `logout.mutate(undefined, { onSuccess })` call
   resolves, so TanStack Query silently drops the `onSuccess` callback — the
   same "observer has no listeners" case `CLAUDE.md` documents for
   `app/Toasts.tsx`'s undo. Found by instrumenting the callback (it never
   ran) rather than by reasoning about the mutation library first. Fixed by
   switching both `TopBar.tsx` and `CommandPalette.tsx` to `mutateAsync()`,
   the pattern already established in this codebase for exactly this shape.

## Phase 2 — milestone 2.9 (finish the /api/v2 migration, remove v1)

```
backend:  324 passed (was 305), 97.13% combined line+branch (was 97.47%).
          app/errors.py               89%   line, 70% branch (was 100%)
          app/main.py                 96%   line
          app/routes_opportunities.py 93%   line
          app/routes_sharing.py       91%   line
          app/routes_timeline.py      93%   line
          app/routes_notifications.py 100%  line
          app/routes_auth.py          100%  line
          Branch floors that brief §6.2 sets at 95% are untouched: auth,
          permissions, soft_delete, audit_utils and the AI modules are all
          at 100%.
frontend: 394 passed (was 393), 96.90% statements, 96.86% line, 95.59%
          functions, 90.20% branch — against the 96/96/95/89 floor 2.8 set.
          lib/queries.ts              98.95% statements, 81.25% branch
          app/test-api.ts             (the fake; excluded from coverage)
e2e:      49, unchanged — no new journey. Three specs that call the API
          directly moved onto v2 paths and stopped reading the opportunity
          id out of a fixed path segment, which shifted by one.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Full `make check` for this milestone, including `pip-audit` and `npm audit`
(both clean) and the 49 Playwright specs with axe. No new dependency.

**The coverage movement is one file and is understood.** `errors.py` went
from 100% to 89% line / 70% branch because its three `is_api_path` guards
each have a "not the API" arm, and removing v1 removed the requests that
reached two of them. The only non-API route left is `main.py`'s
`serve_frontend`, which validates nothing and returns rather than raises, so
a validation error and an unhandled exception on a page path are no longer
reachable by request. The third arm — an `HTTPException` on a page path, which
is what a 405 there is — is covered by a new test,
`test_the_envelope_is_the_api_s_and_not_the_whole_server_s`, which also states
the rule the branch exists for: the envelope describes the API, not every
response this process serves. The guards were kept rather than deleted for
that reason; deleting them would make a browser's 405 on a page path answer in
the API's shape.

Test-count arithmetic, since three numbers moved at once: +24 for the
parametrized `test_v1_paths_are_gone` guard, +1 for
`test_the_api_has_one_error_shape` (which replaces `test_v1_keeps_its_own_shapes`),
+1 for the non-API envelope test, −7 for v1 routes whose per-route tests were
folded into their v2 twin's (the unpaginated audit-log and note-version reads,
the unread-only notification list, and the four list shapes that no longer
exist). Frontend: +2 `fetchAll` walk tests, −1 for `lib/api.test.ts`'s
"detail is a structure rather than a sentence", which described FastAPI's raw
422 list — a body no endpoint answers with now.

Two backend assertions were rewritten rather than moved, both in the
notification suite, because removing v1 removes a behaviour rather than a
shape: marking a notification read no longer makes it vanish from the list,
since the unread-only read was v1's. Each carries the reason in the test body.
Brief §6.5 allows this only for an expectation that is genuinely wrong; the
expectation here described a surface `docs/ROADMAP.md`'s breaking-changes
table scheduled for removal at the end of this phase.

## Phase 2 — milestone 2.10 (edit history for every editable thing)

```
backend:  338 passed (was 324), 97.27% combined line+branch (was 97.13%).
          app/versioning.py           100%  line, 100% branch (new)
          app/routes_opportunities.py 94%   line (was 93%)
          app/routes_timeline.py      93%   line, unchanged
          Branch floors that brief §6.2 sets at 95% are untouched: auth,
          permissions, soft_delete, audit_utils and the AI modules are all
          still at 100%.
frontend: 405 passed (was 394), 96.93% statements, 96.89% line, 95.63%
          functions, 90.29% branch — against the 96/96/95/89 floor 2.8 set.
          app/HistoryDialog.tsx       94.11% statements, 100% branch (new)
          lib/domain.ts               100%  statements, 95.31% branch
e2e:      50 (was 49). e2e/03-note-history.spec.ts now drives brief §6.3's
          journey 3 through the UI end to end instead of reading the
          versions over the API, and a second spec in the same file walks an
          opportunity's value history.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

`make check-fast` plus `make e2e` for this milestone; the full `make check`
runs at the phase gate. No new dependency.

Test-count arithmetic: backend +11 `tests/test_versions.py`, +1 migration
backfill case, +2 authorization-matrix rows (the two new routes; the note
route's existing row moved from 200 to 403 for viewer and editor rather than
being added). Frontend +11 in `app/History.test.tsx` — six UI-driven cases
(the three round trips, the loading, error and no-change states), one that
asserts an editor is offered no history at all, and three unit cases over
`versionChanges`.

One existing test changed rather than moved:
`tests/test_search.py::test_a_hard_delete_removes_the_index_row` simulates an
out-of-band hard delete and now has to remove `timeline_entry_versions` rows
first, because the new table holds a foreign key into `timeline_entries`. The
assertion it makes — that the FTS5 index does not survive a row removed by
other means — is unchanged.

## Phase 2 — milestone 2.11 (edit content where it is read)

```
backend:  338 passed, 97.27% combined line+branch — unchanged, and that is
          the finding rather than an omission: 2.10 had already made every
          write this milestone touches keep a version, and both update routes
          already applied exactly the fields they were given. No route,
          schema, migration or authorization-matrix entry changed.
frontend: 429 passed (was 405), 97.10% statements, 97.07% line, 95.80%
          functions, 90.95% branch. Branch floor raised 89 -> 90; the other
          three stay at 96/96/95, since a floor set a tenth under the
          measurement fails on churn rather than on a regression.
          app/InlineEdit.tsx          100% statements, 100% branch, 100%
                                      functions (new)
          app/OpportunityTable.tsx    100% statements, 95% branch
          app/TimelineEntryList.tsx   100% statements, 86.95% branch
          lib/domain.ts               100% statements, 95.71% branch
e2e:      52 (was 50). e2e/16-edit-in-place.spec.ts, both specs with axe:
          one walks an eight-entry timeline, edits the entry at the bottom of
          it and asserts the reader did not move (window.scrollY within 40px,
          the editor in the viewport, the entry above still drawn), the other
          edits a table cell and reloads to prove the write was real rather
          than an optimistic cache entry.
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Full `make check` for this milestone, not only `make check-fast`: the first
E2E run is what caught D-100 — labelling the inline trigger "Edit Value"
renamed the opportunity's own `<h2>` to that, because an `aria-label` on a
descendant overrides the ancestor's name-from-content. Twenty specs failed at
`openTimeline`, and none of the 405 component tests had noticed, because
`dom-accessibility-api` and Playwright's accname implementation disagree here.
The fix is in the component, not in the helper.

Test-count arithmetic: frontend +10 `app/InlineEdit.test.tsx` (the primitive
on its own, including each value it refuses), +3 `lib/domain.test.ts` over the
field declaration, +5 `app/DashboardPage.test.tsx` over the table cells,
+6 `app/OpportunityPanel.test.tsx` over the entry card, the note and the
heading. E2E +2.

One existing test's selector changed, not its expectation:
`app/History.test.tsx`'s entry-history case asked for the "Title" field
globally and now finds two, since the composer and the edited card's editor
are both on screen; it is scoped to the card it was always about.

The guard test (brief §6.5), confirmed to fail against the unfixed code
before being trusted: `opens an entry's editor inside that entry, with its
neighbours still on screen` in `app/OpportunityPanel.test.tsx`.

## Phase 2 — milestone 2.12 (fold the manual user test's deterministic half into E2E)

```
backend:  338 passed, 97.27% combined line+branch — unchanged, no backend
          code touched.
frontend: 429 passed, 97.10% statements, 97.07% line, 95.80% functions,
          90.95% branch — unchanged, no frontend source outside e2e/ touched.
e2e:      57 (was 52). New: e2e/17-security-regressions.spec.ts (2: cookie
          flags, hostile-markdown round trip). +1 each in
          01-opportunity-lifecycle.spec.ts (ordering — an existing test
          extended, not a new one), 02-sharing-permissions.spec.ts (unrelated
          user sees no trace), 04-mentions.spec.ts (notification history +
          mark-all-read), 11-undo.spec.ts (note/comment audit trail).
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

No coverage floor moved: this milestone adds E2E tests only, which
`vitest.config.ts`'s thresholds and pytest's `--cov-fail-under` do not
measure. All 57 E2E tests were run against the real application (Playwright,
Chromium) before commit, not just typechecked — two of the new assertions
were confirmed to fail first against a wrong assumption (PROGRESS.md's 2.12
entry has both: the timeline-ordering test against entries left at their
default "now" timestamp, and the notification test against a hardcoded
row count of 2), which is what caught a real timing subtlety in the first
case and a wrong assumption about notification fan-out in the second, before
either became a flaky or over-specific regression guard.

## Phase 2 — gate (end of phase, all milestones 2.1–2.13 done, incl. 2.9a)

No application code changed in this session — it re-ran the full sandbox
half of the split gate (brief §3.4) at the commit milestone 2.12 left, to
confirm the phase is ready for `AWAITING_REVIEW`. Figures are unchanged from
the 2.12 gate above, run fresh rather than copied forward:

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          338 passed, 97.27% combined line+branch coverage
          (--cov-fail-under=90 enforced); the six ≥95%-branch modules
          (permissions.py, audit_utils.py, auth.py, soft_delete.py,
          routes_ai.py, versioning.py) all at 100%
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (2 pre-existing warnings, 0 errors — see phase-2-summary.md)
          429 passed, 97.10% statements / 90.95% branch / 95.80% functions /
          97.07% line (thresholds 96/96/95/90 all met)
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
e2e:      57 passed (17 specs), axe clean on every screen in both light and
          dark; the deferred color-contrast ratchet is now empty
docker:   deferred to the host half — scripts/autopilot-gate.sh 2
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend ≥ 90% line / ≥ 80% branch
(97.27% combined); frontend ≥ 80% line (97.07%, well above floor — the
project's own thresholds are 96/96/95/90); the ≥95%-branch modules all at
100%.

Authorization-matrix endpoints: 47 (Phase 1 gate) → 52 (saved views, the
four restore routes, the bulk-action endpoint, three edit-history reads).

Full detail and the try-it steps: `docs/autopilot/reviews/phase-2-summary.md`.

## Phase 3 — milestone 3.0 (one activity log per opportunity)

One new backend module (`app/activity.py`, 100% line and branch), one new
frontend module (`lib/activity.ts`) and one new component
(`app/ActivityDialog.tsx`). No migration and no new table — the milestone is a
read over rows that already existed, which is also why the coverage picture
barely moves: the new code is small and entirely exercised.

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          355 passed (338 at the Phase 2 gate; +16 in the new
          tests/test_activity.py, +1 authorization-matrix endpoint)
          97.36% combined line+branch (--cov-fail-under=90 enforced)
          app/activity.py                    100% line, 100% branch
          the six ≥95%-branch modules (permissions, audit_utils, auth,
          soft_delete, routes_ai, versioning) all still at 100%
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (the same 2 pre-existing warnings, 0 errors)
          442 passed (429 at the Phase 2 gate; +10 lib/activity.test.ts,
          +3 app/Activity.test.tsx)
          97.12% statements / 91.27% branch / 95.75% functions / 97.09% line
          (thresholds 96/96/95/90 all met)
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
e2e:      58 passed (17 specs; +1 journey in 03-note-history.spec.ts),
          axe clean, the deferred-rule ratchet still empty
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend ≥ 90% line / ≥ 80% branch
(97.36% combined); frontend ≥ 80% line (97.09%); the ≥95%-branch modules at
100%.

Authorization-matrix endpoints: 52 (Phase 2 gate) → 53
(`GET /api/v2/opportunities/{id}/activity`, the one route this milestone adds).
It is the first read in the matrix whose expectation is 200 for every role and
whose *rows* differ by role instead — `tests/test_activity.py` is where that
distinction is held, since the matrix asserts status codes.

## Phase 3 — milestone 3.0a (the three bulk actions D-070 deferred)

One new backend module (`app/share_utils.py`, four statements, 100%), two new
routes (`GET /api/v2/opportunities/export/{csv,json}`) and two new actions on
the endpoint that already existed. No migration: the ownership transfer moves a
column that was always there, and "add to view" writes into the saved view's
existing opaque `filters` JSON (D-106).

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          385 passed (355 at milestone 3.0; +25 across
          tests/test_bulk_actions.py and tests/test_export.py, +1 each in
          test_activity.py and test_sharing.py, +2 matrix endpoints)
          97% combined line+branch (--cov-fail-under=90 enforced)
          app/share_utils.py                 100% line, 100% branch
          app/routes_saved_views.py          100% line, 100% branch
          app/routes_export.py               98% line (one partial branch)
          app/routes_opportunities.py        96% line (both gaps pre-date
          this milestone: the no-op PATCH branch and the never-empty
          stalled lookup)
          the six >=95%-branch modules (permissions, audit_utils, auth,
          soft_delete, routes_ai, versioning) all still at 100%
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (the same 2 pre-existing warnings, 0 errors)
          448 passed (442 at milestone 3.0; +4 DashboardPage.test.tsx,
          +1 lib/domain.test.ts, +1 lib/notifications.test.ts)
          97.13% statements / 91.28% branch / 95.73% functions / 97.10% line
          (thresholds 96/96/95/90 all met)
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
e2e:      59 passed (17 specs; +1 journey in 12-bulk-actions.spec.ts),
          axe clean, the deferred-rule ratchet still empty
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend >= 90% line / >= 80% branch (97%
combined); frontend >= 80% line (97.10%); the >=95%-branch modules at 100%.

Authorization-matrix endpoints: 53 (milestone 3.0) → 55, both of them the
selection export. Like `GET /api/v2/search`, they answer 200 for anyone signed
in and carry the permission filter inside the query — `tests/test_export.py`
holds the leakage case, since the matrix asserts status codes. The two new
bulk actions needed no new row: `POST /api/v2/opportunities/bulk` was already
registered, which is also why `tests/test_bulk_actions.py` carries their
per-actor cases itself.

## Phase 3 — milestone 3.0b (follow-up dates on the calendar, D-088)

One new route (`GET /api/v2/timeline/follow-ups`), one new schema
(`FollowUpPublic`), no migration — the read is a column that already existed
on `timeline_entries`, unreachable across opportunities until this endpoint.
The backend, schema, frontend wiring and seed data were already written,
uncommitted, at the start of this session; what was missing and added here:
two `lib/domain.test.ts` cases for the two functions the uncommitted work had
imported but never called, a new E2E journey, and a `test_seed.py` assertion
for the seed tour's new paragraph.

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          392 passed (385 at milestone 3.0a; +6 tests/test_follow_ups.py,
          +1 authorization-matrix row; test_seed.py's addition is assertions
          inside an existing test, not a new one)
          97.49% combined line+branch (--cov-fail-under=90 enforced)
          app/routes_timeline.py             94% line (pre-existing gaps —
          see milestone 3.0a's note; none of the new follow-ups code is among
          the missed lines)
          the six >=95%-branch modules (permissions, audit_utils, auth,
          soft_delete, routes_ai, versioning) all still at 100%
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (the same 2 pre-existing warnings, 0 errors — this session's fix
          removed three warnings the uncommitted work had introduced:
          calendarRange, followUpsOn and aFollowUp all unused before the two
          new test cases were added)
          450 passed (448 at milestone 3.0a; +2 lib/domain.test.ts)
          97.02% statements / 91.30% branch / 95.51% functions / 96.98% line
          (thresholds 96/96/95/90 all met)
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
e2e:      60 passed (17 specs; +1 journey in 15-table-calendar.spec.ts),
          axe clean, the deferred-rule ratchet still empty
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend >= 90% line / >= 80% branch
(97.49% combined); frontend >= 80% line (96.98%); the >=95%-branch modules at
100%.

Authorization-matrix endpoints: 55 (milestone 3.0a) → 56
(`GET /api/v2/timeline/follow-ups`), cross-opportunity like search and the
export routes — 200 for anyone signed in, permission filter inside the query.
`tests/test_follow_ups.py::test_scoped_to_what_the_caller_can_read` holds the
leakage case, since the matrix asserts status codes only.

## Phase 3 — milestone 3.1 (TipTap serializing to Markdown)

No migration, no route, no schema: the backend figures are unchanged because
this milestone is entirely frontend — note, comment and entry bodies were
already Markdown text, which is what `docs/FEATURES.md` §4 meant by "the payoff
for storing Markdown from day one". The one backend file that changed is
`tools/seed.py`, which now writes one Markdown note for the demo tour, with the
assertion holding it true added inside `test_seed.py`'s existing test.

Four dependencies added, all `@tiptap/*` at 3.31.3 (`react`, `starter-kit`,
`extension-list`, `markdown`) plus `@tiptap/extensions` for `Placeholder`;
53 packages in total, `npm audit` clean.

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          392 passed (unchanged from milestone 3.0b — the seed's new note is
          asserted inside an existing test)
          97% combined line+branch (--cov-fail-under=90 enforced)
          the six >=95%-branch modules (permissions, audit_utils, auth,
          soft_delete, routes_ai, versioning) all still at 100%
          pip-audit                                          no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (the same 2 pre-existing warnings, 0 errors)
          487 passed (450 at milestone 3.0b; +13 lib/markdown.test.ts,
          +20 app/RichTextEditor.test.tsx, +2 app/OpportunityPanel.test.tsx,
          +1 app/MarkdownText.test.tsx, +1 lib/keyboard.test.ts)
          97.17% statements / 91.55% branch / 95.65% functions / 97.14% line
          (thresholds 96/96/95/90 all met; branches up from 91.30, functions
          fractionally down from 95.51 — both measured, both above the floor.
          `app/test-editor.ts` joins the other two test-infrastructure files in
          the coverage exclusions)
          app/RichTextEditor.tsx            new, 100% statements
          lib/markdown.ts                   new, 100% statements
          npm audit                                           0 vulnerabilities
contract: scripts/generate-api-client.sh --check               up to date
          (no API change to regenerate against)
e2e:      61 passed (18 specs; +1 journey in the new 18-rich-text.spec.ts),
          axe clean, the deferred-rule ratchet still empty
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend >= 90% line / >= 80% branch (97%
combined); frontend >= 80% line (97.15%); the >=95%-branch modules at 100%.

Authorization-matrix endpoints: 56, unchanged — this milestone adds no route.

Two failures worth recording, because both were real rather than test churn:

- **The typing guard.** `app/Keyboard.test.tsx`'s `does not treat what the
  reader types as commands` failed the moment the note composer became a
  contenteditable `div`: `isTypingTarget` asked only for `isContentEditable`,
  which jsdom leaves `undefined`, so every letter of the note was a command
  again. Fixed in `lib/keyboard.ts` (**D-112**) and confirmed to fail with the
  fix reverted, per brief §6.5.
- **An unnamed form control.** `e2e/07-accessibility.spec.ts` failed with 11
  `label` violations (impact: critical) once the seeded demo note contained a
  checklist: `remark-gfm` renders `- [x]` as a bare `<input type="checkbox">`
  with no accessible name. `app/MarkdownText.tsx` names it from its state, and
  `MarkdownText.test.tsx` asserts the two names. This was latent before the
  milestone — any note could already contain a task list — and the seed data is
  what surfaced it.

One further E2E change worth naming, because it is a behaviour change rather
than a selector change: `e2e/17-security-regressions.spec.ts`'s hostile-note
journey used to assert that a typed `javascript:` link reached the renderer and
came back as an `<a>` with its `href` stripped. The composer now refuses to
make that link at all, so the text stays text and there is no anchor. The
journey asserts both halves: the composer's refusal, **and** the same payload
posted straight to the API — which the composer never sees, and where the
sanitizer is the only thing between it and the reader. That second half is the
property the test was always about, and it is the one Phase 5's email ingestion
will depend on.

## Phase 3 — milestone 3.1a (four corrections from the editor checkpoint, D-115)

Entirely frontend, no migration, no route, no schema — the backend figures are
unchanged from milestone 3.1. Four fixes: the timeline's default reading order
flipped to newest-first (`lib/domain.ts`'s `emptyTimelineFilters`), the three
always-visible per-opportunity export links collapsed into one format-choice
control, the opportunity header and sharing panel moved into the sidebar
column beneath the AI panel so the timeline is the first thing on the page,
and a one-row version history now says "recorded when this was created"
instead of a bare "Version 1".

```
backend:  ruff check, ruff format --check, mypy app tools    all clean
          392 passed (unchanged — no backend file touched)
          97.49% combined line+branch (--cov-fail-under=90 enforced)
          pip-audit                                          not re-run this
          session (unchanged dependencies; last run clean at milestone 3.1)
frontend: tsc --noEmit, eslint, prettier --check              all clean
          (the same pre-existing warnings, 0 errors)
          487 passed (unchanged count — two existing assertions rewritten,
          not added: lib/domain.test.ts's saved-view-matching case, which
          coincided with the new default and had to pick a value that still
          disagrees with it; no new test file)
          97.12% statements / 91.57% branch / 95.53% functions / 97.08% line
          (thresholds met; fractionally down from milestone 3.1's 97.17/91.55/
          95.65/97.14 — noise from moved lines, not a coverage regression)
contract: scripts/generate-api-client.sh --check               up to date
          (no API change to regenerate against)
e2e:      not executed this session — no cached Playwright browser and no
          milestone-commit requirement to run it (brief §3.4: check-fast is
          the milestone gate, full check with e2e is the phase-end gate).
          Three specs edited to match the new UI
          (01-opportunity-lifecycle.spec.ts's reading-order assertion,
          05-export.spec.ts and 06-ai-agent.spec.ts's export-control
          locators) and confirmed type-correct and lint-clean by check-fast's
          tsc/eslint pass, which covers `frontend/e2e/**/*.ts`. Full E2E
          execution is deferred to the Phase 3 gate.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Coverage floors (brief §6.2) all met: backend >= 90% line / >= 80% branch
(97.49% combined); frontend >= 80% line (97.08%).

Authorization-matrix endpoints: 56, unchanged — this milestone adds no route.

One test coincided with the changed default and needed rewriting rather than
just re-running: `lib/domain.test.ts`'s "recognises the view the filters on
screen amount to" used a saved view pinned to `order: "desc"` and asserted
that the bare `emptyTimelineFilters` state did *not* match it — true when the
default was `"asc"`, false now that the default is itself `"desc"`. Rewritten
against `order: "asc"` (the value opposite the new default) so the assertion
still tests what it was written to test: that being at the defaults, with no
view applied, does not read as a view being applied.

## Phase 3 — milestone 3.1b (rework: 3.1a's unexecuted gate, D-118)

Three E2E assertions, no application code. Unlike 3.1a's session, this one's
sandbox had a populated `frontend/node_modules` (D-118 named that volume as
the likely reason the suite could not run before) and the cached Chromium
1194 build — so the full 61-spec suite executed here, in the sandbox, rather
than deferring to the host. That contradicts the standing assumption in this
phase's earlier entries that E2E is host-only; it is not structurally
host-only, only occasionally blocked by the sandbox's node_modules mount
being empty at session start. Worth re-checking at the next gate rather than
assumed either way.

```
backend:  unchanged — no backend file touched. 392 passed, 97.49% coverage
          (re-run as part of this session's check-fast).
frontend: unchanged test count and coverage — 487 passed, 97.12% statements /
          91.57% branch / 95.53% functions / 97.08% line. Only e2e/*.spec.ts
          files changed; vitest does not run against frontend/e2e.
contract: scripts/generate-api-client.sh --check               up to date
e2e:      61 passed (up from 58 passed / 3 failed at D-118's diagnosis), axe
          clean. Same count as milestone 3.1's 61 — no journey added or
          removed, three specs corrected in place.
audits:   pip-audit clean, npm audit 0 vulnerabilities.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Both real regressions D-118 found trace to the same root cause (the
newest-first default from 3.1a) but needed different fixes:

- `09-saved-views.spec.ts:115` — the assertion's before/after swapped: the
  default is now newest-first, so the oldest entry starts at the *bottom*
  with no control touched; selecting "Oldest first" is what now needs to
  move it to the top. Straightforward once the ordering itself was accounted
  for.
- `16-edit-in-place.spec.ts:22` — not a simple default swap. Retargeting the
  test at the literal last entry in the new order ("Call 1") reproduced the
  suite's own assertion under a *different* real cause: with nothing left
  below the very last entry to absorb its editor's growth, opening it grows
  the document past the viewport and the browser follows the newly-focused
  `Title` input with a scroll of its own (measured: 391px, against the
  test's 40px budget). That is a genuine browser behaviour, not the bug this
  test exists to catch (D-051 — the reader jumping to an unrelated composer
  at the top of the page), and it would have fired for *any* entry sitting
  flush against the viewport's bottom edge, in either reading order — it
  surfaced now only because 3.1a's default flip changed which entry that is.
  Confirmed empirically (a throwaway debug spec instrumenting `scrollY`
  before/after, deleted after use) that targeting the second-from-last entry
  instead — one entry of headroom below it — reproduces zero scroll
  regardless of order. Retargeted to that entry (now "Call 2", context
  entry "Call 3") rather than loosening the 40px budget, which would have
  papered over a real, if separate, effect.

The third failure, `05-export.spec.ts:43`, confirmed not a defect: it is the
WeasyPrint-native-library gap `CLAUDE.md` documents, present on a bare host
and absent here (this sandbox has the libraries — the probe returned 200 and
the PDF assertions ran for real rather than skipping). Added the guard D-118
asked for: a one-time probe as the owner before the permission loop, `test.skip`
on a `500` from that probe with a message naming the cause, matching
`tests/test_export.py:224-228`'s `pytest.skip` on the same condition. The
probe is scoped to the owner specifically so a `500` can only mean the
libraries are missing, not a permission bug masquerading as one.

Coverage floors (brief §6.2) all met, unchanged from 3.1a. Authorization-
matrix endpoints: 56, unchanged. No new decisions beyond this entry's note on
the node_modules assumption, recorded in DECISIONS.md as D-119.

---

## Phase 3 — milestone 3.1c (restore a previous version, one place to read history, D-116)

Three new routes and a consolidation on the screen that reads them. The
frontend test count *fell* by two (487 → 485) while coverage rose, which is
the shape of this milestone: `app/History.test.tsx` and `app/HistoryDialog.tsx`
were deleted with the destination they tested, and the assertions worth
keeping moved into `app/Activity.test.tsx` (3 cases → 7) beside a new
`app/VersionChanges.test.tsx` (5 cases).

```
backend:  403 passed (up from 392), 97.49% line / 90.61% branch — the line
          figure is unchanged to two decimals because the new code is small
          and fully covered: app/versioning.py 100.00%, and the three restore
          routes are exercised by nine cases in tests/test_versions.py plus
          three authorization-matrix entries.
frontend: 485 passed (from 487), 97.20% statements / 91.61% branch / 95.69%
          functions / 97.17% line — every figure above the 3.1b baseline
          (97.12 / 91.57 / 95.53 / 97.08) and above vitest.config.ts's
          thresholds (96 / 90 / 95 / 96), which were not touched.
contract: scripts/generate-api-client.sh --check               up to date
          (regenerated: the three restore routes are the only additions)
e2e:      61 passed, axe clean. Same count — 03-note-history.spec.ts's three
          journeys were rewritten against the single destination rather than
          added to, and 11-undo.spec.ts's two audit-trail reads moved from
          the sharing panel's disclosure to the same dialog.
audits:   pip-audit clean, npm audit 0 vulnerabilities.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization-matrix endpoints: 59, up from 56 — one per restore route. Each
is `scoped(viewer=403, editor=403, owner=200)`, the rule the history read it
restores from already had (D-096). The matrix test failed as intended before
the entries were added, naming all three paths.

Two coverage notes worth keeping, since both are about what was *removed*
rather than added:

- `lib/domain.ts`'s `versionChanges` lost its `previous === undefined`
  branch. It rendered version 1 as a whole state, which only the deleted
  per-item dialog ever asked for; the activity log always compares a version
  against the one before it. Making the parameter required deleted dead code
  rather than leaving an untested branch behind — the file is now 100%
  statements.
- `app/VersionChanges.tsx`'s remaining low-traffic branches (the history
  failing to load, an edit whose fields all render the same, a version the
  feed named but the history does not hold) are covered by
  `app/VersionChanges.test.tsx` driving the component directly. They are
  unreachable through the feed by construction, which is exactly why they
  needed a test that does not go through it.

Coverage floors (brief §6.2) all met. New decisions: D-120 (what a restore
writes) and D-121 (one destination, `needs human review: Y`).

---

## Phase 3 — milestone 3.2 (the composer's three typed triggers, D-111)

One new backend read and a frontend feature that is mostly declaration: what
`@`, `/` and `#` offer is data in `lib/suggestions.ts`, which is why the
largest test file added takes no DOM at all.

```
backend:  406 passed (up from 403), 97.51% total / 90.61% branch — the new
          route is exercised by two cases in tests/test_sharing.py, one
          matrix entry and one tour assertion in test_seed.py.
frontend: 510 passed (from 485), 97.31% statements / 91.86% branch / 95.94%
          functions / 97.28% line — every figure above the 3.1c baseline
          (97.20 / 91.61 / 95.69 / 97.17) and above vitest.config.ts's
          thresholds (96 / 90 / 95 / 96), which were not touched: the gain is
          a few tenths, which is churn rather than a ratchet worth keeping.
contract: scripts/generate-api-client.sh --check               up to date
          (regenerated: GET /api/v2/opportunities/{id}/members and
          OpportunityMemberPublic are the only additions)
e2e:      64 passed (from 61), axe clean — including an audit taken with a
          suggestion menu open, which is the state the aria-activedescendant
          wiring had to survive.
audits:   pip-audit clean, npm audit 0 vulnerabilities across the one added
          package (@tiptap/suggestion 3.31.3, pinned exact like its four
          siblings, no dependencies of its own).
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization-matrix endpoints: 60, up from 59 — `GET
/api/v2/opportunities/{id}/members`, `scoped(viewer=200, editor=200,
owner=200)`, which is the widening D-123 records. The matrix test failed as
intended before the entry was added, naming the path.

Three notes on what the numbers do and do not show:

- **The new modules are covered by tests that do not need a browser.**
  `lib/suggestions.ts` is 100%: the matching, the three insert shapes and the
  slash commands are all pure, and the commands are run against a recording
  chain rather than an editor. `app/Suggestions.tsx` is 98.21% line — the one
  uncovered line is the `!menu` guard in the key handler, which the plugin
  cannot reach (it only calls `onKeyDown` while its state is active).
- **The gap those numbers leave is typing**, and it is the same gap D-113
  named for 3.1: a paste opens the menu under jsdom, but the Markdown input
  rules and the caret are a browser's. `e2e/19-suggestions.spec.ts` types all
  three triggers in Chromium, which is why the E2E count moved by three rather
  than one.
- **One pre-existing figure improved for a reason worth noting**:
  `app/MarkdownText.tsx` gained a branch (a relative href renders as a router
  `Link`) and stayed at 100% line, because both sides of it are asserted —
  the in-app link in `app/OpportunityPanel.test.tsx`'s journey and the
  external one in the existing protocol-allowlist tests.

Coverage floors (brief §6.2) all met. New decisions: D-122 (mentions stay
plain `@address` text), D-123 (the member list and who may read it, `needs
human review: Y`), D-124 (the entry link, its target and what happens on
arrival), D-125 (how the popup is positioned and kept current).

---

## Phase 3 — milestone 3.3 (threaded comments and resolve/unresolve, D-126)

Three columns on one table, two routes, one new component. The read shape
changed for every caller of a note's comments, which is why the backend count
moves further than the two routes alone would explain — the assembly, the
delete cascade and the reply's notification are each their own case.

```
backend:  423 passed (up from 406), 97.64% total / 91.36% branch — from
          tests/test_comment_threads.py (14), one new invariant test
          (resolving writes no body), two authorization-matrix entries and
          three seed assertions. The modules this milestone
          touched: soft_delete.py 100%, permissions.py 100% (unchanged, no
          new rule), notification_service.py 97%, routes_timeline.py 95%.
frontend: 519 passed (from 510), 97.34% statements / 91.72% branch / 96.00%
          functions / 97.31% line — statements, functions and lines above
          3.2's (97.31 / 95.94 / 97.28), branches a shade under it (91.86),
          and all four well above vitest.config.ts's thresholds
          (96 / 90 / 95 / 96), which were not touched.
          `app/CommentThread.tsx` is 100% line and 86.2% branch: what is
          uncovered there is the `?? "a colleague"` fallback for a resolver
          whose name is missing (the API always sends it) and the two error
          paragraphs, which need a failing mutation to render.
contract: scripts/generate-api-client.sh --check               up to date
          (regenerated: CommentThread is new, CommentPublic gains parent_id,
          CommentCreate gains parent_id, NotePublic.comments is now a list of
          threads)
e2e:      66 passed (from 64), axe clean — including an audit of a resolved
          thread expanded again, which is the one state with a disclosure
          control in it.
audits:   pip-audit clean, npm audit 0 vulnerabilities. No dependency was
          added: threading is a schema change and a component.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization-matrix endpoints: 62, up from 60 — `POST
/api/v2/comments/{id}/resolve` and `.../unresolve`, both
`scoped(viewer=403, editor=403, owner=200)`, which is the author-or-owner
rule (D-128) read through the matrix's fixture, where the comment belongs to
the owner. The matrix test failed as intended before the entries were added,
naming both paths.

Two notes on what the numbers do and do not show:

- **The cascade guards were confirmed red first** (brief §6.5). With the
  reply cascade removed from `soft_delete_comment`, exactly two of the new
  tests fail — the thread-delete round trip and the one that proves a reply
  leaves the FTS5 index with its thread — and they fail for the right
  reason, on the reply that stayed behind.
- **`routes_timeline.py` at 95%** is unchanged in kind from before this
  milestone: the misses are `HTTPException` raises on rows that other tests
  cover through a different route, not the new code. Every branch of
  `create_comment`'s parent validation and of `set_thread_resolved` is
  asserted, including both idempotent paths.

Coverage floors (brief §6.2) all met. New decisions: D-126 (splitting the
roadmap's 3.3, with reactions and watchers left as 3.3a inside this phase),
D-127 (one level of threading, enforced in the route), D-128 (who may
resolve, and that it is recorded on the thread rather than in the audit log).

## Phase 3 — milestone 3.3a (reactions and watchers, D-126)

The other half of 3.3's split. Two new tables, six new routes across two
routers, one new permission function that is a deliberate exception to every
other one in the module.

```
backend:  443 passed (up from 423), 97.73% (pytest-cov's `--cov-branch`
          combined statement+branch figure) — cov-fail-under=90 comfortably
          cleared. New tests: tests/test_reactions.py (7),
          tests/test_watchers.py (7).
          Modules this milestone touched: permissions.py 100% branch
          (require_opportunity_exists's only branch, the 404, is exercised by
          test_watch_routes_404_a_deleted_or_unknown_opportunity),
          soft_delete.py 100% (unchanged — reactions/watchers are
          deliberately absent from USER_DATA_TABLES, so there is no new
          branch to cover, only the absence to assert, which
          test_soft_delete.py's table-list scan already does), routes_sharing.py
          95%, routes_timeline.py 96%, notification_service.py 97%,
          schemas.py 99%.
frontend: 522 passed (up from 519), 97.06% statements / 91.38% branch /
          95.64% functions / 97.02% lines — all four above
          vitest.config.ts's thresholds (96 / 90 / 95 / 96), which were not
          touched. `app/CommentThread.tsx` (ReactionBar folded in) is 100%
          line / 90.69% branch.
contract: scripts/generate-api-client.sh --check               up to date
          (regenerated: ReactionPublic, ReactionCreate, ReactionEmoji,
          CommentPublic.reactions, WatcherPublic, WatchStatus)
e2e:      67 passed (from 66), axe clean — e2e/21-reactions-watchers.spec.ts
          is new: reacting and withdrawing a reaction on a real comment
          (audited), and a second user with no share following the
          opportunity from its own "not available" screen, still unable to
          read it, then showing up on the owner's watchers list (audited
          again on the not-available screen with the watch toggle live on
          it).
audits:   not re-run this milestone (no dependency was added — two tables and
          six routes over the existing stack); still clean as of 3.3.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization-matrix endpoints: 68, up from 62 — the three `.../watch`
routes (`authenticated_only(200)`, per D-129: any signed-in caller, not a
scoped role), `GET .../watchers` (`scoped(viewer=403, editor=403,
owner=200)`, owner-only like the share list), and the two reaction routes
(`scoped(viewer=403, editor=200, owner=200)`, any role that may write the
timeline).

One note on what the backend implementation and its tests were doing before
this session touched them: the routes, schema, migration, and both new test
files existed uncommitted in the working tree already, apparently written in
full but never run through the gate or logged in the state files. This
session verified them against the running app rather than assuming they
were correct — full backend suite, `make check-fast`, and the full Playwright
suite were all run fresh — and found one real defect, in a test fixture
rather than in application code:

- **`app/CommentThread.test.tsx`'s `threadedTimeline()` helper shared a
  mutable array across tests.** It shallow-spread the file's module-level
  `question` object, so any call that did not override `replies` pointed at
  the exact same array as `question.replies`. `test-api.ts`'s fake reply-post
  handler mutates a thread's `replies` in place (`parent.replies.push`),
  which silently leaked a reply from one test into every later test in the
  file that opened a thread without its own `replies` override. It was inert
  until a test's assertion happened to be sensitive to the exact element
  count the leaked reply also affected — this milestone's `getByRole("button",
  { name: "React" })` (ambiguous with two threads, one real and one leaked)
  was the first. Confirmed by running the failing test alone (passes) against
  the whole file (fails identically every time) and by dumping the rendered
  DOM. Fixed at the source — `threadedTimeline` now seeds fresh
  `replies`/`reactions` arrays unless an override supplies its own — rather
  than adjusting the new test's selector, per brief §6.5's root-cause rule.

Coverage floors (brief §6.2) all met. New decisions: D-129 (the one
existence-only exception to the access gate, scoped to watching and nothing
else), D-130 (reactions and watchers are hard-deleted like `sessions`, not
soft-deleted, and both toggle routes return the resulting state rather than
204).

## Phase 3 — milestone 3.4 (SSE live updates and the 409 note edit guard, ADR 0003)

Both halves of ADR 0003 in one milestone: the stream that tells a second
reader something happened, and the guard that stops the second writer
overwriting the first. No migration — nothing here adds a table or a column.

```
backend:  456 passed (up from 443), 98% (pytest-cov's `--cov-branch`
          combined statement+branch figure) — cov-fail-under=90 comfortably
          cleared. New test file: tests/test_events.py (12 — nine for the
          stream, three for the guard).
          New modules: app/events.py 100% line / 100% branch (the
          `RuntimeError` arm is reached by
          test_publishing_to_a_stream_whose_loop_has_gone_is_not_an_error,
          which registers a subscriber on a loop it then closes),
          app/routes_events.py 100%.
          Modules this milestone touched: routes_timeline.py 96%,
          routes_opportunities.py 99%, routes_sharing.py 95%,
          schemas.py 99% — all unchanged from 3.3a, so the ~30 new publish
          calls and the guard arrived covered rather than diluting anything.
frontend: 530 passed (up from 522), 97.13% statements / 91.35% branch /
          95.71% functions / 97.09% lines — all four above
          vitest.config.ts's thresholds (96 / 90 / 95 / 96), which were not
          touched. New: lib/liveUpdates.ts 100% on all four,
          app/NoteBlock.tsx 100% on all four, lib/api.ts 100% line with the
          new ApiError.
contract: scripts/generate-api-client.sh --check               up to date
          (regenerated twice: once for the new `GET .../events` operation
          and `NoteUpdate.updated_at`, once more because a route docstring
          is the operation's OpenAPI description and editing it makes the
          generated client stale — worth remembering, it is not obvious)
e2e:      69 passed (from 67), axe clean — e2e/22-live-updates.spec.ts is
          new and is the only suite that needs two real browser contexts:
          Blair's entry appearing on Alex's untouched page, and Blair's save
          against a note Alex has just replaced being refused with the
          conflict message and the "Discard my edit" way out.
audits:   not re-run this milestone (no dependency was added — the stream is
          Starlette's own StreamingResponse and the client is the browser's
          EventSource); still clean as of 3.3.
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Authorization-matrix endpoints: 69, up from 68 — `GET
/api/v2/opportunities/{opportunity_id}/events`, `scoped(viewer=200,
editor=200, owner=200)`: the same gate as reading the timeline, because an
event says only "read it again". That row is only callable at all because the
stream closes itself (D-131) — `TestClient` buffers a response whole, so an
endless stream would hang the matrix rather than fail it, which is the worse
of the two failures.

Two things worth recording about how the suites had to change, neither a
weakened assertion:

- **The guard is a required field, so every existing note-edit caller
  changed.** `tools/seed.py` gained `edit_note` (and `add_note` now returns
  the created note, since an edit needs the value it was written against),
  and `tests/test_timeline.py` gained an `edit_note` helper that reads the
  current `updated_at` first — nine call sites across seven test files now go
  through it. The point is that those tests exercise the *edit*, not the
  guard: `tests/test_events.py` is the only place a stale value is sent, and
  it is sent on purpose.
- **The conflict test uses a stepped clock, not real time.** `utc_now()` has
  one-second resolution, so two edits inside one second share an `updated_at`
  and the guard has nothing to compare (D-132's documented blind spot). The
  end-to-end two-writer test patches `routes_timeline.utc_now` with a
  one-second-per-call generator rather than depending on how fast the machine
  runs (brief §6.5, deterministic time).

Coverage floors (brief §6.2) all met. New decisions: D-131 (a bounded stream
with `retry:` over an endless one), D-132 (a required `updated_at`, and
`updated_at` over a version number — the one needing human review, as this
milestone's single client-visible API break), D-133 (explicit publish after
commit, and a two-word event vocabulary), D-134 (the guard sends the value
the editor was opened with, not the one on screen at save time).

---

## Phase 3 — milestone 3.5 (PDF export renders Markdown)

Backend-only, no migration, no API/schema change: `export_service.py`'s three
call sites that used to `escape()` a body as plain text now render it through
`markdown-it-py` and sanitize the result through `app/sanitize.py`.

```
backend:  458 passed (was 456), 98.08% combined line+branch coverage
          (was 98%; --cov-fail-under=90 enforced)
          app/export_service.py  97% (2 uncovered branches, both pre-existing
                                 and unrelated to this milestone: an empty
                                 entry_ids list, an empty opportunity_ids list)
          app/sanitize.py        100% (unchanged; first caller from
                                 application code rather than only its own
                                 tests, per brief §4.5)
frontend: 530 passed, 97.13% statements / 91.35% branch / 95.71% functions /
          97.09% lines (unchanged — no frontend file touched)
e2e:      69 passed (unchanged — no new journey; docs/code_review.md
          finding 9's own recommended fix for this gap was a direct backend
          test on render_export_html, not a browser journey)
docker:   deferred to the host half — scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md)
```

Two new tests, both confirmed to fail against the pre-milestone code first
(brief §6.5): `test_pdf_html_renders_markdown_instead_of_escaping_it` (bold
and a list render as markup, not literal syntax; a `javascript:` link posted
straight to the API — bypassing the composer's own refusal — produces no
`href` carrying that scheme; a comment's Markdown renders too) and
`test_pdf_html_sanitizes_raw_html_even_if_the_markdown_parser_let_it_through`
(forces the parser's `html` option back to `True` — `commonmark`'s own
default, discovered while writing the first test — and proves the sanitizer
underneath still strips a raw `<script>` tag). The pre-existing
`test_pdf_html_renders_timeline_in_order_and_escapes_bodies` needed no
change: a literal `<script>` is now escaped by the parser rather than by
`html.escape`, the same visible result from a different mechanism.

New dependency: `markdown-it-py>=4.2.0`, made direct in `pyproject.toml`
(previously only a transitive dependency of `rich`, itself a `pip-audit`
dependency, which `uv sync --no-dev` would have dropped from the production
image). `pip-audit`: no known vulnerabilities.

Coverage floors (brief §6.2) all met, unchanged from the 3.4 gate on every
module other than `export_service.py`. New decision: **D-135** (`markdown-it-py`
over `python-markdown`, chosen for sharing a lineage with the editor's own
`@tiptap/markdown` parser family and for already being resolvable in the
sandbox; sanitizing the rendered HTML rather than trusting the parser alone,
and setting `html: False` explicitly rather than relying on `commonmark`'s
default).

## Phase 3 — gate (end of phase, every milestone 3.0–3.6 done)

One documentation fix this session — `backend/tools/seed.py`'s printed tour,
which still claimed the PDF export escaped Markdown after milestone 3.5 made
that false, and had no paragraph for 3.4 at all. No application code, no
schema, no route. The full sandbox half of the split gate (brief §3.4) was
run twice: once at milestone 3.6's commit `831a239` to establish the phase
was ready, and again after that fix, so the figures below belong to the
commit this entry is recorded on rather than being copied forward from 3.5's
gate. Both runs were identical.

```
backend:  ruff check (all passed), ruff format --check (88 files),
          mypy app tools (42 source files)              all clean
          458 passed, 98.08% combined line+branch coverage
          (--cov-fail-under=90 enforced); the ≥95%-branch modules
          (permissions.py, audit_utils.py, auth.py, soft_delete.py,
          routes_ai.py, versioning.py) all at 100%, and this phase's
          new modules too -- activity.py 100%, events.py 100%,
          routes_events.py 100%
          pip-audit                                     no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check         all clean
          (0 errors, 3 warnings -- the two carried from Phase 2 plus
          MarkdownText.tsx:71's unused `_node`, new in 3.1; all three
          named in phase-3-summary.md §4 rather than left to be found)
          530 passed (34 files), 97.13% statements / 91.35% branch /
          95.71% functions / 97.09% line (thresholds 96/96/95/90 all met)
          npm audit                                      0 vulnerabilities
contract: scripts/generate-api-client.sh --check          up to date
e2e:      69 passed (22 specs), axe clean on every screen in both light
          and dark; DEFERRED_AXE_RULES still empty
docker:   deferred to the host half -- scripts/autopilot-gate.sh 3
          (no Docker socket in this sandbox, per sandbox/README.md).
          Load-bearing this phase: 3.5 changed the PDF renderer and the
          one test that renders a real PDF is the one test that cannot
          run here.
```

Coverage floors (brief §6.2) all met with room: backend ≥ 90% line / ≥ 80%
branch (98.08% combined); frontend ≥ 80% line (97.09%, against the project's
own 96/96/95/90 thresholds); the auth, permissions, soft-delete, audit and
AI-agent modules ≥ 95% branch (all at 100%).

Authorization-matrix endpoints: 52 (Phase 2 gate) → 69 (the activity log, the
members read, the follow-ups read, the two multi-record export routes and the
bulk export action, three version-restore routes, resolve/unresolve,
reactions, the three watch routes, the watchers read, and the event stream).
One new invariant test: `test_invariant_resolving_a_thread_writes_no_body`.

Coverage across the phases so far:

| | Phase 1 gate | Phase 2 gate | Phase 3 gate |
|---|---|---|---|
| Backend tests | 258 | 338 | 458 |
| Backend coverage | 97.28% | 97.27% | 98.08% |
| Frontend tests | 102 | 429 | 530 |
| Frontend line coverage | 88.38% | 97.07% | 97.09% |
| E2E tests | 18 (7 specs) | 57 (17 specs) | 69 (22 specs) |
| Authorization-matrix endpoints | 47 | 52 | 69 |

Full detail and the try-it steps: `docs/autopilot/reviews/phase-3-summary.md`.

## Phase 4 — gate (end of phase, every milestone 4.1–4.8 done, plus 4.9)

Eleven milestones: 4.1 and 4.1b (the task model, its eight routes and its three
screens), 4.2 (the `follow_up_date` migration), 4.2a (the checkpoint rework —
`task_versions`, the task editor, the 401 that left the app looking signed in),
4.3 (attachments), 4.3a (attaching from the composer, from the gate review),
4.4 (the export manifest), and the human's "build both" ruling as 4.5 (a task's
discussion) and 4.6 (more than one person on a task) — then **4.7** (the AI context labels
what a person wrote) and **4.8** (a file is found by its name), which are the
human's two "now" rulings from the final round. Six schema revisions beyond
4.1's: `0011_task_description_and_versions`, `0012_attachments`,
`0013_task_comments`, `0014_task_assignees` and `0015_search_attachments` —
the last of which rebuilds the search index, because widening the rowid
encoding moves every row in it (**D-167**).

Then **4.9**, which is not a milestone the roadmap planned: the human reported
the AI as not working during this review and it was not working at all
(**D-168**). `openai_timeout_seconds` shipped at 20.0 against a reasoning
model whose floor latency is ~29s even spending zero reasoning tokens, so
every call failed three times and answered 502 after 61s — *no call could ever
have succeeded* on the configured `gpt-5-nano`. It is 90.0s now with one retry
rather than two, and `openai_reasoning_effort` defaults to `low`, which the
measurement says costs a few hundred reasoning tokens where the default costs
2176–4480 and answers at least as fully. **The nineteen existing AI tests all
passed throughout**, because every one of them stubs the SDK and the defect
lived in a default — so the four added here assert on the serialized request
body through an `httpx.MockTransport`, and one asserts a bound on the default
itself, which is the only shape of test that could have caught it. No schema
change.

**Re-measured on 2026-10-09** after 4.5 and 4.6; the figures below replace the
4.4 ones. Two numbers moved for reasons worth naming: the backend suite grew by
the task discussion and the assignee set, and the **frontend branch threshold
was briefly missed** (89.79% against 90%) because 4.6 added branches faster
than tests covered them. It was met by covering what the new code added —
every notification sentence, which had been at 66% branch since `task_assigned`
shipped — rather than by lowering the threshold, which `CLAUDE.md` forbids.

The figures below were taken after 4.4's last change, with the full sandbox
half of the split gate re-run from scratch — including a second Playwright run
after the dependency bump below, because a bundler patch changes the artifact
every end-to-end test loads.

```
backend:  ruff check (all passed), ruff format --check (96 files),
          mypy app tools (45 source files)                all clean
          583 passed, 1 skipped, 97.52% combined line+branch coverage
          (--cov-fail-under=90 enforced); the >=95%-branch modules
          (permissions.py, audit_utils.py, auth.py, soft_delete.py,
          routes_ai.py, versioning.py) all at 100%, and this phase's
          new modules too -- routes_tasks.py, routes_attachments.py,
          attachment_utils.py and uploads.py all 100%
          the one skip is the real-PDF render (WeasyPrint's native
          libraries are absent on macOS, CLAUDE.md's WeasyPrint note);
          4.4 added the attachment manifest to that renderer, so this
          skip is load bearing for this phase the way 3.5's was
          pip-audit                                      no known vulnerabilities
frontend: tsc --noEmit, eslint, prettier --check          all clean
          (0 errors, 3 warnings -- the same three named at the Phase 3
          gate, none of them new this phase)
          581 passed (36 files), 96.9% statements / 90.63% branch /
          95.6% functions / 96.9% line (thresholds 96/96/95/90 all met)
          npm audit            5 high, all one package, no upstream fix
                               (D-156 -- `braces` <=3.0.3 with 3.0.3 the
                               latest published release, reached through
                               micromatch -> fast-glob ->
                               @next/eslint-plugin-next -> eslint-config-next;
                               a development dependency, and the image copies
                               only `frontend/out` into the final stage, so
                               nothing of it ships). The critical one in the
                               same report -- Next.js `next/og` RCE -- was
                               fixed by bumping next and eslint-config-next
                               16.3.4 -> 16.3.8, and `npm audit fix` cleared
                               brace-expansion at the lockfile level.
contract: scripts/generate-api-client.sh --check           up to date
e2e:      78 passed, 1 skipped (25 specs), axe clean on every screen in
          both light and dark; DEFERRED_AXE_RULES still empty. The skip
          is the PDF export, for the same reason as the backend's.
docker:   deferred to the host half -- scripts/autopilot-gate.sh 4
          (no Docker socket in this sandbox, per sandbox/README.md).
          Load-bearing this phase for two reasons: the PDF renderer
          gained the manifest (4.4), and attachments write to the
          `/data` volume for the first time (4.3), so the image's
          non-root `app` user has to be able to create
          `/data/attachments`.
```

Coverage floors (brief §6.2) all met with room: backend >= 90% line / >= 80%
branch (97% combined); frontend >= 80% line (96.85%, against the project's own
96/96/95/90 thresholds); the auth, permissions, soft-delete, audit and
AI-agent modules >= 95% branch (all at 100%).

Authorization-matrix endpoints: 69 (Phase 3 gate) → 86 (eight task routes plus
the two 4.2a added, the four attachment routes, and the three a task's
discussion needs). `Case` gained a `files`
leg so the one multipart endpoint is exercised as a real multipart request
rather than a JSON stand-in.

New guard this phase, not a feature test: `lib/activity.ts`'s audit sentence
switch lost its `default` branch, so a new audit action is a build failure
rather than a wrong sentence — which is what it had been since 4.1 shipped
`task_deleted`.

Coverage across the phases so far:

| | Phase 1 gate | Phase 2 gate | Phase 3 gate | Phase 4 gate |
|---|---|---|---|---|
| Backend tests | 258 | 338 | 458 | 584 |
| Backend coverage | 97.28% | 97.27% | 98.08% | 97% |
| Frontend tests | 102 | 429 | 530 | 581 |
| Frontend line coverage | 88.38% | 97.07% | 97.09% | 96.87% |
| E2E tests | 18 (7 specs) | 57 (17 specs) | 69 (22 specs) | 79 (25 specs) |
| Authorization-matrix endpoints | 47 | 52 | 69 | 86 |

Full detail and the try-it steps: `docs/autopilot/reviews/phase-4-summary.md`.

---

## Milestone 6.0 — a search result lands on the match

The human's own report from the Phase 4 gate (**D-170**). Entirely frontend:
no route, schema or table changed, because `SearchResultPublic` already
carried the matched row's own id for every kind and `?entry=` already proved
the behaviour at one level.

```
frontend: typecheck, lint (3 pre-existing warnings, none new),
          prettier                                     all clean
          593 passed (36 files), 96.96% statements /
          90.74% branch / 96.9% lines -- branch up from
          90.63%, because the new logic is in pure
          functions that are cheap to cover exhaustively
backend:  583 passed, 1 skipped, 97.52% -- unchanged, and
          that is the point: nothing backend moved
e2e:      79 passed, 1 skipped (25 specs); the skip is the
          WeasyPrint PDF test, as on every Mac run
gate:     make check-fast -> MAKE_EXIT=0
```

New tests: five in `lib/domain.test.ts` over the pure parts (level
precedence, the four-kinds-to-three-levels mapping, and a stale parameter
reading as no target), six in `app/OpportunityPanel.test.tsx` over the marks
at each level, one in `app/SearchPage.test.tsx` over the hrefs, and one e2e
for the resolved-thread case.

Two things about how this was verified:

- **Five of the six component tests were confirmed failing** against the
  pre-6.0 parser before being trusted, by restricting
  `linkTargetFromParams` to `entry` and re-running.
- **The e2e test for the resolved thread started out skipping.** It was
  conditional on the seed happening to hold a comment matching the query, and
  it skipped — so it proved nothing about the one case this milestone was
  least likely to get right. It now signs up, writes a comment containing a
  nonsense word, resolves the thread, asserts the body really is off screen,
  and only then searches. The project's test rules already forbid depending
  on the wall clock; depending on the seed's wording is the same mistake with
  a different clock.

---

## Milestone 6.1 — custom fields

ADR 0006 and `docs/FEATURES.md` §3. One revision (`0016_custom_fields`), one
new table, one JSON column on each of two tables, five routes, and the three
screens §3 names.

```
backend:  ruff, ruff format, mypy (45 source files)     all clean
          602 passed, 1 skipped, 96.87% line+branch
          app/custom_fields.py and app/routes_custom_fields.py
          both at 100% branch
          authorization matrix: 91 cases, 95 endpoints
frontend: typecheck, lint (3 pre-existing warnings), prettier  clean
          624 passed (38 files), 96.87% statements /
          91.03% branch / 96.82% lines
e2e:      82 passed, 1 skipped (26 specs)
gate:     make check-fast -> MAKE_EXIT=0
```

New tests: 14 in `tests/test_custom_fields.py`, 5 matrix cases, 7 in
`lib/domain.test.ts`, 10 in `app/CustomFieldInputs.test.tsx`, 13 in
`app/CustomFields.test.tsx`, and 3 in `e2e/26-custom-fields.spec.ts` — the
last of which walks the roadmap's acceptance criterion verbatim ("a new select
field appears as a table column, a filter, and on the entry form") in a real
browser, because the three places are three screens reading one definition
list and no component test can watch them agree.

**Branch coverage went under the threshold before it went over it.** The first
green suite left the frontend at 89.19%, because `CustomFieldInputs` has a
branch per field type and only two were exercised. Fixed by adding
`app/CustomFieldInputs.test.tsx` — one test per type, asserting the *shape*
each control reports, since a checkbox that reported `"true"` or a number that
reported `"42"` would be a 422 the reader did not cause. The threshold was not
touched, which is the rule.

Four of the seven acceptance tests were confirmed failing against the unwired
components first (the column picker and the filter bar with their custom-field
branches removed).

---

## Milestone 6.2 — the six dashboard aggregations

`docs/FEATURES.md` §10. One module, one route, one revision, one screen.

```
backend:  ruff, ruff format, mypy (45 source files)     all clean
          613 passed, 1 skipped, 96.86% line+branch
          app/dashboard.py at 100% branch
          authorization matrix: 92 cases, 96 endpoints
frontend: typecheck, lint (3 pre-existing warnings), prettier  clean
          645 passed (39 files), 96.96% statements /
          91.15% branch / 96.91% lines
e2e:      85 passed, 1 skipped (27 specs)
gate:     make check-fast -> MAKE_EXIT=0
```

**The performance assertion is the unusual test here.**
`test_each_aggregate_answers_inside_the_budget` builds §10's own corpus — 400
opportunities and 800,000 activity rows spread across two years — and asserts
each of the six separately against the 300 ms budget. It costs about 25
seconds, which is the price of the one acceptance criterion in this project
that is a number rather than a behaviour, and it earned that cost immediately:
it is what found three aggregations over budget, including one 5x over
(**D-172**).

Two details about how it is written, both deliberate:

- **The corpus is spread over two years**, not stamped now. One of the six
  reads a *window* of history, so a fixture with every row inside that window
  measures something no deployment will ever ask.
- **The margin is reported, not asserted tightly.** It runs on a laptop and in
  a container, and a test that fails at 280 ms on a loaded machine teaches
  nobody anything. What it catches is an order-of-magnitude regression, which
  is exactly what it caught twice while this was being written — confirmed
  afterwards by removing the two planner directives and watching it fail.

---

## Milestone 6.3 — the constrained rule builder

`docs/FEATURES.md` §11. One module, one route module, one revision, one screen,
and the first feature in this project that writes without a person in the
request.

```
backend:  ruff, ruff format, mypy (51 source files)     all clean
          659 passed, 1 skipped, 95.39% line+branch
          app/automations.py 99% / routes_automations.py 100%
          authorization matrix: 98 cases, 102 endpoints
frontend: typecheck, lint (3 pre-existing warnings), prettier  clean
          685 passed (40 files), 96.97% statements /
          91.41% branch / 96.95% lines
e2e:      88 passed (28 specs)
gate:     make check-fast && make e2e -> exit 0
```

**The one-hop guard is a source scan, and that is the interesting choice.**
§11 says "no rule may trigger another rule — one hop only, which removes loop
detection from the design entirely". A behavioural test only covers the chains
somebody thought to write, so `test_invariant_a_rule_cannot_trigger_a_rule`
scans `app/automations.py` for a call to its own entry points — the shape
`test_soft_delete.py`'s hard-delete scanner already has, for the same reason:
this is a thing the code must not *contain*. Confirmed to fail against a
planted call before being trusted (brief §6.5). A behavioural test sits beside
it, over the pair that would chain if anything did.

**Two defensive paths were covered rather than left to a comment**, because
both are reachable states rather than impossible ones:

- a `value` column holding text, which the API cannot write (`OpportunityUpdate`
  parses a `Decimal`) and a hand-edited or imported database can — asserted by
  writing it with raw SQL, the shape `test_custom_fields.py` already uses;
- a rule failing mid-firing, asserted by monkeypatching `fire_event` to raise.
  The property is that **the human's write still succeeds**: somebody renamed a
  deal, and whether a colleague's automation managed to act on that is not
  their problem.

**The frontend's split is the usual one, with one addition.** What a rule *does*
is the backend suite; what the screen does with an answer is
`app/Automations.test.tsx`; and `app/test-api.ts` gained a deliberately
simplified evaluator — same condition comparison, a role check reduced to "does
this caller own the deal" — so a **skip with a reason** is reachable from a
component test. It is explicitly not a second implementation of the triggers.

**The e2e spec is where §11's traceability is read the way a person meets it**:
a rule written through the real form, run, and then the task *and* the entry
naming the rule read back off the deal's own screen by following the run log's
link. `e2e/23-responsive.spec.ts` also gained the two cross-deal screens
(`/automations` and `/reports`) — a screen absent from that list is a screen
where D-138's defect can come back unnoticed.

---

## Milestone 6.3a — the 6.3 review's finding, and its request

Three changes, each small and each for a different reason: a prohibition
removed, a 422's reasons finally reaching a form, and one exception to "a
system entry cannot be deleted".

```
backend:  ruff, ruff format, mypy        all clean
          app/automations.py 99% / routes_automations.py 100%
          authorization matrix: 98 cases, 102 endpoints
frontend: typecheck, lint, prettier      clean
          lib/api.ts 100% statements (3 new tests for `fields`)
e2e:      2 new journeys in 28-automations
```

**Two of the three were found by reproduction rather than by a test**, which
is worth recording because the reproduction is the whole content of the
finding. The human reported a message; replaying the form's exact payloads
showed that the rule they tried *was* permitted in two of its three trigger
combinations, which located the fault in a constraint this agent had invented
(D-179) rather than in the permission model they thought they were hitting.

**And the e2e test for the new capability took three attempts**, all for the
same class of reason — a test that depends on state it does not own:

- triggered by silence, it depended on the seeded deals still being quiet,
  which the test *above it* stops being true the moment it writes an entry on
  them;
- moved to a named stage, it depended on which stage the seed leaves Northwind
  in (Qualification — so "move to Qualification" wrote nothing at all);
- it now signs up its own account and creates its own deal, and asserts the
  badge by class rather than by text, because the entry body contains the word
  "Automation" too.

**One pre-existing defect surfaced on the way**: `e2e/23-responsive.spec.ts`
began failing on the calendar at 420px — a value chip, `white-space: nowrap`
with the flex default `min-width: auto`, refusing to shrink and pushing its
chip past the day cell. In six of seven columns that overlaps the next day and
is merely ugly; in the last one it widens the page. It had been true every day
and only reached the page edge when a seeded close date landed in the last
column, which is to say **the date change exposed it** — the same wall-clock
sensitivity `CLAUDE.md` warns about, here in a layout assertion rather than a
data one.

---

## Milestone 6.5 — the scheduler

ADR 0004, and the last milestone of Phase 6's build.

```
backend:  ruff, ruff format, mypy (53 source files)   all clean
          16 new tests in tests/test_scheduler.py
          app/jobs.py, app/scheduler.py
          authorization matrix: 99 cases, 103 endpoints
frontend: typecheck, lint, prettier      clean
          5 new tests in lib/jobs.test.ts, 2 in app/Automations.test.tsx
```

**Fourteen of the sixteen new tests never start a scheduler**, which is ADR
0004's instruction working as intended: `jobs.py` holds what runs and imports
nothing from APScheduler, so a tick is a function call. The two that do start
one assert the *wiring* and not the timing — an interval trigger's first
firing is one interval away, so a test that waited for a tick would wait
fifteen minutes.

**The test that mattered most is the one that failed first.** A suppression
written to stop a timer nudging the same quiet deal every fifteen minutes was
wrong, and the assertion that caught it expected a *skip* and found no run row
at all — because every action writes a system entry, that entry is activity on
the deal, and the deal had therefore stopped being a candidate. The mechanism
was already there; the code added on top of it would have made a no-activity
rule fire once and never again (**D-182**). A test that had asserted only "one
task, not ninety-six" would have passed over it.

**Two wall-clock dependencies were caught while writing these**, both in the
new tests and both before they could rot: a close date hardcoded as
`2026-10-15` (three days out when written, overdue a week later) is now
`closing_in(3)`. `CLAUDE.md`'s rule had been stated for timestamps; the
calendar defect above is the same rule applying to layout, and these two are
it applying to dates in the future rather than the past.

---

## Milestone 6.5a — the other path to a silent refusal

```
frontend: 5 new tests in lib/formErrors.test.ts
          2 new in app/Automations.test.tsx, 1 new e2e journey
```

**The whole milestone is one lesson about where a test should live.** The
defect was a browser cancelling a submit before any application code ran, and
the fix renders the browser's own `validationMessage`. So:

- **the mechanism** — field marked, reason drawn beside it, nothing sent — is
  asserted in the component test, where it is cheap;
- **the wording** is asserted only in the e2e suite, because **jsdom's
  validation messages are not Chrome's**. A component test asserting "Please
  enter a number." would have passed for the wrong reason on a platform that
  says something else, which is the same class of mistake as 6.2's time-in-
  stage e2e assertion passing because the seed happened to contain no sub-day
  span.

**And it was reproduced in a browser before anything was written**, which is
what located it: `page.evaluate` on the field reported
`{value: "", badInput: true, valid: false}` and the request log was empty.
Reading the component would not have shown that — `type="number"` and
`required` both look correct, and the silence is in what the platform does
with them.

---

## Milestone 6.4 — the AI expansion

`docs/FEATURES.md` §14's safe subset: streaming, date-scoped summaries, and
natural-language filter construction. The last milestone of Phase 6's build.

```
backend:  23 new tests in tests/test_ai_expansion.py
          app/ai_filters.py, the streaming call, the scoped context
          authorization matrix: 101 cases, 105 endpoints
frontend: 9 new tests in app/AiExpansion.test.tsx
          lib/aiStream.ts, app/AiFilterBuilder.tsx
e2e:      2 new journeys in 06-ai-agent.spec.ts
```

**Every test here stubs the SDK**, because `conftest.no_live_network` fails a
run that reaches a paid API — which is the point of it. D-168's lesson is
applied where a stub cannot see: the streaming test asserts `stream=True` on
the **captured call**, and the filter test asserts that no deal content
appears in the instructions or the input, which is a property of the bytes
rather than of the stub.

**The filter parser is where the tests earn their keep**, and they are mostly
about shapes a model actually produces rather than shapes it should: a fenced
answer, `50000` as a number and as a string, `"50k"` as neither, a stage that
does not exist, a key this board has never heard of. Each is a line in
`ai_filters.py` and each would otherwise be a filter that silently did
something else.

**Two defects were found by writing the tests rather than by running them:**

- `CsrfClient` overrode `request` but not `stream`, so the suite's first
  streamed POST met a 403 that had nothing to do with what it was testing.
  Until 6.4 every stream in this app was a GET.
- The fake API matched `segments[3] === "stream"` where the stream is
  `segments[4]` — so the component test read a JSON answer as SSE frames and
  sat at "Thinking..." forever. The symptom was indistinguishable from a
  broken reader, which is worth remembering: a stub with the wrong route
  fails like the code it stands in for.

**And one design error corrected mid-build**, recorded in D-186: the filter
vocabulary first contained `owner` and a close-date range, neither of which
the board can filter by. That is D-179's mistake inverted — inventing a
capability rather than a constraint — and it would have produced a proposal
that was inspectable and unapplicable, which is worse than no proposal. The
fix narrowed the prompt *and* added the value filter §14's own example needs.

## Milestone R.2 — the accessibility bar, and what it was actually asserting

Frontend: **770 unit tests** (46 files), statements 96.3%, branches 90.1%.
Backend untouched at **740** (1 skipped) — R.2 is a frontend and test-suite
milestone. End to end: **112 passed, 1 skipped**, the skip being the documented
WeasyPrint gap on a macOS host; `e2e/30-focus-and-keyboard.spec.ts` is new.

**The first finding was the test suite, not the app.** `auditPage` had asked
axe for `wcag2a, wcag2aa, wcag21a, wcag21aa` since Phase F while `AGENTS.md`
and D-002 say 2.2 AA, so six phases of "axe clean" meant 2.1 (**D-197**). With
the 2.2 tags in, `target-size` passed on the first run — R.1's single 34px
control height had already paid for 2.5.8 without anybody checking.

**Six states had no audit at all**: Tasks, Reports, Automations, the rule
form, the activity dialog, and the board's filter controls, which exist in the
DOM only while the disclosure is open. Three of those are screens R.1 put in
the rail two days earlier. All clean, both themes, first run.

**What the new suite found, which no stylesheet read could have.** 15 controls
on one deal page took keyboard focus while entirely hidden under the sticky
bands (2.4.11) — and the first fix, `scroll-margin-top` on the controls, was
confirmed useless by the same test before `scroll-padding-top` on the root
replaced it (**D-198**). The guard was checked against the unfixed stylesheet
first, as this project requires, and the backward walk is the half that
matters: `Shift+Tab` aligns a control to the top edge, where the chrome is,
and a forward-only walk passes against the broken build.

**Two things about measuring a live page.** An audit has to wait for
transitions to settle — the first 2.2 run reported 2.43:1 on the Ask button,
which was axe sampling a 120ms colour swap 60ms in — and it must wait for
*transitions only*, because two animations here run forever and `finished` on
an infinite animation never resolves.

**And one test was asserting a screen that no longer exists.**
`10-keyboard.spec.ts` pressed `/` on a deal and expected the board's keyword
box to take focus, which R.1 ended; it passed on the race between the
keystroke and React unmounting the board, and this milestone's extra
post-navigation effect was enough to lose that race. The lesson is narrower
than "tests rot": a chord pressed in the instant after a navigation is
genuinely dropped, because the new screen has not registered its listener yet.
A test can hit that window and a finger cannot, so the test now waits for the
screen that owns the chord.

## Milestone R.3 — what the app costs at the scale it was sized for

Backend: **750 tests** (1 skipped), two of them new suites —
`tests/test_performance.py`, which measures every read a person waits on, and
`tests/test_stalled.py`, which is what makes a stored derived answer
trustworthy. `tests/scale.py` is the corpus both share: 805,220 rows.

**The measurement, after R.3's one fix** (805,220 rows, on a laptop):

```
board first page                     2.5 ms      whole board (8 pages)   18.7 ms
timeline first page                  3.6 ms      activity log             2.9 ms
my tasks                             7.2 ms      inbox                    9.2 ms
members                              2.5 ms      health                   1.2 ms
export one deal (json)               5.1 ms      dashboard (six)         20.1 ms
search, as the owner               182.4 ms      search, shared reader   24.7 ms
```

Before it, the board's first page was **63 ms** and the whole board **448 ms**.
Search is the slowest read and the only one above 25 ms; the owner's is slower
than a shared reader's because the owner can read every deal, so more rows are
ranked and more snippets built. It is less than half its budget.

**The tests are where the method shows.** The first hypothesis about the
board's 63 ms was wrong and the test said so — one grouped pass measured 55 ms
against the per-row 56 ms — which is why the fix that landed is a maintained
column rather than a cleverer query (**D-200**, **D-201**). Profiling the
pieces was what found it: the page's own query is 0.3 ms.

**Six guards, each confirmed to fail with its own trigger disabled.** A
maintained column is a cache, and the half a careless denormalization gets
wrong is the answer *falling*: a soft delete, a restore, a deleted note, a
deleted comment, an entry backdated by an edit, and the board's badge agreeing
with the dashboard's list. Two of them only became real guards after being
strengthened — the note-and-comment case passed with its trigger disabled,
because the deal's own creation entry is stamped the same second as the note,
so the test now pushes the entries into the past to make the discussion the
unquestioned latest activity.

**And three test-suite defects the migration surfaced**, all of the same kind:
`test_api_v2.py` and `test_error_handling.py` proved the 500 envelope by
monkeypatching `is_opportunity_stalled`, the function the list route no longer
calls. A test that fakes a failure has to fake it in something the code under
test still reaches.
