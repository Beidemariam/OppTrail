import { describe, expect, it } from "vitest";

import { notificationText } from "./notifications";

type Notification = Parameters<typeof notificationText>[0];

function notification(type: string, payload: Record<string, unknown> = {}): Notification {
  return {
    id: 1,
    type,
    payload,
    read: false,
    created_at: "2026-09-06T14:30:00Z",
  } as unknown as Notification;
}

describe("notificationText", () => {
  it.each([
    ["mention", "You were mentioned in a timeline update."],
    ["comment", "New comment on your note."],
    ["share_added", "An opportunity was shared with you."],
    ["share_role_changed", "Your access role changed."],
    ["share_removed", "Your opportunity access was removed."],
  ])("describes a %s", (type, expected) => {
    expect(notificationText(notification(type))).toBe(expected);
  });

  it("uses the entry title for shared activity when there is one", () => {
    expect(notificationText(notification("shared_activity", { title: "Proposal sent" }))).toBe(
      "Proposal sent",
    );
  });

  it("falls back when shared activity carries no title", () => {
    expect(notificationText(notification("shared_activity", {}))).toBe(
      "New activity on a shared opportunity.",
    );
    expect(notificationText(notification("shared_activity", { title: "" }))).toBe(
      "New activity on a shared opportunity.",
    );
  });

  it("says something rather than nothing for a type it does not know", () => {
    expect(notificationText(notification("invented_later"))).toBe("New notification.");
  });
});
