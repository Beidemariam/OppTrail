# Open Questions

Live list. Each entry states what is unresolved, what I assumed so planning could
continue, what the assumption costs if wrong, and what would resolve it.

**All questions are answered as of this revision.** Q1-Q5 and Q8-Q11 were confirmed
as the assumptions recorded below; Q6 (no workspaces) was confirmed explicitly; Q7
resolved to **20 opportunities per user — 400 total**, which was benchmarked rather
than assumed.

Answered: **scale** (20 users, 400 opportunities, ~200 entries each, 2-3
concurrent), **implementer** (agent-executed across review-gated sessions),
**email scope** (inbound creation of entries, notes and comments), **provider**
(OpenAI), **AI** (hard read-only), **deployment** (single self-hosted container),
**real-time** (SSE, no presence), **mobile** (responsive web), **tenancy** (none).

This file now serves as the record of what was decided and what it would cost to
revisit. New questions get appended as implementation raises them.

---

## Q1 — AI provider: OpenAI or OpenRouter? (blocking a code change, not the plan)

`docs/v2_review_brief.md:14` states OpenRouter with `gpt-oss-20b`. The code uses the
OpenAI SDK directly (`ai_service.py:4,130,131`) configured by `OPENAI_API_KEY` /
`OPENAI_MODEL` (`settings.py:7-8`, default `gpt-5.6-luna`), and `AGENTS.md` says
"Use OpenAI for AI calls." Nothing in the repository references OpenRouter.

**Assumed:** the code is authoritative; OpenAI stays.
**Cost if wrong:** low and contained — the provider call is one function
(`ai_service.ask_openai`). Different SDK, auth and model catalogue, so it changes
`pyproject.toml` and one module, nothing structural.
**Resolves it:** which you actually intend to pay for.

## Q2 — Is human-confirmed AI write access acceptable?

ADR 0012 assumes **no**: the agent stays read-only by construction, and features that
would change data return proposals a human applies.

**Cost if wrong:** we build a proposal-and-apply flow where a confirmation dialog
would have done, costing some interaction speed on notes-to-entry parsing.
**Cost if the looser answer is wrong:** far higher, because inbound email (ADR 0009)
means injected instructions can arrive from outside the user base.
**Resolves it:** your tolerance. I recommend holding the strict line at least until
email ingestion has been running long enough to see what actually arrives.

## Q3 — Deployment target and ops appetite

**Assumed:** self-hosted single container, minimal ops, possibly a small managed
host later. ADRs 0001, 0003, 0004, 0008 and 0011 all rest on **exactly one
application instance**.
**Cost if wrong:** substantial. Multiple instances break in-process SSE fan-out,
double-run every scheduled job, and make a local SQLite file and local attachment
storage untenable. Those five ADRs would need revisiting together.
**Resolves it:** where this will actually run, and whether more than one instance is
ever expected.

## Q4 — Real-time expectations

**Assumed:** live updates via SSE, no presence indicators, no live cursors, no
co-editing (ADR 0003).
**Cost if wrong:** presence would need a bidirectional transport, so ADR 0003 flips
to WebSockets. Co-editing is a different product decision and an explicit `AGENTS.md`
non-goal today.
**Resolves it:** whether "real-time collaboration" in the brief meant *see each
other's changes* or *see each other*.

## Q5 — Mobile

**Assumed:** responsive web, desktop-first. Affects the design system's density
modes and the component inventory materially.
**Cost if wrong:** a mobile-first or native target changes Phase 4 substantially and
would need its own roadmap phase.
**Resolves it:** whether reps are expected to log calls from a phone. If yes, that
argues for a mobile-first *entry creation* path even without a native app.

## Q6 — Workspaces: confirm the cut

ADR 0010 declines the workspace → team → opportunity hierarchy on scale grounds and
invests in a structural authorization dependency instead. This is my largest
departure from the brief.

**Cost if wrong:** adding a tenancy boundary later is cheap *only while there is one
organisation's data in the database*. If a second organisation is foreseeable within
v2, say so now and it goes in the first schema phase.
**Resolves it:** whether OppTrail is ever intended for anyone outside this team.

## Q7 — Scale figure — RESOLVED: 20 per user (400 total)

Confirmed as 20 opportunities **per user**: 400 opportunities, 80,000 entries,
~800,000 rows, ~136 MB.

I said "nothing in the plan changes" and then measured it. Mostly true — SQLite,
the single container and every ADR hold, with ~20x file-size headroom. Three things
did change:

1. **The dashboard N+1 is fine and the obvious fix is a regression.** Measured
   131 ms at 400 opportunities; the "single grouped query" rewrite I recommended in
   the review measured 363 ms. Corrected in `REVIEW.md` §3.1.
2. **FTS5 moved from nicety to justified.** `LIKE` worst case is 294 ms against a
   300 ms budget — no margin. See ADR 0007 for the measured table.
3. **Pagination and virtualization became visible requirements**, not just API
   hygiene: 400 opportunities will not render in an unvirtualized board or table.

## Q8 — Notification digest default

**Assumed:** immediate for mentions and direct assignment, daily digest otherwise.
**Cost if wrong:** trivial, it is a default in a preferences table.

## Q9 — Attachments in PDF export

**Assumed:** listed as a manifest (filename, size, uploader), not embedded, so
export size stays bounded.
**Cost if wrong:** embedding is straightforward for images; arbitrary file embedding
in PDF is not, and would need a scope decision.

## Q10 — CSV import scope

**Assumed:** opportunities only, not historical timeline entries.
**Cost if wrong:** importing timeline history needs an author-mapping step and a
provenance marker, which is a meaningfully larger feature.

## Q11 — Shared saved views: who may edit?

**Assumed:** only the creator edits a shared view; others copy it.
**Cost if wrong:** trivial, a permission check.
