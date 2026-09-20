import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider, ThemeToggle } from "./Theme";
import { THEME_STORAGE_KEY } from "../lib/theme";

/**
 * The theme in the browser (milestone 2.5): what gets applied, what is
 * remembered, and what happens when the operating system changes its mind
 * while the app is open.
 */

let systemPrefersDark = false;
let listeners: Array<(event: MediaQueryListEvent) => void> = [];

/** A media query the test can move, which jsdom does not provide. */
function installMatchMedia() {
  listeners = [];
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      get matches() {
        return systemPrefersDark;
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: () => void) =>
        listeners.push(listener),
      removeEventListener: (_: string, listener: () => void) => {
        listeners = listeners.filter((each) => each !== listener);
      },
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

/** The system switching to dark at sunset, with the app already open. */
function systemSwitchesTo(dark: boolean) {
  systemPrefersDark = dark;
  for (const listener of listeners) {
    listener({ matches: dark } as MediaQueryListEvent);
  }
}

beforeEach(() => {
  systemPrefersDark = false;
  window.localStorage.clear();
  installMatchMedia();
});

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

function renderToggle() {
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
  return screen.getByLabelText("Theme");
}

describe("the theme", () => {
  it("follows the system until the reader chooses", async () => {
    systemPrefersDark = true;
    renderToggle();

    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
  });

  it("changes with the system while the app stays open", async () => {
    renderToggle();
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("light"),
    );

    systemSwitchesTo(true);

    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
  });

  it("holds an explicit choice against the system, and remembers it", async () => {
    const control = renderToggle();

    await userEvent.selectOptions(control, "dark");

    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    // The system moving the other way must not undo what was chosen.
    systemSwitchesTo(false);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("starts from what was remembered", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");

    const control = renderToggle();

    expect(control).toHaveValue("dark");
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
  });

  it("can be handed back to the system", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    const control = renderToggle();
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );

    await userEvent.selectOptions(control, "system");

    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("light"),
    );
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
  });
});
