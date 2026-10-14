import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect } from "vitest";

import { AppRoutes } from "./AppRoot";
import { ALEX, FakeApi } from "./test-api";
import { createQueryClient } from "../lib/query";

/**
 * Mounts the real route table (`AppRoot`'s `AppRoutes`) over the fake API, so
 * a component test walks the same routes and the same query cache the browser
 * does. A fresh `QueryClient` per test keeps one test's cache out of the next.
 */
export function renderApp(
  options: ConstructorParameters<typeof FakeApi>[0] = {},
  path = "/",
) {
  const api = new FakeApi(options);
  api.install();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return api;
}

/** Signed in, with the dashboard's first load finished. */
export async function renderDashboard(
  options: ConstructorParameters<typeof FakeApi>[0] = {},
  path = "/",
) {
  const api = renderApp({ user: ALEX, ...options }, path);
  await screen.findByRole("heading", { name: "Opportunities" });
  return api;
}

/**
 * Signed in, on one deal's own page (R.1, decision 1A), with its record
 * header on screen. A deal is a route rather than a panel under the board,
 * so a test that arrives by URL waits for the record rather than for the
 * board's heading.
 */
export async function renderDeal(
  options: ConstructorParameters<typeof FakeApi>[0] = {},
  opportunityId = 10,
) {
  const api = renderApp(
    { user: ALEX, ...options },
    `/opportunities/${opportunityId}`,
  );
  await screen.findByRole("heading", { level: 2 });
  return api;
}

/** The same, for a deal URL that carries parameters of its own — a link into
 * a note, a comment, or a reading order a reload would use. */
export async function renderDealAt(
  options: ConstructorParameters<typeof FakeApi>[0] = {},
  path = "/opportunities/10",
) {
  const api = renderApp({ user: ALEX, ...options }, path);
  await screen.findByRole("heading", { level: 2 });
  return api;
}

/**
 * Follows a card's own name, which is the link to its timeline and is what
 * gives an opportunity its own URL.
 *
 * Since R.1 that is a page of its own rather than a panel under the board, so
 * this waits for the record header to arrive — the board's own heading is
 * gone by then, and a test that carried on immediately would be asserting
 * against whichever of the two screens happened to be rendered.
 */
export async function openTimeline(name: string) {
  const card = await findCard(name);
  await userEvent.click(within(card).getByRole("link", { name }));
  await screen.findByRole("heading", { name, level: 2 });
}

/**
 * Opens the board's filter and sort controls, which are collapsed behind a
 * trigger since R.1 (decision 3A) — the same disclosure the timeline's bar has
 * had since 3.7. A no-op when a filter is already applied, since the bar opens
 * itself then.
 */
export async function openBoardFilters() {
  // A no-op when they are already showing — `/` opens them too, and a test
  // that pressed it should not have to know whether it did.
  if (screen.queryByLabelText("Filter opportunities by keyword")) {
    return;
  }
  await userEvent.click(
    await screen.findByRole("button", { name: "+ Filter and sort" }),
  );
  await screen.findByLabelText("Filter opportunities by keyword");
}

/** Back to the board from a deal's own page (R.1, decision 1A). */
export async function backToBoard() {
  await userEvent.click(
    screen.getByRole("link", { name: "\u2190 Opportunities" }),
  );
  await screen.findByRole("heading", { name: "Opportunities" });
}

/** The deal screen's AI drawer, which is closed until it is asked for
 * (R.1, decision 2A). */
export async function openAi() {
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  return screen.findByRole("complementary");
}

/** Opens the create/edit dialog milestone 2.7 moved the form into, and
 * returns it. */
export async function openOpportunityForm(name = "New opportunity") {
  await userEvent.click(screen.getByRole("button", { name }));
  return screen.findByRole("dialog");
}

/** The card for one opportunity, once the list behind the board has loaded. */
export async function findCard(name: string) {
  const cards = await screen.findAllByRole("article");
  return cards.find((candidate) => candidate.textContent?.includes(name))!;
}

/**
 * Answers the confirmation dialog milestone 2.5 put in front of the deletes
 * that cascade (`app/ConfirmDialog.tsx`). `typed` is the text the dialog asks
 * the reader to type back; omit it where the question has no typed gate.
 */
export async function acceptConfirmation(typed?: string) {
  const dialog = await screen.findByRole("alertdialog");
  if (typed !== undefined) {
    await userEvent.type(within(dialog).getByRole("textbox"), typed);
  }
  await userEvent.click(
    within(dialog).getByRole("button", { name: /^(Delete|Remove)/ }),
  );
  expect(screen.queryByRole("alertdialog")).toBeNull();
}

/** Declines it, which must leave the API untouched. */
export async function cancelConfirmation() {
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).toBeNull();
}
