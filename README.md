# OppTrail

Timeline note-taking for sales opportunities. A deal is a record with a
history: every call, email, meeting and decision in the order it happened, with
notes, discussion and documents hanging off the moments that need them.

One FastAPI process serves the API and the statically built frontend. One
SQLite file. No broker, no worker, no second service — sized deliberately for
20 users and ~800,000 rows, and argued for in
[ADR 0001](docs/adr/0001-keep-sqlite.md).

## Run it

```bash
cp .env.example .env
./scripts/start_mac.sh        # or start_linux.sh / start_windows.ps1
```

Open <http://localhost:8000>. The container builds the frontend, migrates the
database on startup and needs no setup step; `./data` is bind-mounted for the
database, the uploads and the backups.

Set `OPENAI_API_KEY` in `.env` before using the AI panel — without it the panel
answers 503 and names the setting rather than failing obscurely. Optional:
`OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, `OPENAI_TIMEOUT_SECONDS`,
`OPENAI_MAX_RETRIES`, `ENVIRONMENT`, `PORT`. `docs/operations.md` has the rest.

Set `ADMIN_EMAILS` to the addresses that may define custom fields and write
automation rules. Empty means nobody, so those two screens tell every user to
ask an administrator until it is set.

Stop it with `./scripts/stop_mac.sh`.

## Try it with data in it

```bash
make seed           # five deals, four users, every feature and permission pair
make seed-scale     # the same, plus ~805,000 rows around it (11s)
```

`make seed` prints the sign-in details and a walkthrough: who can see what,
which deal is stalled, which note was edited, where the sealed entry is, and a
search that returns a different result for each of the four users. It refuses
to seed a database that already has users unless you pass `--force`.

## What it does

- **A timeline per deal** — nine entry types, each with a date it *happened*
  that is editable and a date it was written that is not. Notes on entries,
  one-level threaded comments on notes, reactions, and resolvable threads.
- **Four views over one list** — board, list, table, calendar — with filters,
  sorting and saved views that live in the URL, so a view is a link.
- **Sharing** with three roles, where a deal you cannot see answers as though
  it does not exist.
- **Privacy** in two shapes: an entry sealed to its author (not even the
  owner), and a private notebook per person per deal.
- **Tasks** with several assignees and their own discussion; **attachments**
  stored by content hash with sniffed types; **full-text search** across
  everything you can read.
- **Six reports**, computed live, where a number that cannot be computed says
  so instead of showing zero.
- **Automations**: one trigger, flat conditions, one action — always
  dry-runnable, acting with its creator's authority, and structurally unable to
  trigger another rule.
- **An AI panel** that answers from one deal's timeline, cites the entry
  numbers printed on the cards, and **cannot write** — the connection it uses
  refuses writes ([ADR 0012](docs/adr/0012-ai-boundary.md)).
- **Undo instead of confirmations.** Nothing is hard-deleted and no edit
  overwrites what it replaced; a deal's Activity dialog is the history, with a
  Restore on any earlier version.

## Documentation

| Document | For |
|---|---|
| [docs/user-guide.md](docs/user-guide.md) | using the app |
| [docs/operations.md](docs/operations.md) | running it: the volume, backups, restores, the probes |
| [docs/api.md](docs/api.md) | calling the API: auth, pagination, errors, permissions |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how it is built, with the data model and the authorization, real-time and AI boundaries |
| [docs/adr/README.md](docs/adr/README.md) | the twelve decisions and what was amended |
| [CHANGELOG.md](CHANGELOG.md) | what shipped, by phase |
| [AGENTS.md](AGENTS.md) | the requirements and the standards this is held to |
| [CLAUDE.md](CLAUDE.md) | what to know before changing the code |

## Development

```bash
make check-fast   # lint, types, backend and frontend tests, API contract
make check        # the full gate: the above, audits, and Playwright end-to-end
make e2e          # Playwright only
make seed         # demo data
make backup       # a VACUUM INTO snapshot, uploads included
make reindex      # rebuild the search index from the source tables
```

`make check` leaves out the three steps that need a Docker socket —
`make docker`, `make docker-test` (the backend suite inside the image) and
`make docker-smoke`. `.github/workflows/ci.yml` runs all of it.

The backend is Python 3.13 with `uv`, raw `sqlite3` and Alembic; the frontend is
React with TanStack Query, built by Next.js as a static export. Read
`CLAUDE.md` before changing either — several things that look accidental are
load bearing, and it says which.
