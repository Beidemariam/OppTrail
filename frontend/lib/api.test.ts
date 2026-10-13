import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest, csrfToken } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastRequestInit(): RequestInit {
  return vi.mocked(fetch).mock.calls[0][1] as RequestInit;
}

function headerOf(name: string): string | undefined {
  return (lastRequestInit().headers as Record<string, string>)[name];
}

beforeEach(() => {
  document.cookie = "opptrail_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("csrfToken", () => {
  it("reads the double-submit cookie the backend sets", () => {
    document.cookie = "opptrail_csrf=abc123";
    expect(csrfToken()).toBe("abc123");
  });

  it("decodes a percent-encoded value", () => {
    document.cookie = `opptrail_csrf=${encodeURIComponent("a+b/c=")}`;
    expect(csrfToken()).toBe("a+b/c=");
  });

  it("is empty when the cookie has not been issued yet", () => {
    expect(csrfToken()).toBe("");
  });

  it("does not match a different cookie whose name ends the same way", () => {
    document.cookie = "not_opptrail_csrf=wrong";
    expect(csrfToken()).toBe("");
  });
});

describe("apiRequest", () => {
  it("sends the session cookie and no CSRF header on a safe request", async () => {
    document.cookie = "opptrail_csrf=abc123";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));

    await expect(apiRequest("/api/v2/opportunities")).resolves.toEqual({
      ok: true,
    });
    expect(lastRequestInit().credentials).toBe("include");
    expect(headerOf("X-CSRF-Token")).toBeUndefined();
  });

  it("echoes the CSRF cookie on every unsafe method", async () => {
    document.cookie = "opptrail_csrf=abc123";

    for (const method of ["POST", "PATCH", "DELETE", "PUT", "post"]) {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({}));
      await apiRequest("/api/v2/opportunities", { method });
      expect(headerOf("X-CSRF-Token")).toBe("abc123");
      vi.mocked(fetch).mockClear();
    }
  });

  it("returns nothing for a 204, which the delete routes answer with", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    await expect(
      apiRequest("/api/v2/notes/1", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("ignores v1's `detail`, which no endpoint answers any more", async () => {
    // Milestone 2.9 removed v1 and with it the second error shape. A body
    // shaped like the old one is not a message this wrapper knows how to
    // read, and inventing one from it would hide the real failure.
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: "Viewer cannot edit this opportunity" }, 403),
    );

    await expect(
      apiRequest("/api/v2/timeline/1", { method: "PATCH" }),
    ).rejects.toThrow("Request failed");
  });

  it("falls back when the error body is not JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("<html>502</html>", { status: 502 }),
    );
    await expect(apiRequest("/api/v2/opportunities")).rejects.toThrow(
      "Request failed",
    );
  });

  it("raises the envelope's message so the UI can show it", async () => {
    // The API's one error shape, `{"error": {...}}`
    // (`backend/app/errors.py`), which reaches the user through this wrapper.
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "limit must be between 1 and 200",
          },
        },
        422,
      ),
    );

    await expect(apiRequest("/api/v2/search?q=a&limit=500")).rejects.toThrow(
      "limit must be between 1 and 200",
    );
  });

  it("falls back when the v2 envelope carries no message", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ error: { code: "not_found" } }, 404),
    );
    await expect(apiRequest("/api/v2/search?q=a")).rejects.toThrow(
      "Request failed",
    );
  });

  it("falls back when the error body is JSON but not an object", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse("nope", 500));
    await expect(apiRequest("/api/v2/search?q=a")).rejects.toThrow(
      "Request failed",
    );
  });

  it("lets a caller's own headers win", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}));
    await apiRequest("/api/v2/opportunities", {
      headers: { "Content-Type": "text/plain" },
    });
    expect(headerOf("Content-Type")).toBe("text/plain");
  });
});

describe("a 422's per-field reasons (milestone 6.3a, D-180)", () => {
  it("carries them off the envelope onto the error", async () => {
    // The API has emitted these since the envelope existed; nothing read
    // them, so every refused form in the app said only the generic sentence.
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "The request could not be validated",
            fields: { "action.title": "Enter a value", _: "Wrong as a whole" },
          },
        },
        422,
      ),
    );

    await expect(apiRequest("/api/v2/automation-rules")).rejects.toMatchObject({
      status: 422,
      code: "validation_error",
      fields: { "action.title": "Enter a value", _: "Wrong as a whole" },
    });
  });

  it("is an empty map for a failure that names no field", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { error: { code: "conflict", message: "Already there" } },
        409,
      ),
    );

    await expect(apiRequest("/api/v2/automation-rules")).rejects.toMatchObject({
      code: "conflict",
      fields: {},
    });
  });

  it("drops anything in fields that is not a string", async () => {
    // The envelope is the server's and a form is about to render these.
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "no",
            fields: { ok: "a reason", bad: { nested: true }, worse: 7 },
          },
        },
        422,
      ),
    );

    await expect(apiRequest("/api/v2/automation-rules")).rejects.toMatchObject({
      fields: { ok: "a reason" },
    });
  });
});
