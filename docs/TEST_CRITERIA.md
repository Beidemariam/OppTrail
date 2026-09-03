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

- [ ] Owner/Editor can create timeline entries.
- [ ] Viewer cannot create, edit, or delete entries, notes, or comments.
- [ ] Notes can be added to any existing entry after entry creation.
- [ ] Comments can be added to any existing note.
- [ ] Notes can be edited and set `edited = true`.
- [ ] Note create/edit appends `NoteVersion` rows in order.
- [ ] Comments are not editable after posting.
- [ ] Deletes for entries, notes, and comments are soft deletes.
- [ ] Stage changes create traceable system timeline entries.
- [ ] Opportunity creation creates a traceable system timeline entry.
- [ ] Timeline filters work for keyword, entry type, date range, and author.
- [ ] Timeline returns entries, notes, and comments in expected chronological
      structure.
- [ ] Backend tests cover tree creation, permissions, soft deletes, version
      history, system entries, and filters.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: a full entry -> note -> comment chain can be created, edited
where allowed, searched/filtered, and a Viewer is blocked from writing.

Decision: Review | Accept | Reject

## Phase 3 - Sharing

- [ ] Owner can share an opportunity with an existing user by email.
- [ ] Sharing with a nonexistent email returns a clear error.
- [ ] Owner can assign Viewer or Editor role.
- [ ] Owner can change a shared user's role.
- [ ] Owner can remove a share.
- [ ] Non-owner cannot manage sharing.
- [ ] Shared user sees the opportunity on their dashboard.
- [ ] Viewer and Editor permissions are enforced server-side.
- [ ] Share add/change/remove creates audit log entries.
- [ ] Share add/change/remove creates system timeline entries.
- [ ] Owner can view the opportunity audit log.
- [ ] Non-owner cannot view the audit log.
- [ ] Backend tests cover sharing permissions, role changes, audit log, and
      system timeline entries.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: Owner shares with a second test user, who sees the opportunity
with the correct permissions.

Decision: Review | Accept | Reject

## Phase 4 - AI Agent

- [ ] AI endpoint requires a valid session.
- [ ] Viewer, Editor, and Owner can ask read-only timeline questions.
- [ ] User without access to the opportunity cannot ask questions.
- [ ] Backend assembles full chronological timeline context.
- [ ] Prompt and API code expose no database write tool or write path.
- [ ] AI answer references actual timeline entries or dates where possible.
- [ ] OpenAI API errors return a helpful non-crashing response.
- [ ] Tests mock OpenAI and verify context assembly and access control.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: asking "summarize this opportunity" returns a grounded answer
referencing actual entries.

Decision: Review | Accept | Reject

## Phase 5 - Export

- [ ] PDF export requires opportunity access.
- [ ] PDF includes opportunity summary, entries, notes, and comments.
- [ ] PDF renders timeline content in chronological order.
- [ ] PDF excludes soft-deleted content unless explicitly intended otherwise.
- [ ] JSON export includes raw opportunity timeline data.
- [ ] CSV export includes raw timeline rows with enough columns to reconstruct
      entry/note/comment relationships.
- [ ] Viewer, Editor, and Owner can export accessible opportunities.
- [ ] User without access cannot export.
- [ ] Tests cover export permissions and JSON/CSV shape.
- [ ] Manual PDF check confirms readable formatting.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: exported PDF renders all entries/notes/comments in
chronological order and matches the on-screen timeline.

Decision: Review | Accept | Reject

## Phase 6 - Notifications and Reminders

- [ ] Mentions in notes create notification rows for mentioned colleagues.
- [ ] Mentions in comments create notification rows for mentioned colleagues.
- [ ] New comments on a user's notes create notification rows.
- [ ] Activity on shared opportunities creates expected notifications.
- [ ] Notification bell shows unread notifications.
- [ ] User can mark a notification as read.
- [ ] Users cannot read or update another user's notifications.
- [ ] Follow-up date can be set on a timeline entry by Owner/Editor.
- [ ] Viewer cannot set follow-up dates.
- [ ] Dashboard flags opportunities stalled after 14 days without non-deleted
      entry, note, or comment activity.
- [ ] Recent non-deleted activity clears the stalled flag.
- [ ] Tests cover mention parsing, notification permissions, reminder updates,
      and stalled calculations.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: mentioning a colleague creates a notification they can see and
dismiss.

Decision: Review | Accept | Reject

## Phase 7 - Polish

- [ ] Full walkthrough works in Docker: signup -> create opportunity -> log
      entries -> share -> AI question -> PDF export.
- [ ] Core views have loading, empty, error, and permission-denied states.
- [ ] UI follows the project color scheme without becoming one-note.
- [ ] Layout works on desktop and mobile widths.
- [ ] Forms show clear validation errors.
- [ ] Sanitized Markdown renders bold, links, and bullet lists safely.
- [ ] No file/image attachment UI appears in MVP.
- [ ] No obvious text overlap or clipped controls in main workflows.
- [ ] Backend test suite passes.
- [ ] Frontend lint/type checks pass.
- [ ] Backend coverage is at least 80% for implemented business/API modules.

Acceptance gate: full walkthrough works end to end in the Docker container.

Decision: Review | Accept | Reject

## Final MVP Gate

- [ ] All phase acceptance gates pass.
- [ ] No critical known bugs remain.
- [ ] No secrets are committed.
- [ ] Fresh clone setup works from documented steps.
- [ ] Docker build and run work from a clean checkout.
- [ ] README is concise and current.
- [ ] Latest changes are committed locally.
- [ ] Latest changes are pushed to the cloud remote.

Decision: Review | Accept | Reject
