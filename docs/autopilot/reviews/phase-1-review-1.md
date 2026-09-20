# Phase 1 — Review 1

Decision: REJECT
Date: 2026-09-20

## Feedback (address every item before returning to AWAITING_REVIEW)

The host gate failed. `make test-host` and the sandbox half of `make check` both
pass; the failure is in `make docker-test`, the in-image backend suite that
milestone 1.1 added. No gate receipt exists for `0f6cf17`, so the phase cannot
be accepted until this returns to `AWAITING_REVIEW` with a green host gate.

```
FAILED tests/test_health.py::test_health_reports_unwritable_when_the_database_file_is_read_only
FAILED tests/test_search.py::test_search_reads_the_index_and_never_scans_a_source_table
2 failed, 256 passed
```

Neither is a defect in Phase 1's features. Search and notifications work. Both
are environment divergence between where this code is developed and where it
ships, and the in-image stage is the only thing that looks at the latter.

**Do not resolve either of these by relaxing the assertion.** Both tests were
confirmed to fail against mutated code when they were written, and the
query-plan test caught a real regression during 1.4 that the latency test
missed. A test loosened to pass in two environments stops guarding either.

---

## 1. The production image runs as root

Measured:

```
app image (opptrail-gate-candidate:phase-1):  uid 0
sandbox image:                                 uid 501
developer host:                                the developer's own user
```

`Dockerfile` has no `USER` directive. The test chmods the database file, its
`-wal` sidecar and the containing directory to `0500` and expects
`BEGIN IMMEDIATE` to fail, so `/api/health` reports the database unwritable.
Root bypasses permission bits, so the write succeeds, health correctly reports
writable, and the assertion fails.

The test is right and the image is not yet hardened. `PROGRESS.md` milestone
**R.4** already lists "non-root user" as outstanding Phase R work; this test
found it early.

**Ruling: pull R.4's non-root user work forward into this rework.** Add a
non-root user to the `final` stage (and `backend-test`, so the suite runs as the
image does), make `/data` writable by it, and confirm the container still starts,
migrates, and serves. Remove the non-root item from R.4 and note where it moved.

Do not instead skip the test when `os.getuid() == 0`. That keeps a root
container and silently retires the assertion in the only environment that ships.

## 2. SQLite is three years older in the image than anywhere it is tested

Measured:

```
developer host:  3.53.1
sandbox image:   3.50.4
app image:       3.40.1    <- bookworm's system libsqlite3
```

Every `FROM` in `Dockerfile` pins `bookworm`. The query-plan test asserts
`EXPLAIN QUERY PLAN` output, and the planner changed between 3.40 and 3.50.

The failing test is the symptom. The finding is that this project develops and
tests on 3.50/3.53 and ships 3.40.1, while ADR 0001 (WAL, busy_timeout),
ADR 0007 (FTS5 and its query planning) and ADR 0006 (JSON1) all depend on SQLite
specifics. A three-version gap under those ADRs is the actual risk.

**This one needs a decision, not an implementation. Log it with
`needs human review: Y`, recommend an option, and stop — do not adopt one
unilaterally.** The options as they look from here:

- (a) Move the image to a base with a modern SQLite (a `trixie` base, or build
  SQLite in the image). Closes the gap in the direction of the version the ADRs
  were reasoned and benchmarked against. Costs a base-image change affecting
  every stage, and needs the WeasyPrint packages re-verified on the new base.
- (b) Pin development and the sandbox to bookworm's 3.40.1 so all three
  environments agree. Cheapest to reason about, but freezes the project on an
  older FTS5 and contradicts ADR 0007's benchmarks if they were taken on a newer
  engine — state whether they were.
- (c) Keep the gap and make the assertion version-aware. Rejected above; listed
  only so the decision records why.

Whichever is recommended, state explicitly which SQLite version ADR 0001's and
ADR 0007's benchmark numbers were measured on. If that was a newer engine than
the image ships, those numbers do not currently describe production, and that
belongs in the decision.

## 3. Add a guard so this class of gap fails loudly

Both of these were invisible to the sandbox gate because the sandbox happens to
be non-root on a newer SQLite. Milestone 1.1's in-image stage is the only reason
they surfaced at all, and only on a human's machine.

Add an assertion that the environments agree — for example, a test or a
`make check` step that fails when the image's SQLite version differs from the
one development runs against, naming both. The point is that the next
divergence announces itself rather than waiting for a query plan to change.

Record it in `DECISIONS.md` alongside D-030, which is the same failure mode one
layer out: a check that looked like it was verifying something while verifying
nothing.

---

## Definition of done for this rework

- `scripts/autopilot-gate.sh 1` passes on the host, including `make docker-test`,
  and writes a receipt.
- The non-root change is made and R.4 updated to say where it went.
- The SQLite decision is logged as `needs human review: Y` with a
  recommendation and the benchmark-version question answered, and is **not**
  implemented.
- Neither failing assertion has been weakened; both still fail against the code
  that would break them.
- `STATUS` returns to `AWAITING_REVIEW phase=1` with the review packet updated.
