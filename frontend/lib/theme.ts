/**
 * Light and dark themes as a preference, resolved to one of two palettes
 * (milestone 2.5, **D-003** accepted).
 *
 * `docs/DESIGN-SYSTEM.md` ships dark "from the start, because retrofitting
 * means auditing every component twice", and makes it "a palette swap" by
 * keeping every colour a semantic role. That is why this module carries no
 * colours at all: it decides which palette is in force and writes one
 * attribute, and `app/globals.css` holds the two sets of role values behind
 * `:root` and `[data-theme="dark"]`.
 *
 * Resolution happens here rather than in CSS `prefers-color-scheme` so that
 * both palettes live behind the same attribute selector: one declaration to
 * read, one to test, and a reader's explicit choice can override the system's
 * without a second copy of the dark block.
 */

/** What the reader chose. `system` follows the operating system. */
export type ThemePreference = "system" | "light" | "dark";

/** What is actually painted. */
export type Theme = "light" | "dark";

export const THEME_PREFERENCES: readonly ThemePreference[] = [
  "system",
  "light",
  "dark",
] as const;

/** Where the choice survives a reload. Not a cookie: the server never needs
 * it, because nothing is rendered on the server (ADR 0005). */
export const THEME_STORAGE_KEY = "opptrail-theme";

/** The media query the `system` preference asks. */
export const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/**
 * The system preference, as an external store `useSyncExternalStore` can read
 * — which is what it is: state that lives outside React and changes on its own
 * (a reader switching their desktop to dark at sunset).
 */
export function subscribeToDarkScheme(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_SCHEME_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_SCHEME_QUERY).matches;
}

function isPreference(value: string | null): value is ThemePreference {
  return value !== null && THEME_PREFERENCES.includes(value as ThemePreference);
}

/**
 * The stored preference, or `system` when there is none — which is also the
 * answer when storage is unavailable (a private window can throw on read).
 */
export function readThemePreference(
  storage: Storage | undefined,
): ThemePreference {
  try {
    const stored = storage?.getItem(THEME_STORAGE_KEY) ?? null;
    return isPreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

/** Remembers the choice. A failed write costs the reader nothing but the
 * memory of it, so it is not worth raising. */
export function storeThemePreference(
  storage: Storage | undefined,
  preference: ThemePreference,
): void {
  try {
    storage?.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Ignored deliberately: see above.
  }
}

/** The palette a preference resolves to, given what the system asks for. */
export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark: boolean,
): Theme {
  if (preference === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return preference;
}

/**
 * Puts the resolved theme where the stylesheet can see it.
 *
 * `color-scheme` rides along so the parts of the page the app does not paint —
 * scrollbars, native form control chrome, the canvas behind an overscroll —
 * follow the same palette.
 */
export function applyTheme(root: HTMLElement, theme: Theme): void {
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

/** The label the theme control shows for each preference. */
export function themeLabel(preference: ThemePreference): string {
  return preference === "system"
    ? "System"
    : preference === "light"
      ? "Light"
      : "Dark";
}
