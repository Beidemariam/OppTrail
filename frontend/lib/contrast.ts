/**
 * WCAG relative luminance and contrast ratio (milestone 2.5).
 *
 * `docs/DESIGN-SYSTEM.md` opens with a contrast audit that is "measured, not
 * assumed", and says of the dark palette: "keep the same contrast floors, and
 * re-run the audit on the dark palette rather than assuming inversion
 * preserves it". This is what re-runs it — `lib/contrast.test.ts` reads the
 * tokens straight out of `app/globals.css` and asserts every pair the app
 * actually paints, in both themes.
 *
 * axe checks the same thing in the browser (`frontend/e2e`), but only for
 * pairs a rendered page happens to contain. A token edited to an unreadable
 * value fails here first, in the unit suite, naming the token.
 */

/** Text against its background, per WCAG 2.2 AA. */
export const AA_TEXT_RATIO = 4.5;

/** Large text, and the non-text contrast floor for borders and focus rings. */
export const AA_LARGE_RATIO = 3;

function channel(value: number): number {
  const proportion = value / 255;
  return proportion <= 0.04045
    ? proportion / 12.92
    : ((proportion + 0.055) / 1.055) ** 2.4;
}

/** Accepts `#rgb` and `#rrggbb`. Anything else is a bug in the caller. */
export function parseHex(color: string): [number, number, number] {
  const hex = color.trim().replace("#", "");
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((digit) => digit + digit)
          .join("")
      : hex;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) {
    throw new Error(`not a hex colour: ${color}`);
  }
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

export function relativeLuminance(color: string): number {
  const [red, green, blue] = parseHex(color);
  return (
    0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
  );
}

/** The WCAG ratio between two opaque colours, from 1 to 21. */
export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}
