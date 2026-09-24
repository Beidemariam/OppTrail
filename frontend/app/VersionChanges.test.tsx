import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../lib/query";
import type { OpportunityVersion } from "../lib/domain";
import { opportunityVersionFields } from "../lib/domain";
import { ToastProvider } from "./Toasts";
import { VersionDiff, VersionFields } from "./VersionChanges";

/**
 * The states an opened edit row can be in, driven directly rather than
 * through the activity log: the log only ever hands this component a version
 * that exists and a history that loaded, which is exactly why the other
 * answers need a test of their own.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function aVersion(overrides: Partial<OpportunityVersion> = {}) {
  return {
    id: 1,
    opportunity_id: 10,
    version_number: 1,
    name: "Northwind rollout",
    account_name: "Northwind",
    value: "185000",
    currency: "USD",
    stage: "Negotiation",
    expected_close_date: "2026-12-01",
    edited_by: 1,
    editor_name: "Alex",
    created_at: "2026-09-01T09:00:00Z",
    ...overrides,
  } as OpportunityVersion;
}

function stub(
  result: Partial<UseQueryResult<OpportunityVersion[], Error>>,
): (
  id: number,
  enabled: boolean,
) => UseQueryResult<OpportunityVersion[], Error> {
  return () => result as UseQueryResult<OpportunityVersion[], Error>;
}

function renderDiff(
  useVersions: (
    id: number,
    enabled: boolean,
  ) => UseQueryResult<OpportunityVersion[], Error>,
  versionNumber = 2,
) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ToastProvider>
        <VersionDiff
          target="opportunity"
          targetId={10}
          versionNumber={versionNumber}
          fields={opportunityVersionFields}
          useVersions={useVersions}
        />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("an opened edit row", () => {
  it("says the history is loading before it arrives", () => {
    renderDiff(stub({ isPending: true, isError: false }));

    expect(screen.getByText("Loading what changed...")).toBeInTheDocument();
  });

  it("reports a history that could not be read", () => {
    renderDiff(
      stub({ isError: true, error: new Error("Opportunity not found") }),
    );

    expect(screen.getByText("Opportunity not found")).toBeInTheDocument();
  });

  it("draws nothing when the version behind the row is not in the history", () => {
    // Unreachable through the feed, which builds an edit row by joining a
    // version to the one before it; the branch exists because `find` cannot
    // know that.
    renderDiff(
      stub({ isPending: false, isError: false, data: [aVersion()] }),
      5,
    );

    expect(screen.queryByRole("button")).toBeNull();
    expect(document.querySelector(".history-fields")).toBeNull();
  });

  it("says so when an edit moved nothing a reader is shown", () => {
    // `currency` is versioned but read as part of the value (D-098), so a
    // version can differ from its predecessor in a column that renders the
    // same. An empty list is said in words rather than drawn as a gap.
    render(<VersionFields changes={[]} />);

    expect(
      screen.getByText("Saved with no field changed."),
    ).toBeInTheDocument();
  });

  it("reports a restore the server refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "not_found", message: "Version not found" },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderDiff(
      stub({
        isPending: false,
        isError: false,
        data: [
          aVersion(),
          aVersion({ id: 2, version_number: 2, value: "250000" }),
        ],
      }),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Restore version 1" }),
    );

    await waitFor(() =>
      expect(screen.getByText("Version not found")).toBeInTheDocument(),
    );
  });
});
