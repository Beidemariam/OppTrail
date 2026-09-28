/**
 * The only way this app talks to its API.
 *
 * One wrapper rather than scattered `fetch` calls, so the session cookie, the
 * CSRF header and the API's error shape are handled in exactly one place.
 */

export const CSRF_COOKIE_NAME = "opptrail_csrf";
export const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * The API rejects any unsafe request whose `X-CSRF-Token` header does not match
 * this cookie (`backend/app/security.py`). The cookie is deliberately readable
 * from script — that is what makes the double-submit pattern work; the session
 * cookie stays HttpOnly.
 */
export function csrfToken(): string {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${CSRF_COOKIE_NAME}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : "";
}

/**
 * A failed request, carrying the envelope's named `code` as well as its
 * sentence.
 *
 * `backend/app/errors.py` defines `code` precisely so a client can branch on
 * it rather than on a status number or on the wording of a message, and
 * milestone 3.4 gave the app its first reason to: a note edit refused as
 * `conflict` (ADR 0003's edit guard) needs a different answer from every other
 * failure — the reader's copy is stale, not their request wrong. Every
 * existing caller reads `.message` and is unaffected.
 */
export class ApiError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === "conflict";
}

/**
 * The API's one error shape, `{"error": {"code", "message"}}`
 * (`backend/app/errors.py`), reduced to what a caller acts on. v1's
 * `{"detail": ...}` was the second shape this read until milestone 2.9
 * removed that surface.
 */
function apiError(body: unknown): ApiError {
  if (typeof body === "object" && body !== null) {
    const { error } = body as { error?: { message?: unknown; code?: unknown } };
    if (typeof error?.message === "string") {
      return new ApiError(
        error.message,
        typeof error.code === "string" ? error.code : "unknown",
      );
    }
  }
  return new ApiError("Request failed", "unknown");
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(SAFE_METHODS.has(method) ? {} : { "X-CSRF-Token": csrfToken() }),
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw apiError(await response.json().catch(() => null));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
