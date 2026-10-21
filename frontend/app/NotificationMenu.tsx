"use client";

import { useMemo, useState } from "react";
import { Link } from "react-router";

import { notificationTypeOptions, type NotificationType } from "../lib/domain";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "../lib/queries";
import { notificationHref, notificationText } from "../lib/notifications";
import { formatTimestamp } from "../lib/time";

/**
 * The inbox from milestone 1.7: full history rather than unread-only, read
 * from `GET /api/v2/notifications` and marked read through v1's per-row PATCH
 * (`CLAUDE.md`, "Notifications").
 *
 * **Each line is a link since milestone 6.1a**, on the human's ruling. Until
 * then the panel rendered no anchor at all, so being told somebody mentioned
 * you in a comment left you to go and find it — the same failure milestone 6.0
 * removed from search results, and reusing that mechanism rather than a second
 * one (`lib/notifications.ts`'s `notificationHref`). Following a line marks it
 * read and closes the panel: clicking through *is* reading it, and a panel left
 * open would cover the row it just sent the reader to. The explicit Mark read
 * button stays for the notifications that lead nowhere and for a reader
 * clearing the list without visiting anything.
 */
export function NotificationMenu() {
  const [open, setOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState<NotificationType | "">("");
  const notifications = useNotifications(true);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const items = useMemo(() => notifications.data ?? [], [notifications.data]);
  const unreadCount = items.filter((item) => !item.read_at).length;
  // Filtered over the loaded page: an inbox at this app's scale never needs a
  // second round trip to narrow a type the first page already holds. The
  // server-side filter (`?type=`) is what a non-UI client uses.
  const visible = typeFilter
    ? items.filter((item) => item.type === typeFilter)
    : items;

  return (
    <div className="notification-menu">
      <button
        type="button"
        className="ghost-button notification-button"
        onClick={() => {
          setOpen(!open);
          void notifications.refetch();
        }}
      >
        Notifications
        {unreadCount > 0 && <span>{unreadCount}</span>}
      </button>
      {open && (
        <div className="notification-panel">
          <div className="section-heading">
            <h3>Notifications</h3>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void notifications.refetch()}
            >
              Refresh
            </button>
          </div>
          <div className="notification-controls">
            <label htmlFor="notification-type-filter">Filter</label>
            <select
              id="notification-type-filter"
              value={typeFilter}
              onChange={(event) =>
                setTypeFilter(event.target.value as NotificationType | "")
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
              className="secondary-button"
              disabled={unreadCount === 0}
              onClick={() => markAllRead.mutate()}
            >
              Mark all read
            </button>
          </div>
          {(markRead.isError || markAllRead.isError) && (
            <p className="error">
              {(markRead.error ?? markAllRead.error)?.message}
            </p>
          )}
          {visible.length === 0 ? (
            <p className="empty-state">
              {items.length === 0
                ? "No notifications yet"
                : "No notifications of this type"}
            </p>
          ) : (
            <div className="notification-list">
              {visible.map((notification) => {
                const href = notificationHref(notification);
                return (
                  <article
                    className={
                      notification.read_at
                        ? "notification-row is-read"
                        : "notification-row"
                    }
                    key={notification.id}
                  >
                    <div>
                      {href ? (
                        <Link
                          className="notification-link"
                          to={href}
                          onClick={() => {
                            if (!notification.read_at) {
                              markRead.mutate(notification.id);
                            }
                            setOpen(false);
                          }}
                        >
                          {notificationText(notification)}
                        </Link>
                      ) : (
                        <strong>{notificationText(notification)}</strong>
                      )}
                      <span>{formatTimestamp(notification.created_at)}</span>
                    </div>
                    {!notification.read_at && (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => markRead.mutate(notification.id)}
                      >
                        Mark read
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
