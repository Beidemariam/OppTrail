# Test Criteria

This document is the phase-by-phase quality gate for OppTrail. At the end of
each phase, check off the relevant items before moving on.

## Testing Standard

- Target at least 80% automated test coverage for backend business logic and API
  behavior once those modules exist.
- Do not over-test framework defaults, trivial getters, static copy, or purely
  decorative UI.
- Always test the highest-risk behavior: authentication, permissions, timeline
  integrity, soft deletes, auditability, exports, and AI read-only boundaries.
- A phase can pass with small cosmetic issues, but not with known data-loss,
  security, permission, migration, or broken acceptance-flow issues.
- Each phase must include a quick manual walkthrough of its acceptance scenario.
- Each phase summary must include user test steps the user can run in the app.
- Each phase ends with an explicit decision: Review, Accept, or Reject.

## Phase Decision

Use this decision block at the end of every phase:

```text
Decision: Review | Accept | Reject
Reviewer:
Date:
Notes:
```

- **Review** means the phase is implemented and ready for user inspection, but
  not yet approved as complete.
- **Accept** means the phase gate passed and work can move to the next phase.
- **Reject** means the phase gate failed or the implementation does not match
  requirements; record the issue, fix it, and retest before requesting review
  again.

## Failure Loop

When a test fails or manual verification finds an issue:

1. Identify the root cause with evidence before changing code.
2. Fix the root cause directly, without unrelated refactors.
3. Re-run the smallest failing test first.
4. Re-run the relevant phase gate checks.
5. Record a short summary: issue, root cause, fix, and retest result.

Use this format in phase notes or commit messages when useful:

```text
Issue:
Root cause:
Fix:
Retest:
```

## Phase 0 - Scaffolding

- [x] Docker image builds successfully.
- [x] Container starts FastAPI and serves the built NextJS static site at `/`.
- [x] `/api/health` or equivalent health endpoint returns success.
- [x] SQLite database file is created automatically when missing.
- [x] Migrations or schema initialization can run from a clean database.
- [x] Start/stop scripts work on the current development machine.
- [x] `.env.example` documents required variables without real secrets.
- [x] `.env` is ignored by Git.

Acceptance gate: the container builds and serves an empty NextJS page through
FastAPI.

Decision: Review
Reviewer:
Date: 2026-09-02
Notes: Phase 0 scaffold is ready for user review.

## Phase 1 - Auth, Opportunities, Dashboard

- [x] User can sign up with email, name, and password.
- [x] Duplicate email signup is rejected cleanly.
- [x] User can log in and receives an HttpOnly session cookie.
- [x] User can log out and the session no longer authenticates.
- [x] Unauthenticated users cannot access protected endpoints.
- [x] Authenticated user can create an opportunity.
- [x] Owner can view and update their own opportunity.
- [x] Owner can soft-delete their own opportunity.
- [x] Dashboard lists owned opportunities grouped by fixed sales stage.
- [x] Backend tests cover auth/session and opportunity ownership rules.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: a user can sign up, create an opportunity, and see it on the
dashboard.

Decision: Review
Reviewer:
Date: 2026-09-02
Notes: Phase 1 auth, opportunity CRUD, and dashboard grouping are ready for user review.

## Phase 2 - Timeline Tree

- [x] Owner/Editor can create timeline entries.
- [x] Viewer cannot create, edit, or delete entries, notes, or comments.
- [x] Notes can be added to any existing entry after entry creation.
- [x] Comments can be added to any existing note.
- [x] Notes can be edited and set `edited = true`.
- [x] Note create/edit appends `NoteVersion` rows in order.
- [x] Comments are not editable after posting.
- [x] Deletes for entries, notes, and comments are soft deletes.
- [x] Stage changes create traceable system timeline entries.
- [x] Opportunity creation creates a traceable system timeline entry.
- [x] Timeline filters work for keyword, entry type, date range, and author.
- [x] Timeline returns entries, notes, and comments in expected chronological
      structure.
- [x] Backend tests cover tree creation, permissions, soft deletes, version
      history, system entries, and filters.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: a full entry -> note -> comment chain can be created, edited
where allowed, searched/filtered, and a Viewer is blocked from writing.

User test steps:
1. Open `http://localhost:8000` and sign up or sign in.
2. Create an opportunity from the left form, then select `Timeline` on its card.
3. Confirm the timeline shows the system-generated `Opportunity created` entry.
4. Add a manual entry with a unique keyword in the body, such as `pricing-risk`.
5. Add a note under that entry, then add a comment under that note.
6. Edit the note and confirm it shows the `edited` indicator.
7. Edit the manual entry title or type and confirm the timeline updates.
8. Use the keyword filter with `pricing-risk` and confirm only the matching entry
   remains visible.
9. Use the entry type filter and confirm entries are narrowed by type.
10. Change the opportunity stage, reopen or refresh the timeline, and confirm a
    system `Stage changed to ...` entry appears.
11. Delete the comment, note, and manual entry, then refresh and confirm the
    deleted items no longer appear.
12. Permission checks for Viewer write blocking are covered by automated backend
    tests until the Phase 3 sharing UI exists.

Decision: Review
Reviewer:
Date: 2026-09-03
Notes: Phase 2 timeline APIs, UI workflow, filters, permissions, system entries, and backend coverage gate are ready for user review.

Issue: Two timeline tests failed after initial implementation.
Root cause: The tests assumed fixed list positions even though timeline results are intentionally sorted by event timestamp and system entries use the real creation timestamp.
Fix: Updated tests to find entries by ID/title and use a date range that intentionally excludes the system creation entry.
Retest: Focused failing tests passed; full backend suite passed with 94% coverage.

Issue: User review found the creation system entry missing for an existing opportunity, cramped card buttons, and related timeline data remaining after parent deletion.
Root cause: Existing opportunities created before Phase 2 had no backfilled system entry; action buttons were forced into three narrow columns; delete paths only marked the immediate parent record.
Fix: Added an idempotent creation-entry backfill, responsive auto-wrapping buttons, tighter layout styling, and cascading soft deletes from opportunity -> entries -> notes -> comments and entry -> notes -> comments.
Retest: Focused regression tests passed; full backend suite passed with 94% coverage; frontend lint, typecheck, and build passed.

## Phase 3 - Sharing

- [x] Owner can share an opportunity with an existing user by email.
- [x] Sharing with a nonexistent email returns a clear error.
- [x] Owner can assign Viewer or Editor role.
- [x] Owner can change a shared user's role.
- [x] Owner can remove a share.
- [x] Non-owner cannot manage sharing.
- [x] Shared user sees the opportunity on their dashboard.
- [x] Viewer and Editor permissions are enforced server-side.
- [x] Share add/change/remove creates audit log entries.
- [x] Share add/change/remove creates system timeline entries.
- [x] Owner can view the opportunity audit log.
- [x] Non-owner cannot view the audit log.
- [x] Backend tests cover sharing permissions, role changes, audit log, and
      system timeline entries.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: Owner shares with a second test user, who sees the opportunity
with the correct permissions.

User test steps:
1. Open `http://localhost:8000` in one browser or profile and sign in as the
   opportunity Owner.
2. In a second browser or private window, sign up a colleague account, then sign
   out.
3. Return to the Owner session, open an opportunity timeline, and use the
   Sharing panel to add the colleague email as Viewer.
4. Confirm the colleague appears in the share list and the timeline shows a
   `Shared with ...` system entry.
5. Open the Audit Log and confirm a `share_added` row appears.
6. Sign in as the colleague and confirm the shared opportunity appears on the
   dashboard with role `viewer`.
7. Open the timeline as the Viewer and confirm timeline write controls are not
   shown.
8. Sign back in as Owner, change the colleague role to Editor, and confirm the
   timeline shows `Role changed for ...` and Audit Log shows
   `share_role_changed`.
9. Sign in as the colleague again and confirm entry/note/comment write controls
   are available.
10. Return as Owner, remove the share, and confirm Audit Log shows
    `share_removed`.
11. Sign in as the colleague and confirm the opportunity no longer appears on
    their dashboard.

Decision: Review
Reviewer:
Date: 2026-09-04
Notes: Phase 3 sharing APIs, owner UI, role enforcement, audit log, system timeline entries, and backend coverage gate are ready for user review.

## Phase 4 - AI Agent

- [x] AI endpoint requires a valid session.
- [x] Viewer, Editor, and Owner can ask read-only timeline questions.
- [x] User without access to the opportunity cannot ask questions.
- [x] Backend assembles full chronological timeline context.
- [x] Prompt and API code expose no database write tool or write path.
- [x] AI answer references actual timeline entries or dates where possible.
- [x] OpenAI API errors return a helpful non-crashing response.
- [x] Tests mock OpenAI and verify context assembly and access control.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: asking "summarize this opportunity" returns a grounded answer
referencing actual entries.

User test steps:
1. Confirm `.env` has a valid `OPENAI_API_KEY`. `OPENAI_MODEL` can be omitted to
   use the default.
2. Open `http://localhost:8000` and sign in.
3. Open an opportunity timeline that has at least one manual entry and note.
4. In the AI Agent sidebar, ask `Summarize this opportunity`.
5. Confirm the response discusses actual timeline content and cites entries such
   as `[Entry #id, date]`.
6. Ask `What objections came up?` and confirm the answer stays grounded in the
   timeline.
7. Sign in as a Viewer on a shared opportunity and confirm the AI Agent can
   answer while timeline write controls remain hidden.
8. Temporarily remove or blank `OPENAI_API_KEY`, restart the app, ask the AI
   Agent, and confirm a clear configuration error appears instead of a crash.

Decision: Review
Reviewer:
Date: 2026-09-04
Notes: Phase 4 read-only AI endpoint, timeline context assembly, mocked OpenAI tests, sidebar chat UI, and backend coverage gate are ready for user review.

## Phase 5 - Export

- [x] PDF export requires opportunity access.
- [x] PDF includes opportunity summary, entries, notes, and comments.
- [x] PDF renders timeline content in chronological order.
- [x] PDF excludes soft-deleted content unless explicitly intended otherwise.
- [x] JSON export includes raw opportunity timeline data.
- [x] CSV export includes raw timeline rows with enough columns to reconstruct
      entry/note/comment relationships.
- [x] Viewer, Editor, and Owner can export accessible opportunities.
- [x] User without access cannot export.
- [x] Tests cover export permissions and JSON/CSV shape.
- [x] Manual PDF check confirms readable formatting.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: exported PDF renders all entries/notes/comments in
chronological order and matches the on-screen timeline.

User test steps:
1. Open `http://localhost:8000` and sign in.
2. Open an opportunity timeline with at least one entry, note, and comment.
3. Click `PDF` in the timeline header and confirm the downloaded file opens with
   the opportunity summary and full visible timeline.
4. Click `CSV` and confirm rows include `entry`, `note`, and `comment` values in
   the `row_type` column.
5. Click `JSON` and confirm the file includes `opportunity` plus nested
   `entries`, `notes`, and `comments`.
6. Delete a test entry, export again, and confirm the deleted entry and its
   related notes/comments are excluded.
7. Sign in as a Viewer on a shared opportunity and confirm PDF/CSV/JSON exports
   are still available.
8. Sign in as a user without access and confirm export URLs do not expose the
   opportunity.

Decision: Review
Reviewer:
Date: 2026-09-04
Notes: Phase 5 export endpoints, export buttons, access checks, CSV/JSON shape tests, PDF generation, and backend coverage gate are ready for user review.

Issue: The first export test failed before running any route.
Root cause: WeasyPrint needs Pango/GObject system libraries; the Python package alone is not enough, and importing it at module load made all export routes depend on local desktop libraries.
Fix: Moved the WeasyPrint import into the PDF rendering function and added the required Debian Pango/Harfbuzz packages to the Docker image.
Retest: Focused export tests passed; full backend suite passed with 92% coverage; PDF generation was verified in Docker.

## Phase 6 - Notifications and Reminders

- [x] Mentions in notes create notification rows for mentioned colleagues.
- [x] Mentions in comments create notification rows for mentioned colleagues.
- [x] New comments on a user's notes create notification rows.
- [x] Activity on shared opportunities creates expected notifications.
- [x] Notification bell shows unread notifications.
- [x] User can mark a notification as read.
- [x] Users cannot read or update another user's notifications.
- [x] Follow-up date can be set on a timeline entry by Owner/Editor.
- [x] Viewer cannot set follow-up dates.
- [x] Dashboard flags opportunities stalled after 14 days without non-deleted
      entry, note, or comment activity.
- [x] Recent non-deleted activity clears the stalled flag.
- [x] Tests cover mention parsing, notification permissions, reminder updates,
      and stalled calculations.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: mentioning a colleague creates a notification they can see and
dismiss.

User test steps:
1. Open `http://localhost:8000` and sign in as the opportunity Owner.
2. Share an opportunity with a colleague account as Editor.
3. Add or edit a note containing the colleague email as a mention, for example
   `@colleague@example.com`.
4. Sign in as the colleague and confirm the `Notifications` button shows an
   unread count.
5. Open `Notifications` and confirm the mention appears.
6. Click `Mark read` and confirm the notification disappears from the unread
   list.
7. As the colleague Editor, comment on one of the Owner's notes.
8. Sign back in as the Owner and confirm a new comment notification appears.
9. Set a follow-up date on a timeline entry as Owner or Editor and confirm it
   appears on the timeline.
10. Sign in as a Viewer and confirm entry editing/follow-up updates are not
    available.
11. Check the dashboard for any `Stalled` badges on opportunities with no recent
    activity.

Decision: Review
Reviewer:
Date: 2026-09-04
Notes: Phase 6 mention notifications, comment/shared-activity notifications, notification bell, mark-read API, follow-up permission coverage, stalled dashboard flag, and backend coverage gate are ready for user review.

Issue: Focused notification tests initially passed with deprecation warnings.
Root cause: Stalled calculation used `datetime.utcnow()`, which is deprecated in the current Python runtime.
Fix: Switched stalled comparison to timezone-aware UTC while preserving compatibility with existing SQLite timestamp strings.
Retest: Focused notification tests passed without warnings; full backend suite passed with 93% coverage.

## Phase 7 - Polish

- [x] Full walkthrough works in Docker: signup -> create opportunity -> log
      entries -> share -> AI question -> PDF export.
- [x] Core views have loading, empty, error, and permission-denied states.
- [x] UI follows the project color scheme without becoming one-note.
- [x] Layout works on desktop and mobile widths.
- [x] Forms show clear validation errors.
- [x] Sanitized Markdown renders bold, links, and bullet lists safely.
- [x] No file/image attachment UI appears in MVP.
- [x] No obvious text overlap or clipped controls in main workflows.
- [x] Backend test suite passes.
- [x] Frontend lint/type checks pass.
- [x] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: full walkthrough works end to end in the Docker container.

User test steps:
1. Open `http://localhost:8000` and sign up or sign in.
2. Create an opportunity, open its timeline, and add an entry.
3. Add a note containing Markdown, such as `**Important**`, `- next step`, and
   `[link](https://example.com)`, then confirm it renders cleanly.
4. Add a comment with the same Markdown patterns and confirm it renders cleanly.
5. Share the opportunity with another account and confirm permissions still look
   correct for Viewer and Editor.
6. Ask the AI sidebar a question and confirm it answers without editing data.
7. Export PDF, CSV, and JSON from the timeline header.
8. Resize the browser to a narrow width and confirm buttons, cards, and the
   notification panel remain readable.

Decision: Accept
Reviewer: Beide Worku
Date: 2026-09-06
Notes: Phase 7 Markdown rendering, README setup notes, final polish, Docker walkthrough, frontend checks, and backend coverage gate were accepted.

Issue: The first Docker walkthrough script failed on the final frontend check.
Root cause: The script uppercased the HTML response but compared it to a mixed-case `<!DOCTYPE html>` literal.
Fix: Corrected the assertion to compare against uppercase HTML markers.
Retest: Corrected frontend served check passed; the app flow before it had already completed successfully.

## Final MVP Gate

- [x] All phase acceptance gates are implemented and ready for review.
- [x] No critical known bugs remain.
- [x] No secrets are committed.
- [x] Fresh clone setup works from documented steps.
- [x] Docker build and run work from a clean checkout.
- [x] README is concise and current.
- [x] Latest changes are committed locally.
- [x] Latest accepted MVP changes are pushed to the cloud remote.

Decision: Accept
Reviewer: Beide Worku
Date: 2026-09-06
Notes: Final MVP implementation was accepted locally and confirmed pushed to the cloud remote by the reviewer. This shell could not independently verify the remote because GitHub SSH authentication is unavailable here.
