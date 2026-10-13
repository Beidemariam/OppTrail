import type { JobRun } from "./domain";
import { formatTimestamp } from "./time";

/**
 * What the automations screen says about the scheduler, in one line.
 *
 * Its own module rather than part of `lib/domain.ts`, for the reason
 * `lib/notifications.ts` and `lib/activity.ts` are theirs: this is the one
 * place a record becomes a sentence a person reads, and it needs the
 * timestamp formatting that `domain.ts` deliberately does not import.
 *
 * `docs/ARCHITECTURE.md` names the failure the line answers — "a silently
 * dead scheduler is the most likely v2 production failure" — and the person
 * who would notice is the one on this screen wondering why a rule has not
 * fired. So it reports the *checking* rather than the jobs, and the awkward
 * case is the middle one: a run left at `started` is a process that died
 * mid-job, which is worth saying plainly rather than reporting as a check
 * that happened.
 */
export function schedulerLine(runs: JobRun[]): string {
  const checks = runs.filter((run) => run.job === "automations");
  if (checks.length === 0) {
    return "Time-based rules have not been checked yet.";
  }
  const latest = checks[0];
  if (latest.status === "failed") {
    return `The last check failed: ${latest.detail ?? "no reason recorded"}`;
  }
  if (latest.status === "started") {
    return `A check started ${formatTimestamp(latest.started_at)} and did not finish.`;
  }
  return `Time-based rules last checked ${formatTimestamp(latest.started_at)}.`;
}
