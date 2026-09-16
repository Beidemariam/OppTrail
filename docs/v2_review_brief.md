# OppTrail v2 — comprehensive review and roadmap to a ClickUp-class product

You are acting as a principal engineer and product architect joining the OppTrail project. Your job in this session is **review and planning only — do not write feature code.** The single deliverable is a set of planning documents good enough that a competent team (or you, in later sessions) could execute from them without re-deciding anything important.

## Context

OppTrail is a sales **opportunity tracker**. Not a project management tool, not a full CRM. The unit of work is a single sales opportunity, and the heart of the product is a chronological timeline of everything that happened on that opportunity: calls, emails, meetings, site visits, proposals sent, objections raised, stage changes. Entries carry notes, comments, attachments, and typed metadata. Colleagues collaborate on the same opportunity with viewer/editor permissions. There is a read-only AI agent that answers questions about a timeline, and will export in PDF, CSV, and JSON.

Current stack (do not change without an explicit, argued ADR):
- Next.js + TypeScript, App Router
- Python FastAPI backend, also serving the static frontend
- SQLite, auto-created on startup
- Session auth: bcrypt + HttpOnly cookies
- OpenAI (`OPENAI_API_KEY` / `OPENAI_MODEL`) for the AI agent
- WeasyPrint for server-side PDF
- Single Docker container, `uv` for Python packaging

**The goal for v2:** keep the domain narrow (opportunity tracking only) but raise the product surface and interaction quality to the level of ClickUp — multiple views over the same data, custom fields, saved filtered views, rich text, real-time collaboration, notifications, automations, dashboards, keyboard-first navigation. Depth of UX, not breadth of domain.

## Phase 1 — Read and inventory

Before proposing anything, actually read the repository. Do not rely on `AGENTS.md` and `PLAN.md` alone; they describe intent, and intent drifts from code.

1. Read `AGENTS.md` and `PLAN.md` in full.
2. Walk the codebase: routing structure, component tree, API surface, database schema and migration story, auth flow, AI agent implementation, PDF pipeline, Docker build, tests, CI.
3. Produce an inventory table of every feature in the MVP scope with a status of **implemented / partial / stubbed / absent**, each row citing the specific files that justify the verdict.
4. Note every place where the code diverges from what the planning docs claim.

Then assess quality honestly, with file-and-line evidence:
- Data model: normalization, indexing, soft-delete handling, timestamp semantics, N+1 query risks
- API design: consistency, pagination, error shapes, validation, authorization checks at every endpoint (look specifically for object-level authz gaps — the sharing model makes these likely)
- Frontend: state management, server/client component boundaries, data fetching and caching strategy, loading and error states, accessibility, re-render hot spots
- Security: session handling, CSRF posture, file upload validation, prompt injection surface in the AI agent, tenant isolation
- Operations: migrations, backups, logging, config management, container startup, what happens on the second deploy

Rank the findings as **blockers / high / medium / low**. Be blunt. If something needs to be torn out before the codebase can carry a bigger product, say so plainly and explain the cost of leaving it.

## Phase 2 — Feature design

Translate ClickUp's interaction model onto opportunity tracking. For every feature you propose, state the user problem it solves in one sentence. If you cannot, drop it.

Cover at minimum:

**Views over one dataset.** Timeline (the default and signature view), List, Board grouped by stage, Table with inline editing, Calendar. Per-view grouping, filtering, sorting, column/field selection. Saved views, personal and shared. A default view per user.

**Entry model.** Typed entries (call, email, meeting, site visit, proposal sent, quote revised, objection, competitor intel, stage change, internal note, task) with icons and colors. Which fields are type-specific and which are universal. How system-generated entries (stage changes, sharing changes) differ from user-authored ones.

**Custom fields.** On opportunities and on entries. Types, validation, per-workspace definitions, effect on views and filters, storage strategy (EAV vs JSON column vs hybrid) with a recommendation and its query-performance consequences.

**Rich content.** Rich text editor with slash commands, @mentions, inline attachments, checklists, links to other entries. Pick a concrete editor library and justify it. Define the storage format and the migration path from existing plain-text notes.

**Attachments.** Storage backend, size and type limits, virus/type validation, thumbnails, access control that respects opportunity sharing, and how they appear in PDF export.

**Collaboration.** Threaded comments, reactions, resolve/unresolve, @mentions, watchers, real-time presence and live updates. Specify the transport (WebSocket vs SSE vs polling) and the conflict model for concurrent edits.

**Tasks and follow-ups.** Action items with assignee, due date, reminder, and completion — scoped to an opportunity, not a general task manager. Overdue and upcoming surfaces.

**Notifications.** In-app inbox, email digests, per-user preferences, batching rules to avoid noise. Name the background job mechanism.

**Permissions.** Workspace → team → opportunity. Roles, guest access, public read-only share links with expiry. Define the authorization check that every endpoint must pass through.

**Automations.** Rule builder: trigger (stage change, no activity for N days, field value) → action (create task, notify, add entry, change stage). Keep it constrained and legible; do not build a general workflow engine.

**Templates and playbooks.** Per-stage checklists, standard entry templates, opportunity templates.

**Dashboards and reporting.** Pipeline by stage and value, win/loss rate, average time in stage, stalled opportunities, activity volume per rep, simple forecast. Define exactly which aggregations are needed and how they are computed efficiently.

**AI.** Extend the existing agent: timeline summarization, next-best-action suggestions, draft follow-up emails, unstructured-notes-to-structured-entry parsing, weekly digests, natural-language filter construction. **Preserve the read-only-by-construction constraint** — if any feature would require write access, propose an explicit human-confirmation step rather than granting the agent write tools. Address prompt injection from attachment and email content.

**Navigation and input.** Command palette, keyboard shortcuts throughout, bulk actions, drag-and-drop, optimistic updates, undo. This is a large part of why ClickUp feels the way it does — treat it as a feature, not polish.

**Import/export.** CSV import, CSV/JSON export alongside the existing PDF.

Then write an explicit **non-goals** list. Anything that would make this a project management tool, a full CRM, a marketing automation platform, or a document workspace. Be specific and defend each exclusion — this list is what protects the product's focus.

## Phase 3 — Architecture decisions

Write short ADRs for each of these, giving options, a recommendation, and the reasoning:

1. SQLite vs Postgres. Say what forces the change and at what point. Include the migration path.
2. Migration tooling (Alembic or equivalent) — non-negotiable at this scale; specify how to adopt it against an existing auto-created schema.
3. Real-time transport.
4. Background jobs and scheduling.
5. Frontend data layer — server components vs a client cache, and the mutation/invalidation pattern.
6. Custom field storage.
7. Full-text search.
8. File storage.
9. Multi-tenancy boundary and how isolation is enforced in one place rather than per-endpoint.
10. Whether the single-container deployment survives v2, and what replaces it if not.

Also define: testing strategy across the pyramid, CI pipeline, observability, performance budgets (name concrete numbers — timeline load with 500 entries, view switch latency), and an accessibility target.

## Phase 4 — Design system and UX spec

Define the information architecture: navigation shell, the opportunity detail layout, how views switch, where filters and saved views live. Specify the design system — the existing palette is deep navy, accent teal, signal amber, slate gray, success green, alert red; extend it into a proper token set covering spacing, typography scale, elevation, radii, motion, density modes, and dark mode. Specify the core component inventory. Describe empty, loading, error, and permission-denied states as first-class designs. ClickUp-level information density is the target: dense but not cramped, and legible at a glance.

## Phase 5 — Roadmap

Produce a phased plan where **every phase ends in something shippable and demoable**. No phase may be pure refactoring with no user-visible outcome; fold structural work into the phase that needs it.

For each phase: goal, user-visible outcome, features included, technical work, schema changes, dependencies on prior phases, testable acceptance criteria, rough effort, and the risks with mitigations.

Sequence by dependency and by risk — the things most likely to force a rewrite go earliest. Prioritize the backlog explicitly (RICE or similar) and show the scoring. Mark clearly which items are v2 scope and which are deferred to v3. Call out every breaking change and its migration path.

## Deliverables

Write these files to the repo:

- `docs/REVIEW.md` — Phase 1 inventory, quality assessment, ranked findings
- `docs/FEATURES.md` — Phase 2 feature specs, prioritized, with non-goals
- `docs/ARCHITECTURE.md` + `docs/adr/NNNN-*.md` — Phase 3
- `docs/DESIGN-SYSTEM.md` and `docs/UX.md` — Phase 4
- `docs/ROADMAP.md` — Phase 5
- Updated `AGENTS.md` reflecting the v2 scope, conventions, and constraints
- `docs/OPEN-QUESTIONS.md` — anything you could not resolve and what information would resolve it

## How to work

- **Ask me clarifying questions before you start.** Batch them — no more than eight, ordered by how much the answer changes the plan. Cover at least: expected users and opportunities per workspace, deployment target and ops appetite, whether email/calendar integration is in scope, whether mobile is in scope, and the realistic timeline and team size. Wait for my answers.
- Where you make an assumption, mark it **[ASSUMPTION]** inline so I can correct it.
- Recommend, don't enumerate. Give options where the choice is genuinely contested, then pick one and say why.
- Cite file paths for every claim about the existing code.
- Prefer boring, proven technology. Every new dependency needs a justification.
- Optimize for a small team shipping continuously, not for a big-bang rewrite.
- If any part of my framing is wrong — a feature that doesn't belong, a sequencing mistake, a stack choice that won't hold — say so directly rather than planning around it.

Start with Phase 1 and your clarifying questions.