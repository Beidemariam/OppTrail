# Changelog

What shipped, by phase. Each phase was reviewed and accepted before the next
began; the tag is the accepted commit. The detail behind any line is in
`docs/autopilot/PROGRESS.md`, and the reasoning in `docs/autopilot/DECISIONS.md`
or `docs/adr/`.

Dates are the acceptance dates. Versions are phases rather than semver: this is
one deployment, not a published package.

## Phase R — release readiness · `phase-R-accepted` · 2026-10-21

Hardening, with no new product surface except the two shapes of privacy the
human asked for mid-phase.

- **R.1 — the layout pass.** A deal is its own page rather than a panel
  appended under the board (its first pixel was at y 888 on a 900px screen);
  the record is a pinned band and the AI is a drawer that narrows the timeline
  and never the rail; the board's eight filter controls are a disclosure with
  removable chips; and all six screens sit in one shell with a collapsible rail
  of destinations, which is how Reports finally became reachable from
  Automations. Chosen by the human from four drawn options.
- **R.1b — keeping something to yourself.** A **private entry**, readable by
  its author alone and not by the deal's owner either; sealing one afterwards
  withdraws the notifications it already sent. And **a notebook per person per
  deal**, outside the deal's history entirely. New entries are private by
  default. R.1b shipped the sealed entry *standing in everybody's timeline*
  emptied of everything but its number and author; **R.1c reversed that** at
  the human's request, so the R.1c entry below is what the app does.
- **R.2 — accessibility.** The audit had been asking axe for WCAG 2.1 since
  Phase F while the stated bar was 2.2; it asks for 2.2 now, six screens that
  had no audit entry are in it, and 2.4.11 turned out to be a real failure —
  15 controls on one deal page took keyboard focus while hidden under the
  sticky bands. Plus a skip link, and focus that follows a navigation.
- **R.3 — performance.** Measured against 805,220 rows. One read was slow and
  not the one the plan expected: the board's page cost 63 ms, of which 60 was
  the 14-day stalled rule walking 240,000 note and comment rows. It is a
  column maintained by triggers now; the page is 2.5 ms and the whole board 19.
- **R.4 — the container.** ADR 0011's `HEALTHCHECK` and restart policy, which
  three documents had described as existing and nothing had implemented;
  `/healthz` and `/readyz` beside `/api/health`; a bound on graceful shutdown,
  because an open live-update stream was turning every `docker stop` into a
  kill; and a connection leak the new probe found within minutes.
- **R.5 — data safety.** Backups now include the uploads, which is the half of
  ADR 0011 item 2 nothing had built: one content-addressed mirror rather than a
  copy per snapshot, and a restore that puts back what the volume is missing.
  `docs/operations.md` is the documented layout.
- **R.6 — CI.** `make check` in GitHub Actions with coverage and Playwright
  artifacts. `npm audit` is a ratchet now rather than a wall, because the one
  advisory this tree carried had no fix published anywhere — an entry that
  the ratchet itself later removed when the advisory was withdrawn upstream
  (D-223).
- **R.7 — seed data.** Phase 6 and R.1b had never been seeded; they are now,
  including the private entry the seed's own docstring had claimed for two
  milestones. `make seed-scale` layers the confirmed scale on top of the demo
  data using the same corpus the performance budgets are measured against.
- **R.8 — documentation.** This file, `docs/user-guide.md`, `docs/api.md`, the
  ADR index, and `docs/ARCHITECTURE.md`'s data model, authorization, real-time
  and AI sections.
- **R.1c — the shakedown's corrections, and what reviewing the phase found.**
  A sealed entry is **absent** from a colleague's timeline rather than standing
  there emptied — *"better not to mention anything instead of saying it is kept
  private"* — with the numbering counted per reader so no gap is left where it
  was; the activity log stopped announcing one to the deal's owner; the 14-day
  rule lost a fourth copy hiding in the one feature named after it. Defining a
  custom field and writing an automation rule are an **administrator's** now.
  `make backup` and `make restore` name the deployment's database, after the
  documented restore turned out to overwrite a scratch file beside the code and
  report success. One button size, measured rather than read. A follow-up date
  that creates the task by default. The sign-in screen opens on sign-in.

### After acceptance

Maintenance on `main`, no new product surface. The backup got a schedule
outside the application — a `launchd` LaunchAgent, because cron skips a job it
sleeps through and would have reproduced the defect it was installed to fix
(D-221). Playwright 1.64 and the races it resampled; the derived sticky
padding, which was short at every width and 66px short at 1024 (D-219); the
report bars wrap rather than overflow; the performance budgets scale to the
hardware. Three rounds of dependency advisories, all with fixes available and
all taken (D-220, D-223).

## Phase 6 — the v2 feature set · `phase-6-accepted` · 2026-10-13

- **Custom fields** (ADR 0006): admin-defined fields on opportunities and
  entries, validated on write and never trusted on read, so a field can be
  archived without rewriting a single value.
- **Six reports**, computed live with no rollup tables, each inside a 300 ms
  budget asserted against an 800,000-row corpus — a budget that immediately
  found three of the six too slow and rewrote them.
- **Automations**: a constrained builder (one trigger, flat ANDed conditions,
  one action) that cannot express a rule that branches, always dry-runnable,
  acting with its creator's authority, and structurally incapable of
  triggering another rule.
- **The AI expansion**: streamed answers, date-scoped summaries that say so,
  and a sentence turned into an inspectable board filter.
- **The scheduler** (ADR 0004): APScheduler in-process, the two time-driven
  triggers and the backup that had had no schedule since Phase 1, with every
  run recorded so a dead scheduler is visible rather than silent.

## Phase 4 — collaboration · `phase-4-accepted` · 2026-10-09

Tasks with multiple assignees and their own discussion; attachments (ADR 0008)
with sniffed content types and content-addressed storage; the export carrying
the files it cannot embed; a search result landing on the thing it matched; and
the AI context labelling every piece of user text as untrusted.

## Phase 3 — the writing surface · `phase-3-accepted` · 2026-09-29

One TipTap composer storing Markdown everywhere content is written, with `@`,
`/` and `#` triggers; threaded comments with reactions and watchers; live
updates over SSE (ADR 0003) carrying invalidations and never payloads, with a
409 guard on concurrent note edits; one activity log joining the three
mechanisms that record what happened; and editing content where it is read.

## Phase 2 — the board · `phase-2-accepted` · 2026-09-23

Four renderers over one dataset (board, list, table, calendar); linkable view
state and saved views; a design token system with light and dark palettes, both
measured against WCAG AA in the unit suite; the keyboard map and command
palette; bulk actions; optimistic writes with Undo instead of confirmations;
and the v2 API boundary — keyset pagination and one error envelope — with v1
removed.

## Phase 1 — foundations · `phase-1-accepted` · 2026-09-20

Alembic migrations (ADR 0002); the request security trio (CSRF double-submit,
security headers, cookie flags); structured logging with request ids; the
notification inbox; full-text search over FTS5 (ADR 0007); health reporting
substance rather than liveness; backups with an exercised restore; and CI.

## Phase F — foundations audit · `phase-F-accepted` · 2026-09-16

Reconnaissance of the accepted MVP against its own requirements: one
authorization boundary (ADR 0010), the canonical timestamp format, soft deletes
everywhere with an audit row per deletion, and the editor-may-not-rewrite-a-
colleague's-item rule the human overruled in favour of the stricter reading.

## The MVP · before this plan

Opportunities, timelines, notes, comments, sharing, the AI sidebar, and the
single-container deployment — accepted, then audited by Phase F.
