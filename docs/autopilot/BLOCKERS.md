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
phase's review packet rather than silently skipped.
