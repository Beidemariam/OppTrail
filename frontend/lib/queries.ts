/**
 * Every server read and write the app makes, expressed against the TanStack
 * Query cache (ADR 0005, milestone 2.1).
 *
 * `app/Home.tsx` used to hold the same calls as "await the write, then refetch
 * everything into component state". Collecting them here means a view declares
 * what it needs, a write declares what it invalidates, and no component copies
 * a response into `useState` where it can go stale.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import type { ActivityEditTarget, ActivityEvent } from "./activity";
import { apiRequest } from "./api";
import type { components } from "./api-types";
import type {
  AiChatMessage,
  AppNotification,
  CustomField,
  CustomFieldCreate,
  Dashboard,
  CustomFieldEntity,
  CustomFieldUpdate,
  NoteVersion,
  Opportunity,
  OpportunityFieldPatch,
  OpportunityMember,
  OpportunityShare,
  OpportunityVersion,
  ReactionEmoji,
  SavedView,
  SavedViewEntity,
  ShareRole,
  Task,
  TaskVersion,
  TimelineEntry,
  TimelineEntryVersion,
  TimelineFilters,
  User,
  Watcher,
} from "./domain";
import { localInputToUtc } from "./time";

type AuthResponse = components["schemas"]["AuthResponse"];
type NotificationPage = components["schemas"]["Page_NotificationPublic_"];
type AiAskResponse = components["schemas"]["AiAskResponse"];
type SavedViewPage = components["schemas"]["Page_SavedViewPublic_"];
type SavedViewCreate = components["schemas"]["SavedViewCreate"];
type SavedViewUpdate = components["schemas"]["SavedViewUpdate"];
type WatchStatus = components["schemas"]["WatchStatus"];

const NOTIFICATION_PAGE_SIZE = 50;
const SAVED_VIEW_PAGE_SIZE = 100;
/** `MAX_LIMIT` in `backend/app/pagination.py`: the largest page it will serve. */
const MAX_PAGE_SIZE = 200;

/**
 * The v2 envelope with its item type left open. Every generated
 * `Page_<Model>_` matches it; `fetchAll` is generic over the item, so it
 * cannot name one of them.
 */
type PageOf<ItemT> = { items: ItemT[]; next_cursor?: string | null };

/**
 * Every page of a v2 collection, walked to the end (milestone 2.9, D-093).
 *
 * `/api/v2` paginates every collection read, and four of this app's reads want
 * the whole set rather than a window: the board derives its keyboard cursor,
 * its bulk selection and the calendar's month from the complete filtered list
 * (`applyOpportunityView`), and a timeline, a share list and an audit log are
 * each read start to finish. So the cursor is followed here rather than being
 * pushed into the views — what a component asks for is unchanged from v1, and
 * at the 400-opportunity scale milestone 2.3 was written for this is two or
 * three requests, not one per row.
 *
 * `next_cursor` is null on the last page, so the loop ends on the server's
 * answer rather than on a count the client compares for itself.
 */
async function fetchAll<ItemT>(path: string): Promise<ItemT[]> {
  const separator = path.includes("?") ? "&" : "?";
  const items: ItemT[] = [];
  let cursor: string | null | undefined = null;

  do {
    const query: string = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
    const page: PageOf<ItemT> = await apiRequest<PageOf<ItemT>>(
      `${path}${separator}limit=${MAX_PAGE_SIZE}${query}`,
    );
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);

  return items;
}

export const keys = {
  session: ["session"] as const,
  opportunities: ["opportunities"] as const,
  timeline: (opportunityId: number, filters: TimelineFilters) =>
    ["timeline", opportunityId, filters] as const,
  /** Every page of every opportunity's timeline, for a write to invalidate. */
  allTimelines: ["timeline"] as const,
  shares: (opportunityId: number) => ["shares", opportunityId] as const,
  /** Who is on one opportunity, for the mention autocomplete (milestone 3.2).
   * Separate from `shares` because it is a different read with a different
   * rule: the owner is a row, and every role may ask. */
  members: (opportunityId: number) => ["members", opportunityId] as const,
  /** Every opportunity's member list, for a write that changes who has
   * access without knowing which lists are open — a bulk `assign_owner`
   * (3.0a) changes the owner row of each id it touched. */
  allMembers: ["members"] as const,
  notifications: ["notifications"] as const,
  /**
   * One item's edit history (milestone 2.10), keyed by what kind of thing it
   * hangs off as well as by id: the three id spaces are separate tables.
   */
  versions: (kind: "opportunity" | "entry" | "note" | "task", id: number) =>
    ["versions", kind, id] as const,
  /**
   * Every history, for a write to invalidate. An edit appends a version to
   * exactly one of them, and the mutation that made it knows its own id — but
   * a stage change from the board, a bulk move and the entry form all write
   * through different hooks, so one prefix is what keeps an open dialog
   * honest without each of them naming a key.
   */
  allVersions: ["versions"] as const,
  /** Every entity's saved views, for a write that does not know which
   * entity it touched — `add_to_view` sends a view id and nothing else
   * (milestone 3.0a). */
  allSavedViews: ["saved-views"] as const,
  /** One opportunity's merged activity log (milestone 3.0). */
  activity: (opportunityId: number) => ["activity", opportunityId] as const,
  /**
   * Every opportunity's activity log, and since milestone 3.1c the only
   * place those rows are read: the feed merges the system entries, the audit
   * rows and the version rows (`backend/app/activity.py`), so every write
   * that touches one of the three invalidates this. A delete knows its own
   * id rather than which opportunity it hung under, which is why the prefix
   * is invalidated rather than one key.
   */
  allActivity: ["activity"] as const,
  /** One month of the calendar's task layer (milestone 3.0b as follow-ups,
   * milestone 4.2 as tasks), keyed by the `from`/`to` range the grid draws so
   * switching months costs a request and switching back is cached. */
  tasksDue: (from: string, to: string) => ["tasks-due", from, to] as const,
  aiConversation: (opportunityId: number) =>
    ["ai-conversation", opportunityId] as const,
  savedViews: (entity: SavedViewEntity) => ["saved-views", entity] as const,
  /** The custom field definitions for one entity type (milestone 6.1).
   * Keyed by entity rather than read whole, because the two sets are drawn by
   * different screens -- the table and the entry form -- and neither needs
   * the other's. */
  customFields: (entity: CustomFieldEntity) =>
    ["custom-fields", entity] as const,
  /** The six aggregations (milestone 6.2), keyed by the window they were
   * asked for: a different period is a different answer, not a refetch. */
  dashboard: (since: string, weeks: number) =>
    ["dashboard", since, weeks] as const,
  /** Whether the caller is watching one opportunity (milestone 3.3a) --
   * separate from `shares` because it needs no access to read: watching is
   * available with no share at all (D-129). */
  watch: (opportunityId: number) => ["watch", opportunityId] as const,
  /** Who is watching, owner-only (milestone 3.3a). */
  watchers: (opportunityId: number) => ["watchers", opportunityId] as const,
  /** One deal's tasks (milestone 4.1). */
  tasks: (opportunityId: number) => ["tasks", opportunityId] as const,
  /** The caller's own assignments across every deal they can see. Keyed apart
   * from one deal's list because it is a different read with a different rule,
   * and `allTasks` covers both when a write does not know which lists are
   * open. */
  myTasks: ["my-tasks"] as const,
  allTasks: ["tasks"] as const,
};

export function timelinePath(
  opportunityId: number,
  filters: TimelineFilters,
): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    params.set(
      key,
      key === "from" || key === "to" ? localInputToUtc(trimmed) : trimmed,
    );
  });

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/v2/opportunities/${opportunityId}/timeline${suffix}`;
}

/**
 * The signed-in user, or `null`.
 *
 * A 401 here is the ordinary signed-out answer rather than a failure worth
 * reporting — the app shows the auth panel either way — so it resolves to
 * `null` instead of rejecting, and every view can branch on the same value.
 */
export function useSession() {
  return useQuery<User | null>({
    queryKey: keys.session,
    queryFn: () =>
      apiRequest<AuthResponse>("/api/v2/auth/me")
        .then((data) => data.user)
        .catch(() => null),
  });
}

export function useOpportunities(enabled: boolean) {
  return useQuery<Opportunity[]>({
    queryKey: keys.opportunities,
    enabled,
    queryFn: () => fetchAll<Opportunity>("/api/v2/opportunities"),
  });
}

export function useTimeline(opportunityId: number, filters: TimelineFilters) {
  return useQuery<TimelineEntry[]>({
    queryKey: keys.timeline(opportunityId, filters),
    queryFn: () =>
      fetchAll<TimelineEntry>(timelinePath(opportunityId, filters)),
  });
}

export function useShares(opportunityId: number, enabled: boolean) {
  return useQuery<OpportunityShare[]>({
    queryKey: keys.shares(opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<OpportunityShare>(
        `/api/v2/opportunities/${opportunityId}/shares`,
      ),
  });
}

/**
 * Whether the caller is watching this opportunity (milestone 3.3a).
 *
 * Reads `require_opportunity_exists` rather than `require_opportunity_access`
 * on the server (D-129), so it succeeds even where `useShares` above would
 * 404 -- which is what lets `OpportunityPanel` offer a Watch toggle on the
 * "not available" screen for a deal the reader has no share on at all.
 */
export function useWatchStatus(opportunityId: number, enabled: boolean) {
  return useQuery<WatchStatus>({
    queryKey: keys.watch(opportunityId),
    enabled,
    queryFn: () =>
      apiRequest<WatchStatus>(`/api/v2/opportunities/${opportunityId}/watch`),
  });
}

/** Who is following this opportunity, owner-only (milestone 3.3a) -- the
 * same visibility rule as `useShares`. */
export function useWatchers(opportunityId: number, enabled: boolean) {
  return useQuery<Watcher[]>({
    queryKey: keys.watchers(opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<Watcher>(`/api/v2/opportunities/${opportunityId}/watchers`),
  });
}

/**
 * Follow or unfollow (milestone 3.3a). One mutation with a `watching` flag,
 * like `useSetReaction` above -- both directions are idempotent on the
 * server, and the response is the resulting state.
 */
export function useSetWatch(opportunityId: number) {
  const client = useQueryClient();
  return useMutation<WatchStatus, Error, boolean>({
    mutationFn: (watching) =>
      apiRequest(`/api/v2/opportunities/${opportunityId}/watch`, {
        method: watching ? "POST" : "DELETE",
      }),
    onSuccess: () =>
      invalidate(
        client,
        keys.watch(opportunityId),
        keys.watchers(opportunityId),
      ),
  });
}

/**
 * Everyone a mention on this opportunity would reach (milestone 3.2, D-123):
 * the owner and every share, which is what the `@` trigger offers.
 *
 * Read for every role, unlike `useShares` beside it, and read whole — a deal
 * has a handful of participants, and the autocomplete filters the list in the
 * client as the reader types rather than asking the server per keystroke.
 */
export function useMembers(opportunityId: number) {
  return useQuery<OpportunityMember[]>({
    queryKey: keys.members(opportunityId),
    queryFn: () =>
      fetchAll<OpportunityMember>(
        `/api/v2/opportunities/${opportunityId}/members`,
      ),
  });
}

/**
 * The merged activity log for one opportunity (milestone 3.0, D-101).
 *
 * Read whole, like the audit log beside it: the feed is a narrative and the
 * dialog that shows it scrolls rather than paging. `enabled` is the dialog
 * being open, so a timeline costs no request until someone asks what
 * happened.
 *
 * **Newest first** since milestone 3.8, and reversed here rather than in the
 * query: the timeline beside it defaults to newest-first (D-137), so a reader
 * met the two histories of one deal disagreeing about which end was the
 * present. The route stays oldest-first — it is keyset-paginated, and
 * `AGENTS.md`'s audit log is oldest-first for the same forensic reason a log
 * file is — so the change is one `reverse()` over a list `fetchAll` has
 * already read to its last page. Reversing the five merged keyset queries
 * instead would mean reversing each comparison as well as each `ORDER BY`,
 * for a feed that is never read a page at a time.
 */
export function useActivity(opportunityId: number, enabled: boolean) {
  return useQuery<ActivityEvent[]>({
    queryKey: keys.activity(opportunityId),
    enabled,
    queryFn: async () => {
      const events = await fetchAll<ActivityEvent>(
        `/api/v2/opportunities/${opportunityId}/activity`,
      );
      return events.reverse();
    },
  });
}

/**
 * The calendar's follow-up layer (milestone 3.0b, D-088), for the month on
 * screen — `enabled` is the calendar view being on screen, so switching to
 * the board or the table costs no request for a layer nothing is drawing.
 */
export function useTasksDueIn(from: string, to: string, enabled: boolean) {
  return useQuery<Task[]>({
    queryKey: keys.tasksDue(from, to),
    enabled,
    queryFn: () =>
      fetchAll<Task>(
        // `assignee=any`, because the layer this replaced drew every
        // accessible entry's follow-up whoever wrote it (3.0b, D-088). Open
        // only, which is the server's default: a calendar of things already
        // done is a calendar nobody reads.
        `/api/v2/tasks?assignee=any&from=${from}&to=${to}`,
      ),
  });
}

/**
 * The three edit histories (milestone 2.10), each read whole and each
 * owner-only on the server — the hooks are called with `enabled` false until
 * the dialog that shows them is opened, so a timeline of forty entries is not
 * forty requests nobody asked for.
 */
export function useOpportunityVersions(
  opportunityId: number,
  enabled: boolean,
) {
  return useQuery<OpportunityVersion[]>({
    queryKey: keys.versions("opportunity", opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<OpportunityVersion>(
        `/api/v2/opportunities/${opportunityId}/versions`,
      ),
  });
}

export function useTimelineEntryVersions(entryId: number, enabled: boolean) {
  return useQuery<TimelineEntryVersion[]>({
    queryKey: keys.versions("entry", entryId),
    enabled,
    queryFn: () =>
      fetchAll<TimelineEntryVersion>(`/api/v2/timeline/${entryId}/versions`),
  });
}

export function useNoteVersions(noteId: number, enabled: boolean) {
  return useQuery<NoteVersion[]>({
    queryKey: keys.versions("note", noteId),
    enabled,
    queryFn: () => fetchAll<NoteVersion>(`/api/v2/notes/${noteId}/versions`),
  });
}

/** A task's edit history (milestone 4.2a), the fourth of the same shape. */
export function useTaskVersions(taskId: number, enabled: boolean) {
  return useQuery<TaskVersion[]>({
    queryKey: keys.versions("task", taskId),
    enabled,
    queryFn: () => fetchAll<TaskVersion>(`/api/v2/tasks/${taskId}/versions`),
  });
}

/**
 * Put a recorded version back as the current one (milestone 3.1c, D-116).
 *
 * The write side of the three reads above, and not the `useRestore*` hooks
 * further down: those clear a `deleted_at`, this one undoes an *edit*. The
 * server writes the old snapshot back and appends a version for having done
 * it, so what comes back is a new current state and a longer history —
 * everything that reads either is invalidated rather than patched in place.
 */
export function useRestoreVersion(
  target: ActivityEditTarget,
  targetId: number,
) {
  const client = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (versionNumber: number) =>
      apiRequest(`${versionPath(target, targetId)}/${versionNumber}/restore`, {
        method: "POST",
      }),
    onSuccess: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allVersions,
        keys.allActivity,
        // A restored task changes both task reads; the other three targets are
        // unaffected by these keys, and an extra invalidation is cheaper than a
        // per-target branch (ADR 0003's "broader, never narrower" applied to the
        // cache rather than to an event).
        keys.allTasks,
        keys.myTasks,
      ),
  });
}

function versionPath(target: ActivityEditTarget, targetId: number): string {
  if (target === "opportunity") {
    return `/api/v2/opportunities/${targetId}/versions`;
  }
  if (target === "timeline_entry") {
    return `/api/v2/timeline/${targetId}/versions`;
  }
  // Tasks since milestone 4.2a, which is the fourth of these and the reason the
  // chain is an `if` ladder rather than a ternary pair.
  return target === "task"
    ? `/api/v2/tasks/${targetId}/versions`
    : `/api/v2/notes/${targetId}/versions`;
}

/**
 * The saved views a caller may apply to one entity's URL state: their own,
 * plus anyone's shared ones (`backend/app/routes_saved_views.py`).
 */
export function useSavedViews(entity: SavedViewEntity) {
  return useQuery<SavedView[]>({
    queryKey: keys.savedViews(entity),
    queryFn: () =>
      apiRequest<SavedViewPage>(
        `/api/v2/saved-views?entity=${entity}&limit=${SAVED_VIEW_PAGE_SIZE}`,
      ).then((page) => page.items),
  });
}

export function useCreateSavedView() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: SavedViewCreate) =>
      apiRequest<SavedView>("/api/v2/saved-views", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (created) => invalidate(client, keys.savedViews(created.entity)),
  });
}

/**
 * Rename a saved view, or change who can use it and whether it opens by
 * default (milestone 2.13). The manage dialog is the only caller: editing a
 * view is a deliberate act taken from one place, not a control beside every
 * name (`AGENTS.md`'s Design bar).
 */
export function useUpdateSavedView(entity: SavedViewEntity) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: SavedViewUpdate & { id: number }) =>
      apiRequest<SavedView>(`/api/v2/saved-views/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidate(client, keys.savedViews(entity)),
  });
}

export function useDeleteSavedView(entity: SavedViewEntity) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (viewId: number) =>
      apiRequest(`/api/v2/saved-views/${viewId}`, { method: "DELETE" }),
    onSuccess: () => invalidate(client, keys.savedViews(entity)),
  });
}

/**
 * The live custom field definitions for one entity type (milestone 6.1,
 * ADR 0006).
 *
 * Read whole through `fetchAll`, like the members list: a deployment has a
 * handful of fields, every one of them is drawn at once as a column, a filter
 * or a form input, and a window of them would mean a table whose columns
 * depend on how far somebody scrolled. Archived definitions are excluded by
 * the route, which is what makes archiving take effect everywhere at once.
 */
export function useCustomFields(entity: CustomFieldEntity, enabled = true) {
  return useQuery<CustomField[]>({
    queryKey: keys.customFields(entity),
    enabled,
    queryFn: () =>
      fetchAll<CustomField>(`/api/v2/custom-fields?entity_type=${entity}`),
  });
}

/**
 * Every definition including the archived ones, for the screen that manages
 * them -- which is the one place an archived field has to be visible, because
 * it is where it gets restored.
 */
export function useAllCustomFields(enabled = true) {
  return useQuery<CustomField[]>({
    queryKey: [...keys.customFields("opportunity"), "all"],
    enabled,
    queryFn: () =>
      fetchAll<CustomField>("/api/v2/custom-fields?include_archived=true"),
  });
}

/** Invalidates both entity sets and the manage screen's list: a definition
 * write changes what every column, filter and form may offer. */
function invalidateCustomFields(client: ReturnType<typeof useQueryClient>) {
  invalidate(client, ["custom-fields"]);
  // A field's values appear on the records themselves, and `visible_values`
  // decides which keys a read returns -- so archiving one changes every
  // opportunity and timeline payload too, not just the definition list.
  invalidate(client, keys.opportunities);
  invalidate(client, keys.allTimelines);
}

export function useCreateCustomField() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomFieldCreate) =>
      apiRequest<CustomField>("/api/v2/custom-fields", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidateCustomFields(client),
  });
}

export function useUpdateCustomField() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: CustomFieldUpdate & { id: number }) =>
      apiRequest<CustomField>(`/api/v2/custom-fields/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidateCustomFields(client),
  });
}

/** Archive, or put one back. Two routes, one hook: the manage screen offers
 * whichever the row's state calls for, and both answer with the row. */
export function useArchiveCustomField() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, archived }: { id: number; archived: boolean }) =>
      apiRequest<CustomField>(
        `/api/v2/custom-fields/${id}/${archived ? "restore" : "archive"}`,
        { method: "POST" },
      ),
    onSuccess: () => invalidateCustomFields(client),
  });
}

/**
 * The dashboard's six aggregations (milestone 6.2, `docs/FEATURES.md` §10).
 *
 * One request, not six: a dashboard draws them together, and six round trips
 * would make the slowest metric the whole screen's latency. Not read through
 * `fetchAll` either -- this is the one read in the app that is not a
 * collection, so there is no cursor to walk.
 */
export function useDashboard(since = "", weeks = 8, enabled = true) {
  return useQuery<Dashboard>({
    queryKey: keys.dashboard(since, weeks),
    enabled,
    queryFn: () => {
      const params = new URLSearchParams({ weeks: String(weeks) });
      if (since) {
        params.set("since", since);
      }
      return apiRequest<Dashboard>(`/api/v2/dashboard?${params}`);
    },
  });
}

export function useNotifications(enabled: boolean) {
  return useQuery<AppNotification[]>({
    queryKey: keys.notifications,
    enabled,
    queryFn: () =>
      apiRequest<NotificationPage>(
        `/api/v2/notifications?limit=${NOTIFICATION_PAGE_SIZE}`,
      ).then((page) => page.items),
  });
}

/**
 * The AI transcript for one opportunity.
 *
 * It is held in the cache rather than in the panel's own state because the
 * panel unmounts when the reader opens another opportunity, and a conversation
 * they can walk back to by returning is the behaviour this app already had.
 * Nothing fetches it: the mutation below appends each turn.
 */
export function useAiConversation(opportunityId: number) {
  return useQuery<AiChatMessage[]>({
    queryKey: keys.aiConversation(opportunityId),
    queryFn: () => [],
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

function dropEverythingButTheSession(client: QueryClient) {
  client.removeQueries({
    predicate: (query) => query.queryKey[0] !== keys.session[0],
  });
}

function invalidate(
  client: QueryClient,
  ...queryKeys: readonly (readonly unknown[])[]
) {
  return Promise.all(
    queryKeys.map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

/**
 * Optimistic updates (milestone 2.4b). `docs/UX.md`: "Every mutation applies
 * immediately, reconciles on response, and rolls back with an explanatory
 * toast on failure."
 *
 * A snapshot is every affected cache entry as it was, which `onError` writes
 * back. The timeline has one entry per filter set, all of them stale after a
 * write, so the snapshot is a list rather than a single value.
 */
type Snapshot = readonly (readonly [readonly unknown[], unknown])[];

function rollback(client: QueryClient, snapshot: Snapshot | undefined) {
  snapshot?.forEach(([queryKey, data]) => client.setQueryData(queryKey, data));
}

/**
 * Applies an edit to every cached timeline, whatever filters it was fetched
 * under, and returns what they held before.
 *
 * In-flight fetches are cancelled first: one that resolves after this would
 * overwrite the optimistic state with the server's pre-write answer.
 */
async function optimisticTimelines(
  client: QueryClient,
  update: (entries: TimelineEntry[]) => TimelineEntry[],
): Promise<Snapshot> {
  await client.cancelQueries({ queryKey: keys.allTimelines });
  const snapshot = client.getQueriesData<TimelineEntry[]>({
    queryKey: keys.allTimelines,
  });
  client.setQueriesData<TimelineEntry[]>(
    { queryKey: keys.allTimelines },
    (entries) => (entries ? update(entries) : entries),
  );
  return snapshot;
}

/** The same, for the one cached opportunity list. */
async function optimisticOpportunities(
  client: QueryClient,
  update: (opportunities: Opportunity[]) => Opportunity[],
): Promise<Snapshot> {
  await client.cancelQueries({ queryKey: keys.opportunities });
  const previous = client.getQueryData<Opportunity[]>(keys.opportunities);
  client.setQueryData<Opportunity[]>(keys.opportunities, (opportunities) =>
    opportunities ? update(opportunities) : opportunities,
  );
  return [[keys.opportunities, previous]];
}

/** The same for an entry's files (milestone 4.3), so an optimistic delete
 * reaches them wherever the entry sits. */
function mapAttachments(
  entries: TimelineEntry[],
  update: (
    attachments: TimelineEntry["attachments"],
  ) => TimelineEntry["attachments"],
): TimelineEntry[] {
  return entries.map((entry) => ({
    ...entry,
    attachments: update(entry.attachments),
  }));
}

/** Every note in a timeline, wherever it hangs, through one function. */
function mapNotes(
  entries: TimelineEntry[],
  update: (notes: TimelineEntry["notes"]) => TimelineEntry["notes"],
): TimelineEntry[] {
  return entries.map((entry) => ({ ...entry, notes: update(entry.notes) }));
}

export interface Credentials {
  mode: "login" | "signup";
  email: string;
  password: string;
  name: string;
}

export function useAuthenticate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, email, password, name }: Credentials) =>
      apiRequest<AuthResponse>(`/api/v2/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(
          mode === "signup" ? { email, password, name } : { email, password },
        ),
      }),
    onSuccess: (data) => {
      // Whatever a previous session left behind is dropped here rather than on
      // the way out: at this moment only the auth panel is mounted, so no
      // observer is watching those keys and removing them cannot start a
      // refetch. Seeding the session afterwards is what mounts the dashboard,
      // which then fetches its own data.
      dropEverythingButTheSession(client);
      client.setQueryData(keys.session, data.user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest("/api/v2/auth/logout", { method: "POST" }),
    // Only the session is written here. The rest of the cache still has
    // mounted readers for one more render, and removing it under them asks the
    // API for data the user has just stopped being allowed to see; the next
    // sign-in drops it instead, before anything can read it.
    onSuccess: () => client.setQueryData(keys.session, null),
  });
}

export interface OpportunityPayload {
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  expected_close_date: string | null;
}

export function useSaveOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number | null;
      payload: OpportunityPayload;
    }) =>
      apiRequest<Opportunity>(
        id ? `/api/v2/opportunities/${id}` : "/api/v2/opportunities",
        { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) },
      ),
    // A stage change writes a system timeline entry, so the timeline is stale
    // too (`backend/app/routes_opportunities.py`), and every field this sends
    // is versioned (milestone 2.10).
    onSuccess: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allVersions,
        keys.allActivity,
      ),
  });
}

/**
 * One field of one opportunity, changed where it is read.
 *
 * Every partial write to an opportunity goes through here: dragging a card to
 * another stage column and the two keyboard paths that do the same thing
 * (milestone 2.7 — the card's move-to-stage select and the `[`/`]` chords),
 * and since milestone 2.11 the inline editors on the table cells and the
 * opportunity's own heading. A partial `PATCH` rather than the whole form
 * `useSaveOpportunity` sends: the route updates exactly the fields it is
 * given (`backend/app/routes_opportunities.py`), so one edited field is one
 * key and nothing the reader did not touch is rewritten.
 *
 * Optimistic, because the cache holds the row and none of these fields is the
 * server's to decide; the server's own consequences — the `stage_change`
 * system timeline entry, the new version, `updated_at`, the stalled flag —
 * are not guessed and arrive with the invalidation.
 */
export function useEditOpportunity() {
  const client = useQueryClient();
  return useMutation<
    Opportunity,
    Error,
    { id: number; fields: OpportunityFieldPatch },
    Snapshot
  >({
    mutationFn: ({ id, fields }) =>
      apiRequest<Opportunity>(`/api/v2/opportunities/${id}`, {
        method: "PATCH",
        body: JSON.stringify(fields),
      }),
    onMutate: ({ id, fields }) =>
      optimisticOpportunities(client, (opportunities) =>
        opportunities.map((opportunity) =>
          opportunity.id === id ? { ...opportunity, ...fields } : opportunity,
        ),
      ),
    onError: (_error, _variables, snapshot) => rollback(client, snapshot),
    onSettled: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allVersions,
        keys.allActivity,
      ),
  });
}

export function useDeleteOpportunity() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (opportunityId: number) =>
      apiRequest(`/api/v2/opportunities/${opportunityId}`, {
        method: "DELETE",
      }),
    onMutate: (opportunityId) =>
      optimisticOpportunities(client, (opportunities) =>
        opportunities.filter((opportunity) => opportunity.id !== opportunityId),
      ),
    onError: (_error, _opportunityId, snapshot) => rollback(client, snapshot),
    onSettled: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allActivity,
      ),
  });
}

/**
 * Undo, for each of the four things that can be deleted.
 *
 * Nothing here is optimistic — what comes back is a server-side cascade
 * (which notes did that delete take?), so the answer is fetched rather than
 * guessed.
 */
function useRestore(
  path: (id: number) => string,
  ...invalidated: readonly (readonly unknown[])[]
): UseMutationResult<unknown, Error, number> {
  const client = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (id: number) => apiRequest(path(id), { method: "POST" }),
    onSuccess: () => invalidate(client, ...invalidated),
  });
}

export function useRestoreOpportunity() {
  return useRestore(
    (id) => `/api/v2/opportunities/${id}/restore`,
    keys.opportunities,
    keys.allTimelines,
    keys.allActivity,
  );
}

export function useRestoreTimelineEntry() {
  return useRestore(
    (id) => `/api/v2/timeline/${id}/restore`,
    keys.allTimelines,
    keys.opportunities,
    keys.allActivity,
  );
}

export function useRestoreNote() {
  return useRestore(
    (id) => `/api/v2/notes/${id}/restore`,
    keys.allTimelines,
    keys.allActivity,
  );
}

export function useRestoreComment() {
  return useRestore(
    (id) => `/api/v2/comments/${id}/restore`,
    keys.allTimelines,
    keys.allActivity,
  );
}

/* ---------------------------------------------------------------------------
 * Attachments (milestone 4.3, `docs/FEATURES.md` §6)
 *
 * An entry's files arrive with the entry (`TimelineEntry["attachments"]`), so
 * there is no read here — only the three writes, and all three invalidate the
 * timeline the files are drawn in. The download is not a request this layer
 * makes at all: it is a plain link, like the three export links, because a
 * file the browser saves has nothing to put in a cache.
 * ------------------------------------------------------------------------- */

/** Where the browser fetches one attachment's bytes. A link, not a hook: the
 * response is a download (`Content-Disposition: attachment`), so routing it
 * through `apiRequest` would buffer a file nothing renders. */
export function attachmentDownloadPath(attachmentId: number): string {
  return `/api/v2/attachments/${attachmentId}/download`;
}

/**
 * Attaching a file.
 *
 * `FormData` rather than JSON, which is the one request in the app that is not
 * JSON — `lib/api.ts` leaves the content type to the browser for exactly this
 * body, because a multipart boundary is the browser's to generate. Not
 * optimistic: the server decides the file's sniffed type, its size and whether
 * it is allowed at all, so there is nothing truthful to draw until it answers
 * (D-068's rule for creates).
 */
export function useUploadAttachment() {
  return useTimelineWrite(
    ({ entryId, file }: { entryId: number; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      return apiRequest(`/api/v2/timeline/${entryId}/attachments`, {
        method: "POST",
        body,
      });
    },
  );
}

/**
 * Removing one, optimistically — the cache already holds the row that
 * disappears, which is the test 2.4b sets for applying a delete immediately.
 * Paired with `useRestoreAttachment` through `useUndoableDelete`, so there is
 * no confirmation: the toast is the way back.
 */
export function useDeleteAttachment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (attachmentId: number) =>
      apiRequest(`/api/v2/attachments/${attachmentId}`, { method: "DELETE" }),
    onMutate: (attachmentId) =>
      optimisticTimelines(client, (entries) =>
        mapAttachments(entries, (attachments) =>
          attachments.filter((attachment) => attachment.id !== attachmentId),
        ),
      ),
    onError: (_error, _attachmentId, snapshot) => rollback(client, snapshot),
    // An audit row, so the activity log is stale too — the rule every other
    // delete here follows.
    onSettled: () => invalidate(client, keys.allTimelines, keys.allActivity),
  });
}

export function useRestoreAttachment() {
  return useRestore(
    (id) => `/api/v2/attachments/${id}/restore`,
    keys.allTimelines,
    keys.allActivity,
  );
}

/* ---------------------------------------------------------------------------
 * Tasks (milestone 4.1, `docs/FEATURES.md` §8)
 *
 * Reads are whole rather than windowed, like the activity log's: a deal has a
 * handful of open action items and My Tasks is a to-do list, not an archive.
 * Writes are **not** optimistic, which is a departure from the four deletes and
 * the note edit (2.4b) and deliberate: every task write returns the row it
 * changed — `completed_by_name` is a name the cache does not hold, and an
 * assignee resolved from an email is an id the client never had — so predicting
 * the result would mean inventing values the server is about to supply. The one
 * exception is the delete, which has a row to put back and an Undo to offer.
 * ------------------------------------------------------------------------- */

/** One deal's tasks, soonest first, open and done alike -- the per-opportunity
 * surface shows both and hides the done ones behind a disclosure. */
export function useTasks(opportunityId: number, enabled: boolean) {
  return useQuery<Task[]>({
    queryKey: keys.tasks(opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<Task>(`/api/v2/opportunities/${opportunityId}/tasks`),
  });
}

/**
 * My Tasks: the caller's own assignments, across every deal they can see.
 *
 * `include_completed` is a parameter rather than a filter in the client because
 * the server's default is open-only and that is the useful answer -- a list of
 * everything you have ever finished is not a to-do list. It is part of the key,
 * so switching it is a request and switching back is cached.
 */
export function useMyTasks(includeCompleted = false) {
  return useQuery<Task[]>({
    queryKey: [...keys.myTasks, includeCompleted] as const,
    queryFn: () =>
      fetchAll<Task>(
        `/api/v2/tasks${includeCompleted ? "?include_completed=true" : ""}`,
      ),
  });
}

export interface TaskInput {
  title: string;
  description?: string;
  /** Everyone the task is for (milestone 4.6). Sending `[]` on an edit clears
   * it; leaving the key out leaves the list alone, which is the server's own
   * rule for this field. */
  assignee_emails?: string[];
  due_date?: string | null;
  entry_id?: number | null;
}

export function useCreateTask(opportunityId: number) {
  const client = useQueryClient();
  return useMutation<Task, Error, TaskInput>({
    mutationFn: (input) =>
      apiRequest(`/api/v2/opportunities/${opportunityId}/tasks`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    // `allTasks` rather than this deal's key alone: assigning a task to
    // yourself puts it on your own My Tasks, and the notification bell gains a
    // row when you assign it to somebody else.
    onSuccess: () =>
      invalidate(client, keys.allTasks, keys.myTasks, keys.notifications),
  });
}

export function useEditTask(opportunityId: number) {
  const client = useQueryClient();
  return useMutation<Task, Error, { taskId: number; patch: TaskInput }>({
    mutationFn: ({ taskId, patch }) =>
      apiRequest(`/api/v2/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () =>
      invalidate(
        client,
        keys.tasks(opportunityId),
        keys.myTasks,
        keys.notifications,
      ),
  });
}

/**
 * Ticking a task off, and putting it back.
 *
 * One hook for both directions because they are one control: `completed` is
 * what the checkbox now reads, and the route it calls follows from that. Both
 * are idempotent server-side, so a double click costs a request and changes
 * nothing.
 *
 * No `opportunityId`, unlike `useCreateTask` and `useEditTask`: the route takes
 * a task id, and `keys.allTasks` invalidates every deal's list anyway — so the
 * parameter was a lie about what the hook needed, and `TasksPage` was passing
 * `0` to satisfy it. The lint caught it, which is why the warning was worth
 * reading rather than silencing.
 */
export function useSetTaskDone() {
  const client = useQueryClient();
  return useMutation<Task, Error, { taskId: number; completed: boolean }>({
    mutationFn: ({ taskId, completed }) =>
      apiRequest(
        `/api/v2/tasks/${taskId}/${completed ? "complete" : "reopen"}`,
        {
          method: "POST",
        },
      ),
    onSuccess: () => invalidate(client, keys.allTasks, keys.myTasks),
  });
}

/**
 * A task's discussion (milestone 4.5).
 *
 * Writes only: the comments arrive with the task (`Task["comments"]`), so there
 * is no read here — the same shape a note's comments have. Not optimistic, like
 * every other task write: the row the server answers with carries an
 * `author_name` the cache does not hold.
 */
export function useAddTaskComment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, { taskId: number; body: string }>({
    mutationFn: ({ taskId, body }) =>
      apiRequest(`/api/v2/tasks/${taskId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    // The two people a task is about are notified, and one of them may be the
    // reader (`notifications`); both task reads carry the comment.
    onSuccess: () =>
      invalidate(client, keys.allTasks, keys.myTasks, keys.notifications),
  });
}

export function useDeleteTaskComment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (commentId) =>
      apiRequest(`/api/v2/task-comments/${commentId}`, { method: "DELETE" }),
    // An audit row, so the activity log is stale too.
    onSuccess: () =>
      invalidate(client, keys.allTasks, keys.myTasks, keys.allActivity),
  });
}

export function useRestoreTaskComment() {
  return useRestore(
    (id) => `/api/v2/task-comments/${id}/restore`,
    keys.allTasks,
    keys.myTasks,
    keys.allActivity,
  );
}

export function useDeleteTask() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (taskId) =>
      apiRequest(`/api/v2/tasks/${taskId}`, { method: "DELETE" }),
    // A delete writes an audit row, so the activity log is stale too -- the
    // rule every other delete here follows.
    onSuccess: () =>
      invalidate(client, keys.allTasks, keys.myTasks, keys.allActivity),
  });
}

export function useRestoreTask() {
  return useRestore(
    (id) => `/api/v2/tasks/${id}/restore`,
    keys.allTasks,
    keys.myTasks,
    keys.allActivity,
  );
}

type BulkOpportunityAction = components["schemas"]["BulkOpportunityAction"];
type BulkActionResponse = components["schemas"]["BulkActionResponse"];

/**
 * The bulk action bar's one request (milestone 2.4c, completed in 3.0a).
 *
 * Not optimistic, unlike the single-item deletes (D-068 extended to the
 * bulk case, D-071): the response is per-item — some ids may succeed and
 * others fail — so nothing about the outcome is safe to predict before the
 * server answers. `BulkActionBar` reads `results` to report exactly what
 * happened and, for a delete, to offer Undo over the ids that actually went.
 */
export function useBulkOpportunityAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: BulkOpportunityAction) =>
      apiRequest<BulkActionResponse>("/api/v2/opportunities/bulk", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    // A stage change writes a system timeline entry and a delete writes an
    // audit row that cannot be resolved to one opportunity id (same reason
    // `useDeleteOpportunity` invalidates the prefix rather than one key).
    // `add_to_view` writes to a saved view instead of to any opportunity,
    // and `assign_owner` changes the role every list reports, so the whole
    // set is invalidated rather than a branch per action.
    onSuccess: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allVersions,
        keys.allActivity,
        keys.allSavedViews,
        keys.notifications,
        keys.allMembers,
      ),
  });
}

export interface TimelineEntryPayload {
  type: string;
  title: string;
  body: string;
  event_timestamp: string;
  // No `follow_up_date` since milestone 4.2 (**D-144**): a follow-up is a task
  // now. The API still accepts the field for the legacy column, and omitting it
  // from a `PATCH` is what leaves an already-migrated entry's copy of the date
  // untouched rather than clearing it.
}

export function useSaveTimelineEntry(opportunityId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      entryId,
      payload,
    }: {
      entryId: number | null;
      payload: TimelineEntryPayload;
    }) =>
      apiRequest<TimelineEntry>(
        entryId
          ? `/api/v2/timeline/${entryId}`
          : `/api/v2/opportunities/${opportunityId}/timeline`,
        {
          method: entryId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      ),
    // The list carries a stalled flag and a last-activity time, both of which
    // an entry moves; an edit also appends a version (milestone 2.10).
    onSuccess: () =>
      invalidate(
        client,
        keys.allTimelines,
        keys.opportunities,
        keys.allVersions,
        keys.allActivity,
      ),
  });
}

/** Writes below a timeline entry: they change the timeline and nothing else. */
function useTimelineWrite<TVariables>(
  request: (variables: TVariables) => Promise<unknown>,
): UseMutationResult<unknown, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => invalidate(client, keys.allTimelines),
  });
}

export function useDeleteTimelineEntry() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (entryId: number) =>
      apiRequest(`/api/v2/timeline/${entryId}`, { method: "DELETE" }),
    onMutate: (entryId) =>
      optimisticTimelines(client, (entries) =>
        entries.filter((entry) => entry.id !== entryId),
      ),
    onError: (_error, _entryId, snapshot) => rollback(client, snapshot),
    onSettled: () =>
      invalidate(
        client,
        keys.allTimelines,
        keys.opportunities,
        keys.allActivity,
      ),
  });
}

export function useAddNote() {
  return useTimelineWrite(
    ({ entryId, body }: { entryId: number; body: string }) =>
      apiRequest(`/api/v2/timeline/${entryId}/notes`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
  );
}

/**
 * A note edit is the one write whose result the client can predict: the body
 * is what was typed, and the edit marker is on from the first edit onwards. A
 * create cannot be — the server assigns the id — so those still wait.
 */
export function useSaveNote() {
  const client = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { noteId: number; body: string; updatedAt: string },
    Snapshot
  >({
    // `updatedAt` is ADR 0003's edit guard (milestone 3.4): the value the note
    // had when the editor was opened. The server answers 409 if it has moved,
    // which is the one failure here that is about the note rather than about
    // the request — `app/NoteBlock.tsx` says so in its own words.
    mutationFn: ({ noteId, body, updatedAt }) =>
      apiRequest(`/api/v2/notes/${noteId}`, {
        method: "PATCH",
        body: JSON.stringify({ body, updated_at: updatedAt }),
      }),
    onMutate: ({ noteId, body }) =>
      optimisticTimelines(client, (entries) =>
        mapNotes(entries, (notes) =>
          notes.map((note) =>
            note.id === noteId ? { ...note, body, edited: true } : note,
          ),
        ),
      ),
    onError: (_error, _variables, snapshot) => rollback(client, snapshot),
    onSettled: () =>
      invalidate(client, keys.allTimelines, keys.allVersions, keys.allActivity),
  });
}

export function useDeleteNote() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (noteId: number) =>
      apiRequest(`/api/v2/notes/${noteId}`, { method: "DELETE" }),
    onMutate: (noteId) =>
      optimisticTimelines(client, (entries) =>
        mapNotes(entries, (notes) =>
          notes.filter((note) => note.id !== noteId),
        ),
      ),
    onError: (_error, _noteId, snapshot) => rollback(client, snapshot),
    onSettled: () => invalidate(client, keys.allTimelines, keys.allActivity),
  });
}

/**
 * Open a thread on a note, or answer one (milestone 3.3).
 *
 * `parentId` is what makes it a reply. Not optimistic, like every other
 * create: the server assigns the id (D-068).
 */
export function useAddComment() {
  return useTimelineWrite(
    ({
      noteId,
      body,
      parentId,
    }: {
      noteId: number;
      body: string;
      parentId?: number;
    }) =>
      apiRequest(`/api/v2/notes/${noteId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body, parent_id: parentId ?? null }),
      }),
  );
}

export function useDeleteComment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (commentId: number) =>
      apiRequest(`/api/v2/comments/${commentId}`, { method: "DELETE" }),
    // Deleting a thread takes its replies with it on the server
    // (`soft_delete.soft_delete_comment`), so the optimistic half removes
    // both — otherwise the replies hang under nothing until the refetch
    // lands.
    onMutate: (commentId) =>
      optimisticTimelines(client, (entries) =>
        mapNotes(entries, (notes) =>
          notes.map((note) => ({
            ...note,
            comments: note.comments
              .filter((thread) => thread.id !== commentId)
              .map((thread) => ({
                ...thread,
                replies: thread.replies.filter(
                  (reply) => reply.id !== commentId,
                ),
              })),
          })),
        ),
      ),
    onError: (_error, _commentId, snapshot) => rollback(client, snapshot),
    onSettled: () => invalidate(client, keys.allTimelines, keys.allActivity),
  });
}

/**
 * Declare a thread finished, or open it again (milestone 3.3).
 *
 * Not optimistic, unlike the deletes beside it: what the reader is shown is
 * "Resolved by <name>", and the cache holds an id rather than the name to
 * put there. The server answers with the thread it wrote, so the refetch is
 * the only honest source of that line.
 */
export function useResolveThread() {
  return useTimelineWrite(
    ({ commentId, resolved }: { commentId: number; resolved: boolean }) =>
      apiRequest(
        `/api/v2/comments/${commentId}/${resolved ? "resolve" : "unresolve"}`,
        { method: "POST" },
      ),
  );
}

/**
 * React to a comment or reply, or withdraw the caller's own reaction
 * (milestone 3.3a). Idempotent on the server either way, so this is one
 * mutation with a `reacted` flag rather than two -- a toggle, like
 * `useResolveThread` beside it. Not optimistic: the response carries the
 * comment's full reaction list, which is what a like-count control has to
 * show correctly the moment it settles.
 */
export function useSetReaction() {
  return useTimelineWrite(
    ({
      commentId,
      emoji,
      reacted,
    }: {
      commentId: number;
      emoji: ReactionEmoji;
      reacted: boolean;
    }) =>
      apiRequest(
        `/api/v2/comments/${commentId}/reactions${reacted ? "" : `/${encodeURIComponent(emoji)}`}`,
        {
          method: reacted ? "POST" : "DELETE",
          body: reacted ? JSON.stringify({ emoji }) : undefined,
        },
      ),
  );
}

/**
 * Sharing writes. Each one also appends a system timeline entry and an audit
 * row (`backend/app/routes_sharing.py`), so the timeline and the activity log
 * are invalidated beside the share list itself.
 */
function useSharingWrite<TVariables>(
  opportunityId: number,
  request: (variables: TVariables) => Promise<unknown>,
): UseMutationResult<unknown, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () =>
      invalidate(
        client,
        keys.shares(opportunityId),
        keys.members(opportunityId),
        keys.activity(opportunityId),
        keys.allTimelines,
      ),
  });
}

export function useAddShare(opportunityId: number) {
  return useSharingWrite(
    opportunityId,
    (payload: { email: string; role: ShareRole }) =>
      apiRequest(`/api/v2/opportunities/${opportunityId}/shares`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  );
}

export function useUpdateShareRole(opportunityId: number) {
  return useSharingWrite(
    opportunityId,
    ({ userId, role }: { userId: number; role: ShareRole }) =>
      apiRequest(`/api/v2/opportunities/${opportunityId}/shares/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }),
  );
}

export function useRemoveShare(opportunityId: number) {
  return useSharingWrite(opportunityId, (userId: number) =>
    apiRequest(`/api/v2/opportunities/${opportunityId}/shares/${userId}`, {
      method: "DELETE",
    }),
  );
}

export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) =>
      apiRequest(`/api/v2/notifications/${notificationId}/read`, {
        method: "PATCH",
      }),
    onSuccess: () => invalidate(client, keys.notifications),
  });
}

export function useMarkAllNotificationsRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest("/api/v2/notifications/mark-all-read", { method: "POST" }),
    onSuccess: () => invalidate(client, keys.notifications),
  });
}

export function useAskAi(opportunityId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (question: string) =>
      apiRequest<AiAskResponse>(
        `/api/v2/opportunities/${opportunityId}/ai/ask`,
        {
          method: "POST",
          body: JSON.stringify({ question }),
        },
      ),
    onMutate: (question) => {
      append(client, opportunityId, { role: "user", body: question });
    },
    onSuccess: (answer) => {
      append(client, opportunityId, {
        role: "assistant",
        body: answer.answer,
        referenced_entry_numbers: answer.referenced_entry_numbers,
      });
    },
  });
}

function append(
  client: QueryClient,
  opportunityId: number,
  message: AiChatMessage,
) {
  client.setQueryData<AiChatMessage[]>(
    keys.aiConversation(opportunityId),
    (current) => [...(current ?? []), message],
  );
}
