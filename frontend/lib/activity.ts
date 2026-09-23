import type { components } from "./api-types";
import {
  noteVersionFields,
  opportunityVersionFields,
  timelineEntryVersionFields,
  type VersionField,
} from "./domain";

export type ActivityEvent = components["schemas"]["ActivityEventPublic"];
export type ActivityDetail = ActivityEvent["detail"];
export type ActivityEditTarget =
  components["schemas"]["ActivityEditEvent"]["target"];

/**
 * The one sentence shown for a row of the activity log (milestone 3.0).
 *
 * The API returns a discriminated event rather than rendered text
 * (`backend/app/activity.py`), exactly as notifications do — so the wording
 * lives here, beside `lib/notifications.ts`, and each case is spelled out
 * instead of interpolated from field names the server happens to use.
 *
 * Every sentence is written to follow the actor, who is rendered beside it:
 * "Ada Lovelace" + "changed Name and Value on this opportunity".
 */
export function activitySentence(event: ActivityEvent): string {
  const detail = event.detail;
  if (detail.source === "system_entry") {
    // The system entry's body is already a sentence about what happened
    // ("Stage changed from Qualification to Proposal."), and it is the one
    // the timeline shows for the same event, so the two never disagree.
    return detail.body || detail.title;
  }
  if (detail.source === "audit_log") {
    return auditSentence(detail);
  }
  return editSentence(detail);
}

function auditSentence(
  detail: components["schemas"]["ActivityAuditEvent"],
): string {
  switch (detail.action) {
    case "opportunity_deleted":
      return "deleted this opportunity";
    case "opportunity_restored":
      return "restored this opportunity";
    case "timeline_entry_deleted":
      return "deleted the entry";
    case "timeline_entry_restored":
      return "restored the entry";
    case "note_deleted":
      return "deleted a note";
    case "note_restored":
      return "restored a note";
    case "comment_deleted":
      return "deleted a comment";
    case "comment_restored":
      return "restored a comment";
    // Sharing is reported to every reader by its system entry, so the feed
    // drops the audit row that repeats it (`backend/app/activity.py`). The
    // action is still in the type the audit log endpoint answers with, which
    // is why these three are answered rather than left to fall through.
    case "share_added":
      return "shared this opportunity";
    case "share_role_changed":
      return "changed a colleague's role";
    default:
      return "removed a colleague's access";
  }
}

function editSentence(
  detail: components["schemas"]["ActivityEditEvent"],
): string {
  const fields = detail.changed_fields.map((field) =>
    versionFieldLabel(detail.target, field),
  );
  return `changed ${joinWords(fields)} on ${editTargetName(detail.target)}`;
}

function editTargetName(target: ActivityEditTarget): string {
  if (target === "opportunity") {
    return "this opportunity";
  }
  return target === "timeline_entry" ? "a timeline entry" : "a note";
}

/**
 * What a changed column is called, taken from the same declaration the history
 * screen labels it with (`lib/domain.ts`).
 *
 * The fallback is the column name made readable rather than a second table of
 * labels: `currency` is versioned but is read as part of the value rather than
 * as a line of its own (D-098), so it has no declared label and would
 * otherwise need one written only for this screen.
 */
export function versionFieldLabel(
  target: ActivityEditTarget,
  field: string,
): string {
  const declared: VersionField<never>[] =
    target === "opportunity"
      ? opportunityVersionFields
      : target === "timeline_entry"
        ? timelineEntryVersionFields
        : noteVersionFields;
  const match = declared.find((candidate) => candidate.field === field);
  if (match) {
    return match.label;
  }
  const words = field.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** "Name", "Name and Value", "Name, Value and Close date". */
export function joinWords(words: string[]): string {
  if (words.length <= 1) {
    return words[0] ?? "";
  }
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** Who did it. Null where the actor's account is gone, not where nobody acted. */
export function activityActor(event: ActivityEvent): string {
  return event.actor_name ?? "A removed user";
}
