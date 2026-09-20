import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ConfirmProvider,
  useConfirm,
  type ConfirmRequest,
} from "./ConfirmDialog";

/**
 * The real dialog that replaced `window.confirm` (milestone 2.5).
 *
 * The three call sites are covered where they live — `DashboardPage.test.tsx`
 * for the two deletes that cascade, `OpportunityPanel.test.tsx` for removing
 * access. What is tested here is the dialog itself: the typed gate, every way
 * out of it, and the rule it shares with `app/Modal.tsx` — Esc is answered
 * here and not passed on to the board's own Esc binding behind it.
 */

const DELETE_NORTHWIND: ConfirmRequest = {
  title: "Delete Northwind rollout?",
  description: "This deletes the opportunity and its entire timeline.",
  confirmLabel: "Delete opportunity",
  typeToConfirm: "Northwind rollout",
};

/** The answer the last question resolved to, as the caller saw it. */
let answer: boolean | null = null;

function Harness({ request }: { request: ConfirmRequest }) {
  const confirm = useConfirm();
  return (
    <button
      type="button"
      onClick={() => {
        void confirm(request).then((confirmed) => {
          answer = confirmed;
        });
      }}
    >
      Delete
    </button>
  );
}

function renderConfirm(request: ConfirmRequest = DELETE_NORTHWIND) {
  answer = null;
  render(
    <ConfirmProvider>
      <Harness request={request} />
    </ConfirmProvider>,
  );
  return screen.getByRole("button", { name: "Delete" });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the confirmation dialog", () => {
  it("will not confirm until the name is typed back", async () => {
    await userEvent.click(renderConfirm());

    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", {
      name: "Delete opportunity",
    });
    const field = within(dialog).getByRole("textbox");
    expect(confirm).toBeDisabled();

    // A near miss is still a miss: this is the friction `docs/UX.md` keeps on
    // the one delete that cascades across a whole record.
    await userEvent.type(field, "Northwind");
    expect(confirm).toBeDisabled();

    await userEvent.type(field, " rollout");
    expect(confirm).toBeEnabled();

    await userEvent.click(confirm);
    await waitFor(() => expect(answer).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("puts the cursor in the field the reader has to fill", async () => {
    await userEvent.click(renderConfirm());

    const dialog = await screen.findByRole("alertdialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("textbox")).toHaveFocus(),
    );
  });

  it("answers no when it is cancelled", async () => {
    await userEvent.click(renderConfirm());
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Cancel",
      }),
    );

    await waitFor(() => expect(answer).toBe(false));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("answers no on Escape, and does not let the board behind it see the key", async () => {
    const onDocumentEscape = vi.fn();
    document.addEventListener("keydown", onDocumentEscape);

    try {
      await userEvent.click(renderConfirm());
      await screen.findByRole("alertdialog");

      await userEvent.keyboard("{Escape}");

      await waitFor(() => expect(answer).toBe(false));
      expect(onDocumentEscape).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener("keydown", onDocumentEscape);
    }
  });

  it("asks without a typed gate when there is nothing to type", async () => {
    await userEvent.click(
      renderConfirm({
        title: "Remove Blair's access?",
        description: "Blair loses access immediately.",
        confirmLabel: "Remove access",
      }),
    );

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).queryByRole("textbox")).toBeNull();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Remove access" }),
    );
    await waitFor(() => expect(answer).toBe(true));
  });

  it("starts each question empty rather than carrying the last one over", async () => {
    const trigger = renderConfirm();
    await userEvent.click(trigger);
    await userEvent.type(
      within(await screen.findByRole("alertdialog")).getByRole("textbox"),
      "Northwind rollout",
    );
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Cancel",
      }),
    );

    await userEvent.click(trigger);

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByRole("textbox")).toHaveValue("");
    expect(
      within(dialog).getByRole("button", { name: "Delete opportunity" }),
    ).toBeDisabled();
  });
});
