import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NAV_STORAGE_KEY } from "../lib/nav";
import { ALEX, anOpportunity, aTask } from "./test-api";
import { renderApp, renderDashboard } from "./test-app";

afterEach(() => {
  window.localStorage.clear();
});

/**
 * The shell is R.1's decision 4A. What it is for: before it, four of the five
 * screens hand-rolled their own header with no navigation in it, so from
 * Reports there was no way to reach Automations without going back to the
 * board first.
 */
describe("one shell for every screen", () => {
  it("offers every destination from every screen", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    const rail = screen.getByRole("navigation", { name: "Sections" });
    for (const label of [
      "Opportunities",
      "Tasks",
      "Reports",
      "Automations",
      "Search",
    ]) {
      expect(
        screen.getByRole("link", { name: new RegExp(`^${label}`) }),
      ).toBeInTheDocument();
    }
    expect(rail).toBeInTheDocument();
  });

  it("reaches Automations from Reports, which used to be a dead end", async () => {
    renderApp({ user: ALEX }, "/reports");
    await screen.findByRole("heading", { name: "Reports" });

    await userEvent.click(screen.getByRole("link", { name: /^Automations/ }));

    expect(
      await screen.findByRole("heading", { name: "Automations" }),
    ).toBeInTheDocument();
  });

  it("marks the section the reader is in, including on a deal's own page", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    expect(
      screen.getByRole("link", { name: /^Opportunities/ }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("carries what is late, because a task is the only thing with a deadline", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      tasks: [aTask({ id: 501, title: "Call them back" })],
    });

    expect(
      await screen.findByRole("link", { name: /^Tasks/ }),
    ).toHaveTextContent("1");
  });

  it("collapses, and remembers", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.click(
      screen.getByRole("button", { name: "Collapse navigation" }),
    );

    await waitFor(() =>
      expect(window.localStorage.getItem(NAV_STORAGE_KEY)).toBe("collapsed"),
    );
    expect(
      screen.getByRole("button", { name: "Expand navigation" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("starts every screen at the top", async () => {
    // Each screen is its own page since R.1, and the browser keeps the scroll
    // position across a client-side navigation — so going back to the board
    // landed mid-page with its own title and controls above the fold.
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.click(screen.getByRole("link", { name: /^Reports/ }));
    await screen.findByRole("heading", { name: "Reports" });

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "instant" });
    scrollTo.mockRestore();
  });

  it("leaves the scroll alone when a link names a row inside the screen", async () => {
    // `?entry=`, `?note=`, `?comment=` and `?task=` each scroll their own row
    // into view (D-124, D-170); a reset here would fight them.
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    renderApp({ user: ALEX }, "/opportunities/10?entry=100");
    await screen.findByRole("heading", { level: 2 });

    expect(scrollTo).not.toHaveBeenCalled();
    scrollTo.mockRestore();
  });

  it("asks a signed-out reader to sign in, once, for all five", async () => {
    renderApp({ user: null }, "/automations");

    expect(
      await screen.findByRole("heading", {
        name: /Track every sales opportunity/,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Sections" })).toBeNull();
  });
});
