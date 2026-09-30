import { expect, test } from "@playwright/test";

import {
  ALEX,
  BLAIR,
  NORTHWIND,
  card,
  createOpportunity,
  openTimeline,
  signIn,
  signOut,
  signUp,
} from "./helpers";

/**
 * Tasks end to end (milestone 4.1, `docs/FEATURES.md` §8).
 *
 * What the unit tests cannot reach: the real notification arriving in another
 * person's inbox, and the assignee closing a task they did not write — which is
 * **D-142**, the one rule in this feature that is not the app's usual
 * author-or-owner answer.
 */

function taskPanel(page: import("@playwright/test").Page) {
  return page.locator(".task-panel");
}

/** Dates relative to today: "overdue" is a question about the wall clock. */
function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

test("assign a task, the assignee is told, and they close it", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const panel = taskPanel(page);
  await panel.getByRole("button", { name: "Add task" }).click();
  await panel
    .getByLabel("Task", { exact: true })
    .fill("Send the revised pricing");
  await panel.getByLabel("For").selectOption({ label: "Blair Osei" });
  await panel.getByLabel("Due").fill(isoDaysFromToday(-1));
  await panel.getByRole("button", { name: "Add Task" }).click();

  await expect(panel.getByText("Send the revised pricing")).toBeVisible();
  await signOut(page);

  // --- As Blair: told about it, and able to finish it -------------------
  await signIn(page, BLAIR);
  await page.getByRole("button", { name: "Notifications" }).click();
  // `.first()`: the seed assigns Blair a task of its own (`make seed`'s tour
  // line), so the inbox holds more than one assignment and the newest is on top.
  await expect(
    page.getByText("You were assigned: Send the revised pricing").first(),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  // Overdue by a day, so it leads My Tasks under its own heading -- above the
  // seed's own task for Blair, which is due three days out.
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "My tasks" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Overdue" })).toBeVisible();

  // D-142: Blair is an editor and did not write this task, so the ordinary
  // author-or-owner rule would refuse them. Completing is the exception.
  // Addressed through the row rather than by filtering every checkbox on the
  // page: `.first()` over a name match is order-dependent, and the row is what
  // the assertion below is about.
  //
  // `.click()` rather than `.check()`: My Tasks lists open work, so completing a
  // task removes its row — and `check()` waits for the box to *stay* checked,
  // which a row that correctly disappears never does. The assertion is that the
  // task left the list, not that a control it no longer owns changed state.
  const overdueRow = page
    .locator(".task-row")
    .filter({ hasText: "Send the revised pricing" })
    .first();
  await overdueRow.getByRole("checkbox").click();
  await expect(overdueRow).toHaveCount(0);
  // Nothing is overdue any more; the seed's own task for Blair is still under
  // Coming up, which is what makes this about the one just closed rather than
  // about an empty list.
  await expect(page.getByRole("heading", { name: "Overdue" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Coming up" })).toBeVisible();

  // ...and changing what Alex wrote is still not offered to them, which is the
  // line D-142 draws: an assignee closes a task, they do not rewrite or remove
  // it.
  await page.goto("/");
  await openTimeline(page, NORTHWIND);
  const dealPanel = taskPanel(page);

  // Blair's own task on this deal -- the seed's tour line -- *does* offer
  // Delete: they wrote it, so D-005's author rule applies to them here.
  // Asserting the presence as well as the absence is what makes the pair mean
  // something; a panel-wide count of zero Delete buttons would pass for the
  // wrong reason.
  const blairTask = dealPanel
    .locator(".task-row")
    .filter({ hasText: "Send the permissions model" });
  await expect(blairTask).toHaveCount(1);
  await expect(blairTask.getByRole("button", { name: "Delete" })).toHaveCount(
    1,
  );

  // Alex's task is done, so it has left the open list for the Done disclosure --
  // the panel behaviour worth pinning here. Waited for rather than clicked
  // straight away: the panel reads the deal's tasks on mount, so the disclosure
  // appears a render after the navigation and a click sent before it exists
  // lands on nothing.
  const doneDisclosure = dealPanel.getByRole("button", {
    name: /Done \(\d+\)/,
  });
  await expect(doneDisclosure).toBeVisible();
  await doneDisclosure.click();
  await expect(doneDisclosure).toHaveAttribute("aria-expanded", "true");

  const alexTask = dealPanel
    .locator(".task-row")
    .filter({ hasText: "Send the revised pricing" });
  await expect(alexTask).toHaveCount(1);
  await expect(alexTask.getByRole("button", { name: "Delete" })).toHaveCount(0);
});

test("the dashboard says what is overdue, and g then t opens the list", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const email = `tasks-${suffix}@opptrail.test`;
  const opportunity = `Task deal ${suffix}`;
  await signUp(page, email, "Task Owner");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  const panel = taskPanel(page);
  await panel.getByRole("button", { name: "Add task" }).click();
  await panel.getByLabel("Task", { exact: true }).fill("Chase the contract");
  await panel.getByLabel("For").selectOption({ label: "Task Owner" });
  await panel.getByLabel("Due").fill(isoDaysFromToday(-2));
  await panel.getByRole("button", { name: "Add Task" }).click();
  await expect(panel.getByText("Chase the contract")).toBeVisible();

  await page.goto("/");
  await expect(card(page, opportunity)).toBeVisible();
  await expect(page.locator(".task-summary")).toContainText(
    "1 task is overdue",
  );

  // The chord reserved since milestone 2.4a (D-065), bound now that there is
  // somewhere to go.
  await page.keyboard.press("g");
  await page.keyboard.press("t");
  await expect(page.getByRole("heading", { name: "My tasks" })).toBeVisible();
  await expect(page.getByText("Chase the contract")).toBeVisible();
});
