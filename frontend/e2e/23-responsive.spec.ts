import { expect, test, type Page } from "@playwright/test";

import { ALEX, NORTHWIND, card, signIn } from "./helpers";

/**
 * The geometry nobody was testing (milestone 3.8, **D-138**).
 *
 * Three gate reviews reported the same defect — *"they change shape and become
 * vertical with the letters inside of them messed up"* — and each report was
 * read as a different local layout bug, because nothing in this project looked
 * at a rendered box. 530 unit tests and 68 end-to-end tests, and not one
 * measured a control. So a button rule that broke every label to one character
 * per line under pressure (`globals.css`, `min-width: 0` with
 * `overflow-wrap: anywhere`) survived from the MVP through Phase 3.
 *
 * This spec is the ratchet that replaces the reviewer. It asserts two
 * properties over every screen at every width, and nothing about how any
 * particular component is laid out:
 *
 * - **No control is squashed.** A button, link-button or select that renders
 *   taller than it is wide has lost its label to wrapping. The threshold is
 *   generous on purpose (1.3x, and only under 120px wide) so an honestly tall
 *   control — a textarea, a multi-line menu item — cannot fail it.
 * - **No page scrolls sideways.** `body.scrollWidth` may not exceed the
 *   viewport. This is the other half: `white-space: nowrap` trades wrapping for
 *   overflow, so the trade is only safe if overflow is what fails the build.
 *
 * Both are read from the browser rather than from the stylesheet, which is the
 * point — `lib/contrast.test.ts` audits tokens, and this audits what the tokens
 * produce.
 */

/** Narrow enough to be a phone, wide enough to be a desktop, and the awkward
 * middle where the two-column layout is still on and out of room — which is
 * where `Edit` rendered 38x89 and nobody was looking. */
const WIDTHS = [1440, 1280, 1100, 960, 900, 760, 600, 420];

const SCREENS: [string, string][] = [
  ["the board", "/"],
  ["the list", "/?opportunities.view=list"],
  ["the table", "/?opportunities.view=table"],
  ["the calendar", "/?opportunities.view=calendar"],
  ["a timeline", null as unknown as string],
  ["search", "/search?q=pricing"],
  // The two cross-deal screens. `/automations` arrives with milestone 6.3 and
  // `/reports` is 6.2's, added in the same breath: a screen that is not in
  // this list is a screen where D-138's defect can come back unnoticed, which
  // is the whole reason this spec exists.
  ["reports", "/reports"],
  ["automations", "/automations"],
];

interface Squashed {
  label: string;
  width: number;
  height: number;
}

async function audit(page: Page) {
  return page.evaluate(() => {
    const squashed: Squashed[] = [];
    const controls = document.querySelectorAll<HTMLElement>(
      "button, select, a.primary-button, a.secondary-button, a.danger-button",
    );
    for (const el of controls) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 && box.height === 0) {
        continue;
      }
      // Taller than wide, and narrow — a label that has wrapped per character.
      if (box.height > box.width * 1.3 && box.width < 120) {
        squashed.push({
          label: (el.textContent || el.getAttribute("aria-label") || el.tagName)
            .trim()
            .slice(0, 40),
          width: Math.round(box.width),
          height: Math.round(box.height),
        });
      }
    }
    // Which elements actually stick out, not just that something does. A
    // bare "the page scrolls sideways by 2px" sends the next reader hunting
    // through every screen by hand -- and this failure only reproduces under
    // a font stack the author may not have, so the report has to carry its
    // own evidence. Widest first, deepest in the tree preferred: a container
    // is wide *because* of its content, so the leaf is the culprit.
    const overflow = document.body.scrollWidth - window.innerWidth;
    const culprits: string[] = [];
    if (overflow > 0) {
      const limit = window.innerWidth;
      const offenders: { label: string; right: number; depth: number }[] = [];
      for (const el of document.querySelectorAll<HTMLElement>("body *")) {
        const box = el.getBoundingClientRect();
        if (box.width === 0 || box.right <= limit + 0.5) {
          continue;
        }
        let depth = 0;
        for (let node = el.parentElement; node; node = node.parentElement) {
          depth += 1;
        }
        offenders.push({
          label:
            el.tagName.toLowerCase() +
            (el.className && typeof el.className === "string"
              ? `.${el.className.trim().split(/\s+/).slice(0, 2).join(".")}`
              : ""),
          right: Math.round(box.right),
          depth,
        });
      }
      offenders.sort((a, b) => b.right - a.right || b.depth - a.depth);
      for (const o of offenders.slice(0, 4)) {
        culprits.push(`${o.label} reaches ${o.right} (viewport ${limit})`);
      }
    }
    return { squashed, overflow, culprits };
  });
}

test("no control is squashed and no page scrolls sideways, at any width", async ({
  page,
}) => {
  await signIn(page, ALEX);
  // The timeline's URL is the seeded opportunity's, so it is read once here
  // rather than hardcoded.
  await card(page, NORTHWIND).getByRole("link", { name: NORTHWIND }).click();
  await expect(page).toHaveURL(/\/opportunities\/\d+/);
  const timelinePath = new URL(page.url()).pathname;
  const problems: string[] = [];

  for (const [name, path] of SCREENS) {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path ?? timelinePath);
      // The board and the list are virtualized, so what is in the DOM settles
      // one frame after navigation.
      await expect(page.locator(".app-shell")).toBeVisible();
      await page.waitForTimeout(250);

      const result = await audit(page);
      for (const control of result.squashed) {
        problems.push(
          `${name} at ${width}px: "${control.label}" rendered ` +
            `${control.width}x${control.height} — its label has wrapped`,
        );
      }
      if (result.overflow > 0) {
        problems.push(
          `${name} at ${width}px: the page scrolls sideways by ${result.overflow}px` +
            (result.culprits.length > 0
              ? ` — widest: ${result.culprits.join("; ")}`
              : ""),
        );
      }
    }
  }

  // Collected rather than asserted per width, so a regression reports every
  // screen it broke instead of the first one the loop reached — which is the
  // difference between "the board is 47px wide of itself" and the list of
  // controls a reviewer would have had to find by hand.
  expect(problems).toEqual([]);
});
