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
  /** The HTTP status, for the one caller that acts on the number rather than
   * the code: a 401 means the session is gone, whatever the message says
   * (milestone 4.2a, **D-145**). */
  readonly status: number;
  /**
   * A 422's per-field reasons, keyed the way a form can use them — `"stage"`,
   * `"action.title"` — or `"_"` for a failure about the whole request that no
   * single input owns (`backend/app/errors.py`'s `validation_fields`).
   *
   * Carried since milestone 6.3a (**D-180**). The API has emitted this since
   * the error envelope existed and milestone 6.1 was careful to make a custom
   * field's 422 name its field, but nothing on the client ever read it — so
   * every refused form in this app said only "The request could not be
   * validated", which is the sentence that reached the human at the 6.3
   * review. Empty for every failure that is not a validation error.
   */
  readonly fields: Record<string, string>;

  constructor(
    message: string,
    code: string,
    status: number,
    fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.fields = fields;
  }
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === "conflict";
}

/**
 * Whether a failure means the session has gone.
 *
 * Read in exactly one place -- `lib/query.ts`'s cache-level error handler --
 * because the answer has to be the same for every read and every write in the
 * app. Before milestone 4.2a nothing asked: a dead session left every request
 * failing with "Authentication required" while the screen carried on showing a
 * signed-in page, so the reader was told their *action* was refused rather than
 * that they were signed out (**D-145**).
 */
export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** `error.fields` as a string map, dropping anything that is not one: the
 * envelope is the server's, and a form is about to render these. */
function validationFields(raw: unknown): Record<string, string> {
  if (typeof raw !== "object" || raw === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

/**
 * The API's one error shape, `{"error": {"code", "message"}}`
 * (`backend/app/errors.py`), reduced to what a caller acts on. v1's
 * `{"detail": ...}` was the second shape this read until milestone 2.9
 * removed that surface.
 */
function apiError(body: unknown, status: number): ApiError {
  if (typeof body === "object" && body !== null) {
    const { error } = body as {
      error?: { message?: unknown; code?: unknown; fields?: unknown };
    };
    if (typeof error?.message === "string") {
      return new ApiError(
        error.message,
        typeof error.code === "string" ? error.code : "unknown",
        status,
        validationFields(error.fields),
      );
    }
  }
  return new ApiError("Request failed", "unknown", status);
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  // One request in the app sends a file rather than JSON (milestone 4.3's
  // upload). A multipart body carries a boundary the browser generates, so
  // declaring the content type here would send a header that does not match
  // the bytes and the server's parser would find no parts; `fetch` fills it in
  // for a `FormData` body when it is left alone. Everything else is JSON, so
  // the default stays the default.
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(SAFE_METHODS.has(method) ? {} : { "X-CSRF-Token": csrfToken() }),
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw apiError(await response.json().catch(() => null), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
