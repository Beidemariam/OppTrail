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

    await expect(apiRequest("/api/opportunities")).resolves.toEqual({
      ok: true,
    });
    expect(lastRequestInit().credentials).toBe("include");
    expect(headerOf("X-CSRF-Token")).toBeUndefined();
  });

  it("echoes the CSRF cookie on every unsafe method", async () => {
    document.cookie = "opptrail_csrf=abc123";

    for (const method of ["POST", "PATCH", "DELETE", "PUT", "post"]) {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({}));
      await apiRequest("/api/opportunities", { method });
      expect(headerOf("X-CSRF-Token")).toBe("abc123");
      vi.mocked(fetch).mockClear();
    }
  });

  it("returns nothing for a 204, which the delete routes answer with", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    await expect(
      apiRequest("/api/notes/1", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("raises the API's own detail message so the UI can show it", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: "Viewer cannot edit this opportunity" }, 403),
    );

    await expect(
      apiRequest("/api/timeline/1", { method: "PATCH" }),
    ).rejects.toThrow("Viewer cannot edit this opportunity");
  });

  it("falls back when the error body is not JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("<html>502</html>", { status: 502 }),
    );
    await expect(apiRequest("/api/opportunities")).rejects.toThrow(
      "Request failed",
    );
  });

  it("falls back when detail is a structure rather than a sentence", async () => {
    // FastAPI's 422 detail is a list of field errors, not a string.
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: [{ loc: ["body", "stage"], msg: "bad" }] }, 422),
    );
    await expect(
      apiRequest("/api/opportunities", { method: "POST" }),
    ).rejects.toThrow("Request failed");
  });

  it("raises the v2 envelope's message", async () => {
    // `/api/v2/*` answers `{"error": {...}}` rather than `{"detail": ...}`
    // (`backend/app/errors.py`), and both reach the user through this wrapper.
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
    await apiRequest("/api/opportunities", {
      headers: { "Content-Type": "text/plain" },
    });
    expect(headerOf("Content-Type")).toBe("text/plain");
  });
});
