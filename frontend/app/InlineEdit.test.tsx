import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { editableOpportunityFields } from "../lib/domain";
import { InlineEdit } from "./InlineEdit";

/**
 * The primitive behind milestone 2.11, tested on its own: the affordance, the
 * editor that replaces the value in the same space, and the focus rule that
 * is the reason for doing any of it.
 */
function renderField(
  field = editableOpportunityFields.name,
  value = "Northwind rollout",
  editable = true,
) {
  const onSave = vi.fn();
  render(
    <InlineEdit field={field} value={value} editable={editable} onSave={onSave}>
      {value}
    </InlineEdit>,
  );
  return onSave;
}

describe("editing a field where it is read", () => {
  it("offers the value itself as the way in, and opens an editor on it", async () => {
    renderField();

    const trigger = screen.getByTitle("Edit Opportunity");
    expect(trigger).toHaveTextContent("Northwind rollout");

    await userEvent.click(trigger);

    const control = screen.getByLabelText("Opportunity");
    expect(control).toHaveValue("Northwind rollout");
    // The reader is put in the editor, not left to find it.
    expect(control).toHaveFocus();
  });

  it("saves what was typed, and only when it changed", async () => {
    const onSave = renderField();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save Opportunity" }),
    );
    expect(onSave).not.toHaveBeenCalled();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.type(screen.getByLabelText("Opportunity"), " phase two");
    await userEvent.click(
      screen.getByRole("button", { name: "Save Opportunity" }),
    );

    expect(onSave).toHaveBeenCalledWith("Northwind rollout phase two");
  });

  it("saves on Enter without a form around it", async () => {
    const onSave = renderField();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.type(screen.getByLabelText("Opportunity"), "!{Enter}");

    expect(onSave).toHaveBeenCalledWith("Northwind rollout!");
  });

  // The whole point of editing in place: the reader ends where they started.
  it("abandons on Esc and hands focus back to the value it opened from", async () => {
    const onSave = renderField();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.type(screen.getByLabelText("Opportunity"), " and more");
    await userEvent.keyboard("{Escape}");

    expect(onSave).not.toHaveBeenCalled();
    const trigger = screen.getByTitle("Edit Opportunity");
    expect(trigger).toHaveTextContent("Northwind rollout");
    expect(trigger).toHaveFocus();
  });

  it("hands focus back after Cancel too", async () => {
    renderField();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.click(
      screen.getByRole("button", { name: "Cancel editing Opportunity" }),
    );

    expect(screen.getByTitle("Edit Opportunity")).toHaveFocus();
  });

  // What the API would refuse is refused here, because the write is
  // optimistic: an editor that closes and then silently reverts is worse than
  // one that stays open and says why.
  it("keeps a required field open rather than saving it empty", async () => {
    const onSave = renderField();

    await userEvent.click(screen.getByTitle("Edit Opportunity"));
    await userEvent.clear(screen.getByLabelText("Opportunity"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save Opportunity" }),
    );

    expect(onSave).not.toHaveBeenCalled();
    expect(
      screen.getByText("Opportunity cannot be empty."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Opportunity")).toBeInTheDocument();
  });

  it("refuses a negative value", async () => {
    const onSave = renderField(editableOpportunityFields.value, "185000");

    await userEvent.click(screen.getByTitle("Edit Value"));
    await userEvent.clear(screen.getByLabelText("Value"));
    await userEvent.type(screen.getByLabelText("Value"), "-5");
    await userEvent.click(screen.getByRole("button", { name: "Save Value" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(
      screen.getByText("Value must be a number, and not negative."),
    ).toBeInTheDocument();
  });

  // An optional field is how a close date is cleared: the patch sends null.
  it("lets an optional date be emptied", async () => {
    const onSave = renderField(
      editableOpportunityFields.expected_close_date,
      "2026-12-01",
    );

    await userEvent.click(screen.getByTitle("Edit Close date"));
    await userEvent.clear(screen.getByLabelText("Close date"));
    await userEvent.click(
      screen.getByRole("button", { name: "Save Close date" }),
    );

    expect(onSave).toHaveBeenCalledWith("");
    expect(editableOpportunityFields.expected_close_date.patch("")).toEqual({
      expected_close_date: null,
    });
  });

  it("draws the fixed stage list rather than a text box", async () => {
    const onSave = renderField(editableOpportunityFields.stage, "Negotiation");

    await userEvent.click(screen.getByTitle("Edit Stage"));
    await userEvent.selectOptions(screen.getByLabelText("Stage"), "Closed Won");
    await userEvent.click(screen.getByRole("button", { name: "Save Stage" }));

    expect(onSave).toHaveBeenCalledWith("Closed Won");
  });

  it("offers no affordance at all to a reader who may not change it", () => {
    renderField(editableOpportunityFields.name, "Northwind rollout", false);

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
  });
});
