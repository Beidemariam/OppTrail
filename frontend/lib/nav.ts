/**
 * The five destinations, and whether the rail that holds them is collapsed
 * (milestone R.1, decision 4A).
 *
 * Declared here rather than in `app/AppShell.tsx` for the reason
 * `lib/keyboard.ts` declares the shortcut map and `lib/nav`'s neighbours
 * declare their preferences: it is data, it is read by more than one thing
 * (the rail draws it, the palette could), and it is testable without a DOM.
 *
 * Before this the app had no navigation at all beyond three links in the top
 * bar, and four of the five screens hand-rolled their own header without
 * them -- so from Reports there was no way to reach Automations.
 */
export type NavItem = {
  /** What the rail calls it. Also its accessible name. */
  readonly label: string;
  readonly path: string;
};

export const navItems: readonly NavItem[] = [
  { label: "Opportunities", path: "/" },
  { label: "Tasks", path: "/tasks" },
  { label: "Reports", path: "/reports" },
  { label: "Automations", path: "/automations" },
  { label: "Search", path: "/search" },
];

/**
 * Which destination a path belongs to.
 *
 * A deal is its own page from R.1 (decision 1A), so `/opportunities/7` has to
 * light Opportunities rather than nothing: an exact match on "/" would leave
 * the rail saying the reader is nowhere, on the one screen they spend the
 * most time in. Every other item is a prefix match, which is also what keeps
 * a future `/reports/pipeline` under Reports.
 */
export function isNavActive(itemPath: string, pathname: string): boolean {
  if (itemPath === "/") {
    return pathname === "/" || pathname.startsWith("/opportunities");
  }
  return pathname === itemPath || pathname.startsWith(`${itemPath}/`);
}

/**
 * How much sticky chrome a screen keeps above its content (R.2, rewritten).
 *
 * The scrollport has to be shrunk by exactly that much, or `Shift+Tab`
 * scrolls a control to the top edge and under the chrome — WCAG 2.2's 2.4.11.
 * Five screens have only the application bar; a deal has the bar and the
 * record band stuck under it, and the band is the part that varies.
 *
 * **It is measured now, not written down.** This was a literal three times
 * and wrong three times: R.2 took one measurement at one viewport (190px),
 * R.1c found it wrong at every width and replaced it with three measured
 * literals (D-219), and CI's first Linux run found *those* short — the band
 * wraps to **292.39px** at 1024px under a different font stack where it
 * measured 256px on macOS, so `--sticky-deal: 272px` under-padded by 20px
 * and the 2.4.11 failure was live again for anyone whose fonts render
 * taller. A constant can only ever be right for the configuration it was
 * measured in; the band knows its own height, so it publishes it.
 *
 * `null` means *this is not sticky chrome*: below 900px the band is
 * `position: static` and the application bar is the only thing above the
 * content, which is what `--sticky-bar` is for. That replaces a media query
 * that said the same thing in CSS.
 */
export function stuckBottom(
  position: string,
  top: string,
  height: number,
): number | null {
  if (position !== "sticky") {
    return null;
  }
  // A sticky element's resolved `top` is where it comes to rest, so its
  // bottom edge while stuck is that plus its height — computable without
  // scrolling the page to find out. `top: auto` parses as NaN.
  const offset = Number.parseFloat(top);
  return (Number.isFinite(offset) ? offset : 0) + height;
}

/** Published on `<html>` for `scroll-padding-top` to read. */
export const STICKY_CHROME_PROPERTY = "--sticky-chrome";

export const NAV_STORAGE_KEY = "opptrail-nav";

/**
 * Collapsed is a preference, not state: it survives a reload, like the theme
 * and the density. Unlike those two it writes no root attribute, because
 * nothing outside the rail changes when it collapses -- the main column is
 * simply given the width.
 */
export function readNavCollapsed(): boolean {
  try {
    return window.localStorage.getItem(NAV_STORAGE_KEY) === "collapsed";
  } catch {
    // Safari in private mode throws on access, not on write.
    return false;
  }
}

export function writeNavCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(
      NAV_STORAGE_KEY,
      collapsed ? "collapsed" : "expanded",
    );
  } catch {
    // A preference that cannot be stored still applies for this page load.
  }
}
