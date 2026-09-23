import { describe, expect, it } from "vitest";

import type { components } from "./api-types";
import {
  activityActor,
  activitySentence,
  joinWords,
  versionFieldLabel,
  type ActivityEvent,
} from "./activity";

type ActivityAuditAction =
  components["schemas"]["ActivityAuditEvent"]["action"];

/**
 * Milestone 3.0: the activity log's wording.
 *
 * The API answers with a discriminated event and no rendered text
 * (`backend/app/activity.py`), so the sentence is this module's and these are
 * what hold it to the three shapes it has to read.
 */

function anEvent(detail: ActivityEvent["detail"]): ActivityEvent {
  return {
    id: 1,
    opportunity_id: 7,
    occurred_at: "2026-09-20T10:04:00Z",
    actor_id: 3,
    actor_name: "Ada Lovelace",
    detail,
  };
}

describe("activitySentence", () => {
  it("says what a system entry already says on the timeline", () => {
    const event = anEvent({
      source: "system_entry",
      entry_id: 12,
      title: "Stage changed to Proposal",
      body: "Stage changed from Qualification to Proposal.",
    });

    expect(activitySentence(event)).toBe(
      "Stage changed from Qualification to Proposal.",
    );
  });

  it("falls back to a system entry's title when it carries no body", () => {
    const event = anEvent({
      source: "system_entry",
      entry_id: 12,
      title: "Opportunity created",
      body: "",
    });

    expect(activitySentence(event)).toBe("Opportunity created");
  });

  it("names the fields an edit moved, as the history screen labels them", () => {
    const event = anEvent({
      source: "version",
      target: "opportunity",
      target_id: 7,
      version_number: 4,
      changed_fields: ["name", "value", "expected_close_date"],
    });

    expect(activitySentence(event)).toBe(
      "changed Name, Value and Close date on this opportunity",
    );
  });

  it("names the thing an edit was made to", () => {
    expect(
      activitySentence(
        anEvent({
          source: "version",
          target: "note",
          target_id: 2,
          version_number: 2,
          changed_fields: ["body"],
        }),
      ),
    ).toBe("changed Body on a note");
    expect(
      activitySentence(
        anEvent({
          source: "version",
          target: "timeline_entry",
          target_id: 5,
          version_number: 3,
          changed_fields: ["follow_up_date"],
        }),
      ),
    ).toBe("changed Follow up on a timeline entry");
  });

  it("reads every deletion and its undo out of the audit half", () => {
    // Each of the eight is written out rather than derived from the action
    // name: "opportunity_deleted" reads as "deleted *this* opportunity"
    // while a note reads as "a note", and a rule that produced both would
    // have to know which is which anyway.
    const sentences: [ActivityAuditAction, string][] = [
      ["opportunity_deleted", "deleted this opportunity"],
      ["opportunity_restored", "restored this opportunity"],
      ["timeline_entry_deleted", "deleted the entry"],
      ["timeline_entry_restored", "restored the entry"],
      ["note_deleted", "deleted a note"],
      ["note_restored", "restored a note"],
      ["comment_deleted", "deleted a comment"],
      ["comment_restored", "restored a comment"],
    ];

    for (const [action, sentence] of sentences) {
      expect(
        activitySentence(
          anEvent({
            source: "audit_log",
            action,
            detail: { note_id: 2, entry_id: 5, author_id: 3 },
          }),
        ),
      ).toBe(sentence);
    }
  });

  it("still has a sentence for the access actions the feed leaves out", () => {
    // `backend/app/activity.py` drops these because the system entry beside
    // them says the same thing — but they are in the type the audit log
    // answers with, so the switch has to be total rather than assume. The
    // ownership transfer (milestone 3.0a) is the fourth of them.
    const actions = [
      "share_added",
      "share_role_changed",
      "share_removed",
      "owner_changed",
    ] as const;

    for (const action of actions) {
      const sentence = activitySentence(
        anEvent({
          source: "audit_log",
          action,
          detail: { user_id: 4, email: "sam@example.com", role: "editor" },
        }),
      );
      expect(sentence).not.toBe("");
    }
  });
});

describe("versionFieldLabel", () => {
  it("uses the label the history screen uses", () => {
    expect(versionFieldLabel("opportunity", "account_name")).toBe("Account");
    expect(versionFieldLabel("timeline_entry", "body")).toBe("Details");
  });

  it("makes a column with no declared label readable rather than raw", () => {
    // `currency` is versioned but read as part of the value (D-098), so it
    // has no line of its own on the history screen.
    expect(versionFieldLabel("opportunity", "currency")).toBe("Currency");
  });
});

describe("joinWords", () => {
  it("reads as a list a person would speak", () => {
    expect(joinWords([])).toBe("");
    expect(joinWords(["Name"])).toBe("Name");
    expect(joinWords(["Name", "Value"])).toBe("Name and Value");
    expect(joinWords(["Name", "Value", "Stage"])).toBe("Name, Value and Stage");
  });
});

describe("activityActor", () => {
  it("names the actor, and says so when the account is gone", () => {
    const event = anEvent({
      source: "system_entry",
      entry_id: 1,
      title: "Opportunity created",
      body: "Acme was created.",
    });

    expect(activityActor(event)).toBe("Ada Lovelace");
    expect(activityActor({ ...event, actor_id: null, actor_name: null })).toBe(
      "A removed user",
    );
  });
});
