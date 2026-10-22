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

  /**
   * Keyboard operability of the shell itself (milestone R.2). The rail is
   * what made both of these matter: six links and four bar controls now sit
   * above every screen, on every navigation.
   */
  it("offers a way past the rail, and that way moves the keyboard", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    const skip = screen.getByRole("link", { name: "Skip to content" });
    // The bypass has to be the first thing a Tab reaches, or it is not one.
    await userEvent.tab();
    expect(skip).toHaveFocus();

    // And the target has to be focusable, or activating it scrolls the page
    // and leaves the keyboard in the rail.
    expect(document.getElementById("main-content")).toHaveAttribute(
      "tabindex",
      "-1",
    );
    expect(skip).toHaveAttribute("href", "#main-content");
  });

  it("moves focus into the screen a rail link opens", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.click(screen.getByRole("link", { name: /^Reports/ }));
    await screen.findByRole("heading", { name: "Reports" });

    // Not still on the link: the next Tab belongs to the new screen.
    await waitFor(() =>
      expect(document.getElementById("main-content")).toHaveFocus(),
    );
  });

  it("leaves focus alone on the screen a reader arrives at", async () => {
    // A page load is not a navigation. Taking focus here would interrupt
    // somebody who has not gone anywhere.
    await renderDashboard({ opportunities: [anOpportunity()] });

    expect(document.getElementById("main-content")).not.toHaveFocus();
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
