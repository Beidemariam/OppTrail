import { vi } from "vitest";

import type { components } from "../lib/api-types";

/**
 * A stand-in for the OppTrail API, good enough to drive the whole page.
 *
 * `page.tsx` reloads a list after every write, so a table of canned responses
 * would test the click and not the consequence. This fake keeps the small
 * amount of state the page actually reads back, which is what makes
 * "delete the note, the note is gone" a real assertion.
 *
 * Shapes follow `lib/api-types.ts`, which is generated from the live OpenAPI
 * schema, so a drift between this fake and the API shows up as a type error.
 */

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
}

export interface FakeApiOptions {
  user?: { id: number; email: string; name: string; created_at: string } | null;
  opportunities?: Opportunity[];
  entries?: TimelineEntry[];
  notifications?: Notification[];
  shares?: Share[];
  auditLog?: AuditEntry[];
  searchResults?: SearchResult[];
  /** Paths that should fail, mapped to `[status, detail]`. */
  failures?: Record<string, [number, string]>;
}

interface Opportunity {
  id: number;
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  owner_id: number;
  owner_name: string;
  expected_close_date: string | null;
  created_at: string;
  updated_at: string;
  stalled: boolean;
  current_user_role: "owner" | "editor" | "viewer";
}

interface Comment {
  id: number;
  note_id: number;
  body: string;
  created_by: number;
  author_name: string;
  created_at: string;
}

interface Note {
  id: number;
  entry_id: number;
  body: string;
  created_by: number;
  author_name: string;
  created_at: string;
  updated_at: string;
  edited: boolean;
  comments: Comment[];
}

interface TimelineEntry {
  id: number;
  opportunity_id: number;
  type: string;
  title: string;
  body: string;
  event_timestamp: string;
  follow_up_date: string | null;
  created_by: number | null;
  author_name: string | null;
  system_generated: boolean;
  created_at: string;
  notes: Note[];
}

interface Share {
  user_id: number;
  email: string;
  name: string;
  role: "viewer" | "editor";
  invited_by: number;
  invited_by_name: string;
  created_at: string;
}

interface AuditEntry {
  id: number;
  opportunity_id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export const ALEX = {
  id: 1,
  email: "alex@opptrail.test",
  name: "Alex",
  created_at: "2026-01-01T00:00:00Z",
};
export const BLAIR = {
  id: 2,
  email: "blair@opptrail.test",
  name: "Blair",
  created_at: "2026-01-01T00:00:00Z",
};

export function anOpportunity(
  overrides: Partial<Opportunity> = {},
): Opportunity {
  return {
    id: 10,
    name: "Northwind rollout",
    account_name: "Northwind",
    value: "185000",
    currency: "USD",
    stage: "Negotiation",
    owner_id: ALEX.id,
    owner_name: ALEX.name,
    expected_close_date: "2026-12-01",
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-01T09:00:00Z",
    stalled: false,
    current_user_role: "owner",
    ...overrides,
  };
}

export function anEntry(overrides: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    id: 100,
    opportunity_id: 10,
    type: "call",
    title: "Discovery call",
    body: "Talked budget.",
    event_timestamp: "2026-09-02T14:00:00Z",
    follow_up_date: null,
    created_by: ALEX.id,
    author_name: ALEX.name,
    system_generated: false,
    created_at: "2026-09-02T14:00:00Z",
    notes: [],
    ...overrides,
  };
}

export function aNote(overrides: Partial<Note> = {}): Note {
  return {
    id: 200,
    entry_id: 100,
    body: "Budget holder is the COO.",
    created_by: ALEX.id,
    author_name: ALEX.name,
    created_at: "2026-09-02T14:05:00Z",
    updated_at: "2026-09-02T14:05:00Z",
    edited: false,
    comments: [],
    ...overrides,
  };
}

export function aComment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: 300,
    note_id: 200,
    body: "Agreed.",
    created_by: ALEX.id,
    author_name: ALEX.name,
    created_at: "2026-09-02T14:10:00Z",
    ...overrides,
  };
}

type SearchResult = components["schemas"]["SearchResultPublic"];

export function aSearchResult(
  overrides: Partial<SearchResult> = {},
): SearchResult {
  return {
    kind: "note",
    id: 200,
    opportunity_id: 10,
    opportunity_name: "Northwind rollout",
    entry_id: 100,
    note_id: 200,
    title: "Discovery call",
    snippet: { text: "They want viewer-only for finance.", matches: [] },
    timestamp: "2026-09-02T14:05:00Z",
    author_id: ALEX.id,
    author_name: ALEX.name,
    ...overrides,
  };
}

interface Notification {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export class FakeApi {
  readonly calls: RecordedCall[] = [];
  user: FakeApiOptions["user"];
  opportunities: Opportunity[];
  entries: TimelineEntry[];
  notifications: Notification[];
  shares: Share[];
  auditLog: AuditEntry[];
  searchResults: SearchResult[];
  failures: Record<string, [number, string]>;
  private nextId = 1000;

  constructor(options: FakeApiOptions = {}) {
    this.user = options.user ?? null;
    this.opportunities = options.opportunities ?? [];
    this.entries = options.entries ?? [];
    this.notifications = options.notifications ?? [];
    this.shares = options.shares ?? [];
    this.auditLog = options.auditLog ?? [];
    this.searchResults = options.searchResults ?? [];
    this.failures = options.failures ?? {};
  }

  /** Every call made to a path, for asserting what the page asked the API to do. */
  callsTo(method: string, pathFragment: string): RecordedCall[] {
    return this.calls.filter(
      (call) => call.method === method && call.path.includes(pathFragment),
    );
  }

  install(): void {
    vi.stubGlobal("fetch", vi.fn(this.handle.bind(this)));
  }

  private json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  private async handle(
    path: string,
    options: RequestInit = {},
  ): Promise<Response> {
    const method = (options.method ?? "GET").toUpperCase();
    const body = options.body ? JSON.parse(options.body as string) : undefined;
    this.calls.push({ method, path, body });

    const failure = this.failures[`${method} ${path.split("?")[0]}`];
    if (failure) {
      // v2 answers the `{"error": {...}}` envelope and v1 answers `detail`
      // (`backend/app/errors.py`); the fake follows, so a page that reads the
      // wrong one fails here rather than in production.
      const body = path.startsWith("/api/v2/")
        ? { error: { code: "error", message: failure[1] } }
        : { detail: failure[1] };
      return this.json(body, failure[0]);
    }

    const bare = path.split("?")[0];
    const segments = bare.split("/").filter(Boolean);

    if (bare === "/api/v2/search") {
      return this.searchPage(path);
    }
    if (bare === "/api/auth/me") {
      return this.user
        ? this.json({ user: this.user })
        : this.json({ detail: "Authentication required" }, 401);
    }
    if (bare === "/api/auth/login" || bare === "/api/auth/signup") {
      this.user = this.user ?? {
        ...ALEX,
        email: body.email,
        name: body.name ?? ALEX.name,
      };
      return this.json({ user: this.user });
    }
    if (bare === "/api/auth/logout") {
      this.user = null;
      return this.json({ ok: true });
    }
    if (bare === "/api/notifications") {
      return this.json({
        notifications: this.notifications
          .filter((item) => !item.read_at)
          .map((item) => ({ ...item, read: false })),
      });
    }
    if (bare === "/api/v2/notifications" && method === "GET") {
      return this.notificationsPage(path);
    }
    if (bare === "/api/v2/notifications/mark-all-read" && method === "POST") {
      const unread = this.notifications.filter((item) => !item.read_at);
      const now = new Date().toISOString();
      unread.forEach((item) => {
        item.read_at = now;
      });
      return this.json({ marked: unread.length });
    }
    if (segments[1] === "notifications" && method === "PATCH") {
      const id = Number(segments[2]);
      const found = this.notifications.find((item) => item.id === id)!;
      found.read_at = found.read_at ?? new Date().toISOString();
      return this.json({ ...found, read: true });
    }
    if (bare === "/api/opportunities" && method === "GET") {
      return this.json({ stages: [], opportunities: this.opportunities });
    }
    if (bare === "/api/opportunities" && method === "POST") {
      const created = anOpportunity({
        ...body,
        id: this.nextId++,
        value: String(body.value),
      });
      this.opportunities.push(created);
      return this.json(created, 201);
    }
    if (segments[1] === "opportunities" && segments.length === 3) {
      const id = Number(segments[2]);
      if (method === "PATCH") {
        const found = this.opportunities.find((item) => item.id === id)!;
        Object.assign(found, body, {
          value: String(body.value ?? found.value),
        });
        return this.json(found);
      }
      if (method === "DELETE") {
        this.opportunities = this.opportunities.filter(
          (item) => item.id !== id,
        );
        return new Response(null, { status: 204 });
      }
    }
    if (segments[3] === "timeline") {
      if (method === "GET") {
        return this.json({ entries: this.entries });
      }
      const created = anEntry({
        ...body,
        id: this.nextId++,
        opportunity_id: Number(segments[2]),
      });
      this.entries.push(created);
      return this.json(created, 201);
    }
    if (segments[3] === "shares" || segments[3] === "audit-log") {
      if (segments[3] === "audit-log") {
        return this.json(this.auditLog);
      }
      if (method === "GET") {
        return this.json({ shares: this.shares });
      }
      if (method === "POST") {
        const created: Share = {
          user_id: this.nextId++,
          email: body.email,
          name: body.email.split("@")[0],
          role: body.role,
          invited_by: ALEX.id,
          invited_by_name: ALEX.name,
          created_at: "2026-09-03T09:00:00Z",
        };
        this.shares.push(created);
        return this.json(created, 201);
      }
      const userId = Number(segments[4]);
      if (method === "PATCH") {
        const found = this.shares.find((item) => item.user_id === userId)!;
        found.role = body.role;
        return this.json(found);
      }
      this.shares = this.shares.filter((item) => item.user_id !== userId);
      return new Response(null, { status: 204 });
    }
    if (segments[3] === "ai") {
      return this.json({
        answer: `Answer to: ${body.question}`,
        referenced_entry_ids: [100],
      });
    }
    if (segments[1] === "timeline") {
      const entryId = Number(segments[2]);
      if (segments[3] === "notes") {
        const entry = this.entries.find((item) => item.id === entryId)!;
        const created = aNote({
          id: this.nextId++,
          entry_id: entryId,
          body: body.body,
        });
        entry.notes.push(created);
        return this.json(created, 201);
      }
      if (method === "PATCH") {
        const entry = this.entries.find((item) => item.id === entryId)!;
        Object.assign(entry, body);
        return this.json(entry);
      }
      this.entries = this.entries.filter((item) => item.id !== entryId);
      return new Response(null, { status: 204 });
    }
    if (segments[1] === "notes") {
      const noteId = Number(segments[2]);
      const owner = this.entries.find((entry) =>
        entry.notes.some((note) => note.id === noteId),
      )!;
      const note = owner.notes.find((item) => item.id === noteId)!;
      if (segments[3] === "comments") {
        const created = aComment({
          id: this.nextId++,
          note_id: noteId,
          body: body.body,
        });
        note.comments.push(created);
        return this.json(created, 201);
      }
      if (method === "PATCH") {
        note.body = body.body;
        note.edited = true;
        return this.json(note);
      }
      owner.notes = owner.notes.filter((item) => item.id !== noteId);
      return new Response(null, { status: 204 });
    }
    if (segments[1] === "comments") {
      const commentId = Number(segments[2]);
      for (const entry of this.entries) {
        for (const note of entry.notes) {
          note.comments = note.comments.filter((item) => item.id !== commentId);
        }
      }
      return new Response(null, { status: 204 });
    }

    return this.json(
      { detail: `Unhandled in the fake API: ${method} ${path}` },
      500,
    );
  }

  /**
   * The v2 keyset envelope (`backend/app/pagination.py`): a page of matches
   * plus the cursor for the next one, `null` on the last page. The cursor here
   * is the offset into the filtered list — opaque to the client, which is the
   * only property the page is allowed to depend on.
   */
  private searchPage(path: string): Response {
    const params = new URLSearchParams(path.split("?")[1] ?? "");
    const query = (params.get("q") ?? "").toLowerCase();
    const limit = Number(params.get("limit") ?? 50);
    const offset = Number(params.get("cursor") ?? 0);

    const hits = this.searchResults.filter((result) =>
      [result.opportunity_name, result.title ?? "", result.snippet.text]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
    const items = hits.slice(offset, offset + limit);
    const next = offset + limit;

    return this.json({
      items,
      next_cursor: next < hits.length ? String(next) : null,
    });
  }

  /** `GET /api/v2/notifications`: full history, optionally filtered by type. */
  private notificationsPage(path: string): Response {
    const params = new URLSearchParams(path.split("?")[1] ?? "");
    const type = params.get("type");

    const items = this.notifications
      .filter((item) => !type || item.type === type)
      .map((item) => ({ ...item, grouped_key: null }));

    return this.json({ items, next_cursor: null });
  }
}
