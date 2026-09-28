# OppTrail v2 — Roadmap

Six phases, each ending in something demoable. Structural work is folded into the
phase that needs it, per the brief's rule that no phase may be pure refactoring.

**Execution model:** agent-implemented across review-gated sessions, using the
existing `AGENTS.md` workflow — diff summary, user test steps, then an explicit
Review / Accept / Reject. "Effort" is expressed in **sessions**, each roughly a
working block ending at a gate.

## Prioritization

RICE = (Reach × Impact × Confidence) ÷ Effort. Reach is users out of 20 touching it
weekly; Impact 0.25 minimal → 3 massive; Confidence 0.5-1.0; Effort in sessions.

| Feature | R | I | C | E | RICE | Phase |
|---|---|---|---|---|---|---|
| Search (FTS5, ranked, global) | 20 | 2 | 0.95 | 3 | **12.7** | 1 |
| Tasks and follow-ups | 20 | 2 | 0.9 | 4 | **9.0** | 4 |
| Entry model extension | 20 | 1.5 | 0.9 | 3 | **9.0** | 2 |
| Navigation, palette, keyboard | 20 | 2 | 0.85 | 4 | **8.5** | 2 |
| Rich content (TipTap) | 20 | 2 | 0.9 | 5 | **7.2** | 3 |
| Attachments | 16 | 2 | 0.85 | 4 | **6.8** | 4 |
| Collaboration + live updates | 20 | 2 | 0.85 | 5 | **6.8** | 3 |
| Views over one dataset | 20 | 3 | 0.9 | 8 | **6.75** | 2 |
| Notifications inbox | 20 | 1.5 | 0.9 | 4 | **6.75** | 1 |
| Dashboards and reporting | 8 | 2 | 0.8 | 4 | **3.2** | 6 |
| Email in and out | 18 | 2 | 0.6 | 8 | **2.7** | 5 |
| Custom fields | 12 | 1 | 0.8 | 5 | **1.9** | 6 |
| AI expansion | 14 | 1 | 0.6 | 5 | **1.7** | 6 |
| CSV import | 6 | 1 | 0.8 | 3 | **1.6** | v3 |
| Automations | 10 | 1 | 0.6 | 5 | **1.2** | 6 |
| Templates and playbooks | 8 | 1 | 0.5 | 4 | **1.0** | v3 |

**Sequencing deliberately diverges from RICE**, because RICE measures value density
and cannot see dependency or rewrite risk. Views score 6.75 yet come second, because
every later feature renders inside them; email scores 2.7 yet is a whole phase,
because it was a stated requirement. Where the two disagree, dependency and
rewrite-risk win — which is what the brief asked for.

Infrastructure (CI, Alembic, pagination, the frontend data layer) is **not scored**.
Enablers score badly by construction and it would be misleading to rank them. They
are placed by dependency and each rides inside a phase with a visible outcome.

---

## Phase 1 — Backbone, Search, Notifications

**Goal:** put the non-negotiable foundations in while shipping the two features whose
current implementations are dead ends rather than extensions.

**User-visible outcome:** global ranked search with highlighted snippets across every
opportunity, and a notification inbox that keeps history instead of erasing it.

**Features:** Search (§13), Notifications inbox (§9, minus digests).

**Technical work:**
- GitHub Actions CI: backend suite, frontend typecheck/lint, `docker build`, and the
  backend suite **inside the image** (where WeasyPrint actually runs). Blocker B4.
- Alembic: baseline-stamp the existing database, convert `run_migrations()` to
  revisions, make `normalize_legacy_timestamps` a one-shot. Blocker B2, ADR 0002.
- `/api/v2` with the pagination envelope and the unified error shape. Blocker B3.
- FTS5 contentless index plus triggers, including soft-delete transitions (ADR 0007).
- React Router and TanStack Query introduced — **justified by needing a second
  route**, which is what makes this phase carry blocker B1's first instalment
  honestly rather than as disguised refactoring (ADR 0005).
- Structured logging, `/api/health` detail, WAL, `VACUUM INTO` backup job with a
  *tested* restore (ADR 0011).

**Schema:** `search_index` virtual table + triggers; `notifications` gains
`read_at`, `grouped_key`.

**Depends on:** nothing.

**Acceptance:**
- CI red on a deliberately broken test; green on `main`.
- `alembic upgrade head` applies to an empty database and to a copy of the current
  `data/app.db`, both verified in CI.
- Search for a rare term returns ranked, snippeted results in < 300 ms at seeded
  scale; deleting a note removes it from results.
- A read notification remains visible and filterable.
- v1 endpoints still serve the existing frontend.

**Effort:** 5 sessions. **Risk:** Alembic baseline against the live database —
mitigated by the restore-a-snapshot CI step and by never running the baseline
revision against a stamped database.

---

## Phase 2 — Pipeline Views and Keyboard Navigation

**Goal:** the signature v2 capability — one dataset, five views — and the frontend
structure that makes it possible.

**User-visible outcome:** a pipeline board where dragging a card changes the stage
and auto-logs it; list, table and calendar over the same filters; saved views in the
sidebar; ⌘K to jump anywhere.

**Features:** Views (§1), Entry model extension (§2), Navigation and input (§12).

**Technical work:**
- Decompose `page.tsx` into routed views and feature components. **Blocker B1 lands
  here in full**, paid for by the board view, which cannot be built without it.
- Shared filter/sort/group model serialized to the URL; saved views persisted.
- `VirtualList` — 400 opportunities will not render unvirtualized.
- Command palette, keyboard map, bulk actions, optimistic mutations, undo toasts.
- Design tokens from `DESIGN-SYSTEM.md`, including the three corrected contrast
  values; Radix primitives; real dialogs replacing `window.confirm`.
- Three new entry types with icons.

**Schema:** `saved_views`; `timeline_entries.type` CHECK extended.

**Depends on:** Phase 1 (router, query client, pagination).

**Acceptance:**
- Drag a card between stage columns; a system stage-change entry appears.
- A saved view survives reload and is shareable by URL.
- Every action in the keyboard map works without a mouse, board drag included.
- View switch < 150 ms with data cached; `axe` clean in CI.
- Timeline load stays within 400 ms at seeded scale.
- Light and dark themes both ship, and both pass `axe` contrast checks on every
  component delivered in this phase. `DESIGN-SYSTEM.md` commits to parity from
  the start because retrofitting a dark palette after the token system lands is
  the expensive path.

**Effort:** 8 sessions — the largest phase, and worth keeping large rather than
splitting the decomposition into an invisible phase of its own.
**Risk:** scope creep across five views. Mitigation: board and list are acceptance
criteria; table and calendar may slip to Phase 3 without blocking anything.

---

## Phase 3 — Rich Content and Live Collaboration

**Goal:** make the timeline worth writing in, and make two people on one deal see
each other.

**User-visible outcome:** a real editor with slash commands and @mention
autocomplete; threaded comments that resolve; a colleague's entry appearing within
two seconds without a refresh.

**Features:** Rich content (§4), Collaboration (§7).

**Technical work:**
- TipTap serializing to Markdown — no content migration, the payoff for storing
  Markdown from the start (ADR 0005 rationale, `FEATURES.md` §4).
- Mention autocomplete, fixing requirement 13's discoverability.
- Threaded comments, reactions, resolve/unresolve, watchers.
- SSE endpoint and client invalidation (ADR 0003); 409 edit guard on notes.
- PDF export renders Markdown — closes the other half of requirement 17.

**Schema:** `comments` gains `parent_id`, `resolved_at`; `reactions`; `watchers`.

**Depends on:** Phase 2 (component structure).

**Acceptance:**
- A bullet list can be typed in a note — impossible today, the composers are
  single-line inputs.
- @mention autocompletes and notifies.
- Two browsers: an entry created in one appears in the other in < 2 s.
- Concurrent note edits produce a 409 and a reload prompt, not a silent clobber.
- Exported PDF renders bold and lists rather than literal asterisks.

**Effort:** 6 sessions. **Risk:** editor sanitization regressions — the existing
`rehype-sanitize` allowlist must not be loosened for new node types; covered by
explicit XSS tests.

---

## Phase 4 — Tasks and Attachments

**Goal:** capture the two artifacts a deal actually produces — the next action and
the document.

**User-visible outcome:** "Call them back Thursday" becomes a task with a due date
that appears in My Tasks; proposals and contracts attach to the entry they belong to.

**Features:** Tasks (§8), Attachments (§6).

**Technical work:**
- Task model scoped to an opportunity; My Tasks across opportunities; overdue and
  upcoming surfaces on the dashboard.
- Migrate `timeline_entries.follow_up_date` into tasks, keeping the column until the
  UI has moved.
- Attachments: content-addressed storage, magic-byte validation, streamed authorized
  download, `Content-Disposition: attachment` and `nosniff` (ADR 0008).
- PDF export gains an attachment manifest.

**Schema:** `tasks`; `attachments`.

**Depends on:** Phase 2 (views to surface tasks in), Phase 3 (editor for inline
attachment).

**Acceptance:**
- A task created from an entry appears in My Tasks and on the dashboard when overdue.
- A viewer on a shared opportunity can download an attachment; a non-shared user
  gets 404 — and `/data` is never reachable as a static path.
- Upload rejects a `.exe` renamed to `.pdf` (magic-byte check).
- Existing `follow_up_date` values appear as tasks after migration.

**Effort:** 6 sessions. **Risk:** attachment access control. Mitigated by routing
downloads through the same `OpportunityContext` dependency as everything else, plus
the route-guard enumeration test from ADR 0010.

---

## Phase 5 — Email In and Out

**Goal:** the confirmed email requirement, isolated late so it lands on a stable
platform.

**User-visible outcome:** replying to a comment notification posts the reply as a
comment; forwarding a customer email to an opportunity address files it as an entry.

**Features:** Inbound and outbound email (§5), notification digests and preferences.

**Technical work:**
- APScheduler jobs and the durable outbox (ADR 0004).
- Outbound notification email with `Reply-To` set to the signed threaded address.
- IMAP polling ingestion behind a transport interface so a provider webhook is a
  later swap (ADR 0009).
- HMAC-signed reply addresses; sender-to-user matching; **the normal write check**,
  not a parallel authorization path; DKIM verification; `Message-ID` dedupe;
  per-sender rate limiting.
- Quoted-reply and signature stripping; HTML → Markdown; attachments via Phase 4.
- `source = 'email'` provenance shown in the UI and labelled in AI context (ADR 0012).
- Ingestion log including rejections — silent drops are unacceptable when a
  colleague believes they filed a note.
- Digest batching and per-user preferences.

**Schema:** `email_messages` (dedupe + ingestion log); `source` on entries, notes,
comments; `notification_preferences`.

**Depends on:** Phase 4 (attachments), Phase 1 (jobs, logging).

**Acceptance:**
- Reply to a notification → comment appears, marked as email-sourced.
- Spoofed `From:` for a non-user is rejected and logged, not posted.
- A valid sender **without** write access to the target is rejected.
- Replaying the same message twice creates one record.
- An adversarial email body containing instruction-shaped text does not change the
  AI's behaviour or make it claim it modified anything.

**Effort:** 8 sessions. **Risk:** highest in the plan — the first untrusted input
path into a shared record and into the AI context. Mitigations: transport interface,
strict sender rules reusing existing authorization, adversarial test suite, and the
hard read-only AI boundary confirmed in Q2.

---

## Phase 6 — Custom Fields, Dashboards, Automations

**Goal:** the configurability and reporting layer, once the shape of the data is
settled.

**User-visible outcome:** team-defined fields that appear as table columns and
filters; a pipeline dashboard; a rule that pings you when a deal goes quiet.

**Features:** Custom fields (§3), Dashboards (§10), Automations (§11), AI expansion
(§14, safe subset).

**Technical work:**
- Definition table + JSON value column + expression indexes (ADR 0006); fields flow
  into table columns, filters and the entry form.
- Six aggregations computed live — no rollup tables (`FEATURES.md` §10); index on
  `(created_by, created_at)` for activity-per-rep.
- Constrained rule builder: single-hop only, dry-runnable, every automated write
  producing a traceable system entry naming the rule.
- AI: streaming, date-scoped summaries, natural-language filter construction — the
  safest high-value AI feature, since its output is a query the user inspects
  before applying.

**Schema:** `custom_field_definitions`; `custom_values` JSON on opportunities and
entries; `automation_rules`, `automation_runs`.

**Depends on:** Phase 2 (table view and filter model).

**Acceptance:**
- A new select field appears as a table column, a filter, and on the entry form.
- Each dashboard aggregate returns inside 300 ms at seeded scale, asserted in CI.
- A no-activity-for-14-days rule fires once, creates a task, and logs a system entry
  naming the rule; it cannot trigger another rule.
- The AI still holds read-only under an injected-instruction test.

**Effort:** 7 sessions. **Risk:** automations growing into a workflow engine.
Mitigation: the single-hop, no-OR-tree constraints are acceptance criteria, not
guidelines.

---

## Deferred to v3

| Item | Why deferred |
|---|---|
| Templates and playbooks | Optimizes a process the team may not have standardized yet; lowest RICE at 1.0 |
| CSV import | Narrow reach (6/20), one-time value per user |
| AI draft emails, notes-to-entry parsing | Highest injection leverage; wait until email ingestion has run long enough to see what actually arrives |
| Attachment thumbnails, virus scanning | Volume and threat model do not justify them at 20 known internal users |
| Mobile-specific experience | Responsive degradation covers the one flow that matters (logging an entry) |
| Workspaces, teams, guests, share links | Declined on scale and risk grounds — ADR 0010 |

## Breaking changes and migration paths

| Change | Phase | Break | Migration |
|---|---|---|---|
| Pagination envelope + error shape | 1 | Response shapes | New surface at `/api/v2`; v1 retained until the frontend moves, then removed at the end of Phase 2 |
| Alembic replaces auto-init | 1 | Startup behaviour | Baseline-stamp an existing database; CI applies migrations to a restored snapshot every run |
| Notification model | 1 | Client field names | Additive columns; v1 shape preserved behind `/api/v1` |
| `follow_up_date` → tasks | 4 | Field moves | Backfill into `tasks`; column retained one phase, dropped in 5 |
| Entry `type` enum extension | 2 | CHECK constraint | Additive only; no existing value changes |
| Rich text | 3 | None | Storage stays Markdown — the deliberate payoff of the original choice |
| Note edit guard | 3 | `PATCH /api/v2/notes/{id}` requires `updated_at` | Required rather than optional: an optional guard is no guard, and the value is already on `NotePublic`, so a client echoes back what it read (ADR 0003) |
| Entry numbers | 3 | `TimelineEntryPublic` gains `sequence`; `AiAskResponse.referenced_entry_ids` becomes `referenced_entry_numbers` | The first is additive. The second is a rename because the field's contents changed meaning: the AI cites the number the timeline prints, and a field named `_ids` holding sequence numbers is a trap for the Phase 4 work that will want ids for links (D-139, D-140) |

## Total

**40 sessions across six phases.** Phases 1 and 2 are the ones that matter most: they
carry all four blockers from `REVIEW.md`, and every later phase assumes them. If the
plan is cut short, cutting from the back (6, then 5) leaves a coherent product;
cutting from the front does not.
