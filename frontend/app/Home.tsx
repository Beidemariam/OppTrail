"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import type { components } from "../lib/api-types";
import { apiRequest } from "../lib/api";
import { notificationText } from "../lib/notifications";
import {
  canChangeItem as canChangeItemFor,
  canManageOpportunity,
  canWriteTimeline,
} from "../lib/permissions";
import {
  formatTimestamp,
  localInputToUtc,
  nowDateTimeInput,
  toDateTimeInput,
} from "../lib/time";
import { MarkdownText } from "./MarkdownText";

const stages = [
  "Prospecting",
  "Qualification",
  "Needs Analysis",
  "Proposal",
  "Negotiation",
  "Closed Won",
  "Closed Lost",
] as const;

const entryTypes = [
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "demo", label: "Demo" },
  { value: "proposal", label: "Proposal" },
  { value: "contract", label: "Contract" },
  { value: "stage_change", label: "Stage Change" },
  { value: "other", label: "Other" },
] as const;

type EntryType = (typeof entryTypes)[number]["value"];

const notificationTypeOptions = [
  { value: "mention", label: "Mentions" },
  { value: "comment", label: "Comments" },
  { value: "shared_activity", label: "Activity" },
  { value: "share_added", label: "Sharing added" },
  { value: "share_role_changed", label: "Role changed" },
  { value: "share_removed", label: "Sharing removed" },
] as const;

const NOTIFICATION_PAGE_SIZE = 50;

type User = components["schemas"]["UserPublic"];
type Opportunity = components["schemas"]["OpportunityPublic"];
type OpportunityShare = components["schemas"]["SharePublic"];
type AuditLogEntry = components["schemas"]["AuditLogEntryPublic"];
type AppNotification = components["schemas"]["NotificationPublicV2"];
type NotificationType = AppNotification["type"];
type TimelineEntry = components["schemas"]["TimelineEntryPublic"];

type AuthResponse = components["schemas"]["AuthResponse"];
type OpportunityListResponse = components["schemas"]["OpportunityListResponse"];
type TimelineResponse = components["schemas"]["TimelineResponse"];
type ShareListResponse = components["schemas"]["ShareListResponse"];
type NotificationPage = components["schemas"]["Page_NotificationPublicV2_"];
type AiAskResponse = components["schemas"]["AiAskResponse"];

type AiChatMessage = {
  role: "user" | "assistant";
  body: string;
  referenced_entry_ids?: number[];
};

type OpportunityForm = {
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  expected_close_date: string;
};

type TimelineEntryForm = {
  type: EntryType;
  title: string;
  body: string;
  event_timestamp: string;
  follow_up_date: string;
};

type TimelineFilters = {
  q: string;
  type: string;
  from: string;
  to: string;
  author_id: string;
};

type ShareForm = {
  email: string;
  role: components["schemas"]["ShareCreate"]["role"];
};

const emptyOpportunityForm: OpportunityForm = {
  name: "",
  account_name: "",
  value: "0",
  currency: "USD",
  stage: "Prospecting",
  expected_close_date: "",
};

const emptyEntryForm: TimelineEntryForm = {
  type: "call",
  title: "",
  body: "",
  event_timestamp: "",
  follow_up_date: "",
};

const emptyFilters: TimelineFilters = {
  q: "",
  type: "",
  from: "",
  to: "",
  author_id: "",
};

const emptyShareForm: ShareForm = {
  email: "",
  role: "viewer",
};

function confirmDelete(description: string) {
  return window.confirm(`Delete ${description}? This cannot be undone here.`);
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("signup");
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [opportunityForm, setOpportunityForm] =
    useState<OpportunityForm>(emptyOpportunityForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<
    number | null
  >(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [entryForm, setEntryForm] = useState<TimelineEntryForm>({
    ...emptyEntryForm,
    event_timestamp: nowDateTimeInput(),
  });
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [timelineFilters, setTimelineFilters] =
    useState<TimelineFilters>(emptyFilters);
  const [shareForm, setShareForm] = useState<ShareForm>(emptyShareForm);
  const [shares, setShares] = useState<OpportunityShare[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiConversations, setAiConversations] = useState<
    Record<number, AiChatMessage[]>
  >({});
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const aiChatRef = useRef<HTMLDivElement | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notificationTypeFilter, setNotificationTypeFilter] = useState<
    NotificationType | ""
  >("");
  const [noteForms, setNoteForms] = useState<Record<number, string>>({});
  const [editingNotes, setEditingNotes] = useState<Record<number, string>>({});
  const [commentForms, setCommentForms] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Loading...");

  const selectedOpportunity = useMemo(
    () =>
      opportunities.find(
        (opportunity) => opportunity.id === selectedOpportunityId,
      ) ?? null,
    [opportunities, selectedOpportunityId],
  );
  // The rules themselves live in ../lib/permissions.ts, next to the note
  // explaining why editing and deleting resolve through one function.
  const selectedRole = selectedOpportunity?.current_user_role;
  const canManageSelectedOpportunity = canManageOpportunity(selectedRole);
  const canWriteSelectedTimeline = canWriteTimeline(selectedRole);
  const canChangeItem = (authorId: number | null) =>
    canChangeItemFor({ role: selectedRole, userId: user?.id, authorId });
  const canEdit = (authorId: number | null) => canChangeItem(authorId);
  const canDelete = (authorId: number | null) => canChangeItem(authorId);
  const aiMessages = useMemo(
    () =>
      selectedOpportunityId
        ? (aiConversations[selectedOpportunityId] ?? [])
        : [],
    [aiConversations, selectedOpportunityId],
  );
  const unreadNotificationCount = useMemo(
    () => notifications.filter((notification) => !notification.read_at).length,
    [notifications],
  );
  // Filtered client-side over the loaded page: an inbox at this app's scale
  // (20 known users) never needs a second round trip just to narrow a type
  // the first page already holds. The server-side filter
  // (`GET /api/v2/notifications?type=`) is what a non-UI client uses.
  const visibleNotifications = useMemo(
    () =>
      notificationTypeFilter
        ? notifications.filter(
            (notification) => notification.type === notificationTypeFilter,
          )
        : notifications,
    [notifications, notificationTypeFilter],
  );

  useEffect(() => {
    apiRequest<AuthResponse>("/api/auth/me")
      .then((data) => {
        setUser(data.user);
        setStatus("");
        return Promise.all([loadOpportunities(), loadNotifications()]);
      })
      .catch(() => {
        setStatus("");
      });
  }, []);

  useEffect(() => {
    const chat = aiChatRef.current;
    if (!chat) {
      return;
    }
    chat.scrollTop = chat.scrollHeight;
  }, [aiMessages, aiLoading, aiError, selectedOpportunityId]);

  const groupedOpportunities = useMemo(
    () =>
      stages.map((stage) => ({
        stage,
        items: opportunities.filter(
          (opportunity) => opportunity.stage === stage,
        ),
      })),
    [opportunities],
  );

  async function loadOpportunities() {
    const data =
      await apiRequest<OpportunityListResponse>("/api/opportunities");
    setOpportunities(data.opportunities);
  }

  async function loadNotifications() {
    const data = await apiRequest<NotificationPage>(
      `/api/v2/notifications?limit=${NOTIFICATION_PAGE_SIZE}`,
    );
    setNotifications(data.items);
  }

  async function loadTimeline(opportunityId = selectedOpportunityId) {
    if (!opportunityId) {
      return;
    }

    const params = new URLSearchParams();
    Object.entries(timelineFilters).forEach(([key, value]) => {
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
    const data = await apiRequest<TimelineResponse>(
      `/api/opportunities/${opportunityId}/timeline${suffix}`,
    );
    setTimelineEntries(data.entries);
  }

  async function loadSharingData(opportunityId: number, role: string) {
    if (role !== "owner") {
      setShares([]);
      setAuditLog([]);
      return;
    }

    const [shareData, auditData] = await Promise.all([
      apiRequest<ShareListResponse>(
        `/api/opportunities/${opportunityId}/shares`,
      ),
      apiRequest<AuditLogEntry[]>(
        `/api/opportunities/${opportunityId}/audit-log`,
      ),
    ]);
    setShares(shareData.shares);
    setAuditLog(auditData);
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus(authMode === "signup" ? "Creating account..." : "Signing in...");

    try {
      const payload =
        authMode === "signup"
          ? { email: authEmail, password: authPassword, name: authName }
          : { email: authEmail, password: authPassword };
      const data = await apiRequest<AuthResponse>(`/api/auth/${authMode}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setUser(data.user);
      setAuthPassword("");
      setStatus("");
      await Promise.all([loadOpportunities(), loadNotifications()]);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Authentication failed",
      );
      setStatus("");
    }
  }

  async function logout() {
    setError("");
    await apiRequest("/api/auth/logout", { method: "POST" });
    setUser(null);
    setOpportunities([]);
    setTimelineEntries([]);
    setShares([]);
    setAuditLog([]);
    setNotifications([]);
    setShowNotifications(false);
    setAiConversations({});
    setAiQuestion("");
    setAiError("");
    setSelectedOpportunityId(null);
    setOpportunityForm(emptyOpportunityForm);
    setEditingId(null);
  }

  async function submitOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus(
      editingId ? "Updating opportunity..." : "Creating opportunity...",
    );

    const payload = {
      ...opportunityForm,
      expected_close_date: opportunityForm.expected_close_date || null,
    };

    try {
      if (editingId) {
        await apiRequest(`/api/opportunities/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        await apiRequest("/api/opportunities", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setOpportunityForm(emptyOpportunityForm);
      setEditingId(null);
      setStatus("");
      await loadOpportunities();
      if (selectedOpportunityId) {
        await loadTimeline(selectedOpportunityId);
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save opportunity",
      );
      setStatus("");
    }
  }

  function editOpportunity(opportunity: Opportunity) {
    setEditingId(opportunity.id);
    setOpportunityForm({
      name: opportunity.name,
      account_name: opportunity.account_name,
      value: opportunity.value,
      currency: opportunity.currency,
      stage: opportunity.stage,
      expected_close_date: opportunity.expected_close_date ?? "",
    });
  }

  async function deleteOpportunity(opportunityId: number) {
    const opportunity = opportunities.find((item) => item.id === opportunityId);
    if (
      !confirmDelete(
        `"${opportunity?.name ?? "this opportunity"}" and its entire timeline`,
      )
    ) {
      return;
    }

    setError("");
    setStatus("Deleting opportunity...");
    try {
      await apiRequest(`/api/opportunities/${opportunityId}`, {
        method: "DELETE",
      });
      setStatus("");
      await loadOpportunities();
      if (editingId === opportunityId) {
        setEditingId(null);
        setOpportunityForm(emptyOpportunityForm);
      }
      if (selectedOpportunityId === opportunityId) {
        setSelectedOpportunityId(null);
        setTimelineEntries([]);
        setShares([]);
        setAuditLog([]);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not delete opportunity",
      );
      setStatus("");
    }
  }

  async function openTimeline(opportunity: Opportunity) {
    setSelectedOpportunityId(opportunity.id);
    setTimelineEntries([]);
    setTimelineFilters(emptyFilters);
    setEditingEntryId(null);
    setEntryForm({ ...emptyEntryForm, event_timestamp: nowDateTimeInput() });
    setAiQuestion("");
    setAiError("");
    setStatus("Loading timeline...");
    setError("");

    try {
      const data = await apiRequest<TimelineResponse>(
        `/api/opportunities/${opportunity.id}/timeline`,
      );
      setTimelineEntries(data.entries);
      await loadSharingData(opportunity.id, opportunity.current_user_role);
      setStatus("");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load timeline",
      );
      setStatus("");
    }
  }

  async function submitTimelineEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedOpportunityId) {
      return;
    }

    setError("");
    setStatus(editingEntryId ? "Updating entry..." : "Adding entry...");
    const payload = {
      ...entryForm,
      event_timestamp: localInputToUtc(entryForm.event_timestamp),
      follow_up_date: entryForm.follow_up_date || null,
    };

    try {
      if (editingEntryId) {
        await apiRequest(`/api/timeline/${editingEntryId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        await apiRequest(
          `/api/opportunities/${selectedOpportunityId}/timeline`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          },
        );
      }
      setEntryForm({ ...emptyEntryForm, event_timestamp: nowDateTimeInput() });
      setEditingEntryId(null);
      setStatus("");
      await loadTimeline(selectedOpportunityId);
      await loadOpportunities();
      await loadOpportunities();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save entry",
      );
      setStatus("");
    }
  }

  async function submitShare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedOpportunity) {
      return;
    }

    setError("");
    setStatus("Sharing opportunity...");
    try {
      await apiRequest(`/api/opportunities/${selectedOpportunity.id}/shares`, {
        method: "POST",
        body: JSON.stringify(shareForm),
      });
      setShareForm(emptyShareForm);
      await loadSharingData(
        selectedOpportunity.id,
        selectedOpportunity.current_user_role,
      );
      await loadTimeline(selectedOpportunity.id);
      setStatus("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not share opportunity",
      );
      setStatus("");
    }
  }

  async function updateShareRole(userId: number, role: "viewer" | "editor") {
    if (!selectedOpportunity) {
      return;
    }

    setError("");
    setStatus("Updating share...");
    try {
      await apiRequest(
        `/api/opportunities/${selectedOpportunity.id}/shares/${userId}`,
        {
          method: "PATCH",
          body: JSON.stringify({ role }),
        },
      );
      await loadSharingData(
        selectedOpportunity.id,
        selectedOpportunity.current_user_role,
      );
      await loadTimeline(selectedOpportunity.id);
      setStatus("");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not update share",
      );
      setStatus("");
    }
  }

  async function removeShare(userId: number) {
    if (!selectedOpportunity) {
      return;
    }

    const share = shares.find((item) => item.user_id === userId);
    if (!confirmDelete(`access for ${share?.name ?? "this colleague"}`)) {
      return;
    }

    setError("");
    setStatus("Removing share...");
    try {
      await apiRequest(
        `/api/opportunities/${selectedOpportunity.id}/shares/${userId}`,
        { method: "DELETE" },
      );
      await loadSharingData(
        selectedOpportunity.id,
        selectedOpportunity.current_user_role,
      );
      await loadTimeline(selectedOpportunity.id);
      setStatus("");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not remove share",
      );
      setStatus("");
    }
  }

  function editTimelineEntry(entry: TimelineEntry) {
    setEditingEntryId(entry.id);
    setEntryForm({
      type: entry.type,
      title: entry.title,
      body: entry.body,
      event_timestamp: toDateTimeInput(entry.event_timestamp),
      follow_up_date: entry.follow_up_date ?? "",
    });
  }

  async function deleteTimelineEntry(entryId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    if (!confirmDelete("this timeline entry, with its notes and comments")) {
      return;
    }

    setError("");
    setStatus("Deleting entry...");
    try {
      await apiRequest(`/api/timeline/${entryId}`, { method: "DELETE" });
      setStatus("");
      await loadTimeline(selectedOpportunityId);
      await loadOpportunities();
      await loadOpportunities();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not delete entry",
      );
      setStatus("");
    }
  }

  async function addNote(entryId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    const body = (noteForms[entryId] ?? "").trim();
    if (!body) {
      return;
    }

    setError("");
    setStatus("Adding note...");
    try {
      await apiRequest(`/api/timeline/${entryId}/notes`, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      setNoteForms({ ...noteForms, [entryId]: "" });
      setStatus("");
      await loadTimeline(selectedOpportunityId);
      await loadOpportunities();
      await loadOpportunities();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add note");
      setStatus("");
    }
  }

  async function saveNote(noteId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    const body = (editingNotes[noteId] ?? "").trim();
    if (!body) {
      return;
    }

    setError("");
    setStatus("Saving note...");
    try {
      await apiRequest(`/api/notes/${noteId}`, {
        method: "PATCH",
        body: JSON.stringify({ body }),
      });
      const nextEditingNotes = { ...editingNotes };
      delete nextEditingNotes[noteId];
      setEditingNotes(nextEditingNotes);
      setStatus("");
      await loadTimeline(selectedOpportunityId);
      await loadOpportunities();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save note",
      );
      setStatus("");
    }
  }

  async function deleteNote(noteId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    if (!confirmDelete("this note and its comments")) {
      return;
    }

    setError("");
    setStatus("Deleting note...");
    try {
      await apiRequest(`/api/notes/${noteId}`, { method: "DELETE" });
      setStatus("");
      await loadTimeline(selectedOpportunityId);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not delete note",
      );
      setStatus("");
    }
  }

  async function addComment(noteId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    const body = (commentForms[noteId] ?? "").trim();
    if (!body) {
      return;
    }

    setError("");
    setStatus("Adding comment...");
    try {
      await apiRequest(`/api/notes/${noteId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      setCommentForms({ ...commentForms, [noteId]: "" });
      setStatus("");
      await loadTimeline(selectedOpportunityId);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not add comment",
      );
      setStatus("");
    }
  }

  async function deleteComment(commentId: number) {
    if (!selectedOpportunityId) {
      return;
    }

    if (!confirmDelete("this comment")) {
      return;
    }

    setError("");
    setStatus("Deleting comment...");
    try {
      await apiRequest(`/api/comments/${commentId}`, { method: "DELETE" });
      setStatus("");
      await loadTimeline(selectedOpportunityId);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not delete comment",
      );
      setStatus("");
    }
  }

  async function markNotificationRead(notificationId: number) {
    setError("");
    try {
      await apiRequest(`/api/notifications/${notificationId}/read`, {
        method: "PATCH",
      });
      await loadNotifications();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not update notification",
      );
    }
  }

  async function markAllNotificationsRead() {
    setError("");
    try {
      await apiRequest("/api/v2/notifications/mark-all-read", {
        method: "POST",
      });
      await loadNotifications();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not update notifications",
      );
    }
  }

  async function applyTimelineFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus("Filtering timeline...");
    try {
      await loadTimeline();
      setStatus("");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not filter timeline",
      );
      setStatus("");
    }
  }

  async function clearTimelineFilters() {
    setTimelineFilters(emptyFilters);
    setError("");
    if (selectedOpportunityId) {
      setStatus("Clearing filters...");
      try {
        const data = await apiRequest<TimelineResponse>(
          `/api/opportunities/${selectedOpportunityId}/timeline`,
        );
        setTimelineEntries(data.entries);
        setStatus("");
      } catch (caught) {
        setError(
          caught instanceof Error ? caught.message : "Could not clear filters",
        );
        setStatus("");
      }
    }
  }

  async function submitAiQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedOpportunityId) {
      return;
    }

    const question = aiQuestion.trim();
    if (!question || aiLoading) {
      return;
    }

    const userMessage: AiChatMessage = { role: "user", body: question };
    setAiQuestion("");
    setAiError("");
    setAiLoading(true);
    setAiConversations((current) => ({
      ...current,
      [selectedOpportunityId]: [
        ...(current[selectedOpportunityId] ?? []),
        userMessage,
      ],
    }));

    try {
      const response = await apiRequest<AiAskResponse>(
        `/api/opportunities/${selectedOpportunityId}/ai/ask`,
        {
          method: "POST",
          body: JSON.stringify({ question }),
        },
      );
      setAiConversations((current) => ({
        ...current,
        [selectedOpportunityId]: [
          ...(current[selectedOpportunityId] ?? []),
          {
            role: "assistant",
            body: response.answer,
            referenced_entry_ids: response.referenced_entry_ids,
          },
        ],
      }));
    } catch (caught) {
      setAiError(
        caught instanceof Error ? caught.message : "AI request failed",
      );
    } finally {
      setAiLoading(false);
    }
  }

  if (!user) {
    return (
      <main className="auth-shell">
        <section className="auth-panel">
          <div>
            <p className="eyebrow">OppTrail</p>
            <h1>Track every sales opportunity from first touch to close.</h1>
            <p className="lede">
              Sign in to manage your opportunity dashboard and timeline notes.
            </p>
          </div>

          <form className="form" onSubmit={submitAuth}>
            <div className="segmented">
              <button
                type="button"
                className={authMode === "signup" ? "active" : ""}
                onClick={() => setAuthMode("signup")}
              >
                Sign up
              </button>
              <button
                type="button"
                className={authMode === "login" ? "active" : ""}
                onClick={() => setAuthMode("login")}
              >
                Sign in
              </button>
            </div>

            {authMode === "signup" && (
              <label>
                Name
                <input
                  value={authName}
                  onChange={(event) => setAuthName(event.target.value)}
                  required
                />
              </label>
            )}

            <label>
              Email
              <input
                type="email"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                required
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={authPassword}
                minLength={8}
                onChange={(event) => setAuthPassword(event.target.value)}
                required
              />
            </label>

            <button className="primary-button" type="submit">
              {authMode === "signup" ? "Create account" : "Sign in"}
            </button>
            {status && <p className="status">{status}</p>}
            {error && <p className="error">{error}</p>}
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OppTrail</p>
          <h1>Opportunities</h1>
        </div>
        <div className="user-block">
          <Link className="secondary-button" to="/search">
            Search
          </Link>
          <div className="notification-menu">
            <button
              type="button"
              className="secondary-button notification-button"
              onClick={() => {
                setShowNotifications(!showNotifications);
                void loadNotifications();
              }}
            >
              Notifications
              {unreadNotificationCount > 0 && (
                <span>{unreadNotificationCount}</span>
              )}
            </button>
            {showNotifications && (
              <div className="notification-panel">
                <div className="section-heading">
                  <h3>Notifications</h3>
                  <button
                    type="button"
                    className="secondary-button compact-button"
                    onClick={() => void loadNotifications()}
                  >
                    Refresh
                  </button>
                </div>
                <div className="notification-controls">
                  <label htmlFor="notification-type-filter">Filter</label>
                  <select
                    id="notification-type-filter"
                    value={notificationTypeFilter}
                    onChange={(event) =>
                      setNotificationTypeFilter(
                        event.target.value as NotificationType | "",
                      )
                    }
                  >
                    <option value="">All types</option>
                    {notificationTypeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="secondary-button compact-button"
                    disabled={unreadNotificationCount === 0}
                    onClick={() => void markAllNotificationsRead()}
                  >
                    Mark all read
                  </button>
                </div>
                {visibleNotifications.length === 0 ? (
                  <p className="empty-state">
                    {notifications.length === 0
                      ? "No notifications yet"
                      : "No notifications of this type"}
                  </p>
                ) : (
                  <div className="notification-list">
                    {visibleNotifications.map((notification) => (
                      <article
                        className={
                          notification.read_at
                            ? "notification-row is-read"
                            : "notification-row"
                        }
                        key={notification.id}
                      >
                        <div>
                          <strong>{notificationText(notification)}</strong>
                          <span>
                            {formatTimestamp(notification.created_at)}
                          </span>
                        </div>
                        {!notification.read_at && (
                          <button
                            type="button"
                            className="secondary-button compact-button"
                            onClick={() =>
                              void markNotificationRead(notification.id)
                            }
                          >
                            Mark read
                          </button>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <span>{user.name}</span>
          <button type="button" className="secondary-button" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <section className="dashboard-layout">
        <form className="form sidebar-form" onSubmit={submitOpportunity}>
          <h2>{editingId ? "Edit Opportunity" : "New Opportunity"}</h2>

          <label>
            Opportunity
            <input
              value={opportunityForm.name}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  name: event.target.value,
                })
              }
              required
            />
          </label>

          <label>
            Account
            <input
              value={opportunityForm.account_name}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  account_name: event.target.value,
                })
              }
              required
            />
          </label>

          <div className="form-grid">
            <label>
              Value
              <input
                type="number"
                min="0"
                step="0.01"
                value={opportunityForm.value}
                onChange={(event) =>
                  setOpportunityForm({
                    ...opportunityForm,
                    value: event.target.value,
                  })
                }
                required
              />
            </label>

            <label>
              Currency
              <input
                maxLength={3}
                minLength={3}
                value={opportunityForm.currency}
                onChange={(event) =>
                  setOpportunityForm({
                    ...opportunityForm,
                    currency: event.target.value,
                  })
                }
                required
              />
            </label>
          </div>

          <label>
            Stage
            <select
              value={opportunityForm.stage}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  stage: event.target.value,
                })
              }
            >
              {stages.map((stage) => (
                <option key={stage}>{stage}</option>
              ))}
            </select>
          </label>

          <label>
            Expected close
            <input
              type="date"
              value={opportunityForm.expected_close_date}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  expected_close_date: event.target.value,
                })
              }
            />
          </label>

          <button className="primary-button" type="submit">
            {editingId ? "Save changes" : "Create opportunity"}
          </button>
          {editingId && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setEditingId(null);
                setOpportunityForm(emptyOpportunityForm);
              }}
            >
              Cancel edit
            </button>
          )}
          {status && <p className="status">{status}</p>}
          {error && <p className="error">{error}</p>}
        </form>

        <section className="workspace">
          {/* The board scrolls horizontally, so it needs to be focusable or a
              keyboard-only user cannot reach the stages past the fold
              (axe: scrollable-region-focusable). */}
          <section
            className="stage-board"
            aria-label="Opportunities grouped by stage"
            tabIndex={0}
          >
            {groupedOpportunities.map(({ stage, items }) => (
              <div className="stage-column" key={stage}>
                <div className="stage-header">
                  <h2>{stage}</h2>
                  <span>{items.length}</span>
                </div>

                {items.length === 0 ? (
                  <p className="empty-state">No opportunities</p>
                ) : (
                  <div className="opportunity-list">
                    {items.map((opportunity) => (
                      <article
                        className={
                          selectedOpportunityId === opportunity.id
                            ? "opportunity-card selected"
                            : "opportunity-card"
                        }
                        key={opportunity.id}
                      >
                        <div>
                          <div className="card-title-row">
                            <h3>{opportunity.name}</h3>
                            {opportunity.stalled && (
                              <span className="stalled-badge">Stalled</span>
                            )}
                          </div>
                          <p>{opportunity.account_name}</p>
                        </div>
                        <dl>
                          <div>
                            <dt>Value</dt>
                            <dd>
                              {opportunity.currency} {opportunity.value}
                            </dd>
                          </div>
                          <div>
                            <dt>Owner</dt>
                            <dd>{opportunity.owner_name}</dd>
                          </div>
                          <div>
                            <dt>Your role</dt>
                            <dd>{opportunity.current_user_role}</dd>
                          </div>
                          <div>
                            <dt>Close</dt>
                            <dd>
                              {opportunity.expected_close_date ?? "Not set"}
                            </dd>
                          </div>
                        </dl>
                        <div className="card-actions">
                          <button
                            type="button"
                            className="primary-button"
                            onClick={() => void openTimeline(opportunity)}
                          >
                            Timeline
                          </button>
                          {opportunity.current_user_role === "owner" && (
                            <>
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={() => editOpportunity(opportunity)}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="danger-button"
                                onClick={() =>
                                  deleteOpportunity(opportunity.id)
                                }
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </section>

          {selectedOpportunity ? (
            <section className="timeline-panel">
              <div className="timeline-heading">
                <div>
                  <p className="eyebrow">{selectedOpportunity.account_name}</p>
                  <h2>{selectedOpportunity.name}</h2>
                  <p className="meta-row">
                    Your role: {selectedOpportunity.current_user_role}
                  </p>
                </div>
                <div className="export-actions">
                  <a
                    className="secondary-button"
                    href={`/api/opportunities/${selectedOpportunity.id}/export/pdf`}
                  >
                    PDF
                  </a>
                  <a
                    className="secondary-button"
                    href={`/api/opportunities/${selectedOpportunity.id}/export/csv`}
                  >
                    CSV
                  </a>
                  <a
                    className="secondary-button"
                    href={`/api/opportunities/${selectedOpportunity.id}/export/json`}
                  >
                    JSON
                  </a>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void loadTimeline(selectedOpportunity.id)}
                  >
                    Refresh
                  </button>
                </div>
              </div>

              {canManageSelectedOpportunity && (
                <section className="sharing-panel">
                  <div className="section-heading">
                    <h3>Sharing</h3>
                    <span>{shares.length} shared</span>
                  </div>

                  <form className="share-form" onSubmit={submitShare}>
                    <input
                      type="email"
                      placeholder="Colleague email"
                      value={shareForm.email}
                      onChange={(event) =>
                        setShareForm({
                          ...shareForm,
                          email: event.target.value,
                        })
                      }
                      required
                    />
                    <select
                      aria-label="Role for the colleague being invited"
                      value={shareForm.role}
                      onChange={(event) =>
                        setShareForm({
                          ...shareForm,
                          role: event.target.value as "viewer" | "editor",
                        })
                      }
                    >
                      <option value="viewer">Viewer</option>
                      <option value="editor">Editor</option>
                    </select>
                    <button className="primary-button" type="submit">
                      Share
                    </button>
                  </form>

                  {shares.length === 0 ? (
                    <p className="empty-state">No shared colleagues</p>
                  ) : (
                    <div className="share-list">
                      {shares.map((share) => (
                        <div className="share-row" key={share.user_id}>
                          <div>
                            <strong>{share.name}</strong>
                            <p>{share.email}</p>
                          </div>
                          <select
                            aria-label={`Role for ${share.name}`}
                            value={share.role}
                            onChange={(event) =>
                              updateShareRole(
                                share.user_id,
                                event.target.value as "viewer" | "editor",
                              )
                            }
                          >
                            <option value="viewer">Viewer</option>
                            <option value="editor">Editor</option>
                          </select>
                          <button
                            type="button"
                            className="danger-button"
                            onClick={() => removeShare(share.user_id)}
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <details className="audit-panel">
                    <summary>Audit Log</summary>
                    {auditLog.length === 0 ? (
                      <p className="empty-state">No audit events yet</p>
                    ) : (
                      <div className="audit-list">
                        {auditLog.map((item) => (
                          <div className="audit-row" key={item.id}>
                            <strong>{item.action}</strong>
                            <span>{formatTimestamp(item.created_at)}</span>
                            <p>{item.actor_name ?? "System"}</p>
                            <code>{JSON.stringify(item.detail)}</code>
                          </div>
                        ))}
                      </div>
                    )}
                  </details>
                </section>
              )}

              <form className="filter-bar" onSubmit={applyTimelineFilters}>
                <input
                  aria-label="Filter the timeline by keyword"
                  placeholder="Keyword"
                  value={timelineFilters.q}
                  onChange={(event) =>
                    setTimelineFilters({
                      ...timelineFilters,
                      q: event.target.value,
                    })
                  }
                />
                <select
                  aria-label="Filter the timeline by entry type"
                  value={timelineFilters.type}
                  onChange={(event) =>
                    setTimelineFilters({
                      ...timelineFilters,
                      type: event.target.value,
                    })
                  }
                >
                  <option value="">All types</option>
                  {entryTypes.map((entryType) => (
                    <option key={entryType.value} value={entryType.value}>
                      {entryType.label}
                    </option>
                  ))}
                </select>
                <input
                  aria-label="Show entries from"
                  type="datetime-local"
                  value={timelineFilters.from}
                  onChange={(event) =>
                    setTimelineFilters({
                      ...timelineFilters,
                      from: event.target.value,
                    })
                  }
                />
                <input
                  aria-label="Show entries up to"
                  type="datetime-local"
                  value={timelineFilters.to}
                  onChange={(event) =>
                    setTimelineFilters({
                      ...timelineFilters,
                      to: event.target.value,
                    })
                  }
                />
                <input
                  aria-label="Filter the timeline by author id"
                  type="number"
                  min="1"
                  placeholder="Author ID"
                  value={timelineFilters.author_id}
                  onChange={(event) =>
                    setTimelineFilters({
                      ...timelineFilters,
                      author_id: event.target.value,
                    })
                  }
                />
                <button className="primary-button" type="submit">
                  Filter
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={clearTimelineFilters}
                >
                  Clear
                </button>
              </form>

              {canWriteSelectedTimeline && (
                <form className="timeline-form" onSubmit={submitTimelineEntry}>
                  <div className="timeline-form-grid">
                    <label>
                      Type
                      <select
                        value={entryForm.type}
                        onChange={(event) =>
                          setEntryForm({
                            ...entryForm,
                            type: event.target.value as EntryType,
                          })
                        }
                      >
                        {entryTypes.map((entryType) => (
                          <option key={entryType.value} value={entryType.value}>
                            {entryType.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Event time
                      <input
                        type="datetime-local"
                        value={entryForm.event_timestamp}
                        onChange={(event) =>
                          setEntryForm({
                            ...entryForm,
                            event_timestamp: event.target.value,
                          })
                        }
                        required
                      />
                    </label>
                    <label>
                      Follow up
                      <input
                        type="date"
                        value={entryForm.follow_up_date}
                        onChange={(event) =>
                          setEntryForm({
                            ...entryForm,
                            follow_up_date: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    Title
                    <input
                      value={entryForm.title}
                      onChange={(event) =>
                        setEntryForm({
                          ...entryForm,
                          title: event.target.value,
                        })
                      }
                      required
                    />
                  </label>
                  <label>
                    Body
                    <textarea
                      value={entryForm.body}
                      onChange={(event) =>
                        setEntryForm({ ...entryForm, body: event.target.value })
                      }
                      rows={3}
                    />
                  </label>
                  <div className="inline-actions">
                    <button className="primary-button" type="submit">
                      {editingEntryId ? "Save Entry" : "Add Entry"}
                    </button>
                    {editingEntryId && (
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => {
                          setEditingEntryId(null);
                          setEntryForm({
                            ...emptyEntryForm,
                            event_timestamp: nowDateTimeInput(),
                          });
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </form>
              )}

              {timelineEntries.length === 0 ? (
                <p className="empty-state">
                  No timeline entries match this view.
                </p>
              ) : (
                <div className="timeline-list">
                  {timelineEntries.map((entry) => (
                    <article className="timeline-entry" key={entry.id}>
                      <div className={`timeline-marker ${entry.type}`} />
                      <div className="timeline-entry-body">
                        <div className="timeline-entry-header">
                          <div>
                            <div className="meta-row">
                              <span className={`type-badge ${entry.type}`}>
                                {
                                  entryTypes.find(
                                    (entryType) =>
                                      entryType.value === entry.type,
                                  )?.label
                                }
                              </span>
                              {entry.system_generated && (
                                <span className="system-badge">System</span>
                              )}
                              <span>
                                {formatTimestamp(entry.event_timestamp)}
                              </span>
                            </div>
                            <h3>{entry.title}</h3>
                            <p className="timeline-copy">
                              {entry.body || "No details"}
                            </p>
                          </div>
                          {canChangeItem(entry.created_by) &&
                            !entry.system_generated && (
                              <div className="inline-actions">
                                {canEdit(entry.created_by) && (
                                  <button
                                    type="button"
                                    className="secondary-button"
                                    onClick={() => editTimelineEntry(entry)}
                                  >
                                    Edit
                                  </button>
                                )}
                                {canDelete(entry.created_by) && (
                                  <button
                                    type="button"
                                    className="danger-button"
                                    onClick={() =>
                                      deleteTimelineEntry(entry.id)
                                    }
                                  >
                                    Delete
                                  </button>
                                )}
                              </div>
                            )}
                        </div>
                        <p className="meta-row">
                          By {entry.author_name ?? "System"}
                          {entry.follow_up_date
                            ? ` | Follow up ${entry.follow_up_date}`
                            : ""}
                        </p>

                        <div className="notes-list">
                          {entry.notes.map((note) => (
                            <section className="note-block" key={note.id}>
                              <div className="note-header">
                                <p>
                                  {note.author_name}
                                  {note.edited ? " | edited" : ""}
                                </p>
                                {canChangeItem(note.created_by) && (
                                  <div className="inline-actions">
                                    {canEdit(note.created_by) && (
                                      <button
                                        type="button"
                                        className="secondary-button"
                                        onClick={() =>
                                          setEditingNotes({
                                            ...editingNotes,
                                            [note.id]: note.body,
                                          })
                                        }
                                      >
                                        Edit
                                      </button>
                                    )}
                                    {canDelete(note.created_by) && (
                                      <button
                                        type="button"
                                        className="danger-button"
                                        onClick={() => deleteNote(note.id)}
                                      >
                                        Delete
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>

                              {editingNotes[note.id] !== undefined ? (
                                <div className="stacked-form">
                                  <textarea
                                    aria-label="Edit this note"
                                    value={editingNotes[note.id]}
                                    onChange={(event) =>
                                      setEditingNotes({
                                        ...editingNotes,
                                        [note.id]: event.target.value,
                                      })
                                    }
                                    rows={3}
                                  />
                                  <div className="inline-actions">
                                    <button
                                      type="button"
                                      className="primary-button"
                                      onClick={() => saveNote(note.id)}
                                    >
                                      Save
                                    </button>
                                    <button
                                      type="button"
                                      className="secondary-button"
                                      onClick={() => {
                                        const nextEditingNotes = {
                                          ...editingNotes,
                                        };
                                        delete nextEditingNotes[note.id];
                                        setEditingNotes(nextEditingNotes);
                                      }}
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <MarkdownText content={note.body} />
                              )}

                              <div className="comment-list">
                                {note.comments.map((comment) => (
                                  <div className="comment-row" key={comment.id}>
                                    <div>
                                      <strong>{comment.author_name}</strong>
                                      <MarkdownText content={comment.body} />
                                    </div>
                                    {canDelete(comment.created_by) && (
                                      <button
                                        type="button"
                                        className="danger-button compact"
                                        onClick={() =>
                                          deleteComment(comment.id)
                                        }
                                      >
                                        Delete
                                      </button>
                                    )}
                                  </div>
                                ))}
                              </div>

                              {canWriteSelectedTimeline && (
                                <div className="inline-compose">
                                  <input
                                    aria-label="Add a comment to this note"
                                    placeholder="Add comment"
                                    value={commentForms[note.id] ?? ""}
                                    onChange={(event) =>
                                      setCommentForms({
                                        ...commentForms,
                                        [note.id]: event.target.value,
                                      })
                                    }
                                  />
                                  <button
                                    type="button"
                                    className="secondary-button"
                                    onClick={() => addComment(note.id)}
                                  >
                                    Post
                                  </button>
                                </div>
                              )}
                            </section>
                          ))}

                          {canWriteSelectedTimeline && (
                            <div className="inline-compose">
                              <input
                                aria-label="Add a note to this entry"
                                placeholder="Add note"
                                value={noteForms[entry.id] ?? ""}
                                onChange={(event) =>
                                  setNoteForms({
                                    ...noteForms,
                                    [entry.id]: event.target.value,
                                  })
                                }
                              />
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={() => addNote(entry.id)}
                              >
                                Add Note
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
              <aside className="ai-sidebar">
                <div className="section-heading">
                  <h3>AI Agent</h3>
                  <span>Read-only</span>
                </div>

                <div className="ai-chat" ref={aiChatRef}>
                  {aiMessages.length === 0 ? (
                    <p className="empty-state">Ask a timeline question.</p>
                  ) : (
                    aiMessages.map((message, index) => (
                      <div className={`ai-message ${message.role}`} key={index}>
                        <p>{message.body}</p>
                        {message.referenced_entry_ids &&
                          message.referenced_entry_ids.length > 0 && (
                            <span>
                              Entries: {message.referenced_entry_ids.join(", ")}
                            </span>
                          )}
                      </div>
                    ))
                  )}
                  {aiLoading && <p className="status">Thinking...</p>}
                  {aiError && <p className="error">{aiError}</p>}
                </div>

                <form className="ai-form" onSubmit={submitAiQuestion}>
                  <textarea
                    aria-label="Ask the read-only AI agent about this timeline"
                    value={aiQuestion}
                    onChange={(event) => setAiQuestion(event.target.value)}
                    placeholder="Where do we stand?"
                    rows={3}
                    required
                  />
                  <button
                    type="submit"
                    className="primary-button"
                    disabled={aiLoading}
                  >
                    Ask
                  </button>
                </form>
              </aside>
            </section>
          ) : (
            <section className="timeline-panel empty-panel">
              <h2>Select an opportunity to open its timeline.</h2>
            </section>
          )}
        </section>
      </section>
    </main>
  );
}
