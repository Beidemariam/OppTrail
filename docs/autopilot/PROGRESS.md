STATUS: IN_PROGRESS phase=F

# Autopilot Progress

This file is the resumption point required by brief §3.2: it must be accurate
enough for a fresh session to continue using only the brief and the files in
`docs/autopilot/`. Update it every session per §3.3.

Base commit for `autopilot/phase-F`: `4c16a70` on `main` (clean checkout, no
tags exist yet — this is the project's first autopilot run).

---

## Phase F — Foundations

Branch: `autopilot/phase-F`. No new user-facing features in this phase (brief §4).

### F.1 — Reconnaissance (§4.1) — **DONE**

- [x] Inventory: directory map, data model, every API route with permission
      behavior, frontend routes, existing tests, environment variables →
      `docs/autopilot/INVENTORY.md`, all claims file-cited.
- [x] Ran the app's existing test suite and captured baseline coverage →
      `docs/autopilot/COVERAGE.md` (39 passed, 96% backend line coverage).
      No failing test was weakened or skipped.
- [x] Read `docs/ROADMAP.md` in full; converted Phases 1-6 into the milestone
      lists below, preserving roadmap wording and order.
- [x] Scope cross-check against brief §7 → `docs/autopilot/DECISIONS.md`
      ("Scope cross-check summary"). One proposal logged (D-003, dark theme
      acceptance criterion), not added to the plan per §4.1.4.
- [x] Gap analysis (security, correctness, missing tests, invariant checks) →
      folded into milestones F.2-F.8 below, each citing its source finding.
- [x] Fixed the stale `gpt-oss-20b`/OpenRouter reference in
      `docs/v2_review_brief.md:14` → `docs/autopilot/DECISIONS.md` D-001.

Work log: single session, no code changes to the application itself — only
`docs/v2_review_brief.md`'s stale line and the new `docs/autopilot/` state
files. Gate for this milestone: existing 39 tests still pass unmodified
(re-verified after the doc edit — the edit touches no code path); no
application behavior changed, so `make check-fast` (not yet built — see F.2)
is vacuously satisfied by "the untouched test suite still passes."

### F.2 — Tooling and structure (§4.2) — **DONE**

- [x] `Makefile` with targets: `dev`, `test`, `check`, `check-fast`, `e2e`,
      `build`, `docker`, `seed`, `migrate`. `check-fast` runs everything
      buildable in this sandbox (ruff, mypy, frontend typecheck/lint, pytest
      with coverage floor); `check` adds `pip-audit`/`npm audit` and prints
      explicit "deferred to milestone F.x" notes for pieces whose
      infrastructure doesn't exist yet (frontend unit tests, migration tests,
      contract check, E2E), plus the Docker split-gate note from F.1's
      baseline. Nothing is silently absent.
- [x] `.pre-commit-config.yaml` — local hooks (no fetched repos, so it can't
      drift from the Makefile or need network at hook-install time) that run
      the exact same six commands as `check-fast`. Verified end-to-end with
      `uvx pre-commit run --all-files` — all six pass.
- [x] Permission-check consolidation (D-004): `routes_opportunities.py`'s
      `fetch_accessible_opportunity`/`fetch_owned_opportunity` replaced by a
      role-agnostic `fetch_opportunity_row` plus calls to
      `permissions.require_opportunity_access`/`require_opportunity_owner`.
      Found and fixed one real behavior gap this surfaced (D-007): shared
      non-owners now get 403, not 404, on `PATCH`/`DELETE /api/opportunities`,
      matching `routes_sharing.py`'s existing convention — locked in by a new
      regression test, confirmed to fail pre-fix. Deferred: a full
      routers→services→data-access layer split (brief's other F.2 phrasing)
      is a much larger refactor than this milestone's session budget allows;
      the consolidation closes the specific gap D-004 named without it.
- [x] Typed settings: `field_validator`s on `database_url` (must be
      `sqlite:///`-prefixed) and the new `environment` field
      (`development`/`production`/`test`), plus `validate_assignment=True` so
      later mutation (tests reassign `settings.database_url`) still
      validates. `SESSION_SECRET` removed as dead config per D-008 (ADR 0009
      prefers a dedicated `INBOUND_EMAIL_SECRET` in Phase 5 anyway);
      `environment` added in its place and is what the new error handler
      uses. `.env.example`/`README.md` updated to match.
- [x] Structured JSON logging (`logging_utils.py`): a `JsonFormatter` plus a
      pure-ASGI `RequestLoggingMiddleware` (not `@app.middleware("http")` /
      `BaseHTTPMiddleware` — that has a documented exception-propagation bug
      with sync routes run in the threadpool that surfaced here as a
      genuinely order-independent-but-content-dependent test failure; traced
      to ground before switching approaches, not worked around). Adds
      `X-Request-ID` to every response and logs method/path/status/duration
      for every request, never headers/cookies/bodies. `routes_ai.py`'s
      previously-silent OpenAI-call exception now logs a warning with the
      opportunity id before converting to the 502 the client sees.
- [x] Consistent API error envelope (`errors.py`): a handler for the bare
      `Exception` class returns `{"detail": str}` — the same shape
      `HTTPException` and validation errors already use — instead of
      Starlette's default plain-text 500. This was a real, verified gap, not
      speculative: `apiRequest<T>()` (CLAUDE.md) calls `response.json()` on
      every non-2xx response, which would throw a JSON-parse error on the old
      plain-text body. `detail` is the real exception message outside
      `environment=production`, a generic string inside it. Found and fixed a
      second real bug while writing the regression test: Starlette routes a
      bare-`Exception` handler through `ServerErrorMiddleware`, which sits
      *above* `RequestLoggingMiddleware`, so the response it returns never
      passed through the middleware's `X-Request-ID`-adding `send_wrapper` —
      the handler now sets that header directly.
- [x] Tooling side-effects, all verified rather than assumed: `ruff check`,
      `ruff format --check`, and `mypy --strict app/` all pass clean —
      required reformatting/reordering imports across most of `backend/app`
      and `backend/tests` (cosmetic only, diffed and confirmed), fixing 10
      genuine line-length violations, and annotating ~28 real
      `no-any-return`/missing-type-arg gaps (sqlite3's stubs return `Any` from
      `fetchone()`/`Row.__getitem__` and `cursor.lastrowid` is typed
      `int | None`, so several "assert not None" guards are new and correct,
      not decorative). `pip-audit`/`npm audit` both clean; `pip-audit` found
      one real CVE (PYSEC-2026-3940, a WeasyPrint `url_fetcher` bypass) that
      doesn't apply to this codebase's usage (no `xmp_metadata=`/
      `stylesheets=` arguments are ever passed) but was a trivial, safe
      69.0→70.0 bump, taken anyway. mypy strict is scoped to `app/`, not
      `tests/`, per D-009. Coverage: `--cov-branch` now on by default
      (COVERAGE.md's prior to-do); backend 94% combined line+branch,
      `--cov-fail-under=90` enforced in `check-fast`. Closed two per-module
      gaps against brief §6.2's ≥95% floor for critical modules: `auth.py`
      93%→100%, `settings.py`'s new validators 100%. `ai_service.py` (79%,
      below the floor) is knowingly deferred to F.6, which explicitly owns
      wrapping `ask_openai` with the timeout/retry/graceful-failure work that
      would let its error branches be tested without a live API call.

Work log: single session. Full diff: `backend/app/routes_opportunities.py`
(permission consolidation), new `backend/app/errors.py` and
`backend/app/logging_utils.py`, `backend/app/settings.py`,
`backend/app/main.py`, `backend/app/routes_ai.py` (one added log call),
line-length-only edits to `ai_service.py`/`export_service.py`/
`routes_timeline.py`, mypy-annotation-only edits across 8 more `app/` files,
new `Makefile` and `.pre-commit-config.yaml` at the repo root, `.env.example`
and `README.md` (SESSION_SECRET → ENVIRONMENT), `backend/pyproject.toml`
(ruff/mypy config, `pip-audit`/`mypy`/`ruff` dev deps, weasyprint bump), new
tests in `test_opportunities.py`, `test_auth.py`, and two new files
(`test_error_handling.py`, `test_settings.py`). Every new/changed assertion
was confirmed to fail against the pre-fix code before being trusted (brief
§6.5). Gate: `make check-fast` green (ruff, ruff format, mypy --strict,
frontend typecheck, frontend lint, pytest 47 passed w/ 90% coverage floor);
`make check` green including `pip-audit`/`npm audit` (0 known
vulnerabilities) and the explicit deferred-item notes for F.3/F.4/F.7's
pieces; Docker build+smoke test named as deferred to the host per the split
gate (unchanged from F.1).

### F.3 — API contract (§4.3) — **DONE**

- [x] Typed request/response models for every endpoint in OpenAPI.
      `AuditLogEntryPublic.detail` (was opaque `str` — the JSON blob was never
      even parsed before being wrapped in *another* JSON string on the wire)
      is now a union of 7 typed models, one per audit action, parsed via
      `audit_utils.parse_audit_detail`. `NotificationPublic.payload` (was
      `dict[str, Any]`) is now a union of 6 typed models, one per notification
      type, parsed via `notification_service.parse_notification_payload`.
      Also tightened three previously-`str` fields that are actually closed
      enums: `OpportunityPublic.stage` → `Stage`, `OpportunityPublic.
      current_user_role` → new `CurrentUserRole` Literal, `TimelineEntryPublic.
      type` → `EntryType`, `SharePublic.role` → `ShareRole`. Field-level unions
      chosen over restructuring the two response models into whole-object
      discriminated unions — see D-010 for the reasoning (the frontend has no
      consumer that needs `type`-to-`payload` narrowing at the type level;
      doubling the schema surface for it would be speculative).
- [x] Generated a TypeScript client: `backend/app/export_openapi.py` prints
      `app.openapi()` as JSON with no server boot (D-011); `openapi-typescript`
      (new frontend devDependency) turns it into `frontend/lib/api-types.ts`
      (committed, 1994 lines). `frontend/app/page.tsx`'s hand-declared
      response-mirroring interfaces (`User`, `Opportunity`, `OpportunityShare`,
      `AuditLogEntry`, `AppNotification`, `TimelineComment`, `TimelineNote`,
      `TimelineEntry`, plus the four inline wrapper shapes used with
      `apiRequest<...>()`) are now type aliases onto `components["schemas"][...]`
      from the generated file. `TimelineComment`/`TimelineNote` were dropped
      entirely once nothing referenced them by name (they'd only existed to
      compose the other hand-written interfaces). Form-draft types
      (`OpportunityForm`, `TimelineEntryForm`, `TimelineFilters`, `ShareForm`'s
      `email` field) stay hand-written — they hold provisional UI string state
      before submission (e.g. empty-string sentinels, local-datetime strings),
      which is a genuinely different shape from the wire format, not a
      duplicate of it. Fixed two downstream call sites that read the old
      untyped shapes unconditionally: `notificationText()`'s `shared_activity`
      branch now narrows the payload union with `"title" in payload` instead
      of reading `.title` off every notification type, and the audit-log
      `<code>` block renders `JSON.stringify(item.detail)` instead of a raw
      string. `npm run typecheck`, `npm run lint`, and `npm run build` all
      pass against the new types.
- [x] Gate fails on a stale generated client:
      `scripts/generate-api-client.sh --check` regenerates into a temp file
      and diffs it against the committed `frontend/lib/api-types.ts`, wired
      into both `make check-fast` and `.pre-commit-config.yaml` (new
      `api-client-contract` hook). `make generate-client` regenerates it in
      place. Also closed the human's F.2-review note in DECISIONS.md: added a
      `frontend-deps` Make target (`npm ci` only if `node_modules/.bin` is
      missing) as a prerequisite of `dev`, `check-fast`, and `build`, so
      `make check-fast` now runs from a clean checkout with an empty
      `node_modules` volume, not just a pre-populated one.

Work log: single session. Backend diff: `backend/app/schemas.py` (14 new
typed models + 4 tightened field types), `backend/app/audit_utils.py` /
`backend/app/notification_service.py` (parse helpers), `backend/app/
routes_sharing.py` / `backend/app/routes_notifications.py` (call sites), new
`backend/app/export_openapi.py` + `backend/tests/test_export_openapi.py`.
Two existing tests adjusted to match the tightened contract (not weakened —
see COVERAGE.md's F.3 entry for why each was already testing something the
new types made stricter): `test_deletions_are_recorded_in_the_audit_log`
(`test_timeline.py`) and `test_user_can_mark_only_own_notification_read`
(`test_notifications.py`). Frontend diff: `frontend/app/page.tsx` (type
sourcing + two call-site fixes), new `frontend/lib/api-types.ts` (generated,
committed), `frontend/package.json`/`package-lock.json` (+`openapi-typescript`
devDependency). Tooling diff: new `scripts/generate-api-client.sh`, `Makefile`
(`frontend-deps`, `generate-client` targets; `check-fast` gains the contract
check), `.pre-commit-config.yaml` (new hook). Gate: `make check-fast` green
(48 backend tests, 94.29% combined coverage, ruff/mypy/tsc/eslint all clean,
contract check passes); `make check` also run and green (`pip-audit`/`npm
audit` both 0 vulnerabilities); Docker portion still deferred to the host
per the unchanged split-gate note.

### F.4 — Database (§4.4) — **DONE**

Run on Opus (`MODEL=opus sandbox/run.sh autopilot`), per `scripts/autopilot.sh:11-14`:
the Alembic baseline is one of the two things in the plan that is hardest to
recover from if it lands wrong. The run header records the model in the log file,
so the resulting commit is attributable.

- [x] Alembic introduced with the current schema as the baseline revision.
      `app/schema.sql` is deleted; `alembic/versions/20260916_0001_baseline.py`
      carries its DDL verbatim (`IF NOT EXISTS` dropped — a revision runs once).
      `initialize_database()` now calls `command.upgrade(config, "head")`, so
      zero-setup for new installs is preserved: a fresh database gets the whole
      schema with no manual step, and `make migrate` exists for applying
      revisions by hand. `alembic/env.py` takes its URL from
      `database.sqlalchemy_url()` — derived from the same `settings.database_url`
      the raw `sqlite3` connections use — so the CLI and the startup migration
      can never target different files; `alembic.ini` deliberately sets no URL
      and no logging config (the latter would replace F.2's JSON formatter
      mid-boot). `target_metadata` stays `None`: Alembic is adopted for the
      version table, ordering and batch rebuilds, not as an ORM (ADR 0002).
- [x] `run_migrations()` converted. Not into revisions — see **D-013**: ADR 0002's
      own step 3 (stamp the legacy database at the baseline) and step 4 (convert
      the ALTERs into revisions) contradict each other, because a database
      stamped at the baseline is already past them. The two guarded `ALTER
      TABLE`s, `normalize_legacy_timestamps()` and
      `backfill_opportunity_created_entries()` now live in
      `bridge_pre_alembic_database()`, which runs **once**, against a database
      that has tables but no `alembic_version`, immediately before the stamp.
      ADR 0002's stated goal ("startup stops doing repeated full-table scans")
      is met literally, and
      `test_legacy_repair_runs_once_rather_than_on_every_startup` proves it.
- [x] Consequence of the above, found while testing it rather than predicted:
      **D-014**. Once the repair stops running every boot, a bridged legacy
      database — which keeps its old `DEFAULT CURRENT_TIMESTAMP` columns,
      because SQLite's `ALTER TABLE` cannot rewrite a default — writes
      `"YYYY-MM-DD HH:MM:SS"` values that nothing ever normalizes again. That is
      the exact mixed-format corruption CLAUDE.md's Timestamps section warns
      about. Every `INSERT`/`UPDATE` across `auth.py`, `audit_utils.py`,
      `notification_service.py`, `routes_auth.py`, `routes_opportunities.py`,
      `routes_sharing.py`, `routes_timeline.py` and `timeline_utils.py` now
      supplies its timestamps explicitly via `utc_now()`; column defaults remain
      only as a backstop. `test_writes_to_a_bridged_legacy_database_are_canonical`
      drives the real API against a bridged MVP database and checks all 14
      written timestamp columns; confirmed to fail against the pre-fix code.
- [x] Migration tests (brief §6.1's "upgrade from empty and from an MVP-era
      snapshot with realistic data") — `tests/test_migrations.py`, 6 tests.
      `tests/data/mvp_schema.sql` is the real pre-Alembic schema (commit
      acac885), populated with `CURRENT_TIMESTAMP`-format rows and with
      `system_generated` dropped to match that era. Upgrade-from-empty is
      compared against `tests/data/expected_schema.sql`, so a revision that
      changes the schema has to update that snapshot deliberately.
      `make check`'s "Migration tests: deferred to milestone F.4" note is
      removed, and `make migrate` now runs `alembic upgrade head` instead of
      printing a deferral.
- [x] SQLite: WAL enabled, `PRAGMA foreign_keys = ON` confirmed, busy timeout
      set to 5s — all three in `get_connection()`, all three guarded by the new
      `tests/test_database.py` (3 tests, each confirmed to fail with the pragmas
      removed). Foreign keys are checked by provoking a real `IntegrityError`,
      not just by reading the pragma back. `.gitignore`/`.dockerignore` gained
      `*.db-wal` / `*.db-shm`, which WAL creates alongside the database and
      which `*.db` does not match.
- [x] ADR: SQLite fitness for v2. **Dropped — already satisfied, see D-012**
      (human-accepted 2026-09-16). `docs/adr/0001-keep-sqlite.md` (Accepted,
      benchmarked at the confirmed 800k-row scale) answers it and already
      prescribes the WAL + busy-timeout work above; ADR 0003 covers the
      real-time half and ADR 0011 the single-container half.
- [x] Central soft-delete implementation: `app/soft_delete.py` is now the only
      place user data is deleted. It owns the `deleted_at` cascade down the
      opportunity → entry → note → comment tree (plus shares), and
      `routes_opportunities.py`, `routes_sharing.py` and `routes_timeline.py`
      call its five helpers instead of writing their own `UPDATE ... SET
      deleted_at` — about 100 lines of duplicated cascade SQL removed, and the
      cascade defined once so a new delete path cannot forget a level.
- [x] Test that fails on hard deletes of user data: `tests/test_soft_delete.py`.
      A source scan rather than a runtime check, deliberately — a `DELETE FROM
      notes` on a path no test exercises would still ship. Per brief §6.5 the
      guard is itself guarded: `test_the_guard_detects_a_hard_delete` runs the
      scanner over a file that does contain one, and
      `test_the_guard_allows_session_cleanup` pins the one intentional exclusion
      (`sessions` is ephemeral auth state, not user content, and logout really
      does delete the row). A behavioral companion,
      `test_invariant_deleting_an_opportunity_retains_every_row`, deletes a fully
      populated opportunity through the API and asserts every row across five
      tables survives with `deleted_at` set.

Work log: single session (Opus). Backend diff: `app/database.py` (Alembic wiring,
WAL/busy-timeout pragmas, the bridge, `table_exists`), new `app/soft_delete.py`,
new `backend/alembic.ini` + `backend/alembic/` (env, `script.py.mako`, baseline
revision), deleted `app/schema.sql`, explicit-timestamp edits across 8 `app/`
modules, `pyproject.toml`/`uv.lock` (+`alembic`). Tests: new
`tests/test_migrations.py`, `tests/test_soft_delete.py`, `tests/test_database.py`,
new `tests/data/{mvp_schema,expected_schema}.sql`; one test removed from
`tests/test_opportunities.py` and relocated (**D-016**, justified there — the
same guarantee is now asserted against a real MVP-era database rather than a
hand-built row). Tooling/docs: `Makefile` (`migrate` target, dropped deferral
note), `.gitignore`, `.dockerignore`, `CLAUDE.md` (Migrations, connection
pragmas, and Soft deletes sections rewritten — they document the code, so they
change in this commit). Decisions: **D-013** (bridge instead of revisions),
**D-014** (explicit timestamps), **D-015** (keep `column_exists()` against ADR
0002 step 6), **D-016** (relocated test). None flagged needs-human-review.
Gate: `make check-fast` green — ruff, `ruff format --check`, `mypy --strict`,
frontend typecheck/lint, API-contract check, and 60 backend tests at 94.65%
combined coverage against the 90% floor. `make check` also green (`pip-audit`
and `npm audit` both 0 vulnerabilities). Docker build + smoke test remains
deferred to the host per the split gate (brief §3.4), unchanged.

### F.5 — Security (§4.5)

- [ ] CSRF protection for cookie sessions (none exists today — cookies are
      `httponly`, `samesite=lax` only, `auth.py:39-45`).
- [ ] Secure cookie flags (`secure=True` in production).
- [ ] Session rotation on login (already effectively true — `create_session`
      issues a fresh token every login, `auth.py:28-45` — verify and test
      explicitly), invalidation on logout (already true, `auth.py:48-54`) and
      on password change (**no password-change endpoint exists yet** — new
      endpoint, or explicitly scope it to a later phase since it is not a v1
      requirement).
- [ ] Rate limiting on login/signup (none today, `docs/code_review.md`
      finding 10); generic auth errors (already true, `routes_auth.py:66-70`).
- [ ] Finish the permission-check consolidation from F.2/D-004 across every
      service method touching an opportunity.

**F.5a — Editors may edit only their own content (D-005, overruled by the
human 2026-09-16).** Edit permission must mirror delete exactly: author or
opportunity owner. This closes `docs/code_review.md` finding 4a the way it
asked.

- [ ] Add the edit-side counterpart to `permissions.require_delete_permission`
      (`permissions.py:68-82`) rather than a second inline rule, so both paths
      resolve through one helper.
- [ ] Apply it to timeline entry edit (`routes_timeline.py:340-383`) and note
      edit (`routes_timeline.py:513-577`). Comments stay immutable to everyone
      (invariant §2.2) — no edit route is to be added.
- [ ] Update `test_editor_can_write_and_viewer_is_read_only`
      (`test_timeline.py:225`). **This assertion change is authorised by the
      human ruling in DECISIONS.md D-005** and is therefore not a weakened test
      under brief §6.5; cite D-005 in the commit.
- [ ] Add tests: an editor editing a colleague's entry and note gets 403; the
      author and the opportunity owner both still succeed.
- [ ] Add the endpoints to the authorization matrix (§6.4) with the tightened
      expectations.
- [ ] Frontend: add a `canEdit(authorId)` helper mirroring the existing
      `canDelete(authorId)`, so the UI never offers an edit the API will
      reject.
- [ ] Update `CLAUDE.md`'s Permissions section, which still describes the old
      "editors add and edit freely" behaviour — it documents the code, so it
      changes when the code does, in this milestone's commit.
- [ ] Upload hardening (size limits, content sniffing, randomized stored
      names, safe paths, forced download disposition, traversal tests) — no
      attachments exist yet (Phase 4 feature); stand up the framework here so
      Phase 4 only wires into it, per brief §4.7's intent.
- [ ] Server-side sanitization framework for user HTML, ready for rich text
      (Phase 3) — the frontend already runs `rehype-sanitize` client-side
      (`page.tsx:166-178` per `docs/code_review.md`); a server-side companion
      does not exist yet.
- [ ] Security headers: CSP, `X-Content-Type-Options`, `Referrer-Policy`,
      `frame-ancestors` (none set today).

### F.6 — AI agent hardening (§4.6)

- [ ] Test asserting read-only DB access plus zero write tools (the
      architecture already guarantees this — `ai_service.ask_openai` calls
      `client.responses.create` with no `tools=` argument — but no test names
      this invariant explicitly yet).
- [ ] Cross-opportunity leakage tests (agent inherits the requesting user's
      permissions via `require_opportunity_access`, `routes_ai.py:33` —
      `test_ai_blocks_users_without_access` exists; extend to a positive case
      proving context from one opportunity never appears when asking about
      another).
- [ ] Prompt-injection tests using hostile content in notes (attachments come
      in Phase 4 — injection tests for attachment content land there).
- [ ] Single OpenAI client wrapper with timeouts, retries, and graceful
      failure (today `ask_openai`, `ai_service.py:124-137`, has no timeout or
      retry — a hung OpenAI call currently hangs the request); always mocked
      in tests (already true, `test_ai.py` monkeypatches `ask_openai`).

### F.7 — Test infrastructure (§4.7)

- [ ] Stand up every layer in brief §6.1 not yet present: frontend unit/
      component tests (Vitest + React Testing Library — zero exist today),
      contract tests (generated-client-matches-schema), Playwright E2E with
      `@axe-core/playwright`, migration tests (upgrade-from-empty and
      upgrade-from-an-MVP-snapshot, once F.4's Alembic work lands).
- [ ] Authorization matrix: every endpoint × {owner, editor, viewer, unrelated
      user, anonymous}; unregistered routes fail the test. Build this by
      enumerating `app.routes` at runtime so a new route without a permission
      dependency cannot silently ship (brief §6.4, `AGENTS.md` invariant 2).
- [ ] Invariant tests named `test_invariant_*` for each item in brief §2
      (currently satisfied by construction, per `docs/autopilot/INVENTORY.md`
      §4's review, but not asserted under this naming/organization yet):
      AI read-only, no comment-edit route, hard-delete detection, `created_at`
      immutable via every endpoint, stage list fixed.
- [ ] Seed data script (`make seed`) at a scale useful for manual testing
      (full 800k-row scale is Phase R's concern; Phase F needs a small,
      fast, feature-covering seed).
- [ ] Docker smoke test defined (build, start, health check, sign up, open an
      opportunity, export a PDF) — **cannot run inside this sandbox** (no
      Docker socket, `sandbox/README.md`). Write the smoke-test script/steps
      here; the human runs it via `scripts/autopilot-gate.sh` per the split
      gate (brief §3.4). Do not skip defining it just because it cannot be
      executed here.

### F.8 — Gap-analysis fixes not covered above

- [ ] Remove dead `time_utils.parse_timestamp` (unreferenced,
      `docs/autopilot/INVENTORY.md` §7) or find and fix the caller that should
      exist.
- [ ] Fix `conftest.py` mutating the global `settings.database_url` without
      restoring it (`docs/code_review.md` finding 10) — a test-isolation risk
      once the suite grows in later phases.
- [ ] Remove the dead defensive branch in
      `export_service.fetch_export_data` (`{"opportunity": None}` on a
      condition `require_opportunity_access` already forecloses) per
      `AGENTS.md` coding standard 2.
- [ ] Purge expired `sessions` rows (currently never cleaned up).
- [ ] Replace `passlib` (unmaintained, warns on every test run) with a
      maintained bcrypt wrapper, dropping the `bcrypt<5` pin
      (`docs/code_review.md` finding 10).
- [ ] Pin frontend dependency versions instead of `"latest"`
      (`frontend/package.json`).

### F.9 — Phase F gate and review packet

- [ ] Full `make check` (once F.2 builds it) green, Docker portion named as
      deferred to the host per the split gate.
- [ ] Write `docs/autopilot/reviews/phase-F-summary.md` per brief §3.5.
- [ ] Set `STATUS: AWAITING_REVIEW phase=F`, commit, stop.

---

## Phase 1 — Backbone, Search, Notifications

Branch: `autopilot/phase-1`. Depends on: `phase-F-accepted` tag.

Goal (verbatim from `docs/ROADMAP.md`): put the non-negotiable foundations in
while shipping the two features whose current implementations are dead ends
rather than extensions. User-visible outcome: global ranked search with
highlighted snippets across every opportunity, and a notification inbox that
keeps history instead of erasing it.

### Milestones

- [ ] 1.1 GitHub Actions CI: backend suite, frontend typecheck/lint,
      `docker build`, and the backend suite **inside the image** (WeasyPrint).
      Blocker B4.
- [ ] 1.2 Alembic: baseline-stamp the existing database, convert
      `run_migrations()` to revisions, make `normalize_legacy_timestamps` a
      one-shot. Blocker B2, ADR 0002. (Coordinate with Phase F milestone F.4 —
      if F.4 already did the Alembic baseline, this milestone is the
      roadmap's confirmation/extension of it, not a duplicate.)
- [ ] 1.3 `/api/v2` with the pagination envelope and the unified error shape.
      Blocker B3.
- [ ] 1.4 FTS5 contentless index plus triggers, including soft-delete
      transitions (ADR 0007). Feature: Search (§13).
- [ ] 1.5 React Router and TanStack Query introduced — justified by needing a
      second route, carrying blocker B1's first instalment (ADR 0005).
- [ ] 1.6 Structured logging, `/api/health` detail, WAL, `VACUUM INTO` backup
      job with a tested restore (ADR 0011).
- [ ] 1.7 Notifications inbox rework (§9, minus digests): read/unread with
      history (fixing the current `WHERE read = 0` dead end,
      `routes_notifications.py:24-37`), filtering by type, mark-all-read.
      Schema: `notifications` gains `read_at`, `grouped_key`.

### Acceptance (from ROADMAP.md, all must hold before AWAITING_REVIEW)

- CI red on a deliberately broken test; green on `main`.
- `alembic upgrade head` applies to an empty database and to a copy of the
  current `data/app.db`, both verified in CI.
- Search for a rare term returns ranked, snippeted results in < 300 ms at
  seeded scale; deleting a note removes it from results.
- A read notification remains visible and filterable.
- v1 endpoints still serve the existing frontend.

---

## Phase 2 — Pipeline Views and Keyboard Navigation

Branch: `autopilot/phase-2`. Depends on: `phase-1-accepted` tag.

Goal: the signature v2 capability — one dataset, five views — and the frontend
structure that makes it possible. User-visible outcome: a pipeline board where
dragging a card changes the stage and auto-logs it; list, table and calendar
over the same filters; saved views in the sidebar; ⌘K to jump anywhere.

### Milestones

- [ ] 2.1 Decompose `page.tsx` into routed views and feature components.
      Blocker B1 lands here in full, paid for by the board view.
- [ ] 2.2 Shared filter/sort/group model serialized to the URL; saved views
      persisted. Schema: `saved_views`.
- [ ] 2.3 `VirtualList` for the 400-opportunity scale.
- [ ] 2.4 Command palette, keyboard map, bulk actions, optimistic mutations,
      undo toasts.
- [ ] 2.5 Design tokens from `DESIGN-SYSTEM.md`, including the three
      corrected contrast values; Radix primitives; real dialogs replacing
      `window.confirm` (`page.tsx:229`). **D-003 ACCEPTED by the human
      2026-09-16 — this is now phase scope, not a proposal:** ship light and
      dark themes together, with dark-theme parity asserted by axe contrast
      checks on every component delivered in Phase 2.
- [ ] 2.6 Three new entry types with icons. Schema: `timeline_entries.type`
      CHECK extended.
- [ ] 2.7 Board view (drag to change stage, auto-logs a system entry) and list
      view — acceptance-critical.
- [ ] 2.8 Table and calendar view — may slip to Phase 3 per the roadmap's own
      stated risk mitigation; do not treat slipping these as a blocked
      milestone.

### Acceptance

- Drag a card between stage columns; a system stage-change entry appears.
- A saved view survives reload and is shareable by URL.
- Every action in the keyboard map works without a mouse, board drag included.
- View switch < 150 ms with data cached; `axe` clean in CI (2.2 AA per D-002).
- Timeline load stays within 400 ms at seeded scale.
- Light and dark themes both ship, and both pass axe contrast checks on every
  component delivered in this phase (D-003, accepted 2026-09-16).

---

## Phase 3 — Rich Content and Live Collaboration

Branch: `autopilot/phase-3`. Depends on: `phase-2-accepted` tag.

Goal: make the timeline worth writing in, and make two people on one deal see
each other.

### Milestones

- [ ] 3.1 TipTap serializing to Markdown — no content migration (ADR 0005
      rationale, `FEATURES.md` §4).
- [ ] 3.2 Mention autocomplete, fixing requirement 13's discoverability
      (today mentions require typing a full email address by hand).
- [ ] 3.3 Threaded comments, reactions, resolve/unresolve, watchers. Schema:
      `comments` gains `parent_id`, `resolved_at`; new `reactions`, `watchers`
      tables.
- [ ] 3.4 SSE endpoint and client invalidation (ADR 0003); 409 edit guard on
      notes.
- [ ] 3.5 PDF export renders Markdown, closing the other half of requirement
      17 (`docs/code_review.md` finding 9's "still open" item —
      `export_service.render_export_html` currently escapes bodies as plain
      text).
- [ ] 3.6 If table/calendar views slipped from Phase 2, land them here.

### Acceptance

- A bullet list can be typed in a note (impossible today — single-line
  composers, `docs/code_review.md` finding 10).
- @mention autocompletes and notifies.
- Two browsers: an entry created in one appears in the other in < 2 s.
- Concurrent note edits produce a 409 and a reload prompt, not a silent
  clobber.
- Exported PDF renders bold and lists rather than literal asterisks.

---

## Phase 4 — Tasks and Attachments

Branch: `autopilot/phase-4`. Depends on: `phase-3-accepted` tag.

Goal: capture the two artifacts a deal actually produces — the next action and
the document.

### Milestones

- [ ] 4.1 Task model scoped to an opportunity; My Tasks across opportunities;
      overdue/upcoming surfaces on the dashboard. Schema: `tasks`.
- [ ] 4.2 Migrate `timeline_entries.follow_up_date` into tasks, keeping the
      column until the UI has moved (per the breaking-changes table: dropped
      in Phase 5).
- [ ] 4.3 Attachments: content-addressed storage, magic-byte validation,
      streamed authorized download, `Content-Disposition: attachment` and
      `nosniff` (ADR 0008). Schema: `attachments`. Wire into the upload-
      hardening framework stood up in Phase F milestone F.5.
- [ ] 4.4 PDF export gains an attachment manifest.

### Acceptance

- A task created from an entry appears in My Tasks and on the dashboard when
  overdue.
- A viewer on a shared opportunity can download an attachment; a non-shared
  user gets 404 — `/data` is never reachable as a static path.
- Upload rejects a `.exe` renamed to `.pdf` (magic-byte check).
- Existing `follow_up_date` values appear as tasks after migration.

---

## Phase 5 — Email In and Out

Branch: `autopilot/phase-5`. Depends on: `phase-4-accepted` tag.

Goal: the confirmed email requirement, isolated late so it lands on a stable
platform. This is the highest-risk phase in the plan (first untrusted input
path into a shared record and into the AI context).

### Milestones

- [ ] 5.1 APScheduler jobs and the durable outbox (ADR 0004).
- [ ] 5.2 Outbound notification email with `Reply-To` set to the signed
      threaded address.
- [ ] 5.3 IMAP polling ingestion behind a transport interface (ADR 0009), so a
      provider webhook is a later swap.
- [ ] 5.4 HMAC-signed reply addresses; sender-to-user matching using the
      **normal write check**, not a parallel authorization path; DKIM
      verification; `Message-ID` dedupe; per-sender rate limiting.
- [ ] 5.5 Quoted-reply and signature stripping; HTML → Markdown; attachments
      via Phase 4's pipeline.
- [ ] 5.6 `source = 'email'` provenance shown in the UI and labelled in AI
      context (ADR 0012 — untrusted input must be labelled everywhere per
      `AGENTS.md` invariant 4). Schema: `source` on entries/notes/comments.
- [ ] 5.7 Ingestion log including rejections — silent drops are unacceptable.
      Schema: `email_messages` (dedupe + ingestion log).
- [ ] 5.8 Digest batching and per-user preferences. Schema:
      `notification_preferences`.
- [ ] 5.9 Adversarial test suite: spoofed sender, valid-sender-without-access,
      replay, and an injected-instruction email body that must not change the
      AI's behavior or make it claim it modified anything.

### Acceptance

- Reply to a notification → comment appears, marked as email-sourced.
- Spoofed `From:` for a non-user is rejected and logged, not posted.
- A valid sender **without** write access to the target is rejected.
- Replaying the same message twice creates one record.
- An adversarial email body containing instruction-shaped text does not change
  the AI's behavior or make it claim it modified anything.

---

## Phase 6 — Custom Fields, Dashboards, Automations

Branch: `autopilot/phase-6`. Depends on: `phase-5-accepted` tag.

Goal: the configurability and reporting layer, once the shape of the data is
settled.

### Milestones

- [ ] 6.1 Custom fields: definition table + JSON value column + expression
      indexes (ADR 0006); fields flow into table columns, filters, and the
      entry form. Schema: `custom_field_definitions`; `custom_values` JSON on
      opportunities and entries.
- [ ] 6.2 Six live-computed dashboard aggregations — no rollup tables
      (pipeline, win/loss, time in stage, stalled, activity, forecast per
      `FEATURES.md` §10); index on `(created_by, created_at)` for
      activity-per-rep.
- [ ] 6.3 Constrained rule builder: single-hop only (trigger → condition →
      action), dry-runnable, every automated write producing a traceable
      system entry naming the rule. Schema: `automation_rules`,
      `automation_runs`. This is also the mechanism confirmed in D-006's
      cross-check to satisfy journey §6.3 #9 (stalled → reminder).
- [ ] 6.4 AI expansion (safe subset): streaming, date-scoped summaries,
      natural-language filter construction — output is a query the user
      inspects before applying, never an auto-applied write.

### Acceptance

- A new select field appears as a table column, a filter, and on the entry
  form.
- Each dashboard aggregate returns inside 300 ms at seeded scale, asserted in
  CI.
- A no-activity-for-14-days rule fires once, creates a task, and logs a system
  entry naming the rule; it cannot trigger another rule.
- The AI still holds read-only under an injected-instruction test.

---

## Phase R — Release readiness

Branch: `autopilot/phase-R`. Depends on: `phase-6-accepted` tag. Per §3.3, once
this phase reaches `AWAITING_REVIEW` and is accepted, the project is finished.

### Milestones

- [ ] R.1 UX consistency: loading/empty/error states everywhere; responsive to
      tablet; timeline usable on mobile; design tokens applied consistently.
- [ ] R.2 Accessibility: axe clean (2.2 AA per D-002); focus management in
      dialogs and the command palette; full keyboard operability.
- [ ] R.3 Performance: large-dataset budgets met (800k-row seed per
      `AGENTS.md`'s "Confirmed Scale"); list/timeline virtualization; indexes
      justified by measurement, not guessed.
- [ ] R.4 Docker: multi-stage build, non-root user, pinned versions,
      WeasyPrint dependencies, `HEALTHCHECK`, `/healthz` and `/readyz`,
      graceful shutdown.
- [ ] R.5 Data safety: documented volume layout; SQLite online backup and
      restore procedure with a restore test; uploads included.
- [ ] R.6 CI: GitHub Actions running `make check` on push to `main`, with
      coverage and Playwright report artifacts and an image build (create the
      workflow file; do not push it).
- [ ] R.7 Seed data exercising every shipped feature and permission
      relationship, at the confirmed 800k-row scale.
- [ ] R.8 Documentation: `README.md`, `ARCHITECTURE.md` (Mermaid data model,
      auth/permission model, real-time design, AI read-only guarantee), ADR
      index, API guide, `docs/user-guide.md`, `docs/operations.md`,
      `CHANGELOG.md`, updated `AGENTS.md` and `PLAN.md`.
- [ ] R.9 `docs/autopilot/FINAL-REPORT.md`: what shipped per phase, coverage
      history, invariant and E2E test lists, open blockers, non-reversible
      decisions, recommended next steps.

The Phase R review packet doubles as the release sign-off (brief §8).

---

## Definition of Done (brief §10) — tracking

- [ ] `phase-F-accepted` through `phase-6-accepted` and `phase-R-accepted`
      tags exist (0 of 8 so far)
- [ ] `make check` green on `main` from a clean clone
- [ ] Coverage floors met; history in `COVERAGE.md`
- [ ] Invariant tests and authorization matrix passing
- [ ] All applicable E2E journeys passing with axe checks
- [ ] Docker image passes smoke test, runs non-root; backup/restore tested
- [ ] CI workflow present and valid
- [ ] No unresolved high/critical dependency vulnerabilities
- [ ] Documentation set and `FINAL-REPORT.md` complete
