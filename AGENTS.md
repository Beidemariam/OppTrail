# AGENTS.md

## Project Name
OppTrail — a timeline note-taking app for tracking sales opportunities

## Business Requirements

Core (as specified):
1. A user can sign in
2. Timeline tree per Opportunity, made of three nested levels:
   - **Timeline Entries** — the top-level events (calls, meetings, emails, demos,
     proposals, stage changes, etc.), each with a timestamp, a title, and a body
   - **Notes** — can be attached to any Entry at any time after it's created, to log
     follow-ups or updates on that event
   - **Comments** — can be attached to any Note, for colleague discussion threads
3. Notes can be added to any entry at any time, not just when the entry is created
4. Comments can be made on any note
5. An AI agent, in a sidebar, answers summarized natural-language questions about an
   opportunity's timeline ("Where do we stand?", "What objections came up?",
   "Summarize the last 2 weeks"). The agent is **read-only** — it never edits the
   timeline
6. An Opportunity can be shared with colleagues, who are assigned a role of Viewer
   (read-only) or Editor (can add entries/notes/comments)
7. The full timeline can be exported to a formatted PDF
8. Opportunities dashboard — list of opportunities the signed-in user owns or has
   been shared on, grouped by stage
9. Opportunity record: name, account/company, deal value, currency, sales stage,
   owner, expected close date
10. Automatic system-generated timeline entries for key events (opportunity
    created, stage changed, sharing/role changed) so the tree captures full history
    without manual logging
11. Entry types (Call, Email, Meeting, Demo, Proposal, Contract, Stage Change,
    Other) with a color/icon for quick scanning
12. Search and filter on the timeline: keyword, entry type, date range, author
13. @mentions inside notes/comments that notify the mentioned colleague
14. In-app notification bell (mentions, new comments on your notes, activity on
    shared opportunities)
15. Edit history on notes via a version history table ("edited" indicator +
    who/when) — never silently overwritten
16. "Stalled" flag on the dashboard for opportunities with no timeline activity in
    14 days, plus a lightweight "follow up on [date]" reminder on an entry
17. Rich text for notes/comments (bold, links, bullet lists) — sanitized
    Markdown, no file attachments in MVP
18. Full audit log per opportunity (sharing/role changes, deletions), visible to
    the Owner
19. CSV/JSON export of the raw timeline, alongside the PDF

Explicit non-goals for MVP (future roadmap — do not build now):
- File/image attachments on entries or notes
- Email or calendar integrations (auto-logging emails/meetings)
- Real-time multiplayer cursors / live co-editing
- Public, unauthenticated share links
- Organizations / multi-team workspaces (MVP is one flat pool of users, any of
  whom can be invited to any opportunity)
- AI agent write-access to the timeline

## Limitations
- MVP runs locally in a single Docker container, but uses real multi-user
  accounts (email + password) since sharing/permissions is a core requirement —
  no hardcoded single user like a typical local demo
- Sharing requires the colleague to already have an account (self-serve sign-up);
  auto-creating an account for a brand-new invited email is a future enhancement
- Sales stages are a fixed, ordered default list (Prospecting, Qualification,
  Needs Analysis, Proposal, Negotiation, Closed Won, Closed Lost) — not renamable
  in MVP, so stage-change history stays unambiguous
- SQLite local database (single file) — fine for MVP concurrency; Postgres is the
  natural upgrade path beyond local/single-team use
- AI context for MVP is "assemble the whole timeline as context" — opportunities
  are not expected to be huge. Chunking/map-reduce summarization for very long
  timelines is a future enhancement if token limits become a real issue

## Technical Decisions
- NextJS frontend (TypeScript, App Router)
- Python FastAPI backend, also serving the built NextJS static site at /
- Everything packaged into a single Docker container
- Use "uv" as the package manager for Python in the Docker container
- Use OpenAI for AI calls. An OPENAI_API_KEY is in .env in the project root
- SQLite local database, created automatically if it doesn't exist
- Session-based auth: hashed passwords (passlib/bcrypt), server-side session
  cookie (HttpOnly, SameSite=Lax) — no OAuth/SSO for MVP
- PDF export via WeasyPrint: render an HTML/CSS timeline template server-side and
  stream it back as a PDF download
- Start and Stop server scripts for Mac, PC, Linux in scripts/

## Data Model Summary
(kept intentionally simple — full field list in docs/PLAN.md)
- User
- Opportunity
- OpportunityShare (opportunity_id, user_id, role: viewer | editor — owner is
  implicit via Opportunity.owner_id)
- TimelineEntry (opportunity_id, type, title, body, event_timestamp, created_by)
- Note (entry_id, body, created_by, edited flag)
- NoteVersion (note_id, body, edited_by, version_number, created_at)
- Comment (note_id, body, created_by)
- Notification (user_id, type, payload, read flag)
- AuditLogEntry (opportunity_id, actor_id, action, detail, created_at)

## Permissions Model
- **Owner**: full control — edit opportunity, timeline, sharing, delete opportunity
- **Editor**: can add/edit timeline entries, notes, comments; cannot change
  sharing or delete the opportunity
- **Viewer**: read-only on everything, including the AI agent (can ask questions,
  cannot post entries/notes/comments)

## AI Agent Behavior
- Lives in a sidebar on the Opportunity timeline view, as a chat
- On each question, the backend assembles the full chronological timeline
  (entries + notes + comments) for that opportunity as context and sends it with
  the question to OpenAI
- The agent answers in natural language and references which entries/dates it
  drew from
- The agent never writes to the database — strictly read/summarize for MVP, by
  construction (no write tools exposed to it), not just by prompt instruction

## Starting Point
No existing codebase — this is a greenfield build. Proposed structure:
```
/frontend      NextJS app
/backend       FastAPI app
/scripts       start/stop scripts (mac/pc/linux)
/docs          PLAN.md and other planning docs
Dockerfile
.env           OPENAI_API_KEY, SESSION_SECRET, DATABASE_URL
```

## Color Scheme
- Deep Navy: `#0B2540` - headings, sidebar
- Accent Teal: `#0F9D8C` - timeline markers, links, primary actions
- Signal Amber: `#F2A93B` - highlights, badges, secondary CTAs
- Slate Gray: `#6B7280` - supporting text, timestamps
- Success Green: `#2FA84F` - Closed Won
- Alert Red: `#D64545` - Closed Lost, overdue reminders

## Coding standards
1. Use latest versions of libraries and idiomatic approaches as of today
2. Keep it simple - NEVER over-engineer, ALWAYS simplify, NO unnecessary
   defensive programming. No extra features beyond what's specified - focus on
   simplicity
3. Be concise. Keep README minimal. IMPORTANT: no emojis ever
4. When hitting issues, always identify root cause before trying a fix. Do not
   guess. Prove with evidence, then fix the root cause
5. Every non-user-initiated database write (stage-change auto-entries, audit log
   rows) must be clearly traceable to the action that caused it
6. Deletes are soft deletes (a `deleted_at` flag) — nothing on a shared sales
   record silently disappears
7. The AI agent's tool surface is read-only by construction — never give it a
   write-capable tool, even behind a confirmation step

## Working documentation
All documents for planning and executing this project will be in the docs/
directory. Please review the docs/PLAN.md document before proceeding.
