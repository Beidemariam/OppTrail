# Running OppTrail

Milestone R.5. What a person operating this deployment needs: where the data
lives, how it is backed up, how to put it back, and what the probes mean.
R.8 extends this file with the rest of the operations documentation; the
backup and restore procedure is here because R.5 is where it was finished and
exercised.

## One volume

Everything stateful is under `/data`, which the run scripts bind-mount from
`./data` beside the repository:

```
/data
├── app.db              the database (ADR 0001: SQLite, WAL mode)
├── app.db-wal          WAL sidecar — part of the database, never copied alone
├── app.db-shm          shared-memory index, recreated on open
├── attachments/        uploaded files, content addressed (ADR 0008)
│   └── ab/abcdef…      the first two characters of the SHA-256 shard it
└── backups/
    ├── app-<stamp>.db  VACUUM INTO snapshots, newest `BACKUP_RETENTION_COUNT` kept
    └── attachments/    one mirror of every blob, never pruned (R.5)
```

Three things about this layout are deliberate:

- **The container writes nowhere else.** It runs as uid 1000 and `/data` is
  the only path it needs write access to (ADR 0011 item 5), so a host
  directory writable by that uid is the whole setup step.
- **`attachments/` sits beside the database rather than in a second mount**,
  so a container recreate cannot lose the blobs while keeping the rows.
- **`backups/` is on the same volume as what it backs up.** This protects
  against the failure this app can actually cause — a bad write, a mistaken
  delete, a migration gone wrong — and *not* against losing the disk. Copying
  snapshots off the host is the operator's job and nothing here pretends
  otherwise.

## Backups

A snapshot is taken automatically every `BACKUP_INTERVAL_HOURS` (default 24)
by the scheduler inside the process (ADR 0004, milestone 6.5), and
`make backup` takes one by hand. Both run the same code.

```bash
make backup     # VACUUM INTO a timestamped snapshot, then mirror new uploads
```

- **`VACUUM INTO`, not a file copy.** It writes a consistent snapshot while
  the application keeps serving; copying `app.db` can capture a torn WAL
  checkpoint and produce a file that opens but is wrong.
- **Uploads are part of it** (R.5, ADR 0011 item 2). Blobs are content
  addressed, so `backups/attachments/` is one mirror rather than a copy per
  snapshot, and a backup copies in only the digests the mirror does not
  already hold.
- **Retention applies to the database snapshots only** — the newest
  `BACKUP_RETENTION_COUNT` (default 7, a week at the default interval). The
  blob mirror is never pruned: deleting an attachment in the app is soft and
  undoable and never removes the file, so any retained snapshot may reference
  any digest that has ever existed.
- **`GET /api/health` reports `last_backup_at`**, read from the newest
  snapshot's own filename, so "has this been backed up lately" is answerable
  without a shell.

## Restoring

**Stop the application first.** The restore deletes the WAL sidecars and
overwrites `app.db` in place; a running process must not race with that.

```bash
./scripts/stop_mac.sh                  # or stop_linux.sh
make restore BACKUP=data/backups/app-20261017T093012123456Z.db
./scripts/start_mac.sh
```

What it does, in order: delete `app.db-wal` and `app.db-shm` (stale WAL frames
replayed against a swapped-out main file are not safe), copy the snapshot over
`app.db`, then copy back any blob the live `attachments/` tree is missing. That
last step is why a restore is a restore rather than half of one — a recovered
row pointing at a file the volume lost answers a download with 404.

A blob already present is never overwritten: identical digests are identical
bytes.

`tests/test_backup.py` exercises the whole round trip, including losing a live
blob on purpose and getting it back, because ADR 0011 requires the restore to
be "actually exercised" rather than assumed.

## Seeding a demonstration or a load test

```bash
make seed           # five named deals, every feature, every permission pair
make seed-scale     # the same, then ~805,000 rows around it (11s, ~140 MB)
```

Both refuse to run on a database that already has users unless you pass
`--force`. `make seed` prints a walkthrough of what was created and who can
see what; `tests/test_seed.py` is what keeps those sentences true. The scale
corpus is the one `tests/test_performance.py` measures the read budgets
against, so a load test and a budget are talking about the same database.

## The probes

Three endpoints, three questions (R.4, D-203):

| Endpoint | Question | Answer |
|---|---|---|
| `GET /healthz` | Is the process answering? | 200, with no I/O at all |
| `GET /readyz` | Can it serve a request? | 200, or **503** if the database cannot take a write |
| `GET /api/health` | What state is the deployment in? | schema version, writability, last backup, the newest run of each job |

The container's `HEALTHCHECK` reads `/readyz`, because a healthcheck reads a
status code and `/api/health` answers 200 even while reporting a problem. Use
`/healthz` for liveness and nothing else: restarting a process does not empty
a full disk, and a liveness probe that reads the database would turn a
degraded deployment into a restart loop.

`docker ps` shows the result (`Up 2 minutes (healthy)`), and
`docker inspect <name> --format '{{json .State.Health}}'` shows the last few
checks with their output.

## Settings worth knowing

Read from `.env` at the repository root (`backend/app/settings.py` is the
complete list with defaults):

| Setting | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `/data/app.db` in the image | Where the database lives |
| `BACKUP_INTERVAL_HOURS` | 24 | How often the scheduler snapshots |
| `BACKUP_RETENTION_COUNT` | 7 | How many snapshots to keep |
| `SCHEDULER_ENABLED` | true | Turns off the in-process scheduler entirely |
| `ENVIRONMENT` | development | `production` sets `Secure` on the session cookie |
| `OPENAI_API_KEY` | — | Without it the AI panel answers 503 and says which setting is missing |
