# AGENTS.md

## Project Name
OppTrail — a timeline note-taking app for tracking sales opportunities

**Status: MVP shipped and reviewed. This document now describes v2 scope.**
The v1 requirements are retained below as the shipped baseline. Planning documents
for v2 live in `docs/`: `REVIEW.md`, `FEATURES.md`, `ARCHITECTURE.md`, `adr/`,
`DESIGN-SYSTEM.md`, `UX.md`, `ROADMAP.md`, `OPEN-QUESTIONS.md`.

## Product Definition

OppTrail is a sales **opportunity tracker**. Not a project management tool, not a
CRM, not a document workspace. The unit of work is a single sales opportunity, and
the heart of the product is a chronological timeline of everything that happened on
it.

**The v2 goal is ClickUp-class interaction quality on deliberately boring
infrastructure** — multiple views over one dataset, rich content, live updates,
keyboard-first navigation. Depth of UX, not breadth of domain, and not scale
engineering.

## Confirmed Scale

20 users · 20 opportunities each (400 total) · ~200 entries per opportunity ·
2-3 concurrent. Roughly **800,000 rows in a ~136 MB database**, seeded and
benchmarked (`docs/ARCHITECTURE.md`).

This number is the single most important constraint in the project. It is why there
is no Postgres, no message broker, no job queue, no object storage service and no
multi-tenancy. Proposals that add infrastructure must argue against these measured
figures, not against a hypothetical future.

## v1 Requirements (shipped)

1. A user can sign in
2. Timeline tree per Opportunity: **Timeline Entries** → **Notes** → **Comments**
3. Notes can be added to any entry at any time
4. Comments can be made on any note
5. Read-only AI agent in a sidebar answering questions about a timeline
6. Opportunities shared with colleagues as Viewer or Editor
7. Full timeline exported to a formatted PDF
8. Opportunities dashboard grouped by stage
9. Opportunity record: name, account, value, currency, stage, owner, close date
10. Automatic system-generated entries for created / stage changed / sharing changed
11. Entry types with colour (icons land in v2 Phase 2)
12. Search and filter: keyword, entry type, date range, author
13. @mentions notify the mentioned colleague
14. In-app notification bell
15. Note edit history via a version table
16. "Stalled" flag after 14 days, plus a follow-up date on entries
17. Sanitized Markdown rich text (composers and PDF rendering complete in v2)
18. Full audit log per opportunity including deletions, visible to the Owner
19. CSV/JSON export alongside PDF

## v2 Scope

Specified in `docs/FEATURES.md`, sequenced in `docs/ROADMAP.md`:

1. **Views over one dataset** — timeline, board, list, table, calendar; saved
   views; the timeline orders oldest- or newest-first at the reader's choice
2. **Entry model** — more types, icons, type-specific fields
3. **Custom fields** — admin-defined, typed, on opportunities and entries
4. **Rich content** — TipTap editor, slash commands, @mention autocomplete
5. **Email in and out** — create entries, notes and comments by email; digests.
   **Deferred to v3** (**D-141**): the numbering is kept so every reference to a
   scope item by number stays true
6. **Attachments** — local, content-addressed, access-controlled
7. **Collaboration** — threaded comments, reactions, resolve, watchers, live updates
8. **Tasks and follow-ups** — scoped to an opportunity, not a task manager
9. **Notifications** — real inbox with history, preferences, batching
10. **Dashboards** — pipeline, win/loss, time in stage, stalled, activity, forecast
11. **Automations** — constrained single-hop rules
12. **Navigation and input** — command palette, keyboard throughout, bulk, undo;
    content is edited where it is read, not in a form elsewhere on the page
13. **Search** — FTS5, ranked, snippeted, cross-opportunity
14. **AI** — summarization, NL filter construction; read-only by construction;
    a failure says whether it is a misconfiguration or an outage
15. **Edit history** — every edit to user content keeps the previous value, with a
    screen the opportunity owner can read it from

## Design bar

Minimal and clean, in every UI decision — not as a finishing pass. The
reference point the product owner named is ClickUp: sleek, uncluttered,
nothing on screen that does not earn its place. Two consequences that have
already come up in review:

- Destructive controls do not sit permanently on screen. Put them behind a
  manage or edit affordance rather than beside every item.
- Every control says what it is. A row of unlabelled popovers is a
  comprehension failure, not a styling preference.

Passing the accessibility audit is the floor, not the goal: milestone 2.5
closed the contrast ratchet and the result was still judged crude.

## Non-goals

Would make this a **project management tool**: subtasks, dependencies, Gantt,
sprints, time tracking, or any container that is not an opportunity.

Would make this a **CRM**: contacts and accounts as first-class objects with their
own timelines, lead capture, campaigns, quotas, territories, email sequences.

Would make this a **document workspace**: wiki pages, standalone documents, nested
folders, whiteboards, real-time co-editing.

**Declined on scale or risk grounds** (see `docs/adr/0010`):
- Workspaces, teams, guest roles — 20 users in one organisation
- Public unauthenticated share links — the only proposed feature creating an
  unauthenticated path to customer sales data
- AI write access, even behind confirmation — see the invariant below
- Native mobile apps; SSO/SAML, SCIM, compliance certifications

## Invariants

These are load-bearing. Breaking one is a defect regardless of what else the change
achieves.

1. **Canonical timestamps.** Every timestamp is fixed-width UTC
   `%Y-%m-%dT%H:%M:%SZ` (`time_utils.py`). Timestamps are `TEXT` and all ordering
   and range filtering is lexicographic, so a mixed format silently reorders
   timelines and drops rows from filters. Never use `CURRENT_TIMESTAMP`.
2. **Authorization is structural, not conventional.** No endpoint touches an
   opportunity-scoped object except through the `OpportunityContext` dependency. A
   test enumerates routes and fails the build if one omits the guard.
3. **The AI has no write tools, ever.** Features that would change data return a
   proposal the human applies through the ordinary authenticated endpoint. The
   agent never appears as the actor in an audit row. This holds *by construction*,
   not by prompt instruction — which is the only kind of guarantee that survives
   injected content.
4. **Untrusted input is labelled everywhere.** Content arriving by email or
   attachment carries its `source` in the database, in the UI, and in the AI
   context.
5. **Soft deletes only.** Nothing is hard-deleted; `deleted_at` cascades the tree
   and every read filters it at each level.
6. **Every non-user-initiated write is traceable** to the action that caused it —
   system entries, audit rows, and automation-generated records naming their rule.
7. **Deletions are audited.** All four delete paths write an audit row.
8. **Edits are recoverable.** Every user-editable field keeps its previous value,
   attributed to who changed it and when, and the opportunity owner can read that
   history in the UI. Destroying a record is already traceable under 5 and 7;
   quietly rewriting one must be too. This covers opportunity fields (a deal
   value that changes with no record is the case that prompted this), timeline
   entries, and notes. Comments are exempt because they cannot be edited at all
   (see the Permissions Model) — immutability serves the same end by a different
   route.

## Technical Decisions

Reasoning in `docs/adr/`. Do not change these without an argued ADR.

- **Next.js + TypeScript**, static export — used as a **build tool**, not a server
  framework. No SSR, no server components. React Router + TanStack Query provide
  routing and server state (ADR 0005)
- **Python FastAPI**, also serving the static frontend from one origin
- **SQLite**, permanently at this scale, with WAL, FTS5 and JSON1 used deliberately
  (ADR 0001, 0006, 0007)
- **Alembic** for migrations; the auto-init mechanism is retired (ADR 0002)
- **SSE** for live updates; no presence, no co-editing (ADR 0003)
- **APScheduler** in-process; no broker (ADR 0004). Arrives with Phase 6's
  time-triggered automations, and gives `make backup` the schedule ADR 0011 has
  been waiting for. The durable outbox waits for v3 with the email work, since
  nothing in v2 sends anything (**D-141**)
- **TipTap** editor, storing **Markdown** — no content migration needed
- **Radix UI** headless primitives, styled with the design tokens
- **Local filesystem** for attachments, streamed through an authorized endpoint
  (ADR 0008)
- **IMAP polling** for inbound email behind a transport interface (ADR 0009) —
  **v3**, with scope item 5
- **OpenAI** for AI calls, via `OPENAI_API_KEY` / `OPENAI_MODEL`. Note the v2 brief
  said OpenRouter; the code and this document are authoritative (ADR 0012)
- **WeasyPrint** for PDF, rendered in-container
- **Single Docker container**, `uv` for Python packaging (ADR 0011)
- Start and stop scripts for Mac, PC, Linux in `scripts/`

## Permissions Model

- **Owner** — full control: opportunity, timeline, sharing, editing, deletion
- **Editor** — add entries, notes and comments freely; **edit and delete only
  their own** content
- **Viewer** — read-only, including the AI agent (may ask, may not write)
- **Editing and deleting** an entry, note or comment is limited to its author or
  the opportunity owner. The two rules are deliberately identical: an editor who
  may not remove a colleague's record may not rewrite it either
- Comments remain immutable to everyone once posted
- Absence of access returns **404, not 403**, so existence does not leak

## Quality Bar

- **CI must be green.** Backend suite, frontend typecheck and lint, `docker build`,
  and the backend suite inside the image — that last one is where WeasyPrint runs
- Backend integration coverage ≥ 90%; frontend unit coverage ≥ 70%
- Performance budgets in `docs/ARCHITECTURE.md` are asserted in CI against a seeded
  database at target scale
- **WCAG 2.2 AA**, enforced by `axe` in Playwright rather than a one-off audit
- Every fixed vulnerability keeps its regression test
- Assertions must never depend on the wall clock
- A guard test must be shown to fail against the unfixed code before it is trusted

## Color Scheme

Full token set in `docs/DESIGN-SYSTEM.md`. The brand colours are **safe as fills and
unsafe as text** — measured, with three in-use pairs currently failing WCAG AA. Use
the `-600` text variants for anything that carries type.

- Deep Navy `#0B2540` — headings, sidebar
- Accent Teal `#0F9D8C` fills / `#0B7C6E` text — timeline markers, links, primary
- Signal Amber `#F2A93B` fills / `#8A5A00` text — highlights, badges
- Slate Gray `#6B7280` — supporting text, timestamps
- Success Green `#2FA84F` fills / `#227A3A` text — Closed Won
- Alert Red `#D64545` fills / `#B33838` text — Closed Lost, overdue

## Coding standards

1. Use current versions of libraries and idiomatic approaches
2. Keep it simple — NEVER over-engineer, ALWAYS simplify, NO unnecessary defensive
   programming. No features beyond what is specified
3. Be concise. Keep the README minimal. IMPORTANT: no emojis ever
4. When hitting issues, identify the root cause before trying a fix. Do not guess.
   **Prove with evidence, then fix the root cause** — and when a measurement
   contradicts an earlier claim, correct the claim
5. Every non-user-initiated database write must be clearly traceable to the action
   that caused it
6. Deletes are soft deletes — nothing on a shared sales record silently disappears
7. The AI agent's tool surface is read-only by construction — never give it a
   write-capable tool, even behind a confirmation step
8. Every new dependency needs a justification. Prefer boring, proven technology
9. Cite file paths for claims about existing code

## Change Review Workflow

- After every file change, provide a concise diff summary in chat.
- With each phase summary, include user test steps for the current phase.
- Ask for an explicit decision: Review, Accept, or Reject.
- Do not commit or push changes until the user accepts them.
- If the user rejects a change, identify the issue, adjust the files, and provide a
  new concise diff summary.

## Working documentation
All planning and execution documents live in `docs/`. Review `docs/ROADMAP.md` for
what to build next and `docs/ARCHITECTURE.md` for the standards that apply to it.

## Autopilot (phase-gated)

When running under `docs/autopilot-brief.md`:
- Commits are permitted on `autopilot/phase-<ID>` branches only. Nothing is committed to `main` by the agent.
- The Review / Accept / Reject decision happens at the end of each phase, using the review packet in `docs/autopilot/reviews/`.
- Accept = the human runs `scripts/autopilot-gate.sh <ID>` (host-side Docker build and smoke test), then `scripts/autopilot-accept.sh <ID>` (fast-forwards `main`, tags `phase-<ID>-accepted`). Accept refuses without a gate receipt for that commit.
- Reject = the human runs `scripts/autopilot-reject.sh <ID> <feedback.md>`; the agent reworks on the same branch.
- The agent never merges, pushes, or creates acceptance tags.
- Autopilot runs inside the sandbox in `sandbox/` (`sandbox/run.sh`), which mounts only this repo. See `sandbox/README.md` for the boundary and its documented limits.