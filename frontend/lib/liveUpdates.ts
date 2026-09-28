/**
 * The other half of ADR 0003: what the client does when the server says
 * something changed (milestone 3.4).
 *
 * `backend/app/events.py` pushes **invalidations**, never payloads —
 * `{"type": "timeline.changed", "opportunity_id": 7}` and nothing more — so
 * everything below is a mapping from an event to query keys. No row ever
 * arrives through this path, which is what keeps one place deciding what a
 * timeline entry looks like and who may read it (`lib/queries.ts`, ADR 0005).
 *
 * Three consequences worth knowing before changing it:
 *
 * - **An invalidation may be broader than the write behind it, never
 *   narrower.** `opportunity.changed` invalidates the timeline as well as the
 *   record, because most writes to a record leave a system entry on the
 *   timeline and the event does not say whether this one did. An extra refetch
 *   is a cost; a screen that stays wrong is a defect.
 * - **A reconnect is a gap.** The server closes each stream on a timer and the
 *   browser's `EventSource` reopens it (`settings.sse_max_connection_seconds`),
 *   so a write that landed in between reached nobody. `useLiveUpdates`
 *   therefore refetches everything on every `ready` *after* the first — the
 *   first needs nothing, because the screen has only just read the data.
 * - **`EventSource` does not retry a failed handshake.** A stream the caller
 *   may not read answers 404, which the spec calls a failed connection and
 *   forbids reestablishing; a stream that ends with a 200 behind it is
 *   reopened after the advertised `retry`. So the permission answer needs no
 *   handling here, and the deliberate close needs no reconnect logic.
 */

import { useEffect } from "react";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { keys } from "./queries";

/** The two events `backend/app/events.py` sends, in its own words. */
export const liveEventTypes = [
  "timeline.changed",
  "opportunity.changed",
] as const;

export type LiveEventType = (typeof liveEventTypes)[number];

/**
 * Which reads one event makes stale.
 *
 * `allTimelines` rather than one timeline key: a panel reads the filtered
 * timeline and the unfiltered one the `#` trigger offers, and a filter is part
 * of the key — naming them individually would leave whichever the reader is
 * not looking at behind.
 */
export function liveEventKeys(
  type: LiveEventType,
  opportunityId: number,
): readonly (readonly unknown[])[] {
  const shared = [
    keys.allTimelines,
    keys.activity(opportunityId),
    // Somebody else's write is what puts a row in this reader's inbox, so the
    // badge is live for the same reason the timeline is.
    keys.notifications,
  ];
  if (type === "timeline.changed") {
    return shared;
  }
  return [
    ...shared,
    // The board behind the panel holds this deal's stage, value and name.
    keys.opportunities,
    // Sharing, ownership and watching all arrive as `opportunity.changed`.
    keys.shares(opportunityId),
    keys.members(opportunityId),
    keys.watchers(opportunityId),
  ];
}

function refresh(
  client: QueryClient,
  type: LiveEventType,
  opportunityId: number,
) {
  for (const queryKey of liveEventKeys(type, opportunityId)) {
    void client.invalidateQueries({ queryKey });
  }
}

/**
 * Listen to one opportunity's stream for as long as its panel is open.
 *
 * Guarded on `EventSource` existing: the static export renders this tree once
 * in Node (ADR 0005), and jsdom implements no server-sent events either, so
 * the tests that mean to exercise this install a fake
 * (`app/test-live-updates.ts`) and every other test is unaffected.
 */
export function useLiveUpdates(opportunityId: number) {
  const client = useQueryClient();

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return;
    }

    const source = new EventSource(
      `/api/v2/opportunities/${opportunityId}/events`,
    );
    let reconnected = false;

    source.addEventListener("ready", () => {
      if (reconnected) {
        for (const type of liveEventTypes) {
          refresh(client, type, opportunityId);
        }
      }
      reconnected = true;
    });
    for (const type of liveEventTypes) {
      source.addEventListener(type, () => refresh(client, type, opportunityId));
    }

    return () => source.close();
  }, [client, opportunityId]);
}
