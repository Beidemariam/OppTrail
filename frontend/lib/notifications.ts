import type { components } from "./api-types";

type AppNotification = components["schemas"]["NotificationPublicV2"];

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
  return "New notification.";
}
