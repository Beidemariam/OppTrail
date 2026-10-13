import { describe, expect, it } from "vitest";

import { notificationHref, notificationText } from "./notifications";

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

describe("where a notification leads (milestone 6.1a)", () => {
  it("addresses the row a mention or comment is on", () => {
    // 6.0's mechanism, reused rather than reinvented: these are the same
    // parameters a search result writes.
    expect(
      notificationHref(
        notification("mention", {
          opportunity_id: 3,
          source_type: "comment",
          source_id: 42,
          actor_id: 2,
          email: "a@b.c",
        }),
      ),
    ).toBe("/opportunities/3?comment=42");
    expect(
      notificationHref(
        notification("comment", {
          opportunity_id: 3,
          source_type: "note",
          source_id: 7,
          actor_id: 2,
        }),
      ),
    ).toBe("/opportunities/3?note=7");
    expect(
      notificationHref(
        notification("shared_activity", {
          opportunity_id: 3,
          source_type: "entry",
          source_id: 9,
          actor_id: 2,
          title: "Call",
        }),
      ),
    ).toBe("/opportunities/3?entry=9");
  });

  it("sends an attachment to its deal, not to a row it cannot name", () => {
    // The payload does not carry the entry a file hangs off, and the inbox
    // should not be issuing a lookup to find out.
    expect(
      notificationHref(
        notification("shared_activity", {
          opportunity_id: 3,
          source_type: "attachment",
          source_id: 70,
          actor_id: 2,
          title: "contract.pdf",
        }),
      ),
    ).toBe("/opportunities/3");
  });

  it("sends a task notification to the deal whose panel holds it", () => {
    expect(
      notificationHref(
        notification("task_assigned", {
          opportunity_id: 3,
          actor_id: 2,
          task_id: 5,
          title: "Chase procurement",
          due_date: null,
        }),
      ),
    ).toBe("/opportunities/3");
  });

  it("leads nowhere when access was just removed", () => {
    // The one notification that deliberately has no link: the reader cannot
    // open what it is about, and a link to a 404 is worse than no link.
    expect(
      notificationHref(
        notification("share_removed", {
          opportunity_id: 3,
          actor_id: 2,
          role: "viewer",
        }),
      ),
    ).toBeNull();
  });

  it("opens the record for an access change that still grants access", () => {
    for (const type of [
      "share_added",
      "share_role_changed",
      "owner_changed",
    ] as const) {
      expect(
        notificationHref(
          notification(type, {
            opportunity_id: 3,
            actor_id: 2,
            role: "editor",
          }),
        ),
      ).toBe("/opportunities/3");
    }
  });
});

describe("an automation's notification (milestone 6.3)", () => {
  it("names the rule as well as the message", () => {
    // The rule's name is what makes an automated nudge distinguishable from a
    // colleague's, which is `docs/FEATURES.md` §11's "traceable" read from the
    // inbox rather than from the timeline.
    expect(
      notificationText(
        notification("automation", {
          opportunity_id: 3,
          rule_id: 7,
          rule_name: "Nudge the quiet ones",
          title: "This deal has gone quiet",
          body: null,
        }),
      ),
    ).toBe("This deal has gone quiet (rule: Nudge the quiet ones)");
  });

  it("falls back when the payload is not the shape this version writes", () => {
    expect(notificationText(notification("automation", {}))).toBe(
      "An automation rule fired.",
    );
  });

  it("opens the deal it is about", () => {
    expect(
      notificationHref(
        notification("automation", {
          opportunity_id: 3,
          rule_id: 7,
          rule_name: "Nudge",
          title: "Quiet",
          body: null,
        }),
      ),
    ).toBe("/opportunities/3");
  });
});
