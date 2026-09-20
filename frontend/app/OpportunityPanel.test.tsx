import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ALEX,
  BLAIR,
  aComment,
  aNote,
  anEntry,
  anOpportunity,
} from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the timeline", () => {
  it("shows entries, notes and comments once an opportunity is opened", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote({ comments: [aComment()] })] })],
    });

    await openTimeline("Northwind rollout");

    expect(
      await screen.findByRole("heading", { name: "Discovery call" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Budget holder is the COO.")).toBeInTheDocument();
    expect(screen.getByText("Agreed.")).toBeInTheDocument();
  });

  it("opens the timeline a deep link arrived with", async () => {
    await renderDashboard(
      { opportunities: [anOpportunity()], entries: [anEntry()] },
      "/opportunities/10",
    );

    expect(
      await screen.findByRole("heading", { name: "Discovery call" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Your role: owner")).toBeInTheDocument();
  });

  it("says so when the link names an opportunity the reader cannot see", async () => {
    await renderDashboard(
      { opportunities: [anOpportunity()] },
      "/opportunities/99",
    );

    expect(
      await screen.findByRole("heading", {
        name: "This opportunity is not available.",
      }),
    ).toBeInTheDocument();
  });

  it("adds an entry, converting the local input to UTC", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [],
    });
    await openTimeline("Northwind rollout");

    const form = (
      await screen.findByRole("button", { name: "Add Entry" })
    ).closest("form") as HTMLElement;
    await userEvent.clear(within(form).getByLabelText("Event time"));
    await userEvent.type(
      within(form).getByLabelText("Event time"),
      "2026-09-06T10:30",
    );
    await userEvent.type(within(form).getByLabelText("Title"), "Proposal sent");
    await userEvent.click(
      within(form).getByRole("button", { name: "Add Entry" }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/timeline")).toHaveLength(1),
    );
    // America/New_York in September is UTC-4.
    expect(api.callsTo("POST", "/timeline")[0].body).toMatchObject({
      title: "Proposal sent",
      event_timestamp: "2026-09-06T14:30:00Z",
      follow_up_date: null,
    });
  });

  it("adds a note and a comment to an entry", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    await userEvent.type(
      await screen.findByPlaceholderText("Add note"),
      "A fresh note",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add Note" }));

    expect(await screen.findByText("A fresh note")).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("Add comment"), "A reply");
    await userEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(await screen.findByText("A reply")).toBeInTheDocument();
  });

  it("edits a note and shows the edit marker", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
    });
    await openTimeline("Northwind rollout");

    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;
    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    const textarea = within(note).getByLabelText("Edit this note");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Budget holder is the CFO.");
    await userEvent.click(within(note).getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Budget holder is the CFO."),
    ).toBeInTheDocument();
    expect(await screen.findByText(/edited/)).toBeInTheDocument();
  });

  it("offers no edit or delete on a system entry", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [
        anEntry({
          id: 101,
          title: "Stage changed to Proposal",
          system_generated: true,
          created_by: ALEX.id,
        }),
      ],
    });
    await openTimeline("Northwind rollout");

    const entry = (
      await screen.findByRole("heading", { name: "Stage changed to Proposal" })
    ).closest("article")!;
    expect(within(entry).getByText("System")).toBeInTheDocument();
    expect(
      within(entry).queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
    expect(
      within(entry).queryByRole("button", { name: "Delete" }),
    ).not.toBeInTheDocument();
  });

  it("sends the filter values, converting the date bounds to UTC", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const filters = (
      await screen.findByLabelText("Filter the timeline by keyword")
    ).closest("form") as HTMLElement;
    await userEvent.type(within(filters).getByLabelText(/keyword/i), "budget");
    await userEvent.type(
      within(filters).getByLabelText("Show entries from"),
      "2026-09-01T00:00",
    );
    await userEvent.click(
      within(filters).getByRole("button", { name: "Filter" }),
    );

    await waitFor(() => {
      const filtered = api.callsTo("GET", "q=budget");
      expect(filtered).toHaveLength(1);
      expect(filtered[0].path).toContain("from=2026-09-01T04%3A00%3A00Z");
    });

    await userEvent.click(
      within(filters).getByRole("button", { name: "Clear" }),
    );
    await waitFor(() =>
      expect(within(filters).getByLabelText(/keyword/i)).toHaveValue(""),
    );
  });
});

describe("what each role is offered", () => {
  it("gives a viewer no way to write anything", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ current_user_role: "viewer", owner_id: BLAIR.id }),
      ],
      entries: [
        anEntry({
          created_by: BLAIR.id,
          notes: [aNote({ created_by: BLAIR.id })],
        }),
      ],
    });
    await openTimeline("Northwind rollout");

    await screen.findByRole("heading", { name: "Discovery call" });
    expect(
      screen.queryByRole("button", { name: "Add Entry" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Add note")).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Add comment"),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".sharing-panel")).toBeNull();
  });

  it("lets an editor change their own note but not a colleague's", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ current_user_role: "editor", owner_id: BLAIR.id }),
      ],
      entries: [
        anEntry({
          created_by: BLAIR.id,
          notes: [
            aNote({ id: 201, created_by: BLAIR.id, body: "Blair's note" }),
            aNote({ id: 202, created_by: ALEX.id, body: "Alex's note" }),
          ],
        }),
      ],
    });
    await openTimeline("Northwind rollout");

    const theirs = (await screen.findByText("Blair's note")).closest(
      "section",
    )!;
    const mine = screen.getByText("Alex's note").closest("section")!;

    expect(
      within(theirs).queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
    expect(
      within(mine).getByRole("button", { name: "Edit" }),
    ).toBeInTheDocument();
    // Adding is still open to an editor.
    expect(screen.getByPlaceholderText("Add note")).toBeInTheDocument();
  });

  it("shows the owner the sharing panel and audit log", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      shares: [
        {
          user_id: BLAIR.id,
          email: BLAIR.email,
          name: BLAIR.name,
          role: "viewer",
          invited_by: ALEX.id,
          invited_by_name: ALEX.name,
          created_at: "2026-09-03T09:00:00Z",
        },
      ],
      auditLog: [
        {
          id: 1,
          opportunity_id: 10,
          actor_id: ALEX.id,
          actor_name: ALEX.name,
          action: "share_added",
          detail: { email: BLAIR.email },
          created_at: "2026-09-03T09:00:00Z",
        },
      ],
    });
    await openTimeline("Northwind rollout");

    expect(
      await screen.findByRole("heading", { name: "Sharing" }),
    ).toBeInTheDocument();
    expect(await screen.findByText(BLAIR.email)).toBeInTheDocument();
    expect(screen.getByText("Audit Log")).toBeInTheDocument();
    expect(screen.getByText("share_added")).toBeInTheDocument();
  });

  it("shares, promotes and removes a colleague", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    await userEvent.type(
      await screen.findByPlaceholderText("Colleague email"),
      BLAIR.email,
    );
    await userEvent.click(screen.getByRole("button", { name: "Share" }));
    expect(await screen.findByText(BLAIR.email)).toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText(`Role for ${BLAIR.email.split("@")[0]}`),
      "editor",
    );
    await waitFor(() =>
      expect(api.callsTo("PATCH", "/shares/")).toHaveLength(1),
    );

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(api.callsTo("DELETE", "/shares/")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(screen.getByText("No shared colleagues")).toBeInTheDocument(),
    );
  });
});

describe("the AI panel", () => {
  it("shows the question and the answer, and the entries it cited", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const sidebar = (
      await screen.findByRole("heading", { name: "AI Agent" })
    ).closest("aside") as HTMLElement;
    expect(
      within(sidebar).getByText("Ask a timeline question."),
    ).toBeInTheDocument();

    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "Where do we stand?",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    expect(
      await within(sidebar).findByText("Where do we stand?"),
    ).toBeInTheDocument();
    expect(
      await within(sidebar).findByText("Answer to: Where do we stand?"),
    ).toBeInTheDocument();
    expect(within(sidebar).getByText("Entries: 100")).toBeInTheDocument();
  });

  it("keeps the conversation when the reader looks at another opportunity", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity(),
        anOpportunity({ id: 11, name: "Globex renewal", stage: "Proposal" }),
      ],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    await userEvent.type(
      await screen.findByLabelText(/Ask the read-only AI agent/),
      "Where do we stand?",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Answer to: Where do we stand?");

    await openTimeline("Globex renewal");
    expect(
      await screen.findByText("Ask a timeline question."),
    ).toBeInTheDocument();

    await openTimeline("Northwind rollout");
    expect(
      await screen.findByText("Answer to: Where do we stand?"),
    ).toBeInTheDocument();
  });

  it("reports a failure rather than pretending there was an answer", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      failures: {
        "POST /api/opportunities/10/ai/ask": [
          503,
          "OPENAI_API_KEY is not configured",
        ],
      },
    });
    await openTimeline("Northwind rollout");

    const sidebar = (
      await screen.findByRole("heading", { name: "AI Agent" })
    ).closest("aside") as HTMLElement;
    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "Where do we stand?",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    expect(
      await within(sidebar).findByText("OPENAI_API_KEY is not configured"),
    ).toBeInTheDocument();
  });
});

describe("changing and removing what is already there", () => {
  it("loads an entry into the form and saves the edit", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;
    await userEvent.click(within(entry).getByRole("button", { name: "Edit" }));

    const form = (
      await screen.findByRole("button", { name: "Save Entry" })
    ).closest("form") as HTMLElement;
    expect(within(form).getByLabelText("Title")).toHaveValue("Discovery call");

    await userEvent.clear(within(form).getByLabelText("Title"));
    await userEvent.type(
      within(form).getByLabelText("Title"),
      "Discovery call (revised)",
    );
    await userEvent.click(
      within(form).getByRole("button", { name: "Save Entry" }),
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/timeline/100")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/timeline/100")[0].body).toMatchObject({
      title: "Discovery call (revised)",
    });
  });

  it("abandons an entry edit without sending anything", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;
    await userEvent.click(within(entry).getByRole("button", { name: "Edit" }));

    const form = (
      await screen.findByRole("button", { name: "Save Entry" })
    ).closest("form") as HTMLElement;
    await userEvent.click(within(form).getByRole("button", { name: "Cancel" }));

    expect(
      await screen.findByRole("button", { name: "Add Entry" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("");
    expect(api.callsTo("PATCH", "/api/timeline/100")).toHaveLength(0);
  });

  it("deletes an entry once the confirmation is accepted", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");
    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;

    vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(
      within(entry).getByRole("button", { name: "Delete" }),
    );
    expect(api.callsTo("DELETE", "/api/timeline/100")).toHaveLength(0);

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(
      within(entry).getByRole("button", { name: "Delete" }),
    );

    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/timeline/100")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "Discovery call" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("deletes a note and a comment", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote({ comments: [aComment()] })] })],
    });
    await openTimeline("Northwind rollout");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const comment = (await screen.findByText("Agreed.")).closest(
      ".comment-row",
    ) as HTMLElement;
    await userEvent.click(
      within(comment).getByRole("button", { name: "Delete" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("Agreed.")).not.toBeInTheDocument(),
    );

    const note = screen
      .getByText("Budget holder is the COO.")
      .closest("section")!;
    await userEvent.click(within(note).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(
        screen.queryByText("Budget holder is the COO."),
      ).not.toBeInTheDocument(),
    );
  });

  it("abandons a note edit and leaves the text alone", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
    });
    await openTimeline("Northwind rollout");

    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;
    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    await userEvent.type(
      within(note).getByLabelText("Edit this note"),
      " and the CFO",
    );
    await userEvent.click(within(note).getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Budget holder is the COO.")).toBeInTheDocument();
    expect(api.callsTo("PATCH", "/api/notes/200")).toHaveLength(0);
  });

  it("ignores an empty note or comment instead of posting it", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
    });
    await openTimeline("Northwind rollout");

    await userEvent.click(
      await screen.findByRole("button", { name: "Add Note" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(api.callsTo("POST", "/notes")).toHaveLength(0);
    expect(api.callsTo("POST", "/comments")).toHaveLength(0);
  });
});

describe("when the API refuses", () => {
  it("reports a refused entry edit", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ current_user_role: "editor", owner_id: BLAIR.id }),
      ],
      entries: [anEntry()],
      failures: {
        "POST /api/opportunities/10/timeline": [
          403,
          "Viewer cannot edit this opportunity",
        ],
      },
    });
    await openTimeline("Northwind rollout");

    const form = (
      await screen.findByRole("button", { name: "Add Entry" })
    ).closest("form") as HTMLElement;
    await userEvent.type(within(form).getByLabelText("Title"), "Refused");
    await userEvent.click(
      within(form).getByRole("button", { name: "Add Entry" }),
    );

    expect(
      await screen.findByText("Viewer cannot edit this opportunity"),
    ).toBeInTheDocument();
  });

  it("reports a refused note edit", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
      failures: {
        "PATCH /api/notes/200": [
          403,
          "Only the author or the opportunity owner can edit this note",
        ],
      },
    });
    await openTimeline("Northwind rollout");

    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;
    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    await userEvent.type(within(note).getByLabelText("Edit this note"), "!");
    await userEvent.click(within(note).getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "Only the author or the opportunity owner can edit this note",
      ),
    ).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote({ comments: [aComment()] })] })],
      failures: { "DELETE /api/comments/300": [403, "Not yours to delete"] },
    });
    await openTimeline("Northwind rollout");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const comment = (await screen.findByText("Agreed.")).closest(
      ".comment-row",
    ) as HTMLElement;
    await userEvent.click(
      within(comment).getByRole("button", { name: "Delete" }),
    );

    expect(await screen.findByText("Not yours to delete")).toBeInTheDocument();
    expect(screen.getByText("Agreed.")).toBeInTheDocument();
  });

  it("reports a timeline that will not load", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      failures: {
        "GET /api/opportunities/10/timeline": [404, "Opportunity not found"],
      },
    });

    await openTimeline("Northwind rollout");

    expect(
      await screen.findByText("Opportunity not found"),
    ).toBeInTheDocument();
  });
});
