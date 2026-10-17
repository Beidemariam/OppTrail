# Architecture decisions

Twelve records, each written when the decision was taken rather than
reconstructed afterwards. They hold the *why*, including the alternatives that
were weighed and rejected; `docs/autopilot/DECISIONS.md` holds the smaller
rulings that did not need a record of their own.

An ADR here is amended rather than rewritten when implementation finds
something the decision did not anticipate — two of them carry amendment
sections, and those are the most useful paragraphs in this directory.

| # | Decision | Status |
|---|---|---|
| [0001](0001-keep-sqlite.md) | Keep SQLite; do not migrate to Postgres | Accepted |
| [0002](0002-adopt-alembic.md) | Adopt Alembic for schema migrations | Accepted, implemented |
| [0003](0003-realtime-sse.md) | Server-Sent Events for live updates; no presence | Accepted, implemented (3.4) |
| [0004](0004-background-jobs.md) | In-process scheduler with a durable job table | Accepted, implemented (6.5) |
| [0005](0005-frontend-data-layer.md) | Client-side SPA with TanStack Query; keep the static export | Accepted, implemented |
| [0006](0006-custom-field-storage.md) | Custom fields: definition table plus a JSON value column | Accepted, implemented (6.1) |
| [0007](0007-full-text-search.md) | SQLite FTS5 over a contentless table | Accepted, implemented |
| [0008](0008-file-storage.md) | Attachments on the local filesystem, streamed through the API | Accepted, **amended** (4.3) |
| [0009](0009-inbound-email.md) | Inbound email via IMAP polling, addressed by signed token | Accepted, **deferred to v3** (D-141) |
| [0010](0010-authorization-boundary.md) | No workspace hierarchy; enforce authorization in one dependency | Accepted, implemented |
| [0011](0011-single-container-deployment.md) | Keep the single-container deployment; add backups and a healthcheck | Accepted, **amended** (R.4) |
| [0012](0012-ai-boundary.md) | Keep the AI read-only by construction; treat all context as untrusted | Accepted, implemented |

## The three that shape everything else

**0001 — SQLite.** Twenty users, 400 opportunities, 2–3 concurrent, ~800,000
rows. That measurement is why there is no Postgres, no broker, no job queue, no
object storage and no multi-tenancy, and every proposal to add infrastructure
has to argue against those figures rather than against a hypothetical future.
It also names its own trigger: multiple writers, or no local disk.

**0010 — one authorization boundary.** Every route resolves a role from the
database through `permissions.py`; absence of access is a 404. There is no
workspace, team or tenant above an opportunity, which is what keeps the rule
small enough to be checked by a test matrix of every endpoint against every
kind of actor.

**0012 — the AI cannot write.** Not by instruction but by construction: the
connection is opened with `PRAGMA query_only = ON`, so SQLite itself raises on
any write from that path, and no tool surface is exposed to the model. Its
context labels every piece of user-supplied text as untrusted.

## Where each was amended, and why that matters

**0008** chose a polymorphic `entity_type`/`entity_id` parent for attachments
and a random stored filename. Implementation chose `entry_id` and content
addressing instead — a single foreign key keeps the delete cascade one
statement, and a SHA-256 name deduplicates two uploads of one file. Both
changes are in the amendment with their reasoning.

**0011** asked for a `HEALTHCHECK` against `/api/health`. R.4 found that
endpoint answers 200 while reporting `database_writable: false` — it is a
report, not a verdict — so a healthcheck pointed there would call a read-only
disk healthy. The healthcheck reads `/readyz` instead, and the amendment says
so.
