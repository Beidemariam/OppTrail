# 0010. No workspace hierarchy; enforce authorization in one dependency

Status: Accepted (v2)

## Context

The brief asks for a workspace → team → opportunity hierarchy with roles, guest
access and public read-only share links.

The measured scale is **20 users in one organisation**. The existing model is a flat
user pool with per-opportunity sharing (owner / editor / viewer), which the review
found to be the strongest-implemented part of the codebase, with no object-level
authorization gaps.

## Options

1. Build the full workspace → team → opportunity hierarchy as briefed.
2. **Add a single implicit workspace** boundary now, defer teams, keep
   per-opportunity sharing as the real access model.
3. Keep the flat pool exactly as-is and invest only in how the check is enforced.

## Decision

**Option 3, with the enforcement mechanism rebuilt.** This is a deliberate
departure from the brief.

At 20 users in one company there is no second tenant to isolate. A workspace table
whose every row count is 1 adds a join to every query, a scoping rule to every
endpoint, and a concept to every screen, in exchange for nothing a user can perceive.
Teams are a grouping mechanism for organisations with more people than this one has.
Guest access is already expressible: invite the person and give them `viewer`.

**Public read-only share links are also declined for v2.** `AGENTS.md` lists them as
an explicit non-goal, and they are the one feature here that creates an
unauthenticated path to customer sales data — the exact class of exposure the last
review found and fixed in the static file route.

What the review *did* identify as a real risk is that authorization, though correct
everywhere today, is enforced **by convention**: each route remembers to call a
helper from `permissions.py`. A new endpoint that forgets is silently unguarded, and
v2 roughly doubles the endpoint count.

So the investment goes here instead:

- A FastAPI dependency, `OpportunityContext`, resolves the opportunity and the
  caller's role once and yields both. Routes declare the access level they need
  (`Depends(require_editor)`), and a route that declares nothing gets nothing —
  the object is not reachable without passing through the dependency.
- Nested resources (note, comment, attachment) resolve to their opportunity inside
  the dependency, preserving the `fetch_*_context` pattern that already prevents
  IDOR.
- A test enumerates the application's routes and asserts every non-auth,
  non-public route depends on the guard. This converts "we remembered" into "the
  suite fails if we forget", which is the property that actually scales.

## Revisiting

If OppTrail is ever sold to or shared with a second organisation, the workspace
boundary becomes real and must be added **before** any cross-org data exists. The
migration is a `workspace_id` on `users` and `opportunities` plus a scoping clause
inside the same single dependency — cheap precisely because the check lives in one
place.

## Consequences

- Significant scope removed from v2: no workspaces, teams, guests, or share links.
- Authorization becomes structurally enforced rather than conventionally enforced.
- Anything genuinely needing an unauthenticated link (a customer-facing timeline)
  is deferred to v3 and would need its own scoped, expiring token design.
