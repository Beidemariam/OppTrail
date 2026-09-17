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
