# Coverage History

Coverage floors (brief §6.2, never lowered): backend ≥ 90% line / ≥ 80% branch;
auth, permissions, soft-delete, audit, and AI-agent modules ≥ 95% branch; frontend
≥ 80% line. `AGENTS.md`'s own bar (backend integration ≥ 90%, frontend unit ≥ 70%)
is looser than the brief's; the brief's floor governs per the source-of-truth
hierarchy (higher item wins — but note the brief is item 6, lowest-ranked, so
where `AGENTS.md` sets a *stricter* number than the brief, as it does for backend
line coverage — 90% either way here, no conflict — the stricter of the two always
applies; call out any future case where they actually diverge).

## Phase F — baseline (pre-milestone-work), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-report=term-missing`,
run inside the sandbox (WeasyPrint's native libraries are present here, unlike a
macOS host — see `CLAUDE.md`).

```
39 passed in 14.62s
TOTAL: 1032 stmts, 44 miss, 96% line coverage
```

No branch-coverage figure yet — `pytest-cov` was run without `--cov-branch`; add
it once `make check` exists (Phase F milestone F.2) so branch coverage is
tracked from the same baseline going forward.

| Module | Line % | Notes |
|---|---|---|
| `permissions.py` | 100% | already meets the ≥95% floor for permission-critical modules |
| `audit_utils.py` | 100% | already meets the ≥95% floor |
| `timeline_utils.py` | 100% | |
| `routes_ai.py` | 100% | |
| `routes_auth.py` | 100% | |
| `routes_export.py` | 100% | |
| `routes_notifications.py` | 100% | |
| `schemas.py` | 98% | |
| `export_service.py` | 99% | |
| `routes_sharing.py` | 95% | |
| `auth.py` | 97% | auth-critical module; already at the ≥95% floor, keep it there as sessions/rotation/CSRF work lands in F.5 |
| `notification_service.py` | 97% | |
| `database.py` | 94% | |
| `main.py` | 93% | |
| `routes_timeline.py` | 94% | |
| `routes_opportunities.py` | 92% | |
| `time_utils.py` | 86% | `parse_timestamp` (lines 22-23) is unreferenced by any current caller |
| `ai_service.py` | 82% | the live `ask_openai` call itself and a couple of context-building edge branches are unexercised (mocked in tests by design, per brief §4.6) |

Frontend: no test runner exists yet (0% by absence, not by failing tests).
Standing one up is Phase F milestone F.7.

Full detail: `docs/autopilot/INVENTORY.md` §7.

## Phase F — after milestone F.2 (Tooling and structure), 2026-09-16

Command: `cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`
(now wired into `make check-fast` / `make check`), run inside the sandbox.

```
47 passed in 15.87s
TOTAL: 1126 stmts, 43 miss, 172 branches, 34 partial, 94% combined line+branch coverage
Required test coverage of 90% reached. Total coverage: 94.07%
```

47 tests, up from 39: +1 permission-consolidation regression test
(`test_shared_editor_can_view_but_not_mutate_opportunity`), +2 error-envelope
tests (`test_error_handling.py`), +2 auth-branch tests (expired-session,
logout-without-cookie), +3 settings fail-fast-validation tests
(`test_settings.py`). All new tests were confirmed to fail against the
pre-fix code first, per brief §6.5's guard-test rule.

`--cov-branch` is now part of the standard command (COVERAGE.md's prior baseline
noted this as a to-do for F.2 — done). The `Cover` column below is combined
statement+branch coverage (pytest-cov does not report a branch-only percentage
separately); it is the practical proxy used for the brief §6.2 branch floors.

| Module | Combined line+branch % | Notes |
|---|---|---|
| `auth.py` | 100% | was 93% before this milestone (missing the expired/unknown-session branch and the no-cookie logout branch) — now closes brief §6.2's ≥95% floor for auth-critical modules |
| `permissions.py` | 100% | already met the ≥95% floor; unchanged |
| `audit_utils.py` | 100% | already met the ≥95% floor; unchanged |
| `errors.py` | 100% | new module (F.2) |
| `logging_utils.py` | 100% | new module (F.2) |
| `routes_ai.py` | 100% | new `logger.warning` call on OpenAI failure (F.2) is exercised by the existing `test_ai_returns_helpful_errors` |
| `routes_export.py` | 100% | |
| `routes_auth.py` | 100% | |
| `routes_notifications.py` | 100% | |
| `export_service.py` | 97% | |
| `notification_service.py` | 96% | |
| `schemas.py` | 98% | |
| `routes_timeline.py` | 91% | mostly 404 branches for missing entries/notes/comments |
| `main.py` | 91% | |
| `routes_sharing.py` | 90% | |
| `database.py` | 88% | |
| `time_utils.py` | 88% | `parse_timestamp` still unreferenced — candidate for F.8 |
| `settings.py` | 100% | both fail-fast validators' error branches now covered (`test_settings.py`) |
| `routes_opportunities.py` | 89% | |
| `ai_service.py` | 79% | **below the ≥95% floor brief §6.2 sets for AI-agent modules.** The live `ask_openai` call and several context-building edge branches are unexercised by design (mocked in tests, brief §4.6) — closing this is Phase F milestone F.6's explicit scope ("Single OpenAI client wrapper with timeouts, retries, and graceful failure... always mocked in tests"), not F.2's. Logged here so the gap is visible rather than silently carried forward. |

Frontend: still 0% (no test runner) — unchanged from baseline; F.7's scope.

New tooling this milestone: `ruff check`, `ruff format --check`, and `mypy
--strict app/` are now all green (`backend/pyproject.toml` `[tool.ruff]` /
`[tool.mypy]`), and `pip-audit` / `npm audit` both report zero known
vulnerabilities (weasyprint bumped 69.0 → 70.0 to clear PYSEC-2026-3940, a
`url_fetcher`-bypass finding that does not apply to OppTrail's usage — no
`xmp_metadata=`/`stylesheets=` arguments are ever passed — but the fix was a
trivial, safe version bump so it was taken anyway).
