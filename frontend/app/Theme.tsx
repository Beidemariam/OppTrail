"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  THEME_PREFERENCES,
  applyTheme,
  readThemePreference,
  resolveTheme,
  storeThemePreference,
  subscribeToDarkScheme,
  systemPrefersDark,
  themeLabel,
  type ThemePreference,
} from "../lib/theme";

/**
 * The theme in force, and the control that changes it (milestone 2.5).
 *
 * The provider owns two inputs — what the reader chose and what the operating
 * system asks for — and writes the one attribute `app/globals.css` keys both
 * palettes off (`lib/theme.ts`). It subscribes to the media query rather than
 * reading it once, so a reader whose system switches to dark at sunset does
 * not have to reload.
 */

interface ThemeControl {
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeControl>({
  preference: "system",
  setPreference: () => {},
});

export function useThemePreference(): ThemeControl {
  return useContext(ThemeContext);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    readThemePreference(
      typeof window === "undefined" ? undefined : window.localStorage,
    ),
  );
  // The media query is an external store rather than state of ours: it
  // changes without React's involvement, and the export pass has no window to
  // ask, which is what the third argument answers.
  const prefersDark = useSyncExternalStore(
    subscribeToDarkScheme,
    systemPrefersDark,
    () => false,
  );

  useEffect(() => {
    applyTheme(document.documentElement, resolveTheme(preference, prefersDark));
  }, [preference, prefersDark]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    storeThemePreference(window.localStorage, next);
  }, []);

  return (
    <ThemeContext.Provider value={{ preference, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * The theme control in the header.
 *
 * A select rather than a two-state toggle because there are three answers:
 * "follow my system" is the default and has to stay reachable after a reader
 * has picked one of the other two.
 */
export function ThemeToggle() {
  const { preference, setPreference } = useThemePreference();

  return (
    <select
      className="theme-select"
      aria-label="Theme"
      value={preference}
      onChange={(event) => setPreference(event.target.value as ThemePreference)}
    >
      {THEME_PREFERENCES.map((option) => (
        <option key={option} value={option}>
          {themeLabel(option)}
        </option>
      ))}
    </select>
  );
}
