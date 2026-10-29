"""The `pip-audit` ratchet's three failure modes, each exercised in both directions.

D-207's npm gate was trusted only after both of its modes were exercised; this
is that, as tests rather than by hand, because the tree now has a test suite for
it to live in. Nothing here runs `pip-audit` -- `conftest.no_live_network` would
fail the test if it tried, correctly -- so every case feeds `evaluate` a report
in the shape the real tool produces.

The `brotli` report below is **captured output**, not an invented fixture: it is
what `pip-audit --format json` returned for `brotli==1.2.0` on 2026-10-29, which
is the advisory D-223 took. Keeping a real one is what proves the parser reads
the fields the tool actually emits rather than the fields it was assumed to.
"""

from __future__ import annotations

from typing import Any

from tools.pip_audit_gate import (
    ALLOWED,
    Allowlisted,
    advisories_from_report,
    evaluate,
    render,
)

# Captured from `uv run pip-audit -r <brotli==1.2.0> --no-deps --format json`.
CAPTURED_BROTLI: dict[str, Any] = {
    "dependencies": [
        {
            "name": "brotli",
            "version": "1.2.0",
            "vulns": [
                {
                    "id": "PYSEC-2026-4322",
                    "fix_versions": ["1.2.1"],
                    "aliases": ["CVE-2026-111497"],
                    "description": "Out-of-bounds write in Google's Brotli decoder.",
                }
            ],
        }
    ]
}

NO_FIX_ANYWHERE: dict[str, Any] = {
    "dependencies": [
        {
            "name": "someplugin",
            "version": "1.0.0",
            "vulns": [{"id": "PYSEC-9999-1", "fix_versions": [], "aliases": []}],
        }
    ]
}


def allowlist(advisory_id: str) -> dict[str, Allowlisted]:
    return {
        advisory_id: Allowlisted(
            package="someplugin",
            reviewed="2026-10-29",
            why="Reached only by a dev-group tool; nothing in the shipped image imports it.",
        )
    }


def test_the_parser_reads_the_fields_pip_audit_actually_emits() -> None:
    found = advisories_from_report(CAPTURED_BROTLI)

    assert len(found) == 1
    advisory = found[0]
    assert advisory.id == "PYSEC-2026-4322"
    assert advisory.package == "brotli"
    assert advisory.version == "1.2.0"
    assert advisory.fix_versions == ("1.2.1",)
    assert advisory.aliases == ("CVE-2026-111497",)
    assert advisory.has_fix is True


def test_a_clean_tree_passes() -> None:
    verdict = evaluate(advisories_from_report({"dependencies": []}), {})

    assert verdict.ok
    assert "0 advisory, all accounted for" in "\n".join(render([], verdict, {}))


def test_an_advisory_with_no_entry_blocks() -> None:
    """Failure mode 1: the wall, kept, because there is no severity to narrow it."""
    found = advisories_from_report(CAPTURED_BROTLI)
    verdict = evaluate(found, {})

    assert not verdict.ok
    assert [advisory.id for advisory in verdict.unexpected] == ["PYSEC-2026-4322"]
    report = "\n".join(render(found, verdict, {}))
    assert "BLOCKING" in report
    assert "no entry in" in report


def test_an_allowlisted_advisory_that_no_longer_appears_blocks() -> None:
    """Failure mode 2: D-207's ratchet, the mode that emptied the npm allowlist."""
    verdict = evaluate([], allowlist("PYSEC-9999-1"))

    assert not verdict.ok
    assert verdict.stale == ("PYSEC-9999-1",)
    assert "must not outlive the problem" in "\n".join(
        render([], verdict, allowlist("PYSEC-9999-1"))
    )


def test_an_allowlisted_advisory_that_gains_a_fix_blocks() -> None:
    """Failure mode 3, which the npm gate cannot express: take the fix, drop the entry.

    This is D-220's and D-223's hand-applied rule mechanised -- an entry is for an
    advisory with nothing to upgrade to.
    """
    found = advisories_from_report(CAPTURED_BROTLI)
    allowed = allowlist("PYSEC-2026-4322")
    verdict = evaluate(found, allowed)

    assert not verdict.ok
    assert [advisory.id for advisory in verdict.fixable] == ["PYSEC-2026-4322"]
    assert verdict.unexpected == ()
    assert "now has a published fix" in "\n".join(render(found, verdict, allowed))


def test_an_allowlisted_advisory_with_no_fix_anywhere_passes() -> None:
    """The one state an entry exists for, and the only one that is allowed to pass."""
    found = advisories_from_report(NO_FIX_ANYWHERE)
    allowed = allowlist("PYSEC-9999-1")
    verdict = evaluate(found, allowed)

    assert verdict.ok
    report = "\n".join(render(found, verdict, allowed))
    assert "allowed" in report
    assert "no fix published" in report
    assert "reviewed 2026-10-29" in report
    assert "1 advisory, all accounted for" in report


def test_one_advisory_against_two_packages_is_one_allowlist_entry() -> None:
    """The allowlist's unit is the advisory; the report's unit is the finding."""
    two_packages: dict[str, Any] = {
        "dependencies": [
            {
                "name": "second",
                "version": "2.0.0",
                "vulns": [{"id": "PYSEC-9999-1", "fix_versions": [], "aliases": []}],
            },
            {
                "name": "first",
                "version": "1.0.0",
                "vulns": [{"id": "PYSEC-9999-1", "fix_versions": [], "aliases": []}],
            },
        ]
    }
    found = advisories_from_report(two_packages)

    assert [advisory.package for advisory in found] == ["first", "second"], "sorted for stability"
    assert evaluate(found, allowlist("PYSEC-9999-1")).ok


def test_every_shipped_entry_carries_a_reason_and_a_date() -> None:
    """Trivially true while `ALLOWED` is empty, and the guard that matters when it is not.

    `tools/pip_audit_gate.py` says nothing may be added without the reason it is
    safe in this deployment. This is that sentence as a test, so an entry added
    with an empty `why` fails the build rather than reading as considered.
    """
    for advisory_id, entry in ALLOWED.items():
        assert entry.why.strip(), f"{advisory_id} has no reason"
        assert entry.package.strip(), f"{advisory_id} names no package"
        assert len(entry.reviewed) == 10, f"{advisory_id} needs a YYYY-MM-DD review date"
