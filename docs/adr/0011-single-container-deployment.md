# 0011. Keep the single-container deployment; add backups and a healthcheck

Status: Accepted (v2)

## Context

The app ships as one Docker image: a Next.js static export built in a first stage,
served by FastAPI alongside `/api/*`, with SQLite on a mounted `/data` volume.

The review found no backup, no WAL, no healthcheck, no restart policy, no logging,
and the container running as root.

## Decision

**The single container survives v2.** ADRs 0001, 0003 and 0004 all assume exactly
one application instance, and at 20 users nothing argues for more. One image, one
process, one volume, one origin — no CORS, no reverse proxy, no service discovery.

Fix the operational gaps rather than the architecture:

1. **WAL mode + busy timeout** at connection setup. Readers stop blocking on the
   writer, which is the only real contention at 2-3 concurrent users.
2. **Backups**: a scheduled job (ADR 0004) runs `VACUUM INTO` to produce a
   consistent snapshot of the database — safe while the app is running, unlike
   `cp` — plus a copy of `/data/attachments`, retained on a rolling window.
   **A restore procedure must be written and actually exercised**; an untested
   backup is not a backup.
3. **Structured logging** to stdout with a request ID, closing the review's H3.
   The AI route's bare `except Exception` (`routes_ai.py:43`) must log the cause.
4. **`HEALTHCHECK`** in the Dockerfile against `/api/health`, and a restart policy
   in the run scripts.
5. **Non-root user**; the process needs write access only to `/data`.
6. **`secure` cookie flag** driven by an environment setting, so it is on wherever
   the app is served over HTTPS.

## What would replace it

If ADR 0001's trigger fires (multiple writers, no local disk), the split is:
app container(s) → managed Postgres → object storage → a broker for SSE fan-out and
jobs. That is four services instead of one and should not be adopted until something
forces it.

## Consequences

- Deployment stays a `docker run` with one volume, matching the stated ops appetite.
- Single point of failure and no zero-downtime deploy. Both acceptable for an
  internal tool at this size; both should be stated plainly rather than discovered.
