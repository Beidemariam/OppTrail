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

import { apiRequest } from "./api";
import type { components } from "./api-types";
import type {
  AiChatMessage,
  AppNotification,
  AuditLogEntry,
  Opportunity,
  OpportunityShare,
  SavedView,
  SavedViewEntity,
  ShareRole,
  TimelineEntry,
  TimelineFilters,
  User,
} from "./domain";
import { localInputToUtc } from "./time";

type AuthResponse = components["schemas"]["AuthResponse"];
type OpportunityListResponse = components["schemas"]["OpportunityListResponse"];
type TimelineResponse = components["schemas"]["TimelineResponse"];
type ShareListResponse = components["schemas"]["ShareListResponse"];
type NotificationPage = components["schemas"]["Page_NotificationPublicV2_"];
type AiAskResponse = components["schemas"]["AiAskResponse"];
type SavedViewPage = components["schemas"]["Page_SavedViewPublic_"];
type SavedViewCreate = components["schemas"]["SavedViewCreate"];

const NOTIFICATION_PAGE_SIZE = 50;
const SAVED_VIEW_PAGE_SIZE = 100;

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
  return `/api/opportunities/${opportunityId}/timeline${suffix}`;
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
      apiRequest<AuthResponse>("/api/auth/me")
        .then((data) => data.user)
        .catch(() => null),
  });
}

export function useOpportunities(enabled: boolean) {
  return useQuery<Opportunity[]>({
    queryKey: keys.opportunities,
    enabled,
    queryFn: () =>
      apiRequest<OpportunityListResponse>("/api/opportunities").then(
        (data) => data.opportunities,
      ),
  });
}

export function useTimeline(opportunityId: number, filters: TimelineFilters) {
  return useQuery<TimelineEntry[]>({
    queryKey: keys.timeline(opportunityId, filters),
    queryFn: () =>
      apiRequest<TimelineResponse>(timelinePath(opportunityId, filters)).then(
        (data) => data.entries,
      ),
  });
}

export function useShares(opportunityId: number, enabled: boolean) {
  return useQuery<OpportunityShare[]>({
    queryKey: keys.shares(opportunityId),
    enabled,
    queryFn: () =>
      apiRequest<ShareListResponse>(
        `/api/opportunities/${opportunityId}/shares`,
      ).then((data) => data.shares),
  });
}

export function useAuditLog(opportunityId: number, enabled: boolean) {
  return useQuery<AuditLogEntry[]>({
    queryKey: keys.auditLog(opportunityId),
    enabled,
    queryFn: () =>
      apiRequest<AuditLogEntry[]>(
        `/api/opportunities/${opportunityId}/audit-log`,
      ),
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
      apiRequest<AuthResponse>(`/api/auth/${mode}`, {
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
    mutationFn: () => apiRequest("/api/auth/logout", { method: "POST" }),
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
        id ? `/api/opportunities/${id}` : "/api/opportunities",
        { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) },
      ),
    // A stage change writes a system timeline entry, so the timeline is stale
    // too (`backend/app/routes_opportunities.py`).
    onSuccess: () => invalidate(client, keys.opportunities, keys.allTimelines),
  });
}

export function useDeleteOpportunity() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (opportunityId: number) =>
      apiRequest(`/api/opportunities/${opportunityId}`, { method: "DELETE" }),
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
      ),
  });
}

/**
 * Undo, for each of the four things that can be deleted.
 *
 * Restore is a v2-only route: it has no v1 twin, like
 * `POST /api/v2/notifications/mark-all-read` (`CLAUDE.md`, "API versions").
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
  );
}

export function useRestoreTimelineEntry() {
  return useRestore(
    (id) => `/api/v2/timeline/${id}/restore`,
    keys.allTimelines,
    keys.opportunities,
    keys.allAuditLogs,
  );
}

export function useRestoreNote() {
  return useRestore(
    (id) => `/api/v2/notes/${id}/restore`,
    keys.allTimelines,
    keys.allAuditLogs,
  );
}

export function useRestoreComment() {
  return useRestore(
    (id) => `/api/v2/comments/${id}/restore`,
    keys.allTimelines,
    keys.allAuditLogs,
  );
}

type BulkOpportunityAction = components["schemas"]["BulkOpportunityAction"];
type BulkActionResponse = components["schemas"]["BulkActionResponse"];

/**
 * The bulk action bar's one request (milestone 2.4c, `docs/UX.md`).
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
    onSuccess: () =>
      invalidate(
        client,
        keys.opportunities,
        keys.allTimelines,
        keys.allAuditLogs,
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
          ? `/api/timeline/${entryId}`
          : `/api/opportunities/${opportunityId}/timeline`,
        {
          method: entryId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      ),
    // The list carries a stalled flag and a last-activity time, both of which
    // an entry moves.
    onSuccess: () => invalidate(client, keys.allTimelines, keys.opportunities),
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
      apiRequest(`/api/timeline/${entryId}`, { method: "DELETE" }),
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
      ),
  });
}

export function useAddNote() {
  return useTimelineWrite(
    ({ entryId, body }: { entryId: number; body: string }) =>
      apiRequest(`/api/timeline/${entryId}/notes`, {
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
      apiRequest(`/api/notes/${noteId}`, {
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
    onSettled: () => invalidate(client, keys.allTimelines),
  });
}

export function useDeleteNote() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (noteId: number) =>
      apiRequest(`/api/notes/${noteId}`, { method: "DELETE" }),
    onMutate: (noteId) =>
      optimisticTimelines(client, (entries) =>
        mapNotes(entries, (notes) =>
          notes.filter((note) => note.id !== noteId),
        ),
      ),
    onError: (_error, _noteId, snapshot) => rollback(client, snapshot),
    onSettled: () => invalidate(client, keys.allTimelines, keys.allAuditLogs),
  });
}

export function useAddComment() {
  return useTimelineWrite(
    ({ noteId, body }: { noteId: number; body: string }) =>
      apiRequest(`/api/notes/${noteId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
  );
}

export function useDeleteComment() {
  const client = useQueryClient();
  return useMutation<unknown, Error, number, Snapshot>({
    mutationFn: (commentId: number) =>
      apiRequest(`/api/comments/${commentId}`, { method: "DELETE" }),
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
    onSettled: () => invalidate(client, keys.allTimelines, keys.allAuditLogs),
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
        keys.allTimelines,
      ),
  });
}

export function useAddShare(opportunityId: number) {
  return useSharingWrite(
    opportunityId,
    (payload: { email: string; role: ShareRole }) =>
      apiRequest(`/api/opportunities/${opportunityId}/shares`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  );
}

export function useUpdateShareRole(opportunityId: number) {
  return useSharingWrite(
    opportunityId,
    ({ userId, role }: { userId: number; role: ShareRole }) =>
      apiRequest(`/api/opportunities/${opportunityId}/shares/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }),
  );
}

export function useRemoveShare(opportunityId: number) {
  return useSharingWrite(opportunityId, (userId: number) =>
    apiRequest(`/api/opportunities/${opportunityId}/shares/${userId}`, {
      method: "DELETE",
    }),
  );
}

export function useMarkNotificationRead() {
  const client = useQueryClient();
  return useMutation({
    // Marking one read is still a v1 route; there is no v2 twin to reuse
    // (`CLAUDE.md`, "Notifications").
    mutationFn: (notificationId: number) =>
      apiRequest(`/api/notifications/${notificationId}/read`, {
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
      apiRequest<AiAskResponse>(`/api/opportunities/${opportunityId}/ai/ask`, {
        method: "POST",
        body: JSON.stringify({ question }),
      }),
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
