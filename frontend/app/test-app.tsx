import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

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

/** Follows a card's timeline link, which is what gives it its own URL. */
export async function openTimeline(name: string) {
  const card = await findCard(name);
  await userEvent.click(within(card).getByRole("link", { name: "Timeline" }));
}

/** The card for one opportunity, once the list behind the board has loaded. */
export async function findCard(name: string) {
  const cards = await screen.findAllByRole("article");
  return cards.find((candidate) => candidate.textContent?.includes(name))!;
}
