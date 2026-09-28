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
  await expect(
    page.getByText("You were assigned: Send the revised pricing"),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  // Overdue by a day, so it leads My Tasks under its own heading.
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "My tasks" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Overdue" })).toBeVisible();

  // D-142: Blair is an editor and did not write this task, so the ordinary
  // author-or-owner rule would refuse them. Completing is the exception.
  await page
    .getByRole("checkbox", { name: /Send the revised pricing/ })
    .click();
  await expect(page.getByRole("heading", { name: "Overdue" })).toHaveCount(0);

  // ...and editing it is still not offered to them, on the deal itself.
  await page.goto("/");
  await openTimeline(page, NORTHWIND);
  await expect(
    taskPanel(page).getByRole("button", { name: "Delete" }),
  ).toHaveCount(0);
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
