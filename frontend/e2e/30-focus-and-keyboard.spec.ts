import { expect, test, type Page } from "@playwright/test";

import {
  ALEX,
  NORTHWIND,
  card,
  openTimeline,
  settleTransitions,
  signIn,
} from "./helpers";

/**
 * The half of WCAG 2.2 AA that axe cannot answer (milestone R.2).
 *
 * `AGENTS.md`'s Quality Bar is 2.2 AA and **D-002** ruled that over the
 * brief's 2.1; `e2e/07-accessibility.spec.ts` now audits the 2.2 tags, which
 * machine-checks one of 2.2's new criteria (2.5.8 Target Size) and none of the
 * other three that apply here. Those are measured by hand below, in the same
 * spirit as `e2e/23-responsive.spec.ts`: a rendered box, read back from the
 * browser, rather than a rule read off a stylesheet.
 */

/**
 * Where the keyboard is, and whether any of it can be seen.
 *
 * 2.4.11 fails only when the focused control is *entirely* hidden (partially
 * is 2.4.12, AAA), so this asks whether **any** corner or the centre of the
 * focused element is the topmost thing at its own coordinates. That catches
 * obscuring by anything, rather than only by the two sticky bands this app
 * happens to have.
 */
async function focusedControl(page: Page) {
  await settleTransitions(page);
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return null;
    const box = element.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return null;

    const points: [number, number][] = [
      [box.left + box.width / 2, box.top + box.height / 2],
      [box.left + 2, box.top + 2],
      [box.right - 2, box.top + 2],
      [box.left + 2, box.bottom - 2],
      [box.right - 2, box.bottom - 2],
    ];
    const showing = points.some(([x, y]) => {
      if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) {
        return false;
      }
      const hit = document.elementFromPoint(x, y);
      return hit !== null && (hit === element || element.contains(hit));
    });

    return {
      name: (element.getAttribute("aria-label") ?? element.textContent ?? "")
        .trim()
        .slice(0, 48),
      tag: element.tagName.toLowerCase(),
      top: Math.round(box.top),
      bottom: Math.round(box.bottom),
      showing,
    };
  });
}

/**
 * Walks the tab order and collects everything that took focus without being
 * visible. Collects rather than stopping at the first, so one run reports the
 * whole problem (23-responsive's rule).
 *
 * **Both directions, and the backward one is the point.** Tabbing forward
 * brings a control up from below, and the browser aligns it to the bottom
 * edge — where there is no sticky chrome. `Shift+Tab` brings it down from
 * above and aligns it to the top edge, which is exactly where 190px of
 * application bar and record band are. A forward-only walk would pass against
 * the unfixed stylesheet.
 */
async function tabThrough(page: Page, steps: number) {
  const hidden: string[] = [];
  const record = async () => {
    const control = await focusedControl(page);
    if (control && !control.showing) {
      hidden.push(
        `${control.tag} "${control.name}" at y ${control.top}-${control.bottom}`,
      );
    }
  };

  for (let step = 0; step < steps; step += 1) {
    await page.keyboard.press("Tab");
    await record();
  }
  for (let step = 0; step < steps; step += 1) {
    await page.keyboard.press("Shift+Tab");
    await record();
  }
  return hidden;
}

test.describe("focus not obscured (2.4.11, AA in WCAG 2.2)", () => {
  test("nothing the keyboard reaches on a deal hides under the sticky bands", async ({
    page,
  }) => {
    // The deal page is the one screen with two sticky layers — the
    // application bar at 0 and the record band directly under it (R.1) — so
    // 190px of chrome sits over whatever the browser scrolls to the top edge.
    await signIn(page, ALEX);
    await openTimeline(page, NORTHWIND);

    const hidden = await tabThrough(page, 60);

    expect(hidden, "focused controls entirely hidden on the deal page").toEqual(
      [],
    );
  });

  test("the scroll padding is never less than the chrome it clears", async ({
    page,
  }) => {
    // R.1c. `--sticky-deal` was a literal matching the record band's height
    // when R.2 measured it, and R.1c's one button size made that band
    // shorter — so the number became an over-estimate. Over-padding is
    // harmless; **under**-padding is the 2.4.11 failure R.2 fixed, and the
    // band is taller at narrow widths where its rows wrap. So the invariant
    // worth holding is the inequality, measured rather than commented, at
    // every width the responsive suite uses.
    await signIn(page, ALEX);
    await openTimeline(page, NORTHWIND);

    const tooSmall: string[] = [];
    // The responsive suite's eight, plus 1200, 1100 and 960: the band's
    // height steps at the 1280px media query and then grows as it wraps, so
    // the worst case is inside that range rather than at either end of it.
    for (const width of [
      1440, 1280, 1200, 1100, 1024, 960, 900, 768, 640, 520, 420,
    ]) {
      await page.setViewportSize({ width, height: 900 });
      await settleTransitions(page);
      // **Scrolled, so the bands are actually stuck.** Measuring at rest
      // reads the record band's position in the document flow, which on a
      // narrow screen is hundreds of pixels down the page and is not sticky
      // chrome at all — the first version of this test did exactly that and
      // reported 543px of "chrome" at 900px wide.
      await page.evaluate(() =>
        window.scrollTo({ top: 800, behavior: "instant" }),
      );
      await settleTransitions(page);
      const measured = await page.evaluate(() => {
        const band = document.querySelector(".record-header");
        const root = getComputedStyle(document.documentElement);
        const token = parseFloat(root.getPropertyValue("--sticky-deal"));
        const bottom = band ? band.getBoundingClientRect().bottom : 0;
        return { token, bottom };
      });
      if (measured.token < measured.bottom) {
        tooSmall.push(
          `${width}px: --sticky-deal ${measured.token} < chrome ${measured.bottom}`,
        );
      }
    }

    expect(
      tooSmall,
      "scroll padding smaller than the sticky chrome it has to clear",
    ).toEqual([]);
  });

  test("nor on the board, which has one", async ({ page }) => {
    await signIn(page, ALEX);

    const hidden = await tabThrough(page, 40);

    expect(hidden, "focused controls entirely hidden on the board").toEqual([]);
  });
});

test.describe("bypass blocks (2.4.1, A)", () => {
  test("the first tab skips the rail and lands in the screen", async ({
    page,
  }) => {
    await signIn(page, ALEX);

    await page.keyboard.press("Tab");
    const skip = await focusedControl(page);
    expect(skip?.name).toBe("Skip to content");
    // Visible once focused, which is what makes it a bypass rather than a
    // link nobody can tell they have reached.
    expect(skip?.showing).toBe(true);

    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();

    // And the next tab is inside the screen, not back in the rail.
    await page.keyboard.press("Tab");
    const insideScreen = await page.evaluate(() => {
      const content = document.getElementById("main-content");
      const focused = document.activeElement;
      return content !== null && focused !== null && content.contains(focused);
    });
    expect(insideScreen).toBe(true);
  });
});

test.describe("dragging movements (2.5.7, AA in WCAG 2.2)", () => {
  test("every card that can be dragged can also be moved without dragging", async ({
    page,
  }) => {
    // The board's drag is the browser's own HTML5 drag-and-drop (D-080), so
    // the criterion needs a single-pointer path to the same outcome.
    // `MoveToStage` is it, and it is offered on exactly the cards that are
    // draggable — an owner's, since changing a deal's fields is owner-only.
    await signIn(page, ALEX);

    const draggable = page.locator(
      "article.opportunity-card[draggable='true']",
    );
    const count = await draggable.count();
    expect(count).toBeGreaterThan(0);

    for (let index = 0; index < count; index += 1) {
      const name = await draggable
        .nth(index)
        .getByRole("heading")
        .first()
        .textContent();
      await expect(
        draggable.nth(index).locator("select"),
        `a draggable card with no move control: ${name}`,
      ).toHaveCount(1);
    }
  });

  test("the move control changes the stage, with no pointer gesture at all", async ({
    page,
  }) => {
    await signIn(page, ALEX);

    await card(page, NORTHWIND).locator("select").selectOption("Negotiation");

    await expect(
      page
        .locator(".stage-column")
        .filter({ hasText: "Negotiation" })
        .getByRole("link", { name: NORTHWIND }),
    ).toBeVisible();
  });
});
