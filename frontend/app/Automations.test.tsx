import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ALEX, BLAIR, anOpportunity } from "./test-api";
import { renderApp } from "./test-app";
import {
  automationSentence,
  type AutomationRule,
  type AutomationRuleCreate,
} from "../lib/domain";

/**
 * The automations screen (milestone 6.3, `docs/FEATURES.md` §11).
 *
 * What a rule *does* is `backend/tests/test_automations.py`. What matters here
 * is the half §11 calls legibility: that a rule reads back as a sentence, that
 * a preview says what would happen before anything is written, that a run log
 * shows a skip and its reason, and that somebody else's rule is visible
 * without being operable.
 */
beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  document.cookie = "opptrail_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function aRule(overrides: Partial<AutomationRule> = {}): AutomationRule {
  return {
    id: 50,
    name: "Nudge the quiet ones",
    trigger_type: "no_activity",
    trigger: {
      days: 14,
      to_stage: null,
      from_stage: null,
      entry_type: null,
      field: null,
    },
    conditions: [],
    action_type: "create_task",
    action: {
      title: "Chase this deal",
      body: null,
      recipient: "owner",
      due_in_days: 3,
      entry_type: null,
      stage: null,
    },
    enabled: true,
    created_by: ALEX.id,
    creator_name: ALEX.name,
    created_at: "2026-10-01T09:00:00Z",
    updated_at: "2026-10-01T09:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

async function openAutomations(options: Parameters<typeof renderApp>[0] = {}) {
  const api = renderApp({ user: ALEX, ...options }, "/automations");
  await screen.findByRole("heading", { name: "Automations" });
  return api;
}

describe("reading a rule", () => {
  it("prints the rule as a sentence rather than as its parts", async () => {
    await openAutomations({ automationRules: [aRule()] });

    // The sentence is the whole point of §11's "legible": a reader has to be
    // able to tell what a rule does without reconstructing it from selects.
    expect(
      await screen.findByText(
        "When nothing has happened for 14 days, create a task for the " +
          'deal\'s owner: "Chase this deal".',
      ),
    ).toBeInTheDocument();
  });

  it("names the conditions in the sentence, joined by and", async () => {
    await openAutomations({
      automationRules: [
        aRule({
          conditions: [
            { field: "value", op: "gte", value: "50000" },
            { field: "stage", op: "ne", value: "Closed Won" },
          ],
        }),
      ],
    });

    expect(
      await screen.findByText(
        /if Value is at least 50000 and Stage is not Closed Won/,
      ),
    ).toBeInTheDocument();
  });

  it("shows somebody else's rule without offering its controls", async () => {
    // D-173: a colleague's rule can move a deal you own, so it has to be
    // visible; the API refuses the writes, so the screen does not offer them.
    await openAutomations({
      automationRules: [
        aRule({ created_by: BLAIR.id, creator_name: BLAIR.name }),
      ],
    });

    expect(await screen.findByText(/Blair's/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
  });

  it("suggests the rule worth having when there are none", async () => {
    await openAutomations({ automationRules: [] });
    expect(
      await screen.findByText(/nothing has happened on a deal for fourteen/),
    ).toBeInTheDocument();
  });
});

describe("previewing before running", () => {
  it("says what would happen and writes nothing", async () => {
    const api = await openAutomations({
      automationRules: [aRule()],
      opportunities: [anOpportunity(), anOpportunity({ id: 11, name: "Acme" })],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Preview" }),
    );

    expect(
      await screen.findByText(/Preview: matched 2 of 2 deals/),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("preview only; nothing was written"),
    ).toHaveLength(2);
    // The mode is in the request, which is what decides whether the server
    // writes: a preview that posted `dry_run=false` would be a preview that
    // changed things.
    expect(
      api.calls.some((call) => call.path.includes("/run?dry_run=true")),
    ).toBe(true);
  });

  it("asks before running for real, because it writes to deals off screen", async () => {
    const api = await openAutomations({
      automationRules: [
        aRule({
          action_type: "change_stage",
          action: {
            title: null,
            body: null,
            recipient: "owner",
            due_in_days: null,
            entry_type: null,
            stage: "Proposal",
          },
        }),
      ],
      opportunities: [anOpportunity()],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Run now" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Run it" }),
    );

    await waitFor(() =>
      expect(
        api.calls.some((call) => call.path.includes("/run?dry_run=false")),
      ).toBe(true),
    );
    expect(
      await screen.findByText(/Ran: matched 1 of 1 deals/),
    ).toBeInTheDocument();
  });

  it("does not run when the confirmation is declined", async () => {
    const api = await openAutomations({
      automationRules: [aRule()],
      opportunities: [anOpportunity()],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Run now" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Cancel" }),
    );

    expect(
      api.calls.some((call) => call.path.includes("/run?dry_run=false")),
    ).toBe(false);
  });
});

describe("the run log", () => {
  it("is a disclosure, and shows a skip with its reason", async () => {
    // A skip is the half no timeline can show: a rule that matched and
    // declined leaves no entry anywhere else, so this is where it is read.
    const api = await openAutomations({
      automationRules: [
        aRule({
          creator_name: ALEX.name,
          action_type: "change_stage",
          action: {
            title: null,
            body: null,
            recipient: "owner",
            due_in_days: null,
            entry_type: null,
            stage: "Proposal",
          },
        }),
      ],
      opportunities: [anOpportunity({ owner_id: BLAIR.id })],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Preview" }),
    );
    expect(await screen.findByText("skipped")).toBeInTheDocument();
    expect(
      screen.getByText("Alex may not change stage here"),
    ).toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: /What it has done/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(trigger);

    await waitFor(() =>
      expect(
        api.calls.some((call) =>
          call.path.includes(`/automation-rules/50/runs`),
        ),
      ).toBe(true),
    );
    expect(
      await screen.findByRole("button", { name: /Hide what it has done/ }),
    ).toBeInTheDocument();
  });

  it("says plainly when a rule has not done anything", async () => {
    await openAutomations({ automationRules: [aRule()] });

    await userEvent.click(
      await screen.findByRole("button", { name: /What it has done/ }),
    );
    expect(
      await screen.findByText("This rule has not done anything yet."),
    ).toBeInTheDocument();
  });
});

describe("writing a rule", () => {
  it("offers only the parameters the chosen trigger takes", async () => {
    await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    // `no_activity` is the default and takes days.
    expect(await screen.findByLabelText("Days")).toBeInTheDocument();
    expect(screen.queryByLabelText("Moved to stage")).toBeNull();

    await userEvent.selectOptions(
      screen.getByLabelText("Trigger"),
      "stage_changed",
    );
    expect(await screen.findByLabelText("Moved to stage")).toBeInTheDocument();
    expect(screen.queryByLabelText("Days")).toBeNull();
  });

  it("sends only that kind's keys, so the API is not asked to ignore any", async () => {
    const api = await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(
      await screen.findByLabelText("Name"),
      "Negotiation handoff",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Trigger"),
      "stage_changed",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Moved to stage"),
      "Negotiation",
    );
    await userEvent.selectOptions(screen.getByLabelText("Action"), "add_entry");
    await userEvent.type(screen.getByLabelText("Title"), "Paperwork time");
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));

    const posted = await waitFor(() => {
      const call = api.calls.find(
        (item) =>
          item.method === "POST" && item.path === "/api/v2/automation-rules",
      );
      expect(call).toBeDefined();
      return call!.body as Required<AutomationRuleCreate>;
    });

    expect(posted.trigger_type).toBe("stage_changed");
    expect(posted.trigger.to_stage).toBe("Negotiation");
    // A `stage_changed` trigger takes no `days`, and an `add_entry` action no
    // `due_in_days`: both would be a 422 rather than a key the API ignores.
    expect(posted.trigger.days).toBeNull();
    expect(posted.action.due_in_days).toBeNull();
    expect(posted.action.title).toBe("Paperwork time");
  });

  it("shows the sentence while it is being built, not after saving", async () => {
    await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Trigger"),
      "close_date_approaching",
    );
    expect(
      within(dialog).getByText(/When a close date is 14 days away/),
    ).toBeInTheDocument();
  });

  it("adds and removes a condition, with no way to group them", async () => {
    await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.click(
      await screen.findByRole("button", { name: "Add a condition" }),
    );
    expect(
      await screen.findByLabelText("Condition 1 field"),
    ).toBeInTheDocument();
    // ANDed only (§11): no OR control, and nothing that nests.
    expect(screen.queryByRole("button", { name: /group/i })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /and or or/i })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByLabelText("Condition 1 field")).toBeNull();
  });

  it("offers a live custom field as a condition", async () => {
    await openAutomations({
      automationRules: [],
      customFields: [
        {
          id: 3,
          entity_type: "opportunity",
          key: "region",
          label: "Region",
          type: "select",
          options: ["EMEA", "APAC"],
          required: false,
          position: 0,
          created_by: ALEX.id,
          created_at: "2026-10-01T09:00:00Z",
          updated_at: "2026-10-01T09:00:00Z",
          archived_at: null,
        },
      ],
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Add a condition" }),
    );

    expect(
      within(screen.getByLabelText("Condition 1 field")).getByRole("option", {
        name: "Region",
      }),
    ).toBeInTheDocument();
  });

  it("archives a rule rather than offering to delete it", async () => {
    // There is no DELETE route: the run log points at the row, so a log
    // saying "rule 50 moved this deal" cannot be left pointing at nothing.
    const api = await openAutomations({ automationRules: [aRule()] });

    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    await userEvent.click(
      await screen.findByRole("button", { name: "Archive" }),
    );

    await waitFor(() =>
      expect(
        api.calls.some((call) =>
          call.path.includes("/automation-rules/50/archive"),
        ),
      ).toBe(true),
    );
  });
});

describe("the sentence itself", () => {
  // `automationSentence` is pure, so the cases that would need a dialog each
  // are read here instead -- the same split `lib/activity.ts`'s tests make.
  it("reads every trigger and action", () => {
    const base = aRule();
    expect(
      automationSentence({
        ...base,
        trigger_type: "stage_changed",
        trigger: { ...base.trigger, to_stage: "Proposal" },
      }),
    ).toContain("When a deal moves to Proposal");
    expect(
      automationSentence({
        ...base,
        trigger_type: "entry_created",
        trigger: { ...base.trigger, entry_type: "objection" },
      }),
    ).toContain("When a Objection entry is added");
    expect(
      automationSentence({
        ...base,
        trigger_type: "field_changed",
        trigger: { ...base.trigger, field: "value" },
      }),
    ).toContain("When value changes");
    expect(
      automationSentence({
        ...base,
        action_type: "notify_user",
        action: { ...base.action, recipient: "rule_creator" },
      }),
    ).toContain('notify me: "Chase this deal"');
    expect(
      automationSentence({
        ...base,
        action_type: "change_stage",
        action: { ...base.action, stage: "Closed Won" },
      }),
    ).toContain("move it to Closed Won");
  });
});

describe("editing a rule", () => {
  it("opens with the rule's own values and saves a rewrite", async () => {
    // A rule is read whole, edited in one form and written whole (the custom
    // field definition's shape, not the partial `PATCH`es over content): its
    // parts constrain each other, so a partial update would have to
    // re-validate against the stored half anyway.
    const api = await openAutomations({
      automationRules: [
        aRule({
          trigger_type: "stage_changed",
          trigger: {
            days: null,
            to_stage: "Proposal",
            from_stage: "Qualification",
            entry_type: null,
            field: null,
          },
          conditions: [{ field: "value", op: "gte", value: "50000" }],
        }),
      ],
    });

    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Name")).toHaveValue(
      "Nudge the quiet ones",
    );
    expect(within(dialog).getByLabelText("Moved to stage")).toHaveValue(
      "Proposal",
    );
    expect(within(dialog).getByLabelText("Moved from stage")).toHaveValue(
      "Qualification",
    );
    expect(within(dialog).getByLabelText("Condition 1 value")).toHaveValue(
      "50000",
    );

    await userEvent.clear(within(dialog).getByLabelText("Name"));
    await userEvent.type(within(dialog).getByLabelText("Name"), "Renamed rule");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Save rule" }),
    );

    const patched = await waitFor(() => {
      const call = api.calls.find((item) => item.method === "PATCH");
      expect(call).toBeDefined();
      return call!;
    });
    expect(patched.path).toBe("/api/v2/automation-rules/50");
    expect((patched.body as AutomationRuleCreate).name).toBe("Renamed rule");
  });

  it("closes without writing when Cancel is pressed", async () => {
    const api = await openAutomations({ automationRules: [aRule()] });
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Cancel" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.calls.some((call) => call.method === "PATCH")).toBe(false);
  });
});

describe("every parameter the form can render", () => {
  async function openForm() {
    await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    return screen.findByRole("dialog");
  }

  it("offers the entry type and field controls their triggers take", async () => {
    const dialog = await openForm();

    await userEvent.selectOptions(
      within(dialog).getByLabelText("Trigger"),
      "entry_created",
    );
    const entryType = within(dialog).getByLabelText("Trigger entry type");
    // `stage_change` is never offered: the dashboard's time-in-stage reads
    // that type, and a rule naming it would feed the metric a move that never
    // happened (the API refuses it too).
    expect(
      within(entryType).queryByRole("option", { name: "Stage Change" }),
    ).toBeNull();
    await userEvent.selectOptions(entryType, "call");
    expect(within(dialog).getByText(/When a Call entry is added/)).toBeTruthy();

    await userEvent.selectOptions(
      within(dialog).getByLabelText("Trigger"),
      "field_changed",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Watched field"),
      "account_name",
    );
    expect(
      within(dialog).getByText(/When account_name changes/),
    ).toBeInTheDocument();
  });

  it("offers each action its own parameters and no others", async () => {
    const dialog = await openForm();

    // create_task: recipient and a relative due date, because a rule fires on
    // a day nobody picked.
    expect(within(dialog).getByLabelText("Recipient")).toBeInTheDocument();
    expect(
      within(dialog).getByLabelText("Due in days, optional"),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Recipient"),
      "rule_creator",
    );

    await userEvent.selectOptions(
      within(dialog).getByLabelText("Action"),
      "notify_user",
    );
    expect(within(dialog).getByLabelText("Message")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Due in days, optional")).toBeNull();

    await userEvent.selectOptions(
      within(dialog).getByLabelText("Action"),
      "add_entry",
    );
    expect(within(dialog).getByLabelText("New entry type")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Recipient")).toBeNull();

    await userEvent.selectOptions(
      within(dialog).getByLabelText("Action"),
      "change_stage",
    );
    expect(within(dialog).getByLabelText("New stage")).toBeInTheDocument();
    // A stage change carries no message of its own: the system entry it
    // writes is the `stage_change` one any stage change writes.
    expect(within(dialog).queryByLabelText("Title")).toBeNull();
    expect(within(dialog).queryByLabelText("Details, optional")).toBeNull();
  });

  it("sends the optional body and a parked rule as disabled", async () => {
    const api = await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Parked");
    await userEvent.type(within(dialog).getByLabelText("Title"), "Chase it");
    await userEvent.type(
      within(dialog).getByLabelText("Details, optional"),
      "Procurement was waiting on legal",
    );
    await userEvent.click(within(dialog).getByLabelText("Enabled"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    const posted = await waitFor(() => {
      const call = api.calls.find((item) => item.method === "POST");
      expect(call).toBeDefined();
      return call!.body as Required<AutomationRuleCreate>;
    });
    expect(posted.enabled).toBe(false);
    expect(posted.action.body).toBe("Procurement was waiting on legal");
  });

  it("says which rules the clock checks and which a person triggers", async () => {
    const dialog = await openForm();

    expect(
      within(dialog).getByText(/checked on a schedule/),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Trigger"),
      "stage_changed",
    );
    expect(
      within(dialog).getByText(/runs when somebody makes that change/),
    ).toBeInTheDocument();
  });

  it("shows what the API refused rather than closing", async () => {
    await openAutomations({
      automationRules: [],
      failures: {
        "POST /api/v2/automation-rules": [
          409,
          "You already have 20 enabled rules",
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "One too many");
    await userEvent.type(within(dialog).getByLabelText("Title"), "Chase it");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    expect(
      await within(dialog).findByText("You already have 20 enabled rules"),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("the screen's other answers", () => {
  it("asks an anonymous reader to sign in", async () => {
    renderApp({ user: null }, "/automations");
    // The shell's answer, the same on all five screens since R.1.
    expect(
      await screen.findByRole("heading", {
        name: /Track every sales opportunity/,
      }),
    ).toBeInTheDocument();
  });

  it("surfaces a failed read rather than an empty list", async () => {
    await openAutomations({
      failures: { "GET /api/v2/automation-rules": [500, "Rules unavailable"] },
    });
    expect(await screen.findByText("Rules unavailable")).toBeInTheDocument();
  });

  it("surfaces a failed run", async () => {
    await openAutomations({
      automationRules: [aRule()],
      failures: {
        "POST /api/v2/automation-rules/50/run": [500, "Could not run it"],
      },
    });
    await userEvent.click(
      await screen.findByRole("button", { name: "Preview" }),
    );
    expect(await screen.findByText("Could not run it")).toBeInTheDocument();
  });

  it("surfaces a failed run log read", async () => {
    await openAutomations({
      automationRules: [aRule()],
      failures: {
        "GET /api/v2/automation-rules/50/runs": [500, "No log today"],
      },
    });
    await userEvent.click(
      await screen.findByRole("button", { name: /What it has done/ }),
    );
    expect(await screen.findByText("No log today")).toBeInTheDocument();
  });

  it("keeps an archived rule reachable, marked, and not operable", async () => {
    // The row is kept because its run log points at it ("rule 50 moved this
    // deal" needs rule 50 to still be readable), so it has to be reachable
    // -- but not beside the live rules, which would make this screen a
    // history rather than a list of what runs.
    await openAutomations({
      automationRules: [
        aRule({ archived_at: "2026-10-05T09:00:00Z", enabled: false }),
      ],
    });

    expect(screen.queryByText("Nudge the quiet ones")).toBeNull();
    await userEvent.click(screen.getByLabelText("Show archived rules"));

    expect(await screen.findByText(/Disabled - archived/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).toBeNull();
    expect(
      screen.getByRole("button", { name: /What it has done/ }),
    ).toBeInTheDocument();
  });
});

describe("editing a condition in place", () => {
  it("changes a condition's field, operator and value, and says so", async () => {
    await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add a condition" }),
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Condition 1 field"),
      "value",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Condition 1 operator"),
      "gte",
    );
    await userEvent.type(
      within(dialog).getByLabelText("Condition 1 value"),
      "50000",
    );

    // The sentence is what makes the condition legible, so it is the
    // assertion rather than the three control values.
    expect(
      within(dialog).getByText(/if Value is at least 50000/),
    ).toBeInTheDocument();

    // A second condition is joined by "and", with no control to choose that:
    // §11 ANDs them and rules out OR and nesting.
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add a condition" }),
    );
    expect(within(dialog).getByText("and")).toBeInTheDocument();
  });
});

describe("a refused save says which part was wrong (6.3a, D-180)", () => {
  it("renders the field reason the envelope carries, not the generic sentence", async () => {
    // The defect the human met at the 6.3 review: the API's `fields` have
    // always named the input, and nothing on the client read them, so every
    // refusal read "The request could not be validated".
    await openAutomations({
      automationRules: [],
      failures: {
        "POST /api/v2/automation-rules": [
          422,
          "The request could not be validated",
          { "action.title": "Enter a value" },
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "No title");
    await userEvent.type(within(dialog).getByLabelText("Title"), "x");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    expect(
      await within(dialog).findByText("Enter a value"),
    ).toBeInTheDocument();
    // And the input itself is marked, so the reason is beside what to fix.
    expect(within(dialog).getByLabelText("Title")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      within(dialog).queryByText("The request could not be validated"),
    ).toBeNull();
  });

  it("falls back to the envelope's sentence for a failure with no fields", async () => {
    await openAutomations({
      automationRules: [],
      failures: {
        "POST /api/v2/automation-rules": [
          409,
          "You already have 20 enabled rules",
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "One too many");
    await userEvent.type(within(dialog).getByLabelText("Title"), "Chase it");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    expect(
      await within(dialog).findByText("You already have 20 enabled rules"),
    ).toBeInTheDocument();
  });

  it("shows a whole-rule reason, which belongs to no single input", async () => {
    // `errors.py` keys a cross-field failure `_`, because a rule whose action
    // does not match its trigger is wrong as a whole.
    await openAutomations({
      automationRules: [],
      failures: {
        "POST /api/v2/automation-rules": [
          422,
          "The request could not be validated",
          { _: "A 'create_task' action needs 'title'" },
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "Mismatched");
    await userEvent.type(within(dialog).getByLabelText("Title"), "x");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    expect(
      await within(dialog).findByText("A 'create_task' action needs 'title'"),
    ).toBeInTheDocument();
  });

  it("offers the close-date-plus-change-stage rule the API used to refuse", async () => {
    // **D-179**: the prohibition was mine rather than §11's, and it reached
    // the human as an unexplained 422.
    const api = await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Closing soon");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Trigger"),
      "close_date_approaching",
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Action"),
      "change_stage",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    await waitFor(() =>
      expect(api.calls.some((call) => call.method === "POST")).toBe(true),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("the summary line does not repeat what an input already says", () => {
  it("shows a reason whose input this form does not draw", async () => {
    // A condition's value has no `FieldError` beside it, so the summary is
    // the only place that reason can appear.
    await openAutomations({
      automationRules: [],
      failures: {
        "POST /api/v2/automation-rules": [
          422,
          "The request could not be validated",
          { "conditions.0.value": "'lots' is not a number" },
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(
      within(dialog).getByLabelText("Name"),
      "Bad condition",
    );
    await userEvent.type(within(dialog).getByLabelText("Title"), "x");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    expect(
      await within(dialog).findByText("'lots' is not a number"),
    ).toBeInTheDocument();
    expect(within(dialog).getAllByText("'lots' is not a number")).toHaveLength(
      1,
    );
  });
});

describe("whether the clock is still running (milestone 6.5)", () => {
  it("says when the rules were last checked", async () => {
    await openAutomations({
      automationRules: [aRule()],
      jobRuns: [
        {
          id: 1,
          job: "automations",
          status: "succeeded",
          detail: "1 rules, 2 deals considered, 0 acted on",
          started_at: "2026-10-12T09:00:00Z",
          finished_at: "2026-10-12T09:00:01Z",
        },
      ],
    });

    expect(
      await screen.findByText(/Time-based rules last checked/),
    ).toBeInTheDocument();
  });

  it("says so when nothing has checked them", async () => {
    // The screen a reader is standing on when they wonder why a rule has not
    // fired, which is the only place a dead scheduler is visible.
    await openAutomations({ automationRules: [aRule()], jobRuns: [] });

    expect(
      await screen.findByText("Time-based rules have not been checked yet."),
    ).toBeInTheDocument();
  });
});

describe("what the browser refuses, said out loud (6.5a, D-184)", () => {
  it("explains a days field holding something that is not a number", async () => {
    // The human's finding at the 6.5 review: *"Doesn't take in words for
    // number of days, except for some reason the letter e, and it doesn't say
    // what to fix."* Both halves were true — a number input keeps `e` on
    // screen while reading as empty, and the browser then cancelled the
    // submit with a tooltip that vanished, so nothing was sent and nothing
    // was said.
    const api = await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Letter days");
    await userEvent.type(within(dialog).getByLabelText("Title"), "Chase it");
    const days = within(dialog).getByLabelText("Days");
    await userEvent.clear(days);
    await userEvent.type(days, "e");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    // The *mechanism* is asserted here and the wording in
    // `e2e/28-automations.spec.ts`: the message is the platform's own, and
    // jsdom's is not Chrome's ("Please enter a number." there). What has to
    // hold everywhere is that the field is marked and a reason is drawn
    // beside it.
    expect(days).toHaveAttribute("aria-invalid", "true");
    expect(dialog.querySelector(".field-error")?.textContent).toBeTruthy();
    // Nothing was sent, which is right — and now visible, which is the fix.
    expect(api.calls.some((call) => call.method === "POST")).toBe(false);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("clears the complaint once the field is corrected", async () => {
    const api = await openAutomations({ automationRules: [] });
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Corrected");
    await userEvent.type(within(dialog).getByLabelText("Title"), "Chase it");
    const days = within(dialog).getByLabelText("Days");
    await userEvent.clear(days);
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );
    await waitFor(() =>
      expect(dialog.querySelector(".field-error")?.textContent).toBeTruthy(),
    );

    await userEvent.type(days, "21");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create rule" }),
    );

    await waitFor(() =>
      expect(api.calls.some((call) => call.method === "POST")).toBe(true),
    );
  });
});

describe("who may write one", () => {
  it("offers New rule to an administrator", async () => {
    await openAutomations({ automationRules: [aRule()] });

    expect(
      screen.getByRole("button", { name: "New rule" }),
    ).toBeInTheDocument();
  });

  it("does not offer it to anybody else, and still shows what runs here", async () => {
    // R.1c, **D-215**. Reading the list stays open on purpose: "which
    // automations run here, and whose" is answerable by design (D-173), and a
    // rule's run log is the reason an archived row is kept at all.
    await openAutomations({
      user: { ...ALEX, is_admin: false },
      automationRules: [aRule({ name: "Nudge me about quiet deals" })],
    });

    expect(screen.queryByRole("button", { name: "New rule" })).toBeNull();
    expect(
      await screen.findByText("Nudge me about quiet deals"),
    ).toBeInTheDocument();
  });
});

it("tells a non-administrator why there is no New rule button", async () => {
  // A hidden control with no explanation reads as a missing feature (R.1c).
  await openAutomations({ user: { ...ALEX, is_admin: false } });

  expect(
    await screen.findByText(/Writing one is an administrator's/),
  ).toBeInTheDocument();
});
