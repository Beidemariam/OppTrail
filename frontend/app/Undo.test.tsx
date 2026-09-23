import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { aComment, aNote, anEntry, anOpportunity } from "./test-api";
import { acceptConfirmation, openTimeline, renderDashboard } from "./test-app";
import { TOAST_DURATION_MS, ToastProvider, useToasts } from "./Toasts";

/**
 * Undo, the toast it is offered on, and the optimistic updates it pairs with
 * (milestone 2.4b, `docs/UX.md`: "Optimistic by default, undo instead of
 * confirm").
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

/** Raises the toast a delete raises, without deleting anything. */
function Raise() {
  const show = useToasts();
  return (
    <button
      type="button"
      onClick={() =>
        show({
          message: "Timeline entry deleted.",
          action: { label: "Undo", run: () => {} },
        })
      }
    >
      raise
    </button>
  );
}

describe("the undo toast", () => {
  it("stops offering the way back after the undo window closes", async () => {
    // Rendered on its own rather than through the dashboard: this is about the
    // 10-second window and nothing else, and a fake clock is easier to trust
    // with no requests in flight under it.
    // `shouldAdvanceTime` keeps the clock moving on its own, so userEvent's
    // own awaits still resolve; the jump below is what closes the window.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(
      <ToastProvider>
        <Raise />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "raise" }));
    expect(screen.getByText("Timeline entry deleted.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Undo" })).toBeVisible();

    await act(async () => {
      vi.advanceTimersByTime(TOAST_DURATION_MS);
    });

    expect(screen.queryByText("Timeline entry deleted.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("can be dismissed without undoing anything", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");
    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;

    await userEvent.click(
      within(entry).getByRole("button", { name: "Delete" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Dismiss" }),
    );

    expect(screen.queryByText("Timeline entry deleted.")).toBeNull();
    expect(api.callsTo("POST", "/api/v2/timeline/100/restore")).toHaveLength(0);
    expect(
      screen.queryByRole("heading", { name: "Discovery call" }),
    ).toBeNull();
  });

  it("explains a restore the server refuses, and keeps the row gone", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      failures: {
        "POST /api/v2/timeline/100/restore": [404, "Deleted entry not found"],
      },
    });
    await openTimeline("Northwind rollout");
    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;

    await userEvent.click(
      within(entry).getByRole("button", { name: "Delete" }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));

    expect(
      await screen.findByText(
        /Could not restore the timeline entry: Deleted entry not found/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Discovery call" }),
    ).toBeNull();
  });
});

describe("optimistic updates", () => {
  /**
   * The guard for `onMutate` (brief §6.5, confirmed to fail first): with the
   * optimistic removal taken out of `useDeleteComment`, the comment is still
   * on screen while the request is in flight and this fails.
   */
  it("removes what was deleted before the server has answered", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote({ comments: [aComment()] })] })],
      pending: ["DELETE /api/v2/comments/300"],
    });
    await openTimeline("Northwind rollout");
    const comment = (await screen.findByText("Agreed.")).closest(
      ".comment-row",
    ) as HTMLElement;

    await userEvent.click(
      within(comment).getByRole("button", { name: "Delete" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("Agreed.")).not.toBeInTheDocument(),
    );
    expect(api.callsTo("DELETE", "/api/v2/comments/300")).toHaveLength(1);
    // Still in flight: nothing has confirmed the delete, and the toast that
    // offers Undo has not been raised yet either.
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();

    api.release("DELETE /api/v2/comments/300");
    expect(await screen.findByRole("button", { name: "Undo" })).toBeVisible();
  });

  it("puts a note edit on screen before the save returns", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
      pending: ["PATCH /api/v2/notes/200"],
    });
    await openTimeline("Northwind rollout");
    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;

    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    await userEvent.clear(within(note).getByLabelText("Edit this note"));
    await userEvent.type(
      within(note).getByLabelText("Edit this note"),
      "Budget holder is the CFO.",
    );
    await userEvent.click(within(note).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Budget holder is the CFO.")).toBeVisible();
    api.release("PATCH /api/v2/notes/200");
    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/notes/200")).toHaveLength(1),
    );
    expect(screen.getByText("Budget holder is the CFO.")).toBeVisible();
  });

  it("rolls a refused note edit back to what the server still holds", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
      failures: { "PATCH /api/v2/notes/200": [403, "Not yours to edit"] },
    });
    await openTimeline("Northwind rollout");
    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;

    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    await userEvent.type(
      within(note).getByLabelText("Edit this note"),
      " Maybe.",
    );
    await userEvent.click(within(note).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Not yours to edit")).toBeInTheDocument();

    // The editor stays open on a refused save, holding what was typed. What
    // was rolled back is the cache behind it: abandoning the edit shows the
    // note the server still has, not the optimistic version.
    await userEvent.click(within(note).getByRole("button", { name: "Cancel" }));
    expect(
      await screen.findByText("Budget holder is the COO."),
    ).toBeInTheDocument();
  });
});

describe("deleting an opportunity", () => {
  it("still asks first, and offers undo once it is gone", async () => {
    const api = await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    // The one destructive action that keeps its confirmation, and the only
    // one that makes the reader type the name back: it cascades across a whole
    // record (`docs/UX.md`, milestone 2.5).
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");

    await waitFor(() =>
      expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument(),
    );

    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));

    expect(await screen.findByText("Northwind rollout")).toBeInTheDocument();
    expect(
      api.callsTo("POST", "/api/v2/opportunities/10/restore"),
    ).toHaveLength(1);
    // The exact path, not `callsTo`'s substring: a restore is a POST under
    // `/api/v2/opportunities/...` too, and the point here is that undo did
    // not re-create the card under a new id.
    expect(
      api.calls.filter(
        (call) =>
          call.method === "POST" && call.path === "/api/v2/opportunities",
      ),
    ).toHaveLength(0);
  });

  it("reports a delete the server refuses and leaves the card alone", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      failures: {
        "DELETE /api/v2/opportunities/10": [
          403,
          "Only the owner can delete this",
        ],
      },
    });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");

    expect(
      await screen.findByText(
        /Could not delete the opportunity: Only the owner can delete this/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
  });
});
