import { describe, expect, it } from "vitest";

import { schedulerLine } from "./jobs";
import type { JobRun } from "./domain";

/**
 * The one line the automations screen says about the scheduler (milestone
 * 6.5). Pure, so the four answers are read here rather than through four
 * renders — the split `lib/notifications.ts` and `lib/activity.ts` already
 * make for the same reason.
 */
function aRun(overrides: Partial<JobRun> = {}): JobRun {
  return {
    id: 1,
    job: "automations",
    status: "succeeded",
    detail: "2 rules, 7 deals considered, 1 acted on, 6 skipped",
    started_at: "2026-10-12T09:00:00Z",
    finished_at: "2026-10-12T09:00:02Z",
    ...overrides,
  };
}

describe("schedulerLine", () => {
  it("says when the rules were last checked", () => {
    expect(schedulerLine([aRun()])).toMatch(/Time-based rules last checked/);
  });

  it("says plainly that nothing has run yet", () => {
    // Which is what a fresh install looks like for the first fifteen minutes,
    // and what a scheduler switched off looks like forever.
    expect(schedulerLine([])).toBe(
      "Time-based rules have not been checked yet.",
    );
  });

  it("reports a failed check with its reason", () => {
    expect(
      schedulerLine([
        aRun({
          status: "failed",
          detail: "OperationalError: database is locked",
        }),
      ]),
    ).toBe("The last check failed: OperationalError: database is locked");
  });

  it("does not report an interrupted check as a check", () => {
    // A row left at `started` is a process that died mid-job -- the one
    // failure a finished-only log cannot show, and the reason the row is
    // written on start.
    expect(
      schedulerLine([aRun({ status: "started", finished_at: null })]),
    ).toMatch(/did not finish/);
  });

  it("ignores the backup's runs, which are not a check of the rules", () => {
    expect(
      schedulerLine([
        aRun({ id: 9, job: "backup", detail: "app-20261012T090000Z.db" }),
      ]),
    ).toBe("Time-based rules have not been checked yet.");
  });
});
