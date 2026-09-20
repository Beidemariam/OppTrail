# Blockers

Unresolvable issues, with what was tried, go here. Per brief §3.3: log a repeated
failure after three attempts with no new information, or set `BLOCKED` when no
milestone in the current phase can proceed.

None yet — Phase F's first milestone (reconnaissance) completed without a
blocker.

Known, expected, non-blocking constraint (not logged as a blocker because it is
by design, not a failure): per brief §3.4 and `sandbox/README.md`, this sandbox
has no Docker socket, so the Docker-build-and-smoke-test portion of `make check`
cannot run here. It is deferred to the human's `scripts/autopilot-gate.sh`, as
the brief's split-gate section requires, and will be named explicitly in each
phase's review packet rather than silently skipped. Milestone 1.1 (GitHub
Actions CI) extended this to a new `make docker-test` target and a `docker`
job in `.github/workflows/ci.yml` — both unverified in this sandbox for the
same reason, now also run by `scripts/autopilot-gate.sh` on the host.

Non-blocking tooling gap, milestone 1.1: no YAML parser was installable in
this sandbox to lint `.github/workflows/ci.yml` (`python3` has no `yaml`
module and `pip`/network are unavailable per the egress allowlist; no
`js-yaml` package exists in `frontend/node_modules`). Checked instead by hand
against GitHub Actions' documented syntax, plus a script confirming no tab
characters and consistent indentation. Did not block the milestone — logged
so a reviewer knows this file's YAML syntax specifically wasn't
machine-verified before commit.

## Phase 1 rework 1 — RESOLVED 2026-09-20

The entry that stood here recorded one known, diagnosed host-gate failure held
open pending a human ruling on D-045 (the shipped image's SQLite being three
versions behind everywhere the code is developed). **The human ruled option
(a) on 2026-09-20 and it is implemented**: `Dockerfile`'s two base images moved
`bookworm-slim` → `trixie-slim`, which ships SQLite 3.46.1.

`tests/test_search.py::test_search_reads_the_index_and_never_scans_a_source_table`
and `tests/test_health.py::test_health_reports_unwritable_when_the_database_file_is_read_only`
now both pass inside the image, with neither assertion modified — the first
because the planner change that broke it predates 3.46, the second because of
this rework's non-root `app` user (D-044). The empirical check the sandbox
could not run (no Docker socket, no root to install a second SQLite build) was
run on the host instead: a `backend-test` image on `trixie` passes all 258
backend tests, and the three WeasyPrint packages install under the same names.

No blockers are open.
