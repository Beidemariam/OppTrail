# OppTrail v2 — Feature Specification

Every feature states the user problem it solves in one sentence. Anything that
could not earn that sentence was cut, and the cuts are recorded in Non-goals.

Scale context (confirmed): 20 users, **20 opportunities each — 400 total**, ~200
entries per opportunity, 2-3 concurrent. Roughly 800,000 rows in a ~136 MB
database, benchmarked. Comfortably within what the current stack handles, so
**interaction quality is the entire product gap** — nothing here is justified by
load.

One consequence of the corrected figure: 400 opportunities is too many for an
unpaginated, unvirtualized board or table. Pagination and list virtualization move
from API hygiene to visible requirements.

Assumptions not yet confirmed are marked **[ASSUMPTION]** and mirrored in
`OPEN-QUESTIONS.md`.

---

## Priority tiers

| Tier | Meaning |
|------|---------|
| **P0** | v2 is not credible without it |
| **P1** | Core to the "ClickUp-class" goal |
| **P2** | Real value, deferrable within v2 |
| **P3** | Deferred to v3 |

RICE scoring is in `ROADMAP.md`; this document establishes what the things are.

---

## 1. Views over one dataset — P0

> *A rep planning their week cannot get an overview from a chronological log; the same opportunities need to be seen as a pipeline, a list, or a calendar.*

Five views over one dataset, sharing one filter/sort/group model:

- **Timeline** (default, signature) — the existing per-opportunity tree.
- **Board** — opportunities as cards in stage columns, drag to change stage. The
  drag writes through the existing `PATCH /opportunities/{id}`, which already
  auto-logs a stage-change entry.
- **List** — dense rows, grouped by stage/owner/close month, inline expand.
- **Table** — spreadsheet grid with inline editing and column selection; the
  natural home for custom fields.
- **Calendar** — expected close dates and follow-up dates.

**Saved views** are a named filter + sort + group + column set, personal or shared,
with one default per user. **[ASSUMPTION]** shared views are editable only by their
creator.

State lives in the URL (ADR 0005), which is what makes a view linkable at all.

**Depends on:** ADR 0005 (router, data layer), pagination.

## 2. Entry model — P0

> *A call and a proposal carry different facts, and forcing both into one title-and-body shape loses the detail that makes a timeline worth reading.*

Extend the existing eight types to: call, email, meeting, site visit, proposal sent,
quote revised, objection, competitor intel, stage change, internal note, task.

- **Universal fields** (all types): type, title, body, `event_timestamp`, author,
  attachments, follow-up date, participants.
- **Type-specific fields** are custom fields (§3) scoped to a type, not hardcoded
  columns — proposal gets amount and expiry, objection gets category and severity,
  competitor intel gets competitor name.
- **System-generated entries stay distinct**: `system_generated = 1`, not editable
  or deletable, visually marked. That property is already enforced and tested; v2
  extends it to automation-generated entries, which must be equally traceable to
  their cause (`AGENTS.md` standard 5).
- **Email-originated entries** carry `source = 'email'` and show provenance
  (ADR 0009).

Each type gets an icon — requirement 11 currently ships colour only.

## 3. Custom fields — P1

> *Every sales team tracks two or three things nobody anticipated, and without custom fields those live in the body text where nothing can filter on them.*

Admin-defined, typed, on opportunities and entries. Types: text, number, date,
select, multi-select, checkbox, user.

Storage is a definition table plus a JSON value column, with expression indexes
where a field is filtered often (ADR 0006). **Deliberately not a field builder with
formulas, rollups, or dependencies** — that is a spreadsheet product, and at 20
users it would be a maintenance burden nobody asked for.

Fields appear automatically in Table columns, filters, and the entry form.

## 4. Rich content — P1

> *A note recording a negotiation needs structure — bullets, a bolded number, a link to the proposal — and a single-line input cannot express any of it.*

Requirement 17 is currently half-delivered: rendering is correct and sanitized, but
composers are single-line `<input>` elements, so a bullet list cannot be typed at
all.

- **Editor: TipTap** (ProseMirror). Chosen over Lexical (smaller ecosystem, more
  churn) and Slate (more assembly required). TipTap has first-class slash commands,
  mentions and Markdown input rules, which is exactly this feature list.
- **Storage stays Markdown**, not ProseMirror JSON. Existing note bodies are already
  Markdown, so there is no migration; exports stay diffable; `note_versions` stays
  human-readable. TipTap serializes to Markdown on save.
- Slash commands, @mentions with autocomplete, checklists, inline attachments,
  links to other entries.
- Sanitization stays server-authoritative on render; the existing `rehype-sanitize`
  allowlist is correct and must not be loosened for the new node types.
- **PDF export must render Markdown**, closing the other half of requirement 17 —
  bold currently exports as literal asterisks.

**Migration path:** none needed. This is the payoff for storing Markdown from day
one.

## 5. Inbound and outbound email — P1

> *Half of a sales conversation already happens in email, and re-typing it into a timeline is work nobody does consistently.*

Confirmed in scope: **create entries, notes and comments by email** (ADR 0009).

- Each opportunity, entry and note has a signed reply address. Notification emails
  set `Reply-To`, so replying to a comment notification posts a comment — the
  interaction that makes this feel native.
- Sender must map to a known user who passes the normal write check. The signed
  address proves *which object*, never *who*.
- Quoted replies and signatures stripped; HTML converted to Markdown; attachments
  ingested through §6; deduplicated by `Message-ID`.
- Everything email-originated is visibly marked.
- Outbound: notification emails and digests (§9).

**This is the highest-risk feature in v2** — the first untrusted input path into a
shared record and into the AI's context. It needs the most adversarial tests in the
plan.

## 6. Attachments — P1

> *Proposals, quotes and contracts are the artifacts a deal actually turns on, and today they live in someone's inbox instead of on the timeline.*

Local filesystem, content-addressed, streamed through an authorized endpoint that
runs the same access check as everything else (ADR 0008). Size cap, extension
allowlist, magic-byte sniffing, never served as static files.

Attachments appear in PDF export as a listed manifest with filename, size and
uploader — **not** embedded, which would make exports unbounded. **[ASSUMPTION]**

No virus scanning in v2; accepted risk at 20 known internal users, recorded in the
ADR.

## 7. Collaboration — P1

> *Two colleagues working one deal currently cannot see each other's entries without pressing Refresh, so they duplicate work or miss it.*

- **Live updates via SSE** (ADR 0003) — an entry appears for the other viewer within
  ~2 s.
- **Threaded comments** with reactions and resolve/unresolve. Resolve is what keeps
  a long deal's discussion readable.
- **@mentions with autocomplete.** Today mentions require typing a full email
  address with no hint, which makes requirement 13 effectively undiscoverable.
- **Watchers** — follow an opportunity you are not shared on.
- **No presence, no live cursors, no co-editing.** At 2-3 concurrent users these are
  decoration, and co-editing is an explicit `AGENTS.md` non-goal. Conflicts use
  last-write-wins with a 409 edit guard; note history already makes edits
  recoverable.

## 8. Tasks and follow-ups — P1

> *"Call them back Thursday" is the most common output of a sales conversation and currently has nowhere to live except prose.*

Action items scoped to an opportunity: title, assignee, due date, done state,
optional link to the entry that prompted it. Surfaces: **My Tasks** (across
opportunities), overdue and upcoming on the dashboard, and a per-opportunity list.

Deliberately **not** a task manager — no subtasks, no dependencies, no time
tracking, no sprints. The moment those appear, this is a project management tool.

The existing `follow_up_date` on entries migrates into this model.

## 9. Notifications — P1

> *A colleague who mentions you today produces a notification you can only ever see once, because marking it read deletes it from view.*

The current implementation returns unread only (`routes_notifications.py:33`), so
there is no inbox — this is a rework, not an extension.

- **Inbox** with read/unread, history, filtering by type, mark-all-read.
- **Email digests** — immediate for mentions and direct assignment, batched hourly
  or daily otherwise. **[ASSUMPTION]** daily default.
- **Per-user preferences** per event type, per channel.
- **Batching** — "3 new comments on Acme Expansion", not three emails. This is the
  difference between a notification system people keep on and one they mute.
- Background delivery via the scheduler with a durable outbox (ADR 0004).

## 10. Dashboards and reporting — P2

> *A sales manager needs to know pipeline value, what is stuck, and what closed, without opening twenty opportunities one at a time.*

Six aggregations, chosen because each answers a question someone actually asks:

| Metric | Computation |
|--------|-------------|
| Pipeline by stage (count + value) | `GROUP BY stage` over non-deleted, non-closed |
| Win/loss rate | Closed Won ÷ (Closed Won + Closed Lost) over a period |
| Average time in stage | From stage-change system entries — already recorded |
| Stalled opportunities | Existing 14-day rule, as a list |
| Activity volume per rep | Entries/notes/comments grouped by author and week |
| Simple forecast | Σ (value × stage probability) with configurable probabilities |

At 400 opportunities and ~800,000 activity rows these remain single indexed
aggregate queries — computed live, **no rollup tables, no materialized views, no
warehouse.** The measured dashboard aggregate is 131 ms against a 300 ms budget.
"Activity volume per rep" is the one that scans the most rows and needs an index on
`(created_by, created_at)`; revisit only if a dashboard exceeds budget in CI.

Note "average time in stage" is only correct back to the point stage-change entries
began being recorded; earlier history is absent and should be labelled as such
rather than silently shown as zero.

## 11. Automations — P2

> *"If nothing has happened in two weeks, remind me" is a rule every rep keeps in their head and forgets under pressure.*

A constrained, legible rule builder — explicitly **not** a workflow engine.

- **Triggers:** stage changed, no activity for N days, field value changed,
  close date approaching, entry of type X created.
- **Conditions:** simple field comparisons, ANDed only. No OR trees, no nesting.
- **Actions:** create task, notify user, add a timeline entry, change stage.

Constraints that keep it legible: rules are per-opportunity-template or global,
capped in number, always dry-runnable, and **every automated write produces a
traceable system entry naming the rule** (`AGENTS.md` standard 5). No rule may
trigger another rule — one hop only, which removes loop detection from the design
entirely.

## 12. Navigation and input — P1

> *Speed is the reason people prefer one tool over another for work they do fifty times a day.*

Treated as a feature, not polish, per the brief.

- **Command palette** (⌘K): jump to opportunity, switch view, run an action, search.
- **Keyboard shortcuts** throughout, with a discoverable `?` map.
- **Bulk actions** — multi-select in list/table, bulk stage change or assign.
- **Drag and drop** — board columns, entry reordering within a day.
- **Optimistic updates** everywhere, with rollback on failure (TanStack Query).
- **Undo** via a toast for destructive actions. Soft deletes mean undo is a real
  `deleted_at = NULL`, not a re-create — this is the payoff for the existing design.

Undo also resolves a UX debt: destructive actions currently use `window.confirm`,
which is a modal interruption where an undo toast would be both safer and faster.

## 13. Search — P1

> *Finding "that objection about procurement" currently means scrolling, because search is unranked substring matching within a single opportunity.*

FTS5-backed (ADR 0007): ranked, snippeted, cross-opportunity, filterable by type,
author and date. Reachable from the command palette.

## 14. AI agent — P2

> *A rep returning to a deal after three weeks needs the state of play in a paragraph, not 40 entries.*

Extends the existing agent, **preserving read-only-by-construction** (ADR 0012):

- Timeline summarization (exists; add streaming and date-range scoping).
- Next-best-action suggestions — advisory text, never an action.
- Draft follow-up email — opens in a composer; never auto-sent.
- Unstructured notes → structured entry — returns a **draft** rendered in the normal
  create form; nothing persists until a human submits it.
- Weekly digest per user.
- Natural-language filter construction — "deals stuck in negotiation over 50k"
  produces a filter the user sees and applies. This is the safest high-value AI
  feature here, because its output is a query the user can inspect.

Every one of these is a proposal a human applies. The agent never appears as the
actor in an audit row.

## 15. Import/export — P2

> *A team arriving from a spreadsheet needs a way in, and a team worried about lock-in needs a way out.*

- **CSV import** for opportunities: upload, map columns, preview, validate, commit.
  Dry-run mandatory. **[ASSUMPTION]** opportunities only, not timeline history.
- **Export**: PDF, CSV, JSON already exist and work. PDF gains Markdown rendering
  and an attachment manifest.

## 16. Templates and playbooks — P3

> *Teams that run a repeatable sales process re-type the same checklist on every deal.*

Per-stage checklists, standard entry templates, opportunity templates. Genuinely
useful, and the least urgent thing here — it optimizes a process the team may not
have standardized yet. Deferred to v3 unless it displaces something in §10-11.

---

## Non-goals

Each exclusion is defended, because this list is what protects the product.

**Would make it a project management tool**
- *Subtasks, dependencies, Gantt charts, sprints, time tracking, workload views.*
  Tasks here exist to serve a sales conversation. The moment they gain structure of
  their own, the unit of work stops being the opportunity and the product loses its
  centre.
- *Generic projects or lists not attached to an opportunity.* The opportunity is the
  only container.

**Would make it a CRM**
- *Contact and account management as first-class objects with their own timelines.*
  This is the most tempting adjacent feature and the most dangerous: it doubles the
  data model, and competing with Salesforce on completeness is unwinnable. Accounts
  stay a text field on the opportunity.
- *Lead capture, web forms, campaign attribution, quota and territory management.*
- *Email sequences and mail merge.* Outbound here is notification and human-sent
  follow-up, never bulk sending — which is also what keeps this off spam blocklists.

**Would make it a document workspace**
- *Wiki pages, standalone documents, nested folders.* Rich text belongs inside
  entries, notes and comments. A document tree is a second, competing hierarchy.
- *Whiteboards, mind maps, real-time co-editing.*

**Declined on scale or risk grounds** (departures from the brief — see ADR 0010)
- *Workspaces and teams.* 20 users in one organisation. A hierarchy whose every
  row count is 1 costs a join on every query and a concept on every screen for no
  perceivable benefit. Add it before a second organisation exists, not now.
- *Guest access as a distinct role.* Already expressible: invite them as `viewer`.
- *Public unauthenticated share links.* An explicit `AGENTS.md` non-goal, and the
  only proposed feature that creates an unauthenticated path to customer sales data
  — the same exposure class as the traversal bug fixed in `main.py`. If a
  customer-facing timeline is ever wanted it needs its own scoped, expiring,
  revocable token design.
- *AI write access, even behind confirmation.* Kept read-only by construction
  (ADR 0012). Inbound email makes the injection surface materially worse in v2, and
  a structural guarantee is the only kind that survives injected content.
- *Mobile native apps.* **[ASSUMPTION]** responsive web only.
- *SSO/SAML, SCIM, audit export, compliance certifications.* Enterprise procurement
  features with no buyer at this size.
