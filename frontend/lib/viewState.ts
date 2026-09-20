/**
 * The URL <-> object round trip every view's filter/sort state uses
 * (milestone 2.2, `docs/FEATURES.md` §1: "state lives in the URL").
 *
 * `TimelineFilters` and `OpportunityViewState` (`lib/domain.ts`) are both
 * already flat string-keyed records, which is deliberate: it is what lets a
 * saved view's `filters`/`sort` columns (`SavedViewPublic`, themselves
 * `Record<string, string>`) hold the same shape as the URL with no second
 * conversion in between.
 *
 * Two view states share one query string, because the board and the open
 * timeline are mounted together (D-054). So each state's parameters are
 * namespaced by the entity they belong to — the same `entity` a saved view is
 * filed under, so there is no second naming to keep in sync — and writing one
 * state merges into the URL rather than replacing it. Without both, the two
 * collide: they share the field name `q`, and a whole-query-string write drops
 * whatever the other view had put there (**D-059**).
 */

import type { SavedViewEntity } from "./domain";

/** The prefix one entity's parameters carry in the URL: `timeline.order`,
 * `opportunities.stage`. */
function prefix(entity: SavedViewEntity): string {
  return `${entity}.`;
}

/** Read an entity's state out of `URLSearchParams`, falling back to
 * `defaults` for any field the URL does not mention. */
export function stateFromParams<T extends Record<string, string>>(
  params: URLSearchParams,
  defaults: T,
  entity: SavedViewEntity,
): T {
  const state = { ...defaults };
  for (const key of Object.keys(defaults)) {
    const value = params.get(prefix(entity) + key);
    if (value !== null) {
      (state as Record<string, string>)[key] = value;
    }
  }
  return state;
}

/**
 * The inverse: `params` with this entity's fields rewritten and everything
 * else left alone. Only the fields that differ from `defaults` are kept, so
 * the address bar stays empty rather than spelling out every empty filter.
 */
export function paramsWithState<T extends Record<string, string>>(
  params: URLSearchParams,
  state: T,
  defaults: T,
  entity: SavedViewEntity,
): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of Object.keys(defaults)) {
    const name = prefix(entity) + key;
    const value = state[key];
    if (value && value !== defaults[key]) {
      next.set(name, value);
    } else {
      next.delete(name);
    }
  }
  return next;
}
