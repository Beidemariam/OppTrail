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
