/**
 * Row density as a preference, resolved to one root attribute (milestone 2.8,
 * **D-075**).
 *
 * `docs/DESIGN-SYSTEM.md` specifies two modes — Comfortable (40px rows,
 * `text-sm`) and Compact (30px rows, `text-xs`, tighter cells) — "as a root
 * token change rather than per-component variants", and says what they are
 * for: "the table view and power users". D-075 deferred them to the milestone
 * that builds that view, which is this one.
 *
 * The shape deliberately mirrors `lib/theme.ts`: a stored preference, one
 * `data-` attribute on `<html>`, and no values of its own. `app/globals.css`
 * holds the two sets of size tokens behind `:root` and
 * `[data-density="compact"]`, so a component asks for `--row-height` and
 * never for a number — the same rule that makes the dark palette a swap of
 * one block.
 *
 * Unlike the theme there is no system signal to follow: an operating system
 * has an opinion about light and dark and none about how tall a table row
 * should be. So there are two answers here, not three.
 */

export type Density = "comfortable" | "compact";

export const DENSITIES: readonly Density[] = [
  "comfortable",
  "compact",
] as const;

/** Where the choice survives a reload. Not a cookie, for the same reason the
 * theme's is not: nothing is rendered on the server (ADR 0005). */
export const DENSITY_STORAGE_KEY = "opptrail-density";

function isDensity(value: string | null): value is Density {
  return value !== null && DENSITIES.includes(value as Density);
}

/** The stored choice, or `comfortable` when there is none — which is also the
 * answer when storage is unavailable (a private window can throw on read). */
export function readDensity(storage: Storage | undefined): Density {
  try {
    const stored = storage?.getItem(DENSITY_STORAGE_KEY) ?? null;
    return isDensity(stored) ? stored : "comfortable";
  } catch {
    return "comfortable";
  }
}

/** Remembers it. A failed write costs the reader nothing but the memory of
 * it, so it is not worth raising. */
export function storeDensity(
  storage: Storage | undefined,
  density: Density,
): void {
  try {
    storage?.setItem(DENSITY_STORAGE_KEY, density);
  } catch {
    // Ignored deliberately: see above.
  }
}

/** Puts it where the stylesheet can see it. */
export function applyDensity(root: HTMLElement, density: Density): void {
  root.dataset.density = density;
}

/** The label the control shows. */
export function densityLabel(density: Density): string {
  return density === "compact" ? "Compact" : "Comfortable";
}
