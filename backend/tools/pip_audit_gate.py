"""`pip-audit` as a ratchet rather than a wall — the Python half of D-207.

`make check` has run bare `pip-audit` since R.6, and bare `pip-audit` exits
non-zero on any advisory with no way to record a decision about one. D-220 said
plainly that this is "a bare wall where npm has a ratchet": a Python advisory
with no upgrade available takes the build red with nowhere to write why it is
safe in this deployment, and the only two responses available were to leave the
gate red — which teaches everybody to ignore it — or to drop it. Three rounds of
advisories in eight days (D-220, D-223) made that a real cost rather than a
hypothetical one.

So this is `scripts/audit-gate.mjs`'s shape applied to the Python tree, with one
difference that the data forces and one that the data permits.

**Forced: there is no severity to filter on.** `pip-audit --format json` reports
`id`, `aliases`, `fix_versions` and `description` per advisory, and nothing
else — so where the npm gate blocks on `high` and `critical` and ignores the
rest, this one has to treat *every* advisory as blocking. That makes the
allowlist more load bearing here, not less: every advisory must either be fixed
or consciously written down.

**Permitted: `fix_versions` says whether a fix exists.** D-220 and D-223 both
had to apply the same rule by hand — an allowlist entry is for an advisory with
**no fix anywhere** (D-207's `braces`), never for one you could simply take —
and failure mode 3 below is that rule enforced mechanically. It is the check
that would have caught D-223's `zod` case without anybody noticing it.

Three failure modes rather than the npm gate's two:

  1. **An advisory with no allowlist entry fails.** The wall is kept, because
     there is no severity to narrow it with.
  2. **An allowlisted advisory that no longer appears also fails.** The ratchet
     tightens itself — an entry cannot outlive the problem it documents. This is
     the mode that emptied the npm allowlist in D-223, when the `braces`
     advisory was withdrawn upstream while the package sat unchanged.
  3. **An allowlisted advisory that has gained a fix fails.** An entry here
     means "there is nothing to take"; the moment there is something to take,
     the entry is the wrong answer and the upgrade is the right one.

Nothing may be added to `ALLOWED` without the reason it is safe *in this
deployment*, written out. "Transitive" is not a reason — most of what this tree
reports is transitive, and in D-223 fourteen of sixteen advisories were under
`cachecontrol` -> `pip-audit` itself, dev-group and never shipped, while the one
that mattered reached the image through `weasyprint`. So the reason has to name
reachability, and `uv tree --invert --package <name>` is how you establish it.
A runtime advisory in the PDF path gets verified with `make docker-test`, where
WeasyPrint imports, rather than on a host where that test skips.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

PIP_AUDIT = ("pip-audit", "--format", "json")


@dataclass(frozen=True)
class Allowlisted:
    """Why one advisory is tolerated here, and when somebody last checked."""

    package: str
    reviewed: str
    why: str


# `ALLOWED` is empty, and an empty allowlist is the honest starting state rather
# than a list nobody got round to writing: every advisory this tree has carried
# so far had a fix published, so every one was taken (D-220, D-223). The first
# entry will be the first advisory with nothing to upgrade to.
ALLOWED: dict[str, Allowlisted] = {}


@dataclass(frozen=True)
class Advisory:
    """One advisory against one installed package."""

    id: str
    package: str
    version: str
    fix_versions: tuple[str, ...]
    aliases: tuple[str, ...]

    @property
    def has_fix(self) -> bool:
        return bool(self.fix_versions)

    def describe(self) -> str:
        names = ", ".join((self.id, *self.aliases))
        fix = f"fix in {', '.join(self.fix_versions)}" if self.has_fix else "no fix published"
        return f"{self.package} {self.version}  {names}  ({fix})"


def advisories_from_report(report: dict[str, Any]) -> list[Advisory]:
    """Flatten pip-audit's per-dependency JSON into one advisory per finding.

    A dependency carries a `vulns` list, so the same advisory id can legitimately
    appear against two packages; each pairing is reported on its own line because
    the package and version are what a reader acts on. Identity for the allowlist
    is still the advisory id alone.
    """
    found = [
        Advisory(
            id=vulnerability["id"],
            package=dependency["name"],
            version=dependency["version"],
            fix_versions=tuple(vulnerability.get("fix_versions") or ()),
            aliases=tuple(vulnerability.get("aliases") or ()),
        )
        for dependency in report.get("dependencies") or ()
        for vulnerability in dependency.get("vulns") or ()
    ]
    return sorted(found, key=lambda advisory: (advisory.package, advisory.id))


@dataclass(frozen=True)
class Verdict:
    """What the gate found, split by which failure mode each finding trips."""

    unexpected: tuple[Advisory, ...]
    fixable: tuple[Advisory, ...]
    stale: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.unexpected or self.fixable or self.stale)


def evaluate(found: list[Advisory], allowed: dict[str, Allowlisted]) -> Verdict:
    reported = {advisory.id for advisory in found}
    return Verdict(
        unexpected=tuple(advisory for advisory in found if advisory.id not in allowed),
        fixable=tuple(
            advisory for advisory in found if advisory.id in allowed and advisory.has_fix
        ),
        stale=tuple(sorted(id for id in allowed if id not in reported)),
    )


def render(found: list[Advisory], verdict: Verdict, allowed: dict[str, Allowlisted]) -> list[str]:
    """The gate's own report. Every advisory is listed, allowed or not."""
    lines = []
    for advisory in found:
        mark = "allowed " if advisory.id in allowed else "BLOCKING"
        lines.append(f"{mark}  {advisory.describe()}")
        entry = allowed.get(advisory.id)
        if entry is not None:
            lines.append(f"          reviewed {entry.reviewed}: {entry.why}")

    if verdict.unexpected:
        lines.append("")
        lines.append(
            f"pip-audit: {len(verdict.unexpected)} advisory with no entry in "
            f"tools/pip_audit_gate.py. Take the fix if there is one -- "
            f"`uv lock --upgrade-package <name>` -- or add it with the reason it is "
            f"safe in this deployment and the date you checked."
        )
    if verdict.fixable:
        lines.append("")
        lines.append(
            f"pip-audit: {', '.join(a.id for a in verdict.fixable)} is allowlisted but "
            f"now has a published fix. An entry is for an advisory with nothing to "
            f"upgrade to; take the upgrade and remove the entry."
        )
    if verdict.stale:
        lines.append("")
        lines.append(
            f"pip-audit: {', '.join(verdict.stale)} no longer appears. Remove it from "
            f"tools/pip_audit_gate.py -- an allowlist entry must not outlive the "
            f"problem it documents."
        )
    if verdict.ok:
        lines.append("")
        lines.append(f"pip-audit: {len(found)} advisory, all accounted for.")
    return lines


def audit_report() -> dict[str, Any]:
    """Run `pip-audit` and parse its JSON.

    It exits non-zero whenever it finds anything, which is the whole reason this
    wrapper exists, so the exit code is read from the JSON rather than from the
    process. A run that produces no JSON at all is a different failure -- the tool
    missing, or the advisory service unreachable -- and raises.
    """
    completed = subprocess.run(PIP_AUDIT, capture_output=True, text=True, check=False)
    try:
        parsed: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"pip-audit produced no JSON (exit {completed.returncode}):\n"
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        ) from None
    return parsed


def main() -> int:
    found = advisories_from_report(audit_report())
    verdict = evaluate(found, ALLOWED)
    for line in render(found, verdict, ALLOWED):
        print(line)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
