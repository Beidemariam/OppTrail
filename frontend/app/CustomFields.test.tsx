import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ALEX, aCustomField, anEntry, anOpportunity } from "./test-api";
import {
  openTimeline,
  renderDashboard,
  renderDeal,
  openBoardFilters,
} from "./test-app";

/**
 * Custom fields on screen (milestone 6.1, ADR 0006).
 *
 * `docs/FEATURES.md` §3's requirement is one sentence and it is this file's
 * whole subject: "fields appear automatically in Table columns, filters, and
 * the entry form." The roadmap's acceptance criterion names the same three,
 * for a select field, so each of them is a test here.
 */
beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  document.cookie = "opptrail_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

const REGION = aCustomField({
  id: 900,
  key: "region",
  label: "Region",
  type: "select",
  options: ["EMEA", "APAC"],
});

function seeded() {
  return {
    // A copy, not the shared object: the fake API mutates a definition in
    // place when it is archived (as the real one does, in the database), so
    // passing `REGION` itself would let one test's archive leak into the
    // next -- which it did, and which showed up as an unrelated test failing
    // only when run after this file's others.
    customFields: [{ ...REGION }],
    opportunities: [
      {
        ...anOpportunity({ id: 10, name: "Northwind rollout" }),
        custom_values: { region: "EMEA" },
      },
      {
        ...anOpportunity({ id: 11, name: "Globex platform" }),
        custom_values: { region: "APAC" },
      },
    ],
  };
}

describe("a select field appears in the three places §3 names", () => {
  it("is a column the table can draw", async () => {
    await renderDashboard(seeded(), "/?opportunities.view=table");

    // Scoped to the rows: the filter bar below also offers EMEA, as an
    // `<option>`, which is the same field doing its other job.
    // The table's own section, which is a labelled landmark; the windowed
    // rows inside it carry their label on a plain div with no role
    // (`app/VirtualList.tsx`), so the section is what a query can address.
    const rows = () => screen.getByRole("region", { name: "Opportunities" });

    // The dashboard helper waits for the page heading, not for the rows.
    await screen.findByText("Northwind rollout");

    // Not on by default: a new field does not rearrange everyone's table.
    expect(within(rows()).queryByText("EMEA")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^Columns/ }));
    const panel = screen.getByRole("group", {
      name: "Columns shown in the table",
    });
    await userEvent.click(within(panel).getByLabelText("Region"));

    await waitFor(() =>
      expect(within(rows()).getByText("EMEA")).toBeInTheDocument(),
    );
    expect(within(rows()).getByText("APAC")).toBeInTheDocument();
  });

  it("is a filter, and the filter is in the URL", async () => {
    await renderDashboard(seeded());

    await openBoardFilters();
    const filter = await screen.findByLabelText("Filter by Region");
    await userEvent.selectOptions(filter, "EMEA");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(screen.queryByText("Globex platform")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
  });

  it("is an input on the entry form, for an entry field", async () => {
    const api = await renderDashboard({
      customFields: [
        aCustomField({
          id: 901,
          entity_type: "entry",
          key: "sentiment",
          label: "Sentiment",
          type: "select",
          options: ["Warm", "Cold"],
        }),
      ],
      opportunities: [anOpportunity({ id: 10, name: "Northwind rollout" })],
      entries: [anEntry({ id: 100, title: "Discovery call" })],
    });
    await openTimeline("Northwind rollout");

    await userEvent.click(
      await screen.findByRole("button", { name: "New entry" }),
    );
    await userEvent.type(await screen.findByLabelText("Title"), "Pricing call");
    await userEvent.selectOptions(
      await screen.findByLabelText("Sentiment"),
      "Warm",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add Entry" }));

    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/api/v2/opportunities/10/timeline" &&
            (call.body as { custom_values?: Record<string, unknown> })
              .custom_values?.sentiment === "Warm",
        ),
      ).toBe(true),
    );
  });
});

describe("where a value is read (milestone 6.2a)", () => {
  it("shows a deal's fields on its own summary line", async () => {
    // The human's request at the 6.2 review: "please include Business field
    // as one of the things to show in the top line summary of the opportunity
    // in the right side next to value, close date etc."
    await renderDeal({
      customFields: [
        { ...REGION, type: "text", options: [], label: "Business" },
      ],
      opportunities: [
        {
          ...anOpportunity({ id: 10, name: "Northwind rollout" }),
          custom_values: { region: "Public sector" },
        },
      ],
      entries: [anEntry({ id: 100, title: "Discovery call" })],
    });

    const facts = await screen.findByText(/Business: Public sector/);
    expect(facts).toBeInTheDocument();
  });

  it("leaves an unset field off the summary line entirely", async () => {
    // A summary listing every defined field as empty is a longer line that
    // says less.
    await renderDeal({
      customFields: [
        { ...REGION, type: "text", options: [], label: "Business" },
      ],
      opportunities: [
        {
          ...anOpportunity({ id: 10, name: "Northwind rollout" }),
          custom_values: {},
        },
      ],
      entries: [anEntry({ id: 100, title: "Discovery call" })],
    });

    await screen.findByText("Discovery call");
    expect(screen.queryByText(/Business:/)).not.toBeInTheDocument();
  });

  it("shows a yes/no entry field on the card only when it is yes", async () => {
    // The human's other request, and the rule that makes it useful: a "No"
    // takes up the room of a fact without being one.
    const followUp = aCustomField({
      id: 902,
      entity_type: "entry",
      key: "follow_up",
      label: "Follow up",
      type: "checkbox",
    });
    await renderDeal({
      customFields: [followUp],
      opportunities: [anOpportunity({ id: 10, name: "Northwind rollout" })],
      entries: [
        {
          ...anEntry({ id: 100, title: "Needs chasing" }),
          custom_values: { follow_up: true },
        },
        {
          ...anEntry({ id: 101, title: "Nothing pending" }),
          custom_values: { follow_up: false },
        },
      ],
    });

    const chased = (await screen.findByText("Needs chasing")).closest(
      ".timeline-entry",
    );
    const settled = screen
      .getByText("Nothing pending")
      .closest(".timeline-entry");
    expect(chased).not.toBeNull();
    expect(settled).not.toBeNull();
    // The label alone on the card that has it, and nothing on the one that
    // does not -- not "Follow up: Yes" and "Follow up: No".
    // Awaited: the card renders before the definition list arrives, so the
    // chip appears a tick later than the entry title it sits under.
    expect(
      await within(chased as HTMLElement).findByText("Follow up"),
    ).toBeInTheDocument();
    expect(
      within(settled as HTMLElement).queryByText(/Follow up/),
    ).not.toBeInTheDocument();
  });
});

describe("every field type is filterable from the board (R.1)", () => {
  it("offers a text box for a text field and a yes/no for a checkbox", async () => {
    await renderDashboard({
      customFields: [
        aCustomField({ key: "business", label: "Business", type: "text" }),
        aCustomField({
          id: 903,
          key: "signed",
          label: "Signed",
          type: "checkbox",
        }),
      ],
      opportunities: [
        {
          ...anOpportunity({ id: 10, name: "Northwind rollout" }),
          custom_values: { business: "CTCS", signed: true },
        },
        {
          ...anOpportunity({ id: 11, name: "Globex renewal" }),
          custom_values: { business: "Secunet", signed: false },
        },
      ],
    });
    await openBoardFilters();

    await userEvent.type(screen.getByLabelText("Filter by Business"), "ctcs");
    await userEvent.selectOptions(
      screen.getByLabelText("Filter by Signed"),
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(await screen.findByText("Northwind rollout")).toBeInTheDocument();
    expect(screen.queryByText("Globex renewal")).not.toBeInTheDocument();
    // And both read back as chips, in the field's own words.
    expect(
      screen.getByRole("button", { name: /Business: ctcs/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Signed: true/ }),
    ).toBeInTheDocument();
  });
});

describe("defining and retiring a field", () => {
  it("defines one from a label, deriving the key it is stored under", async () => {
    const api = await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    await userEvent.type(await screen.findByLabelText("Label"), "Deal source");
    // The key is derived rather than typed, and shown because it is
    // permanent: the API refuses to change it (ADR 0006).
    const dialog = screen.getByRole("dialog", { name: "Custom fields" });
    expect(within(dialog).getByText("deal_source")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add field" }));

    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/api/v2/custom-fields" &&
            (call.body as { key: string }).key === "deal_source",
        ),
      ).toBe(true),
    );
    // Listed in the dialog, and -- because the definition read is what every
    // screen draws from -- offered by the filter bar behind it at the same
    // time, which is why this is scoped.
    expect(
      await within(
        screen.getByRole("dialog", { name: "Custom fields" }),
      ).findByText("Deal source"),
    ).toBeInTheDocument();
    // And by the filter bar, once the dialog over it is out of the way: the
    // definition read is what every screen draws from.
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await openBoardFilters();
    expect(screen.getByLabelText("Filter by Deal source")).toBeInTheDocument();
  });

  it("asks for options only when the type needs them", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));

    expect(
      screen.queryByLabelText("Options, separated by commas"),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(
      await screen.findByLabelText("Type"),
      "select",
    );
    expect(
      screen.getByLabelText("Options, separated by commas"),
    ).toBeInTheDocument();
  });

  it("archives a field rather than deleting it, and puts it back", async () => {
    const api = await renderDashboard(seeded());
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));

    // Archive, never Delete: the ADR requires that retiring a field leaves
    // its values alone, so nothing here offers to destroy them.
    expect(
      screen.queryByRole("button", { name: "Delete" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));

    await waitFor(() =>
      expect(
        api.calls.some(
          (call) => call.path === "/api/v2/custom-fields/900/archive",
        ),
      ).toBe(true),
    );
    const restore = await screen.findByRole("button", { name: "Restore" });
    await userEvent.click(restore);
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) => call.path === "/api/v2/custom-fields/900/restore",
        ),
      ).toBe(true),
    );
  });

  it("renames a field without touching its key", async () => {
    // The one edit a definition allows that a reader is likely to want: the
    // label is what every screen shows, and the key the values are filed
    // under cannot change (ADR 0006).
    const api = await renderDashboard(seeded());
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));

    // Scoped to the row: the "Add a field" form below has a Label input too.
    const row = screen.getByRole("listitem");
    const input = within(row).getByLabelText("Label");
    await userEvent.clear(input);
    await userEvent.type(input, "Sales region");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.method === "PATCH" &&
            call.path === "/api/v2/custom-fields/900" &&
            (call.body as { label: string }).label === "Sales region" &&
            !("key" in (call.body as object)),
        ),
      ).toBe(true),
    );
  });

  it("abandons a rename on Cancel", async () => {
    const api = await renderDashboard(seeded());
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const row = screen.getByRole("listitem");
    await userEvent.type(within(row).getByLabelText("Label"), " edited");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      api.calls.some(
        (call) =>
          call.method === "PATCH" && call.path.includes("custom-fields"),
      ),
    ).toBe(false);
    // Back to the row, with the label it had.
    expect(screen.getByRole("button", { name: "Rename" })).toBeInTheDocument();
  });

  it("says why a field could not be added", async () => {
    // Defining a field is the widest write surface in the app (D-171), so a
    // refusal has to be legible rather than silent.
    await renderDashboard({
      ...seeded(),
      failures: {
        "POST /api/v2/custom-fields": [
          409,
          "A field with that key already exists here",
        ],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    await userEvent.type(await screen.findByLabelText("Label"), "Region");
    await userEvent.click(screen.getByRole("button", { name: "Add field" }));

    expect(
      await screen.findByText("A field with that key already exists here"),
    ).toBeInTheDocument();
  });

  it("lists a field's type, options and required flag", async () => {
    await renderDashboard({
      ...seeded(),
      customFields: [
        aCustomField({
          id: 900,
          key: "region",
          label: "Region",
          type: "multi_select",
          options: ["EMEA", "APAC"],
          required: true,
        }),
      ],
    });
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));

    // The row, not the dialog: "Select several" is also an option in the
    // type picker of the form below.
    const row = screen.getByRole("listitem");
    expect(within(row).getByText(/Select several/)).toBeInTheDocument();
    expect(within(row).getByText(/required/)).toBeInTheDocument();
    expect(within(row).getByText("EMEA, APAC")).toBeInTheDocument();
  });

  it("shows the fields for the entity type the dialog is looking at", async () => {
    await renderDashboard({
      ...seeded(),
      customFields: [
        { ...REGION },
        aCustomField({
          id: 901,
          entity_type: "entry",
          key: "sentiment",
          label: "Sentiment",
        }),
      ],
    });
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    const dialog = screen.getByRole("dialog", { name: "Custom fields" });

    expect(await within(dialog).findByText("Region")).toBeInTheDocument();
    expect(within(dialog).queryByText("Sentiment")).not.toBeInTheDocument();

    await userEvent.selectOptions(
      within(dialog).getByLabelText("These fields are on"),
      "entry",
    );
    expect(within(dialog).getByText("Sentiment")).toBeInTheDocument();
    expect(within(dialog).queryByText("Region")).not.toBeInTheDocument();
  });

  it("says so when an entity type has no fields yet", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    expect(
      await screen.findByText("No fields defined here yet."),
    ).toBeInTheDocument();
  });

  it("stops offering an archived field as a filter", async () => {
    // The consequence that matters: archiving takes effect on every screen
    // at once, because the definition read is what each of them draws from.
    const api = await renderDashboard(seeded());
    await openBoardFilters();
    expect(
      await screen.findByLabelText("Filter by Region"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Fields" }));
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) => call.path === "/api/v2/custom-fields/900/archive",
        ),
      ).toBe(true),
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() =>
      expect(
        screen.queryByLabelText("Filter by Region"),
      ).not.toBeInTheDocument(),
    );
  });
});

describe("who may define one", () => {
  it("offers Fields to an administrator", async () => {
    await renderDashboard(seeded());

    expect(
      await screen.findByRole("button", { name: "Fields" }),
    ).toBeInTheDocument();
  });

  it("does not offer it to anybody else, but still draws their columns", async () => {
    // R.1c, **D-215**: the reviewer's ruling at the Phase R gate. The control
    // is hidden rather than the feature — the definitions still arrive, and
    // the column picker and filter bar are built from them, because "which
    // fields does this team track" is not a privileged question.
    await renderDashboard(
      { ...seeded(), user: { ...ALEX, is_admin: false } },
      "/?opportunities.view=table&opportunities.columns=name,custom:region",
    );
    await screen.findByRole("button", { name: "Table" });

    expect(screen.queryByRole("button", { name: "Fields" })).toBeNull();
    expect(await screen.findByText("Region")).toBeInTheDocument();
  });
});
