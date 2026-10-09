import { describe, expect, it } from "vitest";

import { notificationText } from "./notifications";

type Notification = Parameters<typeof notificationText>[0];

function notification(
  type: string,
  payload: Record<string, unknown> = {},
): Notification {
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
    ["owner_changed", "An opportunity was handed over to you."],
  ])("describes a %s", (type, expected) => {
    expect(notificationText(notification(type))).toBe(expected);
  });

  it("uses the entry title for shared activity when there is one", () => {
    expect(
      notificationText(
        notification("shared_activity", { title: "Proposal sent" }),
      ),
    ).toBe("Proposal sent");
  });

  it("falls back when shared activity carries no title", () => {
    expect(notificationText(notification("shared_activity", {}))).toBe(
      "New activity on a shared opportunity.",
    );
    expect(
      notificationText(notification("shared_activity", { title: "" })),
    ).toBe("New activity on a shared opportunity.");
  });

  it("says something rather than nothing for a type it does not know", () => {
    expect(notificationText(notification("invented_later"))).toBe(
      "New notification.",
    );
  });
});

describe("the two notifications a task sends", () => {
  // Both carry the task's title so the inbox line names it, and both fall
  // back rather than printing an empty sentence — the shape `shared_activity`
  // established and the reason an assignment does not read "you were assigned
  // a task" with no hint of which one (milestone 4.1, 4.5).
  it.each([
    ["task_assigned", "You were assigned: Send the pricing"],
    ["task_comment", "New comment on: Send the pricing"],
  ])("names the task in a %s", (type, expected) => {
    expect(
      notificationText(notification(type, { title: "Send the pricing" })),
    ).toBe(expected);
  });

  it.each([
    ["task_assigned", "You were assigned a task."],
    ["task_comment", "New comment on a task."],
  ])("falls back when a %s carries no title", (type, expected) => {
    expect(notificationText(notification(type, {}))).toBe(expected);
    expect(notificationText(notification(type, { title: "" }))).toBe(expected);
  });
});
