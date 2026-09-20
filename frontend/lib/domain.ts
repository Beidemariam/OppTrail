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

/** The timeline query parameters the filter bar sends. */
export interface TimelineFilters {
  q: string;
  type: string;
  from: string;
  to: string;
  author_id: string;
}

export const emptyTimelineFilters: TimelineFilters = {
  q: "",
  type: "",
  from: "",
  to: "",
  author_id: "",
};

/** One turn of the read-only AI conversation about an opportunity. */
export interface AiChatMessage {
  role: "user" | "assistant";
  body: string;
  referenced_entry_ids?: number[];
}
