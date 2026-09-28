import { describe, expect, it } from "vitest";

import { liveEventKeys, liveEventTypes } from "./liveUpdates";
import { keys } from "./queries";

/**
 * What each of ADR 0003's two events makes stale (milestone 3.4).
 *
 * The mapping is the whole client half of the feature: the server pushes a
 * name and nothing else, so an event that invalidates too little leaves a
 * screen wrong, and this is the only place that judgement is written down.
 */

describe("liveEventKeys", () => {
  it("sends a timeline change to the reads a timeline is made of", () => {
    expect(liveEventKeys("timeline.changed", 7)).toEqual([
      keys.allTimelines,
      keys.activity(7),
      keys.notifications,
    ]);
  });

  it("also refreshes the record and who is on it when the record changed", () => {
    // Deliberately a superset of the timeline's: a stage change, a share and
    // an ownership transfer all write a system entry as well as changing the
    // record, and the event does not say which of them happened.
    const timeline = liveEventKeys("timeline.changed", 7);
    const opportunity = liveEventKeys("opportunity.changed", 7);

    expect(opportunity).toEqual(expect.arrayContaining([...timeline]));
    expect(opportunity).toEqual(
      expect.arrayContaining([
        keys.opportunities,
        keys.shares(7),
        keys.members(7),
        keys.watchers(7),
      ]),
    );
  });

  it("keys everything opportunity-scoped to the opportunity it was told about", () => {
    // A stream is per opportunity, so an event must never invalidate another
    // deal's activity log — the reader would refetch a page nobody changed.
    for (const type of liveEventTypes) {
      expect(liveEventKeys(type, 7)).not.toEqual(
        expect.arrayContaining([keys.activity(8)]),
      );
    }
  });
});
