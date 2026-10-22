"""What the app costs at the scale it is sized for (milestone R.3).

`AGENTS.md`'s Confirmed Scale — 400 opportunities, ~200 entries each, roughly
800,000 rows — is the figure every infrastructure decision in this project was
argued against. Milestone 6.2 measured the six dashboard aggregates against a
corpus that size (**D-172**) and found three of them over budget. This suite
asks the same question of **the reads a person waits on**: the board, a deal's
timeline, search, the activity log, the inbox, the export.

Three things about how it measures:

- **Through the real HTTP stack**, not against the helper functions, because
  what a reader waits for includes serialization, the permission resolution
  and the per-page child fetches — and those are where a read of this shape
  goes wrong.
- **As two different readers.** The owner's read is the widest answer;
  a shared editor's is the one that resolves a role and filters sealed
  entries (R.1b). A budget met only by the owner is not met.
- **The budget is per read, and reported with its margin.** The number is
  loose enough to survive a loaded laptop and tight enough to catch a
  formulation that regresses by an order of magnitude — the same bargain
  `test_each_aggregate_answers_inside_the_budget` makes, for the same reason.
"""

import os
import time

from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import db_connection
from tools.scale import build_scale_corpus

#: `AGENTS.md`'s own arithmetic: 400 deals, ~200 entries each.
OPPORTUNITIES = 400
ENTRIES = 80_000

#: Multiplier for the budgets below, for hardware this project did not choose.
#:
#: Measured, `search` costs ~166 ms on a developer machine and **425-459 ms**
#: on a GitHub runner -- about 2.7x, on a network-backed disk shared with
#: whoever else is on the host. That failed 2 of 3 CI runs, and because this
#: suite is in `make check-fast` it aborted the run before the Playwright
#: suite ever started: a gate that fails half the time on the hardware rather
#: than the code is a gate people learn to ignore.
#:
#: Two things this is deliberately **not**. It is not a raised budget: 400 ms
#: stays asserted where the hardware is known, which is a developer machine
#: and `scripts/autopilot-gate.sh`'s in-image run, so the number that matters
#: is still checked before anything is accepted. And it is not a free pass --
#: the scale is printed with the measurements and named in the failure, so a
#: scaled run cannot be read as an absolute one.
#:
#: The cost is honest and worth stating: at the CI scale a genuine 2x
#: regression in `search` would pass there and be caught only by the host
#: gate. Removing that gap means calibrating against a reference workload
#: rather than scaling, which is more machinery than a 20-user app needs
#: today; the cutover point is the first regression this lets through.
#: `or "1"` rather than a plain default: an environment that sets this to
#: the empty string would otherwise fail the whole suite on a ValueError
#: before a single test ran, which is the shape of defect an empty
#: `FORECAST_PROBABILITIES=` already has in `.env.example`.
BUDGET_SCALE = float(os.environ.get("PERF_BUDGET_SCALE") or "1")

#: What a reader waits for, in milliseconds. One number for a page read, and
#: a wider one for the two reads that are deliberately not paginated — the
#: export walks a whole deal and the dashboard answers six aggregates.
PAGE_BUDGET_MS = 400.0 * BUDGET_SCALE
WHOLE_DEAL_BUDGET_MS = 3_000.0 * BUDGET_SCALE


def measure(call) -> tuple[float, object]:
    started = time.perf_counter()
    result = call()
    return (time.perf_counter() - started) * 1000, result


def build() -> object:
    with db_connection() as connection:
        facts = build_scale_corpus(
            connection,
            opportunities=OPPORTUNITIES,
            entries=ENTRIES,
            readers=20,
            shares=True,
            private_every=20,
            notes=ENTRIES,
            comments=ENTRIES * 2,
            tasks=4_000,
            notifications=160_000,
        )
    return facts


def test_the_reads_a_person_waits_on_are_inside_budget(client: TestClient) -> None:
    """Every paginated read, measured at the confirmed scale.

    The corpus is built with raw inserts rather than through the API — 800,000
    rows through HTTP is not a fixture, it is an afternoon — so its users have
    no usable password. Two of them get one here, which is the only thing a
    raw-insert corpus cannot fake: a login.
    """
    facts = build()
    assert facts.rows >= 800_000, f"corpus smaller than the confirmed scale: {facts.summary()}"

    with db_connection() as connection:
        for user_id, email in ((1, "owner@example.com"), (2, "reader@example.com")):
            connection.execute(
                "UPDATE users SET email = ?, password_hash = ? WHERE id = ?",
                (email, hash_password("scale-password-1"), user_id),
            )
        connection.commit()

    def login(email: str) -> None:
        client.post("/api/v2/auth/logout")
        response = client.post(
            "/api/v2/auth/login",
            json={"email": email, "password": "scale-password-1"},
        )
        assert response.status_code == 200, response.text

    login("owner@example.com")
    first_page = client.get("/api/v2/opportunities?limit=50")
    assert first_page.status_code == 200
    deal_id = first_page.json()["items"][0]["id"]

    measurements: dict[str, float] = {}

    def record(name: str, path: str, expected: int = 200) -> None:
        elapsed, response = measure(lambda: client.get(path))
        assert response.status_code == expected, (name, response.status_code, response.text[:200])
        measurements[name] = elapsed

    record("board first page", "/api/v2/opportunities?limit=50")
    record("timeline first page", f"/api/v2/opportunities/{deal_id}/timeline?limit=50")
    record("search", "/api/v2/search?q=entry&limit=50")
    record("activity log", f"/api/v2/opportunities/{deal_id}/activity?limit=50")
    record("my tasks", "/api/v2/tasks?limit=50")
    record("inbox", "/api/v2/notifications?limit=50")
    record("members", f"/api/v2/opportunities/{deal_id}/members?limit=50")
    record("health", "/api/health")

    # The whole board, which is what the frontend actually reads: `fetchAll`
    # walks `next_cursor` to the last page (D-093), so the number that matters
    # is the sum of every request, not the first one.
    def walk_board() -> int:
        cursor = None
        pages = 0
        while True:
            params = {"limit": 50} | ({"cursor": cursor} if cursor else {})
            payload = client.get("/api/v2/opportunities", params=params).json()
            pages += 1
            cursor = payload["next_cursor"]
            if cursor is None:
                return pages

    walked_ms, pages = measure(walk_board)
    measurements[f"whole board ({pages} pages)"] = walked_ms

    # And the same reads as somebody the deals are shared with, which is the
    # path that resolves a role and filters sealed entries.
    login("reader@example.com")
    record("board first page (shared reader)", "/api/v2/opportunities?limit=50")
    record(
        "timeline first page (shared reader)", f"/api/v2/opportunities/{deal_id}/timeline?limit=50"
    )
    record("search (shared reader)", "/api/v2/search?q=entry&limit=50")

    login("owner@example.com")
    elapsed, response = measure(lambda: client.get(f"/api/v2/opportunities/{deal_id}/export/json"))
    assert response.status_code == 200
    measurements["export one deal (json)"] = elapsed

    elapsed, response = measure(lambda: client.get("/api/v2/dashboard"))
    assert response.status_code == 200
    measurements["dashboard (six aggregates)"] = elapsed

    # Printed as well as asserted: the numbers are the point of this test, and
    # a run that passes should still say what it measured (`pytest -s`).
    print(f"\nmeasured at {facts.summary()}")
    if BUDGET_SCALE != 1.0:
        # Said out loud, so a scaled run is never mistaken for an absolute
        # one when somebody reads the log.
        print(
            f"  budgets scaled x{BUDGET_SCALE:g} via PERF_BUDGET_SCALE "
            f"(page {PAGE_BUDGET_MS:.0f} ms, whole-deal {WHOLE_DEAL_BUDGET_MS:.0f} ms)"
        )
    for name, elapsed in measurements.items():
        print(f"  {name:<44} {elapsed:7.1f} ms")

    wide = {"export one deal (json)", "dashboard (six aggregates)"}
    over = {
        name: round(ms, 1)
        for name, ms in measurements.items()
        if ms >= (WHOLE_DEAL_BUDGET_MS if name in wide else PAGE_BUDGET_MS)
    }
    report = {name: round(ms, 1) for name, ms in measurements.items()}
    scale = "" if BUDGET_SCALE == 1.0 else f" (budgets scaled x{BUDGET_SCALE:g})"
    assert not over, f"over budget at {facts.summary()}{scale}: {over}; all of them: {report}"
