import type { components } from "./api-types";

type AppNotification = components["schemas"]["NotificationPublic"];

/**
 * The one sentence shown for a notification.
 *
 * The API returns a discriminated payload rather than a rendered string
 * (`backend/app/schemas.py`), so the wording lives here and each case is
 * spelled out instead of interpolated, which keeps it translatable later and
 * keeps payload fields out of the UI by accident.
 */
export function notificationText(notification: AppNotification): string {
  if (notification.type === "mention") {
    return "You were mentioned in a timeline update.";
  }
  if (notification.type === "comment") {
    return "New comment on your note.";
  }
  if (notification.type === "task_assigned") {
    // The title is in the payload precisely so this sentence can name the task
    // (milestone 4.1): "you were assigned a task" makes the reader open the
    // deal to find out which one.
    const payload = notification.payload;
    return "title" in payload && payload.title
      ? `You were assigned: ${payload.title}`
      : "You were assigned a task.";
  }
  if (notification.type === "task_comment") {
    // Named for the same reason an assignment is (milestone 4.5): "new comment
    // on a task" sends the reader looking for which one.
    const payload = notification.payload;
    return "title" in payload && payload.title
      ? `New comment on: ${payload.title}`
      : "New comment on a task.";
  }
  if (notification.type === "shared_activity") {
    const payload = notification.payload;
    return "title" in payload && payload.title
      ? payload.title
      : "New activity on a shared opportunity.";
  }
  if (notification.type === "share_added") {
    return "An opportunity was shared with you.";
  }
  if (notification.type === "share_role_changed") {
    return "Your access role changed.";
  }
  if (notification.type === "share_removed") {
    return "Your opportunity access was removed.";
  }
  if (notification.type === "owner_changed") {
    return "An opportunity was handed over to you.";
  }
  if (notification.type === "automation") {
    // The rule's name is the half the reader wrote themselves, and it is what
    // makes an automated nudge distinguishable from a colleague's (milestone
    // 6.3, §11's "traceable"). The title is the message they chose; the rule
    // name says what decided to send it.
    const payload = notification.payload;
    return "rule_name" in payload
      ? `${payload.title} (rule: ${payload.rule_name})`
      : "An automation rule fired.";
  }
  return "New notification.";
}

/**
 * Where a notification leads, or `null` when it leads nowhere useful.
 *
 * Milestone 6.1a, on the human's ruling (*"include link in notification"*).
 * Until this, the inbox rendered no anchor at all: being told somebody
 * mentioned you in a comment left you to go and find it, which is the same
 * "depth reads as absence" failure (D-136) that milestone 6.0 removed from
 * search results one screen over. It reuses 6.0's mechanism exactly rather
 * than inventing a second one — `?entry=`, `?note=` and `?comment=` already
 * scroll a row into view and mark it (`lib/domain.ts`'s `LinkTarget`).
 *
 * Three shapes, decided by what the payload actually knows:
 *
 * - **A mention, a comment or shared activity** carries `source_type` and
 *   `source_id`, so it addresses the row itself. An `attachment` source
 *   resolves to the deal rather than to the file: a notification payload does
 *   not carry the entry an attachment hangs off, and inventing a lookup to
 *   find it is a request the inbox should not be making.
 * - **A task** carries `task_id`, and a task is read in its deal's sidebar
 *   panel, so the link opens the deal. `/tasks` is the cross-deal list and is
 *   not where a notification about one deal's task should land.
 * - **An access change** is about the record, so it opens the record. A
 *   `share_removed` is the one notification that deliberately leads nowhere:
 *   the reader can no longer open what it is about, and a link to a 404 is
 *   worse than no link.
 */
export function notificationHref(notification: AppNotification): string | null {
  const payload = notification.payload;
  if (!("opportunity_id" in payload)) {
    return null;
  }
  const deal = `/opportunities/${payload.opportunity_id}`;

  if (notification.type === "share_removed") {
    return null;
  }
  if ("source_type" in payload && "source_id" in payload) {
    return payload.source_type === "attachment"
      ? deal
      : `${deal}?${payload.source_type}=${payload.source_id}`;
  }
  return deal;
}
