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

### F.2 — Tooling and structure (§4.2)

- [ ] `Makefile` with targets: `dev`, `test`, `check`, `check-fast`, `e2e`,
      `build`, `docker`, `seed`, `migrate`.
- [ ] Pre-commit hooks mirroring `check-fast`.
- [ ] Introduce a service layer between routers and data access (routers: HTTP
      only → services: business rules and permission checks → data access),
      starting with the permission-check consolidation named in
      `docs/autopilot/DECISIONS.md` D-004 (`routes_opportunities.py`'s inline
      `fetch_accessible_opportunity`/`fetch_owned_opportunity` should call
      `permissions.py` instead of duplicating it).
- [ ] Typed settings with fail-fast validation in `backend/app/settings.py`
      (currently no validators beyond Pydantic's type coercion — see
      `docs/autopilot/INVENTORY.md` §2); `.env.example` documents every
      variable (already close — verify `SESSION_SECRET` is either wired up or
      removed, per `docs/code_review.md` finding 10).
- [ ] Structured JSON logging with request IDs; no secrets/tokens in logs.
      Currently there is no logging at all (`docs/code_review.md` finding 10,
      `routes_ai.py:43` swallows the OpenAI exception with no record).
- [ ] Consistent API error envelope; no stack traces to clients outside dev
      mode.

### F.3 — API contract (§4.3)

- [ ] Typed request/response models for every endpoint in OpenAPI (mostly
      already true via Pydantic schemas — verify `AuditLogEntryPublic.detail`
      and `NotificationPublic.payload`, which are currently opaque
      `str`/`dict[str, Any]`, are as typed as the data allows).
- [ ] Generate a TypeScript client from the schema; remove any hand-written API
      types on the frontend (frontend currently hand-declares its own request/
      response interfaces in `page.tsx`).
- [ ] Gate fails on a stale generated client.

### F.4 — Database (§4.4)

- [ ] Introduce Alembic with the current schema as the baseline revision;
      convert `run_migrations()` (`database.py:55-71`) into real revisions.
      Preserve zero-setup for new installs (a fresh DB still gets a fully
      migrated schema with no manual step).
- [ ] SQLite: enable WAL, confirm `PRAGMA foreign_keys = ON` (already set,
      `database.py:21`), set a busy timeout (not currently set).
- [ ] ADR: SQLite fitness for v2 given real-time features and a single
      container. **needs human review: Y** (brief §4.4 marks this explicitly).
      Default recommendation is SQLite + WAL with data access kept portable.
      Note ADR 0001 already exists and reaches this conclusion — confirm
      whether a new ADR is needed or 0001 already satisfies this requirement
      before writing a duplicate.
- [ ] Central soft-delete implementation with a test that fails on hard
      deletes of user data (a real regression test, run against the unfixed
      state first per brief §6.5's "guard test" rule — there is currently no
      hard-delete path to guard against, so this test should assert the
      *absence* of any `DELETE FROM` on the four user-data tables, e.g. by
      grepping the codebase or by a runtime assertion).

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
      `window.confirm` (`page.tsx:229`). **Apply D-003 here if accepted at the
      Phase F gate**: dark-theme parity with an explicit axe-contrast
      acceptance criterion.
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
