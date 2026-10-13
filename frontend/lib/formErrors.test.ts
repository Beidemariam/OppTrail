import { describe, expect, it } from "vitest";

import { invalidFields } from "./formErrors";

/**
 * Milestone 6.5a. The human's own report is the specification for this:
 * *"Doesn't take in words for number of days, except for some reason the
 * letter e, and it doesn't say what to fix."*
 */
function formWith(html: string): HTMLFormElement {
  const form = document.createElement("form");
  form.innerHTML = html;
  document.body.append(form);
  return form;
}

describe("invalidFields", () => {
  it("is empty when every control is satisfied", () => {
    const form = formWith(
      '<input name="name" value="Nudge" required /><input name="trigger.days" type="number" value="14" required />',
    );
    expect(invalidFields(form)).toEqual({});
  });

  it("names a required field that was left empty", () => {
    const form = formWith('<input name="action.title" value="" required />');
    // The browser's own sentence, not one invented here: it is better than
    // anything this project would write, and it is already localized.
    expect(Object.keys(invalidFields(form))).toEqual(["action.title"]);
  });

  it("names a number field that holds something that is not a number", () => {
    // The `e` case exactly. A number input keeps the character on screen —
    // `e` is legal in `1e5` — while reporting its value as empty with
    // `badInput` set, so the field looks filled and reads as empty.
    const form = formWith(
      '<input name="trigger.days" type="number" required />',
    );
    const days = form.elements.namedItem("trigger.days") as HTMLInputElement;
    days.value = "e";

    expect(Object.keys(invalidFields(form))).toEqual(["trigger.days"]);
  });

  it("ignores a control with no name, which no display could key on", () => {
    const form = formWith('<input value="" required />');
    expect(invalidFields(form)).toEqual({});
  });

  it("ignores a disabled control, which is not the reader's to fix", () => {
    const form = formWith('<input name="stage" value="" required disabled />');
    expect(invalidFields(form)).toEqual({});
  });
});
