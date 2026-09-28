"use client";

import { useState } from "react";

import {
  reactionEmoji,
  type Access,
  type Comment,
  type CommentThread as Thread,
} from "../lib/domain";
import {
  useAddComment,
  useResolveThread,
  useSession,
  useSetReaction,
} from "../lib/queries";
import { MarkdownText } from "./MarkdownText";
import { Composer } from "./RichTextEditor";

/**
 * The reactions on one comment or reply (milestone 3.3a): the emoji already
 * used, as toggleable pills, plus -- progressive disclosure, like the
 * composer's own controls -- a React trigger that reveals the fixed seven-item
 * set (`lib/domain.ts`'s `reactionEmoji`) rather than showing all seven on
 * every comment.
 */
function ReactionBar({
  commentId,
  reactions,
  canReact,
}: {
  commentId: number;
  reactions: Comment["reactions"];
  canReact: boolean;
}) {
  const session = useSession();
  const setReaction = useSetReaction();
  const [pickerOpen, setPickerOpen] = useState(false);
  const userId = session.data?.id;

  const used = reactionEmoji
    .map((emoji) => ({
      emoji,
      count: reactions.filter((reaction) => reaction.emoji === emoji).length,
      mine: reactions.some(
        (reaction) => reaction.emoji === emoji && reaction.user_id === userId,
      ),
    }))
    .filter((entry) => entry.count > 0);

  if (!canReact && used.length === 0) {
    return null;
  }

  return (
    <div className="reaction-bar">
      {used.map(({ emoji, count, mine }) => (
        <button
          key={emoji}
          type="button"
          className={`reaction-pill${mine ? " is-mine" : ""}`}
          aria-pressed={mine}
          aria-label={
            mine ? `Remove your ${emoji} reaction` : `React with ${emoji}`
          }
          disabled={!canReact}
          onClick={() =>
            setReaction.mutate({ commentId, emoji, reacted: !mine })
          }
        >
          {emoji} {count}
        </button>
      ))}
      {canReact && (
        <div className="reaction-picker-trigger">
          <button
            type="button"
            className="secondary-button compact"
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen((open) => !open)}
          >
            React
          </button>
          {pickerOpen && (
            <div
              className="reaction-picker"
              role="group"
              aria-label="Choose a reaction"
            >
              {reactionEmoji.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  className="reaction-pill"
                  aria-label={`React with ${emoji}`}
                  onClick={() => {
                    setReaction.mutate({ commentId, emoji, reacted: true });
                    setPickerOpen(false);
                  }}
                >
                  {emoji}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * One discussion on a note: the comment that opened it, the answers under it,
 * and whether it is finished (milestone 3.3, `docs/FEATURES.md` §7).
 *
 * Two rules from the backend decide what is drawn here:
 *
 * - **Replies are one level deep** (D-127), so Reply sits on the thread
 *   rather than on each message. A control on a reply would ask for a
 *   comment the API answers 400 to.
 * - **Resolving is the author-or-owner rule** (D-128), the same one that
 *   decides who may delete an item, so the control is offered on exactly the
 *   threads `access.canChangeItem` allows — which is what `lib/permissions.ts`
 *   exists for.
 *
 * A resolved thread collapses to its one-line outcome, because a discussion
 * that stayed open would make a long deal unreadable — which is the whole
 * reason `FEATURES.md` asks for resolve. It is never hidden: Show reopens the
 * reading, separately from Reopen, which changes the state for everybody.
 */
export function CommentThread({
  thread,
  access,
  onDelete,
}: {
  thread: Thread;
  access: Access;
  /** Delete with Undo, owned by the note so one toast serves them all. */
  onDelete: (commentId: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const addComment = useAddComment();
  const resolveThread = useResolveThread();
  const resolved = thread.resolved_at !== null;
  // Resolving and deleting are one rule with one answer (`lib/permissions.ts`).
  const canManageThread = access.canChangeItem(thread.created_by);

  if (resolved && !expanded) {
    return (
      <div className="comment-thread is-resolved is-collapsed">
        <p className="comment-resolved">
          Resolved by {thread.resolved_by_name ?? "a colleague"}
        </p>
        <button
          type="button"
          className="secondary-button compact"
          aria-expanded={false}
          onClick={() => setExpanded(true)}
        >
          Show
        </button>
      </div>
    );
  }

  return (
    <div className={`comment-thread${resolved ? " is-resolved" : ""}`}>
      {resolved && (
        <div className="comment-resolved-header">
          <p className="comment-resolved">
            Resolved by {thread.resolved_by_name ?? "a colleague"}
          </p>
          <button
            type="button"
            className="secondary-button compact"
            aria-expanded
            onClick={() => setExpanded(false)}
          >
            Hide
          </button>
        </div>
      )}

      <div className="comment-row">
        <div>
          <strong>{thread.author_name}</strong>
          <MarkdownText content={thread.body} />
          <ReactionBar
            commentId={thread.id}
            reactions={thread.reactions}
            canReact={access.canWriteTimeline}
          />
        </div>
        <div className="inline-actions">
          {canManageThread && (
            <button
              type="button"
              className="secondary-button compact"
              onClick={() =>
                resolveThread.mutate({
                  commentId: thread.id,
                  resolved: !resolved,
                })
              }
            >
              {resolved ? "Reopen" : "Resolve"}
            </button>
          )}
          {canManageThread && (
            <button
              type="button"
              className="danger-button compact"
              onClick={() => onDelete(thread.id)}
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {thread.replies.length > 0 && (
        <div className="comment-replies">
          {thread.replies.map((reply) => (
            <div className="comment-row" key={reply.id}>
              <div>
                <strong>{reply.author_name}</strong>
                <MarkdownText content={reply.body} />
                <ReactionBar
                  commentId={reply.id}
                  reactions={reply.reactions}
                  canReact={access.canWriteTimeline}
                />
              </div>
              {access.canChangeItem(reply.created_by) && (
                <button
                  type="button"
                  className="danger-button compact"
                  onClick={() => onDelete(reply.id)}
                >
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* A finished thread offers no Reply: answering it is what Reopen is
          for, and a reply nobody is looking at is the state resolve exists
          to prevent. */}
      {access.canWriteTimeline && !resolved && (
        <div className="comment-replies">
          <Composer
            label={`Reply to ${thread.author_name}`}
            trigger="Reply"
            placeholder="Write a reply"
            submitLabel="Reply"
            onSubmit={(body) =>
              addComment.mutateAsync({
                noteId: thread.note_id,
                body,
                parentId: thread.id,
              })
            }
          />
        </div>
      )}

      {resolveThread.isError && (
        <p className="error">{resolveThread.error?.message}</p>
      )}
      {addComment.isError && (
        <p className="error">{addComment.error.message}</p>
      )}
    </div>
  );
}
