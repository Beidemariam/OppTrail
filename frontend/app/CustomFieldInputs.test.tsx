import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CustomFieldInputs } from "./CustomFieldInputs";
import { aCustomField } from "./test-api";

/**
 * The control each field type gets (milestone 6.1).
 *
 * Rendered directly rather than through a page: this component holds no
 * hooks, and the thing worth testing is that seven types produce seven
 * sensible controls and report values in the shape the API validates
 * (`app/custom_fields.py`). A value of the wrong shape is a 422 that names
 * the field, so what matters here is that a checkbox reports a boolean and a
 * number reports a number.
 */
function inputsFor(
  field: Parameters<typeof aCustomField>[0],
  values: Record<string, unknown> = {},
) {
  const onChange = vi.fn();
  render(
    <CustomFieldInputs
      fields={[aCustomField(field)]}
      values={values}
      onChange={onChange}
    />,
  );
  return onChange;
}

describe("the control a field type gets", () => {
  it("renders nothing at all when no fields are defined", () => {
    const { container } = render(
      <CustomFieldInputs fields={[]} values={{}} onChange={vi.fn()} />,
    );
    // Not an empty fieldset with a legend: a deployment that defines no
    // fields should see no change to either form.
    expect(container).toBeEmptyDOMElement();
  });

  it("reports text as typed", async () => {
    const onChange = inputsFor({ type: "text", label: "Region" });
    await userEvent.type(screen.getByLabelText("Region"), "E");
    expect(onChange).toHaveBeenCalledWith({ region: "E" });
  });

  it("reports a number as a number, not as text", async () => {
    // The server refuses a string in a number field, so a form that posted
    // "42" would be a 422 the reader did not cause.
    const onChange = inputsFor({ type: "number", label: "Headcount" });
    const input = screen.getByLabelText("Headcount");
    expect(input).toHaveAttribute("type", "number");
    await userEvent.type(input, "4");
    expect(onChange).toHaveBeenCalledWith({ region: 4 });
  });

  it("clears a number rather than reporting an empty string", async () => {
    const onChange = inputsFor(
      { type: "number", label: "Headcount" },
      {
        region: 42,
      },
    );
    await userEvent.clear(screen.getByLabelText("Headcount"));
    expect(onChange).toHaveBeenCalledWith({});
  });

  it("reports a date through a date control", async () => {
    const onChange = inputsFor({ type: "date", label: "Renews on" });
    const input = screen.getByLabelText("Renews on");
    expect(input).toHaveAttribute("type", "date");
    await userEvent.type(input, "2026-12-01");
    expect(onChange).toHaveBeenCalledWith({ region: "2026-12-01" });
  });

  it("reports a checkbox as a boolean, both ways", async () => {
    const onChange = inputsFor({ type: "checkbox", label: "Strategic" });
    await userEvent.click(screen.getByLabelText("Strategic"));
    expect(onChange).toHaveBeenCalledWith({ region: true });

    const second = inputsFor(
      { type: "checkbox", label: "Strategic" },
      {
        region: true,
      },
    );
    await userEvent.click(screen.getAllByLabelText("Strategic")[1]);
    // `false` is a value, not an absence: unticking has to report it rather
    // than dropping the key, or the reader cannot say "no".
    expect(second).toHaveBeenCalledWith({ region: false });
  });

  it("offers a select's options and a way back to unset", async () => {
    const onChange = inputsFor({
      type: "select",
      label: "Region",
      options: ["EMEA", "APAC"],
    });
    await userEvent.selectOptions(screen.getByLabelText("Region"), "APAC");
    expect(onChange).toHaveBeenCalledWith({ region: "APAC" });

    const second = inputsFor(
      { type: "select", label: "Region", options: ["EMEA", "APAC"] },
      { region: "APAC" },
    );
    await userEvent.selectOptions(screen.getAllByLabelText("Region")[1], "");
    expect(second).toHaveBeenCalledWith({});
  });

  it("builds a multi-select's list by adding and removing", async () => {
    const onChange = inputsFor({
      type: "multi_select",
      label: "Products",
      options: ["Core", "Addon"],
    });
    await userEvent.click(screen.getByLabelText("Core"));
    expect(onChange).toHaveBeenCalledWith({ region: ["Core"] });

    const second = inputsFor(
      { type: "multi_select", label: "Products", options: ["Core", "Addon"] },
      { region: ["Core", "Addon"] },
    );
    await userEvent.click(screen.getAllByLabelText("Core")[1]);
    expect(second).toHaveBeenCalledWith({ region: ["Addon"] });

    // Emptying the last one clears the key rather than storing `[]`.
    const third = inputsFor(
      { type: "multi_select", label: "Products", options: ["Core"] },
      { region: ["Core"] },
    );
    await userEvent.click(screen.getAllByLabelText("Core")[2]);
    expect(third).toHaveBeenCalledWith({});
  });

  it("takes a person as an id", async () => {
    const onChange = inputsFor({ type: "user", label: "Sponsor" });
    await userEvent.type(screen.getByLabelText("Sponsor"), "7");
    expect(onChange).toHaveBeenCalledWith({ region: 7 });
  });

  it("says which fields are required", () => {
    inputsFor({ type: "text", label: "Region", required: true });
    expect(screen.getByLabelText("Region (required)")).toBeInTheDocument();
  });
});
