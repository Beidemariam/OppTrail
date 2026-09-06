# 0003. Server-Sent Events for live updates; no presence

Status: Accepted (v2)

## Context

Today there is no live update at all. `PLAN.md:22-24` promised polling; it was never
built, so two colleagues on one opportunity do not see each other's writes without
pressing Refresh.

Target concurrency is 2-3 users on an opportunity.

## Options

1. **Polling** on an interval. Trivial, no new transport, wasteful and laggy.
2. **SSE** — one long-lived `GET /api/opportunities/{id}/events`, server pushes
   invalidation messages. One-directional, plain HTTP, works through the existing
   single FastAPI process.
3. **WebSockets** — bidirectional, needed for presence and cursors.

## Decision

**Option 2, SSE**, carrying *invalidation* events rather than payloads: the server
emits `{"type": "timeline.changed", "opportunity_id": N}` and the client refetches
through its normal data layer (ADR 0005). This keeps one source of truth for data
shape and avoids reimplementing authorization in a push path.

**No presence, no live cursors, no collaborative text editing** in v2. At 2-3
concurrent users, presence is decoration; co-editing is explicitly excluded by
`AGENTS.md`.

## Conflict model

Last-write-wins with an **edit guard**, not CRDTs or OT. Notes already have full
version history (`note_versions`), so a clobbered edit is recoverable. On note
update the client sends the `updated_at` it read; the server rejects with 409 if it
has moved, and the UI offers to reload. Comments are immutable, entries are rarely
co-edited.

## Consequences

- No message broker. Events are published in-process to subscriber queues; with one
  container this is sufficient and is exactly the assumption ADR 0001 already makes.
- Each SSE connection holds a worker slot. At 20 users this is fine; it is another
  reason the deployment stays single-instance.
- If the app ever runs multiple instances, SSE fan-out needs a shared bus. Same
  trigger as ADR 0001, and they should move together.
