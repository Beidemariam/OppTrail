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

## Amendment (milestone R.4, 2026-10-17)

Item 4 — "**`HEALTHCHECK`** in the Dockerfile against `/api/health`, and a
restart policy in the run scripts" — was unimplemented until R.4, while
`CLAUDE.md`, `docs/ARCHITECTURE.md` and **D-094** all referred to the
container's healthcheck as a thing that existed. Both halves are in now, with
one change to the detail (**D-203**):

- **The healthcheck reads `/readyz`, not `/api/health`.** A `HEALTHCHECK`
  reads its command's exit code and nothing else, and `/api/health` answers
  **200** with `database_writable: false` by design — it is a report, not a
  verdict. Pointed at it, the healthcheck would call a container with a
  read-only mount or a full disk healthy, which is precisely the failure this
  item exists to surface. `/readyz` answers the same question with a status
  code; `/api/health` keeps its richer body for a person or a dashboard.
- **`/healthz` is separate and does no I/O**, because liveness and readiness
  are different questions: restarting a process does not empty a disk, so a
  liveness probe that reads the database turns a degraded deployment into a
  restart loop.
- **`--timeout-graceful-shutdown 8`** on the `CMD`. ADR 0003's SSE streams are
  held open for up to 300 seconds and uvicorn's graceful shutdown waits for
  in-flight requests, so without a bound every `docker stop` with a reader
  connected would wait out Docker's 10-second patience and take a SIGKILL.
- **`--restart unless-stopped`** in all three run scripts.

`scripts/docker-smoke.sh` checks the two probes and waits for the container to
report `healthy`, so the gate now fails if any of this regresses — which is
the part that was missing the first time.
