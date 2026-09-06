# 0004. In-process scheduler with a durable job table

Status: Accepted (v2)

## Context

v2 needs recurring and deferred work: email digests, follow-up reminders, stalled
detection, inbound email polling (ADR 0009), and AI weekly digests. There is no job
mechanism today and nothing runs on a schedule.

## Options

1. **Celery + Redis** (or RQ, or Dramatiq). Industry standard, horizontally
   scalable, and adds a broker plus a worker process to the deployment.
2. **APScheduler in the FastAPI process**, backed by a `jobs` table for durability.
3. **Host cron** invoking a management command.

## Decision

**Option 2.** A broker is unjustifiable for a 20-user, single-container app; it
would double the operational surface to schedule a handful of periodic tasks. Option
3 splits logic across the container boundary and is awkward to test.

Concretely: APScheduler started in the FastAPI `lifespan`, with an `outbox` table
for anything that must not be lost (outbound email, inbound email processing).
Jobs claim rows with a status transition so a restart mid-job retries rather than
drops. Periodic jobs are idempotent and safe to re-run.

Keep job functions free of framework coupling so they stay directly testable.

## Consequences

- No broker, no worker container, no separate deploy unit.
- Jobs die with the process; the `outbox` table plus idempotent periodics is the
  recovery mechanism, not in-memory state.
- This is the second decision (with ADR 0003) that assumes exactly one application
  instance. If that changes, both need revisiting — APScheduler would double-run
  every periodic job across instances.
