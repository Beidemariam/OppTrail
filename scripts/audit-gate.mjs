#!/usr/bin/env node
// `npm audit` as a ratchet rather than a wall (milestone R.6, D-207).
//
// `make check` has always run `npm audit`, and `npm audit` exits non-zero on
// any high advisory — including ones with **no fix published anywhere**, which
// was the state of the one advisory this tree carried when R.6 wrote this gate.
// The two obvious responses are both wrong: `--audit-level=critical` hides
// every future high as well, and leaving the gate red teaches everybody to
// ignore it.
//
// So this is `DEFERRED_AXE_RULES`'s shape (`frontend/e2e/helpers.ts`) applied
// to dependency advisories: a named allowlist with a reason and a date per
// entry, and two failure modes rather than one.
//
//   1. **A high or critical advisory that is not allowlisted fails.** The gate
//      still bites for anything new.
//   2. **An allowlisted advisory that no longer appears also fails.** The
//      ratchet tightens itself — an entry cannot outlive the problem it
//      documents, which is the rule that keeps a list like this honest.
//
// Nothing may be added here without the reason it is safe *in this
// deployment*, written out. "Transitive" is not a reason; "cannot be reached
// by anything that ships" is.

import { execFileSync } from "node:child_process";

// `ALLOWED` is **empty**, and that is the ratchet having tightened rather than
// a list nobody started. R.6's one entry was GHSA-vfj7-8cjw-p6xm in `braces`,
// kept because no fix existed anywhere: the advisory covered `<= 3.0.3` and
// 3.0.3 was the newest release braces had ever had. On 2026-10-29 it stopped
// appearing in `npm audit` while braces@3.0.3 sat unchanged in the tree — the
// advisory was withdrawn upstream rather than fixed here. Failure mode 2 is
// what reported that, which is the whole reason for having it.
const ALLOWED = {};

const BLOCKING = new Set(["high", "critical"]);

function auditReport() {
  // `npm audit` exits non-zero when it finds anything, which is the whole
  // reason this wrapper exists, so the exit code is read from the JSON rather
  // than from the process.
  try {
    return JSON.parse(
      execFileSync("npm", ["audit", "--json"], {
        cwd: new URL("../frontend/", import.meta.url),
        encoding: "utf8",
        maxBuffer: 32 * 1024 * 1024,
      }),
    );
  } catch (error) {
    if (error.stdout) return JSON.parse(error.stdout);
    throw error;
  }
}

/** Every distinct advisory behind the reported packages, by its GHSA id.
 *
 * One advisory surfaces as several vulnerable packages — the `braces` entry
 * this gate was written against was reported five times, once per link in the
 * chain above it — so the unit this gate reasons about is the advisory, not
 * the package. */
function advisories(report) {
  const found = new Map();
  for (const vulnerability of Object.values(report.vulnerabilities ?? {})) {
    for (const via of vulnerability.via) {
      if (typeof via !== "object" || !BLOCKING.has(via.severity)) continue;
      const id = via.url?.split("/").pop() ?? `${via.source}`;
      const existing = found.get(id) ?? { ...via, id, packages: new Set() };
      existing.packages.add(via.name ?? vulnerability.name);
      found.set(id, existing);
    }
  }
  return found;
}

const report = auditReport();
const found = advisories(report);

const unexpected = [...found.values()].filter(({ id }) => !(id in ALLOWED));
const stale = Object.keys(ALLOWED).filter((id) => !found.has(id));

for (const { id, severity, title, packages } of found.values()) {
  const mark = id in ALLOWED ? "allowed" : "BLOCKING";
  console.log(`${mark}  ${severity.padEnd(8)} ${id}  ${title}`);
  console.log(`          packages: ${[...packages].join(", ")}`);
  if (id in ALLOWED) console.log(`          why: ${ALLOWED[id].why}`);
}

if (unexpected.length > 0) {
  console.error(
    `\nnpm audit: ${unexpected.length} high or critical advisory with no entry in ` +
      `scripts/audit-gate.mjs. Fix it, or add it with the reason it is safe in ` +
      `this deployment and the date you checked.`,
  );
  process.exit(1);
}

if (stale.length > 0) {
  console.error(
    `\nnpm audit: ${stale.join(", ")} no longer appears. Remove it from ` +
      `scripts/audit-gate.mjs — an allowlist entry must not outlive the ` +
      `problem it documents.`,
  );
  process.exit(1);
}

console.log(
  `\nnpm audit: ${found.size} high or critical advisory, all accounted for.`,
);
