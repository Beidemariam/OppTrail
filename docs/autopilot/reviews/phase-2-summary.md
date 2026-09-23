# Phase 2 review packet — Pipeline Views and Keyboard Navigation

Branch: `autopilot/phase-2`, at commit `77f4aba`. Depends on the
`phase-1-accepted` tag (present). This packet puts the phase into
`AWAITING_REVIEW`.

Read time budget: 20-30 minutes (brief §3.5).

---

## 1. What changed

Phase 2's stated goal (`docs/ROADMAP.md`): the signature v2 capability — one
dataset, five views — and the frontend structure that makes it possible.
User-visible outcome: a pipeline board where dragging a card changes the
stage and auto-logs it; list, table and calendar over the same filters;
saved views in the sidebar; ⌘K to jump anywhere. All fourteen milestones
(2.1-2.13, plus the 2.9a fix the 2.8 review produced) are done.
Milestone-by-milestone detail and diffs are in `docs/autopilot/PROGRESS.md`;
this is the plain-language summary.

- **2.1 Decompose `Home.tsx`** (Blocker B1, D-038/D-039) — the 1,863-line,
  28-`useState` file is gone, replaced by twelve components under 200 lines
  each, all reads and writes moved onto `lib/queries.ts`'s TanStack Query
  cache. The opportunity and its timeline gained their own URL
  (`/opportunities/:id`, D-054), and search results link into it, closing
  the gap Phase 1 left open (D-039).
- **2.2 URL-serialized filter/sort state, saved views** — `OpportunityViewState`
  and `TimelineFilters` both live in the URL, namespaced per entity
  (`opportunities.*`, `timeline.*`, D-059) so a reload, the back button and a
  shared link all agree. New `saved_views` table and `routes_saved_views.py`:
  personal or shared, creator-only write, at most one default per user per
  entity (a partial unique index). Timeline reading order (oldest/newest
  first) landed here too, raised by the human during the Phase 1 user test
  (D-051).
- **2.3 `VirtualList`** — a generic windowed-rendering wrapper over
  `@tanstack/react-virtual`; the board's stage columns render through it
  instead of mapping every filtered card into the DOM, so a 400-opportunity
  stage still renders under 50 DOM nodes.
- **2.4a Command palette and keyboard map** — one declaration
  (`lib/keyboard.ts`'s `shortcutGroups`) drives both the `?` reference screen
  and the `Chord` type views bind against, so an undocumented-but-bound or
  documented-but-unbound key is a type error (D-065).
- **2.4b Optimistic mutations and undo toasts** — `soft_delete.py` gained its
  missing inverse (`restore_*`, four new `POST .../restore` routes) so undo
  is a real `deleted_at = NULL`, not a re-create. Deletes and the note edit
  apply optimistically and roll back with a toast on failure.
- **2.4c Bulk actions** — multi-select (`x`, shift-click, checkbox), an
  action bar, and `POST /api/v2/opportunities/bulk` (`delete` / `set_stage`,
  per-item results). Three of `docs/UX.md`'s five listed bulk actions
  (assign owner, add to view, export) were not built — they have no
  single-item capability to reuse yet (D-070, open — see §3).
- **2.5 Design tokens, Radix dialogs, light/dark themes** (D-003, accepted) —
  `app/globals.css`'s token set from `docs/DESIGN-SYSTEM.md`, including the
  three corrected contrast values; `window.confirm` replaced by
  `app/ConfirmDialog.tsx`; the theme is a resolved `data-theme` attribute
  (D-074), not a bare media query, with a System/Light/Dark control.
- **2.6 Three new entry types with icons** — `site_visit`, `objection`,
  `competitor_intel`, plus hand-drawn SVG icons on all eleven entry types
  rather than only the three new ones, closing a `DESIGN-SYSTEM.md`
  accessibility rule ("never colour alone") the roadmap sentence didn't
  literally ask for (D-078, open — see §3). First table-rebuild migration in
  this codebase, since SQLite has no `ALTER TABLE ... ADD CHECK`.
- **2.7 Board drag, list view, dashboard layout** — native HTML5 drag and
  drop (no new dependency, D-080) writes the same partial `PATCH` the
  keyboard `[`/`]` and the `MoveToStage` select do; only an owner's card is
  draggable. The create/edit form moved into a dialog (D-079) per reviewer
  feedback on the milestone-2.7 checkpoint.
- **2.13 Saved-view sharing rework** (D-060 → D-076, human-ruled) — an
  explicit private/shared choice at save time, in the ClickUp pattern the
  human named, replacing the installation-wide-by-default visibility that
  confused the milestone-2.5 reviewer. Also from that review round
  (D-082, confirmed): view management moved off the always-visible delete
  control into `ManageSavedViews.tsx`, and the filter/sort popovers gained
  visible labels.
- **2.8 Table and calendar views** — did not slip, despite the roadmap's own
  risk note allowing it to. Table (`OpportunityTable.tsx`) is a styled grid
  of `article` rows through `VirtualList`, not a real `<table>` (D-090, open
  — see §3), with its own column picker and density mode (Comfortable/Compact,
  D-075 → D-089). Calendar places `expected_close_date` only, not
  `timeline_entries.follow_up_date` (D-088, open — see §3, Phase 4 builds the
  cross-opportunity read that would serve the second layer).
- **2.9a Reset view state on sign-out** (D-091, from the 2.8 review) —
  `useLogout` now navigates to a clean URL; one user's `?opportunities.view=`
  parameters no longer render the next signed-in user's first screen through
  them.
- **2.9 Finish the `/api/v2` migration, remove v1** (D-033, ruled) — the
  remaining ~24 endpoints (auth, opportunity/timeline/note/comment writes,
  shares, exports, AI ask) moved under `/api/v2` with their v1 duplicates
  deleted rather than renamed. `GET /api/health` stays unversioned on purpose
  (D-094). The client-side board filter/sort stayed in the client rather than
  moving into SQL (D-093, open — see §3): `fetchAll` walks the new endpoint's
  pagination to the same whole list v1 returned.
- **2.10 Edit history for every editable thing** (`AGENTS.md` invariant 8,
  D-050) — `opportunity_versions` and `timeline_entry_versions` join the
  existing `note_versions`, one `versioning.py` writer, a version-1 baseline
  backfilled for existing rows (D-097, open — see §3). The read is
  owner-only (D-096, open — see §3), which tightens the one route
  (note versions) that had shipped open to every role.
- **2.11 Edit content where it is read** (`AGENTS.md` v2 scope item 12,
  D-051) — frontend-only, since 2.10 already made every write a partial
  `PATCH` that keeps a version. `app/InlineEdit.tsx`'s two shapes
  (`useInlineEditor` for entries/notes, `InlineEdit` for single fields) cover
  the opportunity heading and the table's account/value/close-date cells —
  deliberately not the board card or the calendar chip (D-099).
- **2.12 Fold the manual test's deterministic half into E2E** (D-053) — six
  checks from the Phase 1 hand-run user test that have a fixed right answer
  (cookie flags, timeline ordering, the UI permission matrix, search
  scoping, notification history/mark-all-read, audit-log completeness, and
  the sanitizer's browser-level guarantee) are now Playwright specs; four
  judgment-only checks (timezone display, markdown readability, a PDF a
  person would send, whether an AI answer is grounded) stay manual, listed
  in §2 below.

---

## 2. How to try it

Everything below runs from a clean checkout of this branch.

```bash
git checkout autopilot/phase-2

cd backend && uv sync
cd ../frontend && npm ci
cd ..

make seed          # prints the seeded users and what each can see
make check-fast    # inner loop: lint, types, unit/integration tests
make check          # full gate: adds pip-audit, npm audit, E2E; prints the
                    # Docker deferral note (see §4)
```

Seeded users (password printed by `make seed`): **Alex** owns four
opportunities and views a fifth (Initech); **Blair** edits Northwind and
owns Initech; **Casey** views Northwind and Globex only (every write
refused); **Dana** has access to nothing.

Click paths for this phase's new capabilities:

- **Board drag** — sign in as Alex, open the board, drag an owned card to
  another stage column; a "Stage changed to ..." system entry appears on its
  timeline. Try the same drag on a card Alex does not own (none exist for
  Alex, but Casey's board shows none draggable) — no drag handle offered.
  Keyboard equivalent: focus a card with `j`/`k`, press `[`/`]`.
- **List, table, calendar views** — the view switcher beside the page header;
  `?opportunities.view=table` (or `calendar`, `list`) in the address bar
  confirms the choice is linkable. In table view, edit the Value cell inline
  and reload — the change persists (not just the optimistic cache). Switch
  the density control (Comfortable/Compact) while the table is on screen.
- **Saved views** — as Alex, filter the board (e.g. by stage), save the view,
  choose "just for me" or "for everyone" in the dialog. Sign in as Casey:
  Alex's private view is absent from the menu; a shared one is visible by
  name but, when applied, still shows only what Casey can read (the
  permission-filtering behaviour D-076 clarified rather than changed).
  `ManageSavedViews.tsx` (gear icon in the menu) is where a view is renamed,
  re-shared or deleted.
- **Command palette** — `Ctrl K` (or `⌘K`) from anywhere, including inside a
  text field; `?` opens the shortcut reference. Try `j`/`k` to move the
  keyboard cursor without opening a card, `e` to edit the cursor's item,
  `x` then shift-click to select a range on the board.
- **Undo** — delete a timeline entry; the toast offers Undo for 10 seconds.
  Let it lapse, then check the opportunity's owner-only audit log
  (`timeline_entry_deleted`) — Umbrella Discovery in the seed data already
  has one undone deletion (`timeline_entry_deleted` next to
  `timeline_entry_restored`, the Qualification call entry back on the
  timeline) to look at without performing one yourself.
- **Edit history** — as the owner of an opportunity, open History (the icon
  beside History exports) on the opportunity itself, on a timeline entry, or
  on a note that has been edited. Version 1 renders as the whole starting
  state; later versions show only what moved.
- **Edit in place** — as an owner or an editor, click the opportunity's own
  name/account/value/close-date, or a timeline entry/note body; the field
  swaps for its editor without moving the reader's scroll position, and
  focus returns to the control that opened it on close.
- **Light/dark/system theme** — the control in the top bar; both palettes
  pass the same contrast audit (`lib/contrast.test.ts`, and axe in the E2E
  suite via `prefers-color-scheme` emulation).
- **Three new entry types** — as Blair (editor on Northwind), add a "Site
  visit" or "Competitor intel" entry; its icon is distinct from the eight
  MVP types', not just its colour.
- **v1 is gone** — `curl http://localhost:8000/api/opportunities` (no `/v2`)
  now 404s; every request the frontend makes goes to `/api/v2/*`.

**Left for the human's own judgment** (D-053's non-automatable half,
unchanged from Phase 1): timestamps read correctly in your own timezone,
rendered Markdown is readable, a PDF export is something you would actually
send, and an AI answer is grounded in the timeline it was asked about.

---

## 3. Decisions needing review

Every decision below is still flagged `needs human review: Y` in
`DECISIONS.md` as of this gate (three others raised mid-phase — D-060, D-075,
D-082 — were already resolved by a later ruling in the same phase and are not
repeated here).

| ID | Question | Recommended | Alternative |
|---|---|---|---|
| D-070 | Bulk action bar ships `delete` and `set_stage` only; `docs/UX.md` lists five (also assign owner, add to view, export). The other three have no single-item capability to reuse — ownership transfer and view-membership don't exist as concepts, multi-record export has no contract. | Keep them deferred; do not build ownership transfer, view membership or bulk export speculatively (brief §9 forbids inventing capability to fill out a control). | Confirm a phase to build the missing single-item capabilities first (ownership transfer is a schema change; view-as-membership is a different model from the current filter/sort saved view; bulk export is a new endpoint shape), then extend the same `action` enum. |
| D-078 | Roadmap's 2.6 line reads "Three new entry types with icons" — built as icons on all eleven types (new + the eight MVP ones), on the strength of `DESIGN-SYSTEM.md`'s "never colour alone" rule. | Keep as built — it closes a real accessibility gap and retrofitting later is the more expensive path (the same reasoning that justified building both themes together). | If the roadmap sentence was meant literally, the eight MVP badges revert to colour-only (a narrower, faster milestone, but reopens the accessibility gap). |
| D-088 | Calendar (`docs/FEATURES.md` §1) is scoped as "expected close dates and follow-up dates"; shipped with close dates only. A follow-up date lives on a timeline entry, and no endpoint reads timeline entries across opportunities today. | Accept close-date-only for Phase 2's acceptance line (`docs/ROADMAP.md`'s 2.8 wording is just "Table and calendar view", and allowed both to slip entirely) — Phase 4's milestone 4.1 ("My Tasks across opportunities") builds the cross-opportunity read and 4.2 migrates `follow_up_date` into that model, so a bespoke endpoint now would be superseded almost immediately. | Build a narrow cross-opportunity follow-up endpoint now as a stopgap, accepting it will be replaced within two phases. |
| D-090 | Table view (`OpportunityTable.tsx`) uses a styled grid of `article` rows with visually-hidden per-cell column labels, not `role="grid"`/real `<table>` semantics — a virtualized container of positioned `div`s cannot honestly claim `aria-required-children`. axe is clean on the view as built. | Accept as built for Phase 2; if true dimensional grid navigation (arrow-key cell movement) is wanted, schedule it as an R.2 (accessibility) milestone — it's a `VirtualList` API change affecting every long list in the app, not a table-view-only fix. | Block Phase 2 acceptance on real ARIA grid semantics now. |
| D-093 | With `/api/v2/opportunities` keyset-paginated since 2.9, the board's filter/sort predicate stayed in the client (`fetchAll` walks every page into one list) rather than moving into SQL, which D-061/D-063 had anticipated this milestone would do. | Accept — moving the predicate server-side is a redesign of the four-view layer (bulk selection, calendar month and the `<150ms cached` view-switch acceptance line all currently assume the whole filtered list is in memory) and belongs in Phase R's performance slice against a measured budget, not folded into "finish the v2 port." | Schedule a dedicated view-layer milestone now to move filtering server-side ahead of Phase R. |
| D-096 | Edit-history reads are owner-only for all three kinds (opportunities, timeline entries, notes). This tightens the one route that had already shipped open to every role with access (`GET /api/v2/notes/{id}/versions`) — reachable only by curl before 2.10 built a screen for it, so no client broke. | Accept owner-only, matching the audit log's existing rule — the alternative (any accessible role) answers a different question than "who changed this and what did it say before," which is deliberately audit-log-shaped. | Widen to any role with opportunity access, if editors are meant to see their own note's history even when they aren't the owner (one line per route, no migration). |
| D-097 | The Phase-2.10 backfill wrote a version-1 row for every pre-existing opportunity and timeline entry from its *current* values — for a row edited before this revision shipped, that "version 1" asserts something the database can no longer prove (the true original values are gone). | Accept the documented limitation (recorded in the revision and in `CLAUDE.md`) — the alternative, no backfill, fails the exact case the milestone exists for (a first post-upgrade edit would show only the new value, with nothing to compare it against). | Add a `system_backfilled` flag so the UI can label these rows as approximate (a schema/UI cost for a bounded, already-documented inaccuracy). |

No decision this phase changed the stack, and no database migration shipped
without an accepted ADR.

---

## 4. Quality evidence

**Sandbox half of the split gate** (brief §3.4), run this session at commit
`77f4aba` (no application code changed since milestone 2.12's own gate —
this is a fresh, full `make check` run, not a copied-forward number):

```
ruff check .                      All checks passed!
ruff format --check .             76 files already formatted
mypy app tools                    Success: no issues found in 38 source files
frontend typecheck (tsc)          clean
frontend lint (eslint)            clean (2 pre-existing warnings, 0 errors:
                                   an unused eslint-disable in
                                   MarkdownText.test.tsx, and a React Compiler
                                   "incompatible library" skip on
                                   VirtualList.tsx's useVirtualizer call —
                                   both informational, neither new to this
                                   session)
prettier --check                  All matched files use Prettier code style!
backend pytest                    338 passed, 97.27% combined line+branch
                                   coverage (--cov-fail-under=90 enforced);
                                   the ≥95%-branch modules (permissions.py,
                                   audit_utils.py, auth.py, soft_delete.py,
                                   routes_ai.py, versioning.py) all at 100%
frontend vitest                   429 passed (25 files), 97.10% statements /
                                   90.95% branch / 95.80% functions / 97.07%
                                   line (thresholds 96/90/95/96 all met)
API-contract check                generated client (lib/api-types.ts) current
pip-audit                         No known vulnerabilities found
npm audit                         found 0 vulnerabilities
Playwright E2E + axe              57 passed (17 specs), axe clean on every
                                   screen exercised in both light and dark
                                   (prefers-color-scheme emulation); the
                                   deferred color-contrast ratchet is now
                                   empty (DEFERRED_AXE_RULES) — 2.5's token
                                   work closed the last gap Phase 1 left open
Docker build + smoke test         deferred to the host — no Docker socket in
                                   this sandbox (sandbox/README.md)
```

**Coverage vs. previous phase** (Phase 1's gate → this gate):

| | Phase 1 gate | Phase 2 gate |
|---|---|---|
| Backend tests | 258 | 338 |
| Backend coverage | 97.28% | 97.27% |
| Frontend tests | 102 | 429 |
| Frontend line coverage | 88.38% | 97.07% |
| Frontend coverage thresholds | 85/85/85/78 | 96/96/95/90 |
| E2E tests | 18 (7 specs) | 57 (17 specs) |
| Authorization-matrix endpoints | 47 | 52 |

Full per-milestone history and module breakdowns: `docs/autopilot/COVERAGE.md`.

**New invariant / E2E tests this phase:** the authorization matrix grew from
47 to 52 endpoints (saved views, restore routes, bulk action, edit-history
reads); every new route's registry-guard entry landed with its milestone.
Ten new E2E specs (`09` through `17`) cover saved views, the command palette
and keyboard map, undo, bulk actions, theming, board/list views, table and
calendar views, edit history and inline editing, and the security-regression
suite 2.12 added. Of brief §6.3's journeys: **8 (board view stage drag →
system entry)** completed this phase (`14-board-views.spec.ts`); **13
(keyboard-only: command palette → opportunity → add note)** completed via
2.4a (`10-keyboard.spec.ts`). **Journey 7** ("Custom field → filter view →
save view → persists on reload") is adapted per brief §6.3's own allowance:
custom fields do not exist until Phase 5, so `09-saved-views.spec.ts` proves
the filter/save/reload half only — the custom-field half is still open, and
this journey should be revisited once Phase 5 lands it, not marked done.

**Host half of the split gate:** outstanding. Run
`scripts/autopilot-gate.sh 2` against commit `77f4aba` — it builds the image
from this branch, runs `make docker-test` and `make docker-smoke`.
`scripts/autopilot-accept.sh` will refuse to accept without that receipt.

---

## 5. Risks and known limitations

- **Three of five documented bulk actions are unbuilt** (D-070): ownership
  transfer, add-to-view and bulk export. Not a regression — they never
  existed as single-item capabilities to reuse — but `docs/UX.md`'s spec
  still names all five.
- **The calendar shows expected close dates only, not follow-up dates**
  (D-088) — half of `docs/FEATURES.md` §1's stated scope, deliberately, with
  Phase 4 named as where the missing half's data model actually lives.
- **The table view is not a real ARIA grid** (D-090) — accessible per-cell
  (axe clean, every cell announces its column), but not dimensionally
  navigable by arrow key the way a native `<table>` or `role="grid"` would
  be.
- **Edit-history reads are owner-only** (D-096), which is a real behavior
  change from the one route that had already shipped (open to any role) —
  nothing in the frontend called it before this phase, so no client observed
  the old behavior, but it is worth the human's explicit confirmation since
  it is a tightening of previously-accepted Phase-F scope.
- **Pre-revision edit-history baselines are approximate** (D-097): a version
  1 backfilled for a row edited before the 2.10 migration shows that row's
  *current* values, not its true original ones, which are gone. Documented
  in the revision and in `CLAUDE.md`.
- **The board's filter/sort predicate still runs client-side** (D-093) even
  though the backing endpoint is now paginated — correct at the 400-row
  budget this phase targets, but a candidate for Phase R's performance work
  if the dataset grows past what `fetchAll`'s page-walk should carry.
- **The Docker build + smoke test has not run in this session** (no Docker
  socket in the sandbox) — the one piece of §3.4 not yet verified against
  this exact commit; see §4's "Host half" note.

---

## 6. Out-of-scope items noticed, logged not built

- Nothing new surfaced this phase beyond what earlier gates already logged.
  The capability-list cross-check (brief §7) was performed at the Phase F
  gate; Phase 2's work stayed inside `docs/ROADMAP.md`'s Phase 2 scope and
  the decisions the human already ruled on (D-033, D-060/D-076, D-082) —
  no new CRM/lead-scoring/outbound-pipeline/SSO surface was proposed or
  built, consistent with brief §2 invariant 8 (domain narrowness).
- D-070's three deferred bulk actions and D-088's deferred follow-up-date
  calendar layer are scope *narrowing* decisions inside already-planned
  milestones, not newly noticed capability gaps — recorded in §3 rather than
  here because each is a milestone-level scoping call, not an unplanned
  discovery.

---

## 7. Preview of next phase

Phase 3 — Rich Content and Live Collaboration (`autopilot/phase-3`, depends
on the `phase-2-accepted` tag). First milestones per `PROGRESS.md` (partial,
read the file for the full list):

- Rich text editing for notes (the sanitization framework Phase F built and
  2.12 proved end-to-end is what this writes through).
- PDF export renders Markdown, closing the other half of a requirement 2.12
  noted was still open.
- If table/calendar views had slipped from Phase 2 they would land here —
  moot, since 2.8 shipped both inside Phase 2.

Decisions worth settling before Phase 3 work begins, since they shape
adjacent surfaces: D-090 (table ARIA grid — affects whether Phase 3's own UI
work should route through the same `VirtualList` pattern) and D-096
(owner-only history reads — affects whether a Phase 3 collaboration feature
should read history at all for a non-owner editor).
