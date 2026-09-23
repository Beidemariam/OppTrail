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

import type { ActivityEvent } from "./activity";
import { apiRequest } from "./api";
import type { components } from "./api-types";
import type {
  AiChatMessage,
  AppNotification,
  AuditLogEntry,
  NoteVersion,
  Opportunity,
  OpportunityFieldPatch,
  OpportunityShare,
  OpportunityVersion,
  SavedView,
  SavedViewEntity,
  ShareRole,
  TimelineEntry,
  TimelineEntryVersion,
  TimelineFilters,
  User,
} from "./domain";
import { localInputToUtc } from "./time";

type AuthResponse = components["schemas"]["AuthResponse"];
type NotificationPage = components["schemas"]["Page_NotificationPublic_"];
type AiAskResponse = components["schemas"]["AiAskResponse"];
type SavedViewPage = components["schemas"]["Page_SavedViewPublic_"];
type SavedViewCreate = components["schemas"]["SavedViewCreate"];
type SavedViewUpdate = components["schemas"]["SavedViewUpdate"];

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
  auditLog: (opportunityId: number) => ["audit-log", opportunityId] as const,
  /**
   * Every opportunity's audit log. A delete or a restore writes an audit row
   * (`backend/app/audit_utils.py`) and knows only the id of the thing it
   * removed, not which opportunity that hangs under — so it invalidates the
   * prefix rather than resolving the owner first.
   */
  allAuditLogs: ["audit-log"] as const,
  notifications: ["notifications"] as const,
  /**
   * One item's edit history (milestone 2.10), keyed by what kind of thing it
   * hangs off as well as by id: the three id spaces are separate tables.
   */
  versions: (kind: "opportunity" | "entry" | "note", id: number) =>
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
   * Every opportunity's activity log. The feed merges the system entries, the
   * audit rows and the version rows (`backend/app/activity.py`), so every
   * write that invalidates one of those three invalidates this beside it —
   * and like `allAuditLogs`, a delete knows its own id rather than which
   * opportunity it hung under.
   */
  allActivity: ["activity"] as const,
  aiConversation: (opportunityId: number) =>
    ["ai-conversation", opportunityId] as const,
  savedViews: (entity: SavedViewEntity) => ["saved-views", entity] as const,
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

export function useAuditLog(opportunityId: number, enabled: boolean) {
  return useQuery<AuditLogEntry[]>({
    queryKey: keys.auditLog(opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<AuditLogEntry>(
        `/api/v2/opportunities/${opportunityId}/audit-log`,
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
 */
export function useActivity(opportunityId: number, enabled: boolean) {
  return useQuery<ActivityEvent[]>({
    queryKey: keys.activity(opportunityId),
    enabled,
    queryFn: () =>
      fetchAll<ActivityEvent>(
        `/api/v2/opportunities/${opportunityId}/activity`,
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
        keys.allAuditLogs,
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
    keys.allAuditLogs,
    keys.allActivity,
  );
}

export function useRestoreTimelineEntry() {
  return useRestore(
    (id) => `/api/v2/timeline/${id}/restore`,
    keys.allTimelines,
    keys.opportunities,
    keys.allAuditLogs,
    keys.allActivity,
  );
}

export function useRestoreNote() {
  return useRestore(
    (id) => `/api/v2/notes/${id}/restore`,
    keys.allTimelines,
    keys.allAuditLogs,
    keys.allActivity,
  );
}

export function useRestoreComment() {
  return useRestore(
    (id) => `/api/v2/comments/${id}/restore`,
    keys.allTimelines,
    keys.allAuditLogs,
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
        keys.allAuditLogs,
        keys.allVersions,
        keys.allActivity,
        keys.allSavedViews,
        keys.notifications,
      ),
  });
}

export interface TimelineEntryPayload {
  type: string;
  title: string;
  body: string;
  event_timestamp: string;
  follow_up_date: string | null;
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
        keys.allAuditLogs,
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
    { noteId: number; body: string },
    Snapshot
  >({
    mutationFn: ({ noteId, body }) =>
      apiRequest(`/api/v2/notes/${noteId}`, {
        method: "PATCH",
        body: JSON.stringify({ body }),
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
    onSettled: () =>
      invalidate(
        client,
        keys.allTimelines,
        keys.allAuditLogs,
        keys.allActivity,
      ),
  });
}

export function useAddComment() {
  return useTimelineWrite(
    ({ noteId, body }: { noteId: number; body: string }) =>
      apiRequest(`/api/v2/notes/${noteId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
  );
}

export function useDeleteComment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (commentId: number) =>
      apiRequest(`/api/v2/comments/${commentId}`, { method: "DELETE" }),
    onMutate: (commentId) =>
      optimisticTimelines(client, (entries) =>
        mapNotes(entries, (notes) =>
          notes.map((note) => ({
            ...note,
            comments: note.comments.filter(
              (comment) => comment.id !== commentId,
            ),
          })),
        ),
      ),
    onError: (_error, _commentId, snapshot) => rollback(client, snapshot),
    onSettled: () =>
      invalidate(
        client,
        keys.allTimelines,
        keys.allAuditLogs,
        keys.allActivity,
      ),
  });
}

/**
 * Sharing writes. Each one also appends a system timeline entry and an audit
 * row (`backend/app/routes_sharing.py`), so all three reads are invalidated.
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
        keys.auditLog(opportunityId),
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
        referenced_entry_ids: answer.referenced_entry_ids,
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
