"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  DENSITIES,
  applyDensity,
  densityLabel,
  readDensity,
  storeDensity,
  type Density,
} from "../lib/density";

/**
 * The density in force, and the control that changes it (milestone 2.8,
 * **D-075**).
 *
 * Structurally the theme's smaller sibling (`app/Theme.tsx`): the provider
 * owns the stored preference and writes the one attribute `app/globals.css`
 * keys both token sets off. There is no media query to subscribe to here —
 * nothing outside the app has an opinion about row height — so this is plain
 * state rather than an external store.
 */

interface DensityControl {
  density: Density;
  setDensity: (density: Density) => void;
}

const DensityContext = createContext<DensityControl>({
  density: "comfortable",
  setDensity: () => {},
});

export function useDensity(): DensityControl {
  return useContext(DensityContext);
}

export function DensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensityState] = useState<Density>(() =>
    readDensity(
      typeof window === "undefined" ? undefined : window.localStorage,
    ),
  );

  useEffect(() => {
    applyDensity(document.documentElement, density);
  }, [density]);

  const setDensity = useCallback((next: Density) => {
    setDensityState(next);
    storeDensity(window.localStorage, next);
  }, []);

  return (
    <DensityContext.Provider value={{ density, setDensity }}>
      {children}
    </DensityContext.Provider>
  );
}

/**
 * The density control, beside the view switcher rather than in the top bar.
 *
 * It belongs to the screen showing the rows, not to the application chrome:
 * `docs/DESIGN-SYSTEM.md` introduces the modes as being "for the table view
 * and power users", and a control for how tall a row is reads as noise on a
 * screen with no rows on it. The theme control stays in the top bar for the
 * opposite reason — it applies to everything.
 */
export function DensityToggle() {
  const { density, setDensity } = useDensity();

  return (
    <label className="density-select">
      <span className="control-caption">Density</span>
      <select
        aria-label="Row density"
        value={density}
        onChange={(event) => setDensity(event.target.value as Density)}
      >
        {DENSITIES.map((option) => (
          <option key={option} value={option}>
            {densityLabel(option)}
          </option>
        ))}
      </select>
    </label>
  );
}
