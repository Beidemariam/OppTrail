/**
 * The vocabulary the whole client shares: the fixed stage list, the entry
 * types, and short names for the generated API schemas.
 *
 * These were declared inside `app/Home.tsx` until milestone 2.1 split that
 * file into routed views. They live here now because several views need the
 * same names, and because the stage list is a fixed, non-renamable list
 * (`AGENTS.md` invariant 6) that should have exactly one definition.
 */

import type { components } from "./api-types";

export const stages = [
  "Prospecting",
  "Qualification",
  "Needs Analysis",
  "Proposal",
  "Negotiation",
  "Closed Won",
  "Closed Lost",
] as const;

export const entryTypes = [
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "demo", label: "Demo" },
  { value: "proposal", label: "Proposal" },
  { value: "contract", label: "Contract" },
  { value: "stage_change", label: "Stage Change" },
  { value: "other", label: "Other" },
] as const;

export type EntryType = (typeof entryTypes)[number]["value"];

export function entryTypeLabel(type: EntryType): string {
  return (
    entryTypes.find((candidate) => candidate.value === type)?.label ?? type
  );
}

export const notificationTypeOptions = [
  { value: "mention", label: "Mentions" },
  { value: "comment", label: "Comments" },
  { value: "shared_activity", label: "Activity" },
  { value: "share_added", label: "Sharing added" },
  { value: "share_role_changed", label: "Role changed" },
  { value: "share_removed", label: "Sharing removed" },
] as const;

export type User = components["schemas"]["UserPublic"];
export type Opportunity = components["schemas"]["OpportunityPublic"];
export type OpportunityShare = components["schemas"]["SharePublic"];
export type ShareRole = components["schemas"]["ShareCreate"]["role"];
export type AuditLogEntry = components["schemas"]["AuditLogEntryPublic"];
export type AppNotification = components["schemas"]["NotificationPublicV2"];
export type NotificationType = AppNotification["type"];
export type TimelineEntry = components["schemas"]["TimelineEntryPublic"];
export type TimelineNote = components["schemas"]["NotePublic"];

/** What the signed-in user is allowed to do inside one opportunity. */
export interface Access {
  canWriteTimeline: boolean;
  canManage: boolean;
  /** Edit and delete resolve through one rule (`lib/permissions.ts`). */
  canChangeItem: (authorId: number | null) => boolean;
}

/**
 * The timeline query parameters the filter bar sends, plus the reading order
 * (D-051). Every field is a plain string because this shape is also what
 * lives in the URL and in a saved view's `filters`
 * (`lib/viewState.ts`) — one shape, not a conversion between two.
 */
export type TimelineFilters = {
  q: string;
  type: string;
  from: string;
  to: string;
  author_id: string;
  order: "asc" | "desc";
};

export const emptyTimelineFilters: TimelineFilters = {
  q: "",
  type: "",
  from: "",
  to: "",
  author_id: "",
  order: "asc",
};

/**
 * The opportunity board's filter/sort model (milestone 2.2), URL-serialized
 * the same way as `TimelineFilters`. No `groupBy` field yet: the board's only
 * grouping is by stage, which is what makes it the board rather than the list
 * view (2.7/2.8) — a saved view records `group_by: "stage"` as a constant
 * (`SavedViewsMenu.tsx`) so the column exists in the schema before a second
 * view gives it a reason to vary.
 */
export type OpportunityViewState = {
  q: string;
  stage: string;
  stalled: "" | "true" | "false";
  sortField: "updated_at" | "value" | "expected_close_date" | "name";
  sortDirection: "asc" | "desc";
};

export const emptyOpportunityViewState: OpportunityViewState = {
  q: "",
  stage: "",
  stalled: "",
  sortField: "updated_at",
  sortDirection: "desc",
};

/**
 * Filters and sorts the already-fetched opportunity list against a view
 * state. Client-side rather than a new query parameter on
 * `GET /api/opportunities`, because that endpoint already returns every
 * opportunity the caller can read unpaginated — pushing the predicate into
 * SQL has no payload-size benefit before pagination reaches this list (2.3),
 * and would otherwise have to be re-mirrored onto `/api/v2/opportunities` to
 * avoid the drift `CLAUDE.md`'s "API versions" section warns against.
 */
export function applyOpportunityView(
  opportunities: Opportunity[],
  state: OpportunityViewState,
): Opportunity[] {
  const keyword = state.q.trim().toLowerCase();
  const filtered = opportunities.filter((opportunity) => {
    if (state.stage && opportunity.stage !== state.stage) {
      return false;
    }
    if (state.stalled === "true" && !opportunity.stalled) {
      return false;
    }
    if (state.stalled === "false" && opportunity.stalled) {
      return false;
    }
    if (keyword) {
      const haystack =
        `${opportunity.name} ${opportunity.account_name} ${opportunity.owner_name}`.toLowerCase();
      if (!haystack.includes(keyword)) {
        return false;
      }
    }
    return true;
  });

  const direction = state.sortDirection === "asc" ? 1 : -1;
  return [...filtered].sort((a, b) => {
    switch (state.sortField) {
      case "value":
        return (Number(a.value) - Number(b.value)) * direction;
      case "name":
        return a.name.localeCompare(b.name) * direction;
      case "expected_close_date":
        return (
          (a.expected_close_date ?? "").localeCompare(
            b.expected_close_date ?? "",
          ) * direction
        );
      default:
        return a.updated_at.localeCompare(b.updated_at) * direction;
    }
  });
}

export type SavedView = components["schemas"]["SavedViewPublic"];
export type SavedViewEntity = SavedView["entity"];

/** One turn of the read-only AI conversation about an opportunity. */
export interface AiChatMessage {
  role: "user" | "assistant";
  body: string;
  referenced_entry_ids?: number[];
}

/**
 * The board read as one list: stage column by stage column, and within a
 * column in the order the view state sorted them.
 *
 * `j` and `k` move through this (milestone 2.4a), so the keyboard walks the
 * cards in the order the eye does rather than in whatever order the API
 * returned them.
 */
export function boardOrder(opportunities: Opportunity[]): Opportunity[] {
  return stages.flatMap((stage) =>
    opportunities.filter((opportunity) => opportunity.stage === stage),
  );
}
