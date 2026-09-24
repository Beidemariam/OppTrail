import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  BLAIR,
  aComment,
  aNote,
  aReply,
  anEntry,
  anOpportunity,
} from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";
import { writeInEditor } from "./test-editor";

/**
 * Threaded comments and resolve/unresolve, from the reader's side
 * (milestone 3.3). The rules being checked are the backend's — one level of
 * replies (D-127), author-or-owner resolve (D-128) — and what this file
 * proves is that the screen offers exactly the actions the API would accept.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const question = aComment({ body: "What is their budget?" });

function threadedTimeline(overrides: Parameters<typeof aComment>[0] = {}) {
  const thread = { ...question, ...overrides };
  return [anEntry({ notes: [aNote({ comments: [thread] })] })];
}

async function openThreadedTimeline(
  overrides: Parameters<typeof aComment>[0] = {},
) {
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: threadedTimeline(overrides),
  });
  await openTimeline("Northwind rollout");
  await screen.findByText("What is their budget?");
  return api;
}

function thread() {
  return screen
    .getByText("What is their budget?")
    .closest(".comment-thread") as HTMLElement;
}

it("reads a reply under the comment it answers", async () => {
  await openThreadedTimeline({
    replies: [aReply(question, { body: "Around 25k" })],
  });

  const replies = thread().querySelector(".comment-replies") as HTMLElement;
  expect(within(replies).getByText("Around 25k")).toBeInTheDocument();
  expect(within(replies).getByText(BLAIR.name)).toBeInTheDocument();
});

it("posts a reply as a reply to that thread, not as a new comment", async () => {
  const api = await openThreadedTimeline();

  await userEvent.click(screen.getByRole("button", { name: "Reply" }));
  writeInEditor(screen.getByLabelText("Reply to Alex"), "Around 25k");
  await userEvent.click(screen.getByRole("button", { name: "Reply" }));

  await waitFor(() =>
    expect(api.callsTo("POST", "/api/v2/notes/200/comments")).toHaveLength(1),
  );
  expect(api.callsTo("POST", "/api/v2/notes/200/comments")[0].body).toEqual({
    body: "Around 25k",
    parent_id: question.id,
  });
  expect(await screen.findByText("Around 25k")).toBeInTheDocument();
});

it("offers Reply on the thread and never on a reply", async () => {
  await openThreadedTimeline({
    replies: [aReply(question, { body: "Around 25k" })],
  });

  // One Reply control for the thread, not one per message: threading is one
  // level deep and a second control would ask for a comment the API refuses.
  expect(screen.getAllByRole("button", { name: "Reply" })).toHaveLength(1);
  const replies = thread().querySelector(".comment-replies") as HTMLElement;
  expect(
    within(replies).queryByRole("button", { name: "Reply" }),
  ).not.toBeInTheDocument();
});

it("resolves a thread and collapses it to its outcome", async () => {
  const api = await openThreadedTimeline({
    replies: [aReply(question, { body: "Around 25k" })],
  });

  await userEvent.click(
    within(thread()).getByRole("button", { name: "Resolve" }),
  );

  await waitFor(() =>
    expect(api.callsTo("POST", "/api/v2/comments/300/resolve")).toHaveLength(1),
  );
  expect(await screen.findByText("Resolved by Alex")).toBeInTheDocument();
  // Collapsed: the discussion is off the screen until it is asked for.
  expect(screen.queryByText("What is their budget?")).not.toBeInTheDocument();
  expect(screen.queryByText("Around 25k")).not.toBeInTheDocument();
});

it("shows a resolved thread again without reopening it", async () => {
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: threadedTimeline({
      resolved_at: "2026-09-02T15:00:00Z",
      resolved_by: 1,
      resolved_by_name: "Alex",
      replies: [aReply(question, { body: "Around 25k" })],
    }),
  });
  await openTimeline("Northwind rollout");

  const show = await screen.findByRole("button", { name: "Show" });
  expect(show).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(show);

  expect(screen.getByText("What is their budget?")).toBeInTheDocument();
  expect(screen.getByText("Around 25k")).toBeInTheDocument();
  // Reading is not reopening: nothing was written to say the thread is live
  // again, and no Reply is offered while it is resolved.
  expect(api.callsTo("POST", "/api/v2/comments/300/unresolve")).toHaveLength(0);
  expect(
    screen.queryByRole("button", { name: "Reply" }),
  ).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Hide" }));
  expect(screen.queryByText("What is their budget?")).not.toBeInTheDocument();
  expect(screen.getByText("Resolved by Alex")).toBeInTheDocument();
});

it("reopens a resolved thread", async () => {
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: threadedTimeline({
      resolved_at: "2026-09-02T15:00:00Z",
      resolved_by: 1,
      resolved_by_name: "Alex",
    }),
  });
  await openTimeline("Northwind rollout");

  await userEvent.click(await screen.findByRole("button", { name: "Show" }));
  await userEvent.click(screen.getByRole("button", { name: "Reopen" }));

  await waitFor(() =>
    expect(api.callsTo("POST", "/api/v2/comments/300/unresolve")).toHaveLength(
      1,
    ),
  );
  expect(
    await screen.findByRole("button", { name: "Reply" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Resolved by Alex")).not.toBeInTheDocument();
});

it("offers neither Reply nor Resolve to a viewer", async () => {
  await renderDashboard({
    opportunities: [anOpportunity({ current_user_role: "viewer" })],
    entries: threadedTimeline(),
  });
  await openTimeline("Northwind rollout");
  await screen.findByText("What is their budget?");

  expect(
    screen.queryByRole("button", { name: "Reply" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Resolve" }),
  ).not.toBeInTheDocument();
});

it("offers Resolve on a colleague's thread only to the owner", async () => {
  // An editor reading someone else's thread: they may answer it, and the
  // author-or-owner rule is what stops them closing it (D-128).
  await renderDashboard({
    opportunities: [anOpportunity({ current_user_role: "editor" })],
    entries: threadedTimeline({
      created_by: BLAIR.id,
      author_name: BLAIR.name,
    }),
  });
  await openTimeline("Northwind rollout");
  await screen.findByText("What is their budget?");

  expect(screen.getByRole("button", { name: "Reply" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Resolve" }),
  ).not.toBeInTheDocument();
});

it("deletes a reply without taking the thread with it", async () => {
  const api = await openThreadedTimeline({
    replies: [aReply(question, { body: "Around 25k" })],
  });

  const reply = screen.getByText("Around 25k").closest(".comment-row")!;
  await userEvent.click(
    within(reply as HTMLElement).getByRole("button", { name: "Delete" }),
  );

  await waitFor(() =>
    expect(screen.queryByText("Around 25k")).not.toBeInTheDocument(),
  );
  expect(screen.getByText("What is their budget?")).toBeInTheDocument();
  expect(api.callsTo("DELETE", "/api/v2/comments/301")).toHaveLength(1);
});
