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
 * The two error shapes the API answers with: v1 sends `{"detail": ...}` and
 * v2 sends the envelope `{"error": {"code", "message"}}`
 * (`backend/app/errors.py`). Both reduce to the one sentence a caller shows.
 */
function errorMessage(body: unknown): string {
  if (typeof body === "object" && body !== null) {
    const { detail, error } = body as {
      detail?: unknown;
      error?: { message?: unknown };
    };
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof error?.message === "string") {
      return error.message;
    }
  }
  return "Request failed";
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
    throw new Error(errorMessage(await response.json().catch(() => null)));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
