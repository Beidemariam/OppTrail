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
  /** Who is watching, for the owner-only list (milestone 3.3a). Watching
   * itself (POST/DELETE `.../watch`) is tracked separately, per the current
   * `user`, since it needs no share at all (D-129). */
  watchers?: Watcher[];
  activity?: ActivityEvent[];
  searchResults?: SearchResult[];
  savedViews?: SavedView[];
  /** Tasks (milestone 4.1). Seeded whole, like every other collection here. */
  tasks?: Task[];
  /** Paths that should fail, mapped to `[status, detail]`. */
  failures?: Record<string, [number, string]>;
  /**
   * `"METHOD /path"` entries whose response is held until `release()` is
   * called. An optimistic update is only observable while its request is still
   * in flight, so a test that asserts one needs a request that stays there.
   */
  pending?: string[];
  /**
   * Split every collection read into pages of this size. Unset means one page
   * per read, which is what nearly every test wants; a test that cares how
   * `fetchAll` walks `next_cursor` (`lib/queries.ts`) sets it small.
   */
  pageSize?: number;
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

/** One person's reaction to a comment or reply (milestone 3.3a). */
interface Reaction {
  id: number;
  comment_id: number;
  emoji: string;
  user_id: number;
  user_name: string;
  created_at: string;
}

interface Comment {
  id: number;
  note_id: number;
  parent_id: number | null;
  body: string;
  created_by: number;
  author_name: string;
  created_at: string;
  reactions: Reaction[];
}

/** A thread root as the timeline read returns it (milestone 3.3): its
 * replies come with it, and so does whoever called it finished. */
interface CommentThread extends Comment {
  resolved_at: string | null;
  resolved_by: number | null;
  resolved_by_name: string | null;
  replies: Comment[];
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
  comments: CommentThread[];
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
  /** This entry's number within its opportunity, which the server computes
   * (milestone 3.9, D-139). A fixture value here rather than a count, because
   * no component derives it -- the card prints what the API sent, which is
   * exactly the property worth keeping. */
  sequence: number;
  notes: Note[];
}

/** The calendar's follow-up layer (milestone 3.0b, D-088): a `TimelineEntry`
 * read cross-opportunity, so it carries the opportunity's own name rather
 * than its id alone. */
interface FollowUp {
  id: number;
  opportunity_id: number;
  opportunity_name: string;
  type: string;
  title: string;
  follow_up_date: string;
  created_by: number | null;
  author_name: string | null;
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

/** Who is following an opportunity (milestone 3.3a), owner-only to read. */
interface Watcher {
  id: number;
  opportunity_id: number;
  user_id: number;
  user_name: string;
  user_email: string;
  created_at: string;
}

/** Who is on the opportunity, for the mention autocomplete (milestone 3.2).
 * Derived from the owner and the shares rather than stored, the way the
 * server derives it (`backend/app/routes_sharing.py`). */
type Member = components["schemas"]["OpportunityMemberPublic"];
/** Generated, like `Member`: a task has a dozen fields and the fake has no
 * reason to restate them (milestone 4.1). */
type Task = components["schemas"]["TaskPublic"];

/** The merged activity log's row shape, straight from the generated client. */
type ActivityEvent = components["schemas"]["ActivityEventPublic"];

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
    sequence: 1,
    notes: [],
    ...overrides,
  };
}

/** One task on the seeded opportunity (milestone 4.1). */
export function aTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 500,
    opportunity_id: 10,
    opportunity_name: "Northwind rollout",
    entry_id: null,
    entry_title: null,
    title: "Send the revised pricing",
    assignee_id: ALEX.id,
    assignee_name: ALEX.name,
    due_date: null,
    completed_at: null,
    completed_by: null,
    completed_by_name: null,
    created_by: ALEX.id,
    author_name: ALEX.name,
    created_at: "2026-09-02T14:00:00Z",
    updated_at: "2026-09-02T14:00:00Z",
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

export function aComment(
  overrides: Partial<CommentThread> = {},
): CommentThread {
  return {
    id: 300,
    note_id: 200,
    parent_id: null,
    body: "Agreed.",
    created_by: ALEX.id,
    author_name: ALEX.name,
    created_at: "2026-09-02T14:10:00Z",
    resolved_at: null,
    resolved_by: null,
    resolved_by_name: null,
    replies: [],
    reactions: [],
    ...overrides,
  };
}

/** A reply, for a test that wants a thread with an answer already in it. */
export function aReply(
  parent: CommentThread,
  overrides: Partial<Comment> = {},
): Comment {
  return {
    id: parent.id + 1,
    note_id: parent.note_id,
    parent_id: parent.id,
    body: "Confirmed.",
    created_by: BLAIR.id,
    author_name: BLAIR.name,
    created_at: "2026-09-02T14:12:00Z",
    reactions: [],
    ...overrides,
  };
}

type SearchResult = components["schemas"]["SearchResultPublic"];

/**
 * Edit history (milestone 2.10). The fake writes these itself rather than
 * taking them as an option: what a test wants to assert is "edit it, and the
 * history says what it used to say", which is only a real assertion if the
 * write is what produced the row.
 */
type OpportunityVersion = components["schemas"]["OpportunityVersionPublic"];
type TimelineEntryVersion = components["schemas"]["TimelineEntryVersionPublic"];
type NoteVersion = components["schemas"]["NoteVersionPublic"];

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

interface SavedView {
  id: number;
  created_by: number;
  creator_name: string;
  name: string;
  entity: "opportunities" | "timeline";
  filters: Record<string, string>;
  sort: Record<string, string>;
  group_by: string | null;
  is_shared: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export class FakeApi {
  readonly calls: RecordedCall[] = [];
  user: FakeApiOptions["user"];
  opportunities: Opportunity[];
  entries: TimelineEntry[];
  notifications: Notification[];
  shares: Share[];
  watchers: Watcher[];
  activity: ActivityEvent[];
  searchResults: SearchResult[];
  savedViews: SavedView[];
  tasks: Task[];
  failures: Record<string, [number, string]>;
  // The current `user`'s own watch set (milestone 3.3a), separate from
  // `watchers` above: watching needs no share at all (D-129), so it is not
  // derived from anything else this fake tracks.
  private watching = new Set<number>();
  /** Deleted tasks, so `POST .../restore` has something to put back
   * (milestone 4.1) -- the same shape `deleted` uses for the other kinds. */
  private deletedTasks = new Map<number, Task>();
  private pending: Set<string>;
  private pageSize: number | undefined;
  private held = new Map<
    string,
    { wait: Promise<void>; release: () => void }
  >();
  private nextId = 1000;
  /** A monotonic clock for `updated_at`, so a second edit is distinguishable
   * from the first. Deterministic on purpose (brief §6.5): a real timestamp
   * would make an assertion depend on when the test ran. */
  private clock = 0;
  // Version 1 is recorded when the fake sees the thing created, or — for the
  // rows a test hands it already made — the first time it is edited, from
  // the state it held before that edit. Either way the list opens with what
  // the item said before the change under test.
  private versions = {
    opportunities: new Map<number, OpportunityVersion[]>(),
    entries: new Map<number, TimelineEntryVersion[]>(),
    notes: new Map<number, NoteVersion[]>(),
  };
  // What a delete took, so a restore can put it back where it was — the
  // server keeps the row and clears `deleted_at` (`backend/app/soft_delete.py`),
  // and a fake that dropped the object would make undo untestable.
  private deleted = {
    opportunities: new Map<number, { index: number; item: Opportunity }>(),
    entries: new Map<number, { index: number; item: TimelineEntry }>(),
    notes: new Map<number, { index: number; entryId: number; item: Note }>(),
    comments: new Map<
      number,
      { index: number; noteId: number; item: CommentThread }
    >(),
  };

  constructor(options: FakeApiOptions = {}) {
    this.user = options.user ?? null;
    this.opportunities = options.opportunities ?? [];
    this.entries = options.entries ?? [];
    this.notifications = options.notifications ?? [];
    this.shares = options.shares ?? [];
    this.watchers = options.watchers ?? [];
    this.activity = options.activity ?? [];
    this.searchResults = options.searchResults ?? [];
    this.savedViews = options.savedViews ?? [];
    this.tasks = options.tasks ?? [];
    this.failures = options.failures ?? {};
    this.pending = new Set(options.pending ?? []);
    this.pageSize = options.pageSize;
  }

  /** Lets a held request finish. */
  release(key: string): void {
    this.gate(key).release();
    this.pending.delete(key);
  }

  private gate(key: string) {
    let gate = this.held.get(key);
    if (!gate) {
      let release = () => {};
      const wait = new Promise<void>((resolve) => {
        release = resolve;
      });
      gate = { wait, release };
      this.held.set(key, gate);
    }
    return gate;
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

  private nextTimestamp(): string {
    this.clock += 1;
    return `2026-09-30T12:00:${String(this.clock).padStart(2, "0")}Z`;
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

    if (this.pending.has(`${method} ${path.split("?")[0]}`)) {
      await this.gate(`${method} ${path.split("?")[0]}`).wait;
    }

    const failure = this.failures[`${method} ${path.split("?")[0]}`];
    if (failure) {
      // The API has one error shape (`backend/app/errors.py`), so the fake
      // has one too; a page that reads a different one fails here rather
      // than in production.
      return this.json(
        { error: { code: "error", message: failure[1] } },
        failure[0],
      );
    }

    const bare = path.split("?")[0];
    // One surface since milestone 2.9, so the `/api/v2` prefix is stripped
    // once here and every index below is the route's own.
    const segments = bare
      .replace(/^\/api\/v2/, "")
      .split("/")
      .filter(Boolean);

    if (segments[2] === "restore") {
      return this.restore(segments[0], Number(segments[1]));
    }

    if (bare === "/api/v2/opportunities/bulk" && method === "POST") {
      return this.bulkOpportunityAction(body);
    }

    if (bare === "/api/v2/search") {
      return this.searchPage(path);
    }
    if (bare === "/api/v2/timeline/follow-ups") {
      return this.followUpsPage(path);
    }
    if (bare === "/api/v2/auth/me") {
      return this.user
        ? this.json({ user: this.user })
        : this.json(
            {
              error: {
                code: "unauthorized",
                message: "Authentication required",
              },
            },
            401,
          );
    }
    if (bare === "/api/v2/auth/login" || bare === "/api/v2/auth/signup") {
      this.user = this.user ?? {
        ...ALEX,
        email: body.email,
        name: body.name ?? ALEX.name,
      };
      return this.json({ user: this.user });
    }
    if (bare === "/api/v2/auth/logout") {
      this.user = null;
      return this.json({ ok: true });
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
    if (bare === "/api/v2/saved-views" && method === "GET") {
      const params = new URLSearchParams(path.split("?")[1] ?? "");
      const entity = params.get("entity");
      const items = this.savedViews.filter(
        (view) =>
          (view.created_by === this.user?.id || view.is_shared) &&
          (!entity || view.entity === entity),
      );
      return this.json({ items, next_cursor: null });
    }
    if (bare === "/api/v2/saved-views" && method === "POST") {
      const created: SavedView = {
        id: this.nextId++,
        created_by: this.user?.id ?? ALEX.id,
        creator_name: this.user?.name ?? ALEX.name,
        name: body.name,
        entity: body.entity,
        filters: body.filters ?? {},
        sort: body.sort ?? {},
        group_by: body.group_by ?? null,
        is_shared: Boolean(body.is_shared),
        is_default: Boolean(body.is_default),
        created_at: "2026-09-20T09:00:00Z",
        updated_at: "2026-09-20T09:00:00Z",
      };
      if (created.is_default) {
        this.savedViews.forEach((view) => {
          if (
            view.entity === created.entity &&
            view.created_by === created.created_by
          ) {
            view.is_default = false;
          }
        });
      }
      this.savedViews.push(created);
      return this.json(created, 201);
    }
    if (segments[0] === "saved-views" && method === "PATCH") {
      const id = Number(segments[1]);
      const found = this.savedViews.find((view) => view.id === id);
      if (!found || found.created_by !== this.user?.id) {
        return this.notFound("Saved view not found");
      }
      if (body.is_default) {
        this.savedViews.forEach((view) => {
          if (
            view.entity === found.entity &&
            view.created_by === found.created_by
          ) {
            view.is_default = false;
          }
        });
      }
      Object.assign(found, {
        name: body.name ?? found.name,
        filters: body.filters ?? found.filters,
        sort: body.sort ?? found.sort,
        group_by: body.group_by ?? found.group_by,
        is_shared: body.is_shared ?? found.is_shared,
        is_default: body.is_default ?? found.is_default,
      });
      return this.json(found);
    }
    if (segments[0] === "saved-views" && method === "DELETE") {
      const id = Number(segments[1]);
      const found = this.savedViews.find((view) => view.id === id);
      if (!found || found.created_by !== this.user?.id) {
        return this.notFound("Saved view not found");
      }
      this.savedViews = this.savedViews.filter((view) => view.id !== id);
      return new Response(null, { status: 204 });
    }
    if (segments[0] === "notifications" && method === "PATCH") {
      const id = Number(segments[1]);
      const found = this.notifications.find((item) => item.id === id)!;
      found.read_at = found.read_at ?? new Date().toISOString();
      return this.json(found);
    }
    if (bare === "/api/v2/opportunities" && method === "GET") {
      return this.page(this.opportunities, path);
    }
    if (bare === "/api/v2/opportunities" && method === "POST") {
      const created = anOpportunity({
        ...body,
        id: this.nextId++,
        value: String(body.value),
      });
      this.opportunities.push(created);
      this.recordVersion(
        this.versions.opportunities,
        created.id,
        this.opportunitySnapshot(created),
      );
      return this.json(created, 201);
    }
    if (segments[0] === "opportunities" && segments[2] === "versions") {
      if (segments[4] === "restore") {
        return this.restoreVersion(
          this.versions.opportunities,
          Number(segments[1]),
          Number(segments[3]),
          (version) => {
            const found = this.opportunities.find(
              (item) => item.id === version.opportunity_id,
            )!;
            Object.assign(found, {
              name: version.name,
              account_name: version.account_name,
              value: version.value,
              currency: version.currency,
              stage: version.stage,
              expected_close_date: version.expected_close_date,
            });
            this.recordVersion(
              this.versions.opportunities,
              found.id,
              this.opportunitySnapshot(found),
            );
            return found;
          },
        );
      }
      return this.page(
        this.versions.opportunities.get(Number(segments[1])) ?? [],
        path,
      );
    }
    if (segments[0] === "opportunities" && segments.length === 2) {
      const id = Number(segments[1]);
      if (method === "PATCH") {
        const found = this.opportunities.find((item) => item.id === id)!;
        if (!this.versions.opportunities.has(id)) {
          this.recordVersion(
            this.versions.opportunities,
            id,
            this.opportunitySnapshot(found),
          );
        }
        Object.assign(found, body, {
          value: String(body.value ?? found.value),
        });
        this.recordVersion(
          this.versions.opportunities,
          id,
          this.opportunitySnapshot(found),
        );
        return this.json(found);
      }
      if (method === "DELETE") {
        const index = this.opportunities.findIndex((item) => item.id === id);
        this.deleted.opportunities.set(id, {
          index,
          item: this.opportunities[index],
        });
        this.opportunities = this.opportunities.filter(
          (item) => item.id !== id,
        );
        return new Response(null, { status: 204 });
      }
    }
    if (segments[2] === "timeline") {
      if (method === "GET") {
        return this.page(this.entries, path);
      }
      const created = anEntry({
        ...body,
        id: this.nextId++,
        opportunity_id: Number(segments[1]),
        // The real server numbers chronologically; a created entry is the
        // newest here, which is the same answer for a fixture in order.
        sequence: this.entries.length + 1,
      });
      this.entries.push(created);
      this.recordVersion(
        this.versions.entries,
        created.id,
        this.entrySnapshot(created),
      );
      return this.json(created, 201);
    }
    if (segments[2] === "activity") {
      return this.page(this.activity, path);
    }
    // Tasks (milestone 4.1). One deal's list, and the writes the panel makes.
    if (segments[0] === "opportunities" && segments[2] === "tasks") {
      const opportunityId = Number(segments[1]);
      if (method === "GET") {
        return this.page(
          this.tasks.filter((task) => task.opportunity_id === opportunityId),
          path,
        );
      }
      const opportunity = this.opportunities.find(
        (item) => item.id === opportunityId,
      );
      const member = this.shares.find(
        (share) => share.email === body.assignee_email,
      );
      const created: Task = aTask({
        id: this.nextId++,
        opportunity_id: opportunityId,
        opportunity_name: opportunity?.name ?? "",
        title: String(body.title),
        due_date: body.due_date ?? null,
        // Resolved from the email the way the route does, so a test that
        // assigns somebody reads their name back rather than the author's.
        assignee_id: member?.user_id ?? (body.assignee_email ? 0 : null),
        assignee_name:
          member?.name ?? (body.assignee_email ? body.assignee_email : null),
        entry_id: body.entry_id ?? null,
      });
      this.tasks.push(created);
      return this.json(created, 201);
    }
    if (segments[0] === "tasks" && segments.length === 1) {
      // My Tasks: assigned to the signed-in reader, open unless asked
      // otherwise -- the server's own default, which the page relies on.
      const includeCompleted = path.includes("include_completed=true");
      return this.page(
        this.tasks.filter(
          (task) =>
            task.assignee_id === this.user?.id &&
            (includeCompleted || !task.completed_at),
        ),
        path,
      );
    }
    if (segments[0] === "tasks" && segments.length >= 2) {
      const id = Number(segments[1]);
      const task = this.tasks.find((item) => item.id === id);
      if (!task) {
        return this.json(
          { error: { code: "not_found", message: "Task not found" } },
          404,
        );
      }
      if (segments[2] === "complete" || segments[2] === "reopen") {
        const done = segments[2] === "complete";
        Object.assign(task, {
          completed_at: done ? "2026-09-28T12:00:00Z" : null,
          completed_by: done ? (this.user?.id ?? null) : null,
          completed_by_name: done ? (this.user?.name ?? null) : null,
        });
        return this.json(task);
      }
      if (method === "PATCH") {
        Object.assign(task, body);
        return this.json(task);
      }
      if (method === "DELETE") {
        this.tasks = this.tasks.filter((item) => item.id !== id);
        this.deletedTasks.set(id, task);
        return new Response(null, { status: 204 });
      }
    }
    // `GET .../audit-log` has no branch here on purpose: the app stopped
    // reading it in 3.1c (D-121), and a fake that answers a route nothing
    // calls hides the fact that nothing calls it.
    if (segments[2] === "members") {
      const opportunity = this.opportunities.find(
        (item) => item.id === Number(segments[1]),
      );
      const members: Member[] = [
        ...(opportunity
          ? [
              {
                user_id: opportunity.owner_id,
                email: `${opportunity.owner_name.toLowerCase()}@opptrail.test`,
                name: opportunity.owner_name,
                role: "owner" as const,
              },
            ]
          : []),
        ...this.shares.map((share) => ({
          user_id: share.user_id,
          email: share.email,
          name: share.name,
          role: share.role,
        })),
      ].sort((left, right) => left.name.localeCompare(right.name));
      return this.page(members, path);
    }
    if (segments[2] === "shares") {
      if (method === "GET") {
        return this.page(this.shares, path);
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
      const userId = Number(segments[3]);
      if (method === "PATCH") {
        const found = this.shares.find((item) => item.user_id === userId)!;
        found.role = body.role;
        return this.json(found);
      }
      this.shares = this.shares.filter((item) => item.user_id !== userId);
      return new Response(null, { status: 204 });
    }
    // Watch/unwatch (milestone 3.3a, D-129): unlike every other opportunity-
    // scoped route in this fake, existence of `segments[1]` in
    // `this.opportunities` is never checked -- the real endpoint's whole
    // point is answering someone with no share on it at all.
    if (segments[2] === "watch") {
      const opportunityId = Number(segments[1]);
      if (method === "POST") {
        this.watching.add(opportunityId);
      } else if (method === "DELETE") {
        this.watching.delete(opportunityId);
      }
      return this.json({ watching: this.watching.has(opportunityId) });
    }
    if (segments[2] === "watchers") {
      return this.page(this.watchers, path);
    }
    if (segments[2] === "ai") {
      return this.json({
        answer: `Answer to: ${body.question}`,
        referenced_entry_numbers: [1],
      });
    }
    if (segments[0] === "timeline") {
      const entryId = Number(segments[1]);
      if (segments[2] === "versions") {
        if (segments[4] === "restore") {
          return this.restoreVersion(
            this.versions.entries,
            entryId,
            Number(segments[3]),
            (version) => {
              const entry = this.entries.find((item) => item.id === entryId)!;
              Object.assign(entry, {
                type: version.type,
                title: version.title,
                body: version.body,
                event_timestamp: version.event_timestamp,
                follow_up_date: version.follow_up_date,
              });
              this.recordVersion(
                this.versions.entries,
                entryId,
                this.entrySnapshot(entry),
              );
              return entry;
            },
          );
        }
        return this.page(this.versions.entries.get(entryId) ?? [], path);
      }
      if (segments[2] === "notes") {
        const entry = this.entries.find((item) => item.id === entryId)!;
        const created = aNote({
          id: this.nextId++,
          entry_id: entryId,
          body: body.body,
        });
        entry.notes.push(created);
        this.recordVersion(
          this.versions.notes,
          created.id,
          this.noteSnapshot(created),
        );
        return this.json(created, 201);
      }
      if (method === "PATCH") {
        const entry = this.entries.find((item) => item.id === entryId)!;
        if (!this.versions.entries.has(entryId)) {
          this.recordVersion(
            this.versions.entries,
            entryId,
            this.entrySnapshot(entry),
          );
        }
        Object.assign(entry, body);
        this.recordVersion(
          this.versions.entries,
          entryId,
          this.entrySnapshot(entry),
        );
        return this.json(entry);
      }
      const index = this.entries.findIndex((item) => item.id === entryId);
      this.deleted.entries.set(entryId, { index, item: this.entries[index] });
      this.entries = this.entries.filter((item) => item.id !== entryId);
      return new Response(null, { status: 204 });
    }
    if (segments[0] === "notes") {
      const noteId = Number(segments[1]);
      if (segments[2] === "versions") {
        if (segments[4] === "restore") {
          return this.restoreVersion(
            this.versions.notes,
            noteId,
            Number(segments[3]),
            (version) => {
              const restored = this.entries
                .flatMap((entry) => entry.notes)
                .find((item) => item.id === noteId)!;
              restored.body = version.body;
              restored.edited = true;
              this.recordVersion(
                this.versions.notes,
                noteId,
                this.noteSnapshot(restored),
              );
              return restored;
            },
          );
        }
        return this.page(this.versions.notes.get(noteId) ?? [], path);
      }
      const owner = this.entries.find((entry) =>
        entry.notes.some((note) => note.id === noteId),
      )!;
      const note = owner.notes.find((item) => item.id === noteId)!;
      if (segments[2] === "comments") {
        const created = aComment({
          id: this.nextId++,
          note_id: noteId,
          parent_id: body.parent_id ?? null,
          body: body.body,
          created_by: this.user?.id ?? ALEX.id,
          author_name: this.user?.name ?? ALEX.name,
        });
        // A reply lands under the thread it names; anything else opens one
        // (milestone 3.3). The one-level rule is the server's, so the fake
        // never has to look deeper than a root's own replies.
        const parent = note.comments.find(
          (thread) => thread.id === created.parent_id,
        );
        if (parent) {
          parent.replies.push(created);
        } else {
          note.comments.push(created);
        }
        return this.json(created, 201);
      }
      if (method === "PATCH") {
        // ADR 0003's edit guard (milestone 3.4). The fake enforces it rather
        // than accepting any PATCH, so "two people edited the same note" is a
        // real path through the app and not a canned `failures` entry that
        // would pass whatever the client sends.
        if (body.updated_at !== note.updated_at) {
          return this.json(
            {
              error: {
                code: "conflict",
                message: "This note has changed since you opened it.",
              },
            },
            409,
          );
        }
        if (!this.versions.notes.has(noteId)) {
          this.recordVersion(
            this.versions.notes,
            noteId,
            this.noteSnapshot(note),
          );
        }
        note.body = body.body;
        note.edited = true;
        // Moves on every accepted write, the way the server's does: the next
        // edit has to echo this one back.
        note.updated_at = this.nextTimestamp();
        this.recordVersion(
          this.versions.notes,
          noteId,
          this.noteSnapshot(note),
        );
        return this.json(note);
      }
      this.deleted.notes.set(noteId, {
        index: owner.notes.indexOf(note),
        entryId: owner.id,
        item: note,
      });
      owner.notes = owner.notes.filter((item) => item.id !== noteId);
      return new Response(null, { status: 204 });
    }
    if (segments[0] === "comments") {
      const commentId = Number(segments[1]);
      if (segments[2] === "resolve" || segments[2] === "unresolve") {
        const resolved = segments[2] === "resolve";
        for (const entry of this.entries) {
          for (const note of entry.notes) {
            const thread = note.comments.find((item) => item.id === commentId);
            if (thread) {
              thread.resolved_at = resolved ? "2026-09-02T15:00:00Z" : null;
              thread.resolved_by = resolved ? (this.user?.id ?? ALEX.id) : null;
              thread.resolved_by_name = resolved
                ? (this.user?.name ?? ALEX.name)
                : null;
              return this.json(thread);
            }
          }
        }
        return this.json(
          { error: { code: "not_found", message: "Comment not found" } },
          404,
        );
      }
      if (segments[2] === "reactions") {
        // A reaction can be on a root or a reply alike (milestone 3.3a), so
        // this looks one level deeper than resolve/unresolve does.
        let target: Comment | undefined;
        for (const entry of this.entries) {
          for (const note of entry.notes) {
            for (const thread of note.comments) {
              if (thread.id === commentId) {
                target = thread;
              }
              const reply = thread.replies.find(
                (item) => item.id === commentId,
              );
              if (reply) {
                target = reply;
              }
            }
          }
        }
        if (!target) {
          return this.json(
            { error: { code: "not_found", message: "Comment not found" } },
            404,
          );
        }
        const userId = this.user?.id ?? ALEX.id;
        const userName = this.user?.name ?? ALEX.name;
        const emoji: string =
          segments[3] !== undefined
            ? decodeURIComponent(segments[3])
            : (body as { emoji: string }).emoji;
        if (method === "POST") {
          if (
            !target.reactions.some(
              (reaction) =>
                reaction.emoji === emoji && reaction.user_id === userId,
            )
          ) {
            target.reactions.push({
              id: this.nextId++,
              comment_id: commentId,
              emoji,
              user_id: userId,
              user_name: userName,
              created_at: "2026-09-02T15:30:00Z",
            });
          }
        } else {
          target.reactions = target.reactions.filter(
            (reaction) =>
              !(reaction.emoji === emoji && reaction.user_id === userId),
          );
        }
        return this.json(target);
      }
      for (const entry of this.entries) {
        for (const note of entry.notes) {
          const found = note.comments.find((item) => item.id === commentId);
          if (found) {
            this.deleted.comments.set(commentId, {
              index: note.comments.indexOf(found),
              noteId: note.id,
              item: found,
            });
          }
          note.comments = note.comments.filter((item) => item.id !== commentId);
          // Deleting a reply leaves its thread alone, exactly as the cascade
          // in `soft_delete.soft_delete_comment` does.
          for (const thread of note.comments) {
            thread.replies = thread.replies.filter(
              (reply) => reply.id !== commentId,
            );
          }
        }
      }
      return new Response(null, { status: 204 });
    }

    return this.json(
      {
        error: {
          code: "internal_error",
          message: `Unhandled in the fake API: ${method} ${path}`,
        },
      },
      500,
    );
  }

  /**
   * The v2 collection envelope, split at `pageSize` when a test asks for it.
   *
   * The cursor is an offset rather than the real route's opaque base64: a
   * client may only echo what it was handed, so what it contains is the
   * server's business and the fake's cursor proves the same walk.
   */
  private page(items: unknown[], path: string): Response {
    if (!this.pageSize) {
      return this.json({ items, next_cursor: null });
    }
    const cursor = new URLSearchParams(path.split("?")[1] ?? "").get("cursor");
    const start = cursor ? Number(cursor) : 0;
    const end = start + this.pageSize;
    return this.json({
      items: items.slice(start, end),
      next_cursor: end < items.length ? String(end) : null,
    });
  }

  private opportunitySnapshot(item: Opportunity): OpportunityVersion {
    return {
      id: this.nextId++,
      opportunity_id: item.id,
      version_number: 0,
      name: item.name,
      account_name: item.account_name,
      value: item.value,
      currency: item.currency,
      stage: item.stage as OpportunityVersion["stage"],
      expected_close_date: item.expected_close_date,
      edited_by: this.user?.id ?? 0,
      editor_name: this.user?.name ?? "Owner",
      created_at: item.updated_at,
    };
  }

  private entrySnapshot(item: TimelineEntry): TimelineEntryVersion {
    return {
      id: this.nextId++,
      entry_id: item.id,
      version_number: 0,
      type: item.type as TimelineEntryVersion["type"],
      title: item.title,
      body: item.body,
      event_timestamp: item.event_timestamp,
      follow_up_date: item.follow_up_date,
      edited_by: this.user?.id ?? 0,
      editor_name: this.user?.name ?? "Owner",
      created_at: item.created_at,
    };
  }

  private noteSnapshot(item: Note): NoteVersion {
    return {
      id: this.nextId++,
      note_id: item.id,
      version_number: 0,
      body: item.body,
      edited_by: this.user?.id ?? 0,
      editor_name: this.user?.name ?? "Owner",
      created_at: item.updated_at,
    };
  }

  /**
   * Putting a recorded version back (milestone 3.1c).
   *
   * Stateful like the rest of this fake: the snapshot is written over the
   * live object and appended as a new version, so a test that restores and
   * then reads the history sees what the server would have answered — the
   * restore recorded as an edit of its own rather than the history rewound.
   */
  private restoreVersion<VersionT extends { version_number: number }>(
    history: Map<number, VersionT[]>,
    id: number,
    versionNumber: number,
    apply: (version: VersionT) => unknown,
  ): Response {
    const version = (history.get(id) ?? []).find(
      (candidate) => candidate.version_number === versionNumber,
    );
    if (!version) {
      return this.notFound("Version not found");
    }
    return this.json(apply(version));
  }

  /** Appends a snapshot as the next version, numbering it like the API does. */
  private recordVersion<VersionT extends { version_number: number }>(
    history: Map<number, VersionT[]>,
    id: number,
    snapshot: VersionT,
  ): void {
    const list = history.get(id) ?? [];
    list.push({ ...snapshot, version_number: list.length + 1 });
    history.set(id, list);
  }

  private notFound(message: string): Response {
    return this.json({ error: { code: "not_found", message } }, 404);
  }

  /**
   * `POST /api/v2/<kind>/{id}/restore`: the row comes back with its id and its
   * place, which is what makes undo an undo rather than a re-create. Restoring
   * something that is not deleted is a 404, as the API answers it.
   */
  private restore(kind: string, id: number): Response {
    const put = <T>(list: T[], index: number, item: T) => {
      list.splice(Math.min(index, list.length), 0, item);
    };

    const opportunity = this.deleted.opportunities.get(id);
    if (kind === "opportunities" && opportunity) {
      put(this.opportunities, opportunity.index, opportunity.item);
      this.deleted.opportunities.delete(id);
      return new Response(null, { status: 204 });
    }

    const task = this.deletedTasks.get(id);
    if (kind === "tasks" && task) {
      this.tasks.push(task);
      this.deletedTasks.delete(id);
      return new Response(null, { status: 204 });
    }

    const entry = this.deleted.entries.get(id);
    if (kind === "timeline" && entry) {
      put(this.entries, entry.index, entry.item);
      this.deleted.entries.delete(id);
      return new Response(null, { status: 204 });
    }

    const note = this.deleted.notes.get(id);
    if (kind === "notes" && note) {
      const owner = this.entries.find((item) => item.id === note.entryId);
      if (owner) {
        put(owner.notes, note.index, note.item);
        this.deleted.notes.delete(id);
        return new Response(null, { status: 204 });
      }
    }

    const comment = this.deleted.comments.get(id);
    if (kind === "comments" && comment) {
      const owner = this.entries
        .flatMap((item) => item.notes)
        .find((item) => item.id === comment.noteId);
      if (owner) {
        put(owner.comments, comment.index, comment.item);
        this.deleted.comments.delete(id);
        return new Response(null, { status: 204 });
      }
    }

    return this.json(
      { error: { code: "not_found", message: "Nothing to restore" } },
      404,
    );
  }

  /**
   * `POST /api/v2/opportunities/bulk`: one id at a time, like the real route
   * (`backend/app/routes_opportunities.py`) — an id that does not exist or
   * that the caller does not own fails on its own, and the rest still apply.
   */
  private bulkOpportunityAction(body: {
    ids: number[];
    action: "delete" | "set_stage" | "assign_owner" | "add_to_view";
    stage?: string;
    new_owner_email?: string;
    view_id?: number;
  }): Response {
    // The two failures that are about the request rather than about one id,
    // raised before anything is applied (milestone 3.0a).
    const newOwner = [ALEX, BLAIR].find(
      (person) => person.email === body.new_owner_email,
    );
    if (body.action === "assign_owner" && !newOwner) {
      return this.notFound("User with that email was not found");
    }
    const view = this.savedViews.find((item) => item.id === body.view_id);
    if (
      body.action === "add_to_view" &&
      (!view || view.created_by !== this.user?.id)
    ) {
      return this.notFound("Saved view not found");
    }

    const pinned: number[] = [];
    const results = body.ids.map((id) => {
      const index = this.opportunities.findIndex((item) => item.id === id);
      const found = index === -1 ? undefined : this.opportunities[index];
      if (!found) {
        return { id, status: "error" as const, error: "Opportunity not found" };
      }
      // Pinning writes to the caller's own view rather than to the
      // opportunity, so read access is its whole rule (D-106); everything
      // else here is owner-only.
      if (
        body.action !== "add_to_view" &&
        found.current_user_role !== "owner"
      ) {
        return {
          id,
          status: "error" as const,
          error: "Only the owner can manage this opportunity",
        };
      }
      if (body.action === "delete") {
        this.deleted.opportunities.set(id, { index, item: found });
        this.opportunities = this.opportunities.filter(
          (item) => item.id !== id,
        );
      } else if (body.action === "set_stage") {
        found.stage = body.stage ?? found.stage;
      } else if (body.action === "assign_owner") {
        if (found.owner_id === newOwner!.id) {
          return {
            id,
            status: "error" as const,
            error: "Opportunity is already owned by that user",
          };
        }
        found.owner_id = newOwner!.id;
        found.owner_name = newOwner!.name;
        found.current_user_role = "editor";
      } else {
        pinned.push(id);
      }
      return { id, status: "ok" as const, error: null };
    });

    if (view && pinned.length > 0) {
      const existing = String(view.filters.ids ?? "")
        .split(",")
        .filter(Boolean)
        .map(Number);
      view.filters = {
        ...view.filters,
        ids: [
          ...existing,
          ...pinned.filter((id) => !existing.includes(id)),
        ].join(","),
      };
    }
    return this.json({ results });
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

  /**
   * `GET /api/v2/timeline/follow-ups`: every entry across every opportunity
   * that has a follow-up date, windowed to `from`/`to` (milestone 3.0b).
   * Derived from `this.entries` rather than held separately, the same way
   * the real endpoint reads `timeline_entries` rather than a table of its
   * own — this fake has one source of truth for an entry's fields too.
   */
  private followUpsPage(path: string): Response {
    const params = new URLSearchParams(path.split("?")[1] ?? "");
    const from = params.get("from");
    const to = params.get("to");

    const items: FollowUp[] = this.entries
      .filter((entry): entry is TimelineEntry & { follow_up_date: string } =>
        Boolean(entry.follow_up_date),
      )
      .filter(
        (entry) =>
          (!from || entry.follow_up_date >= from) &&
          (!to || entry.follow_up_date <= to),
      )
      .sort((a, b) => a.follow_up_date.localeCompare(b.follow_up_date))
      .map((entry) => ({
        id: entry.id,
        opportunity_id: entry.opportunity_id,
        opportunity_name:
          this.opportunities.find(
            (opportunity) => opportunity.id === entry.opportunity_id,
          )?.name ?? "",
        type: entry.type,
        title: entry.title,
        follow_up_date: entry.follow_up_date,
        created_by: entry.created_by,
        author_name: entry.author_name,
      }));

    return this.page(items, path);
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
