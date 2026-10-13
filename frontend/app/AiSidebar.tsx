"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { submitFormOnModEnter } from "../lib/keyboard";
import { useAiConversation, useStreamAi } from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";

/**
 * The read-only AI agent (`backend/app/routes_ai.py`).
 *
 * Read-only is enforced by the server — a read-only connection and no tool
 * surface — not by anything here. Viewers may ask questions too.
 *
 * **The answer streams** (milestone 6.4). D-168 measured this deployment's
 * model at a ~29 second floor and 40.1 seconds for a long deal, and the
 * human's report at the Phase 4 gate was that the feature did not work — it
 * did, eventually, behind a spinner. Watching an answer being written is a
 * different experience from watching a spinner for the same duration, and it
 * is the whole of what changed: same prompt, same context, same answer.
 *
 * **And it can be scoped to a date range**, which §14 asks for. Collapsed
 * behind a trigger like every other control that is not always needed
 * (D-110): most questions are about the deal, and the range is for the ones
 * that are about a quarter.
 */
export function AiSidebar({ opportunityId }: { opportunityId: number }) {
  const [question, setQuestion] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const conversation = useAiConversation(opportunityId);
  const { ask, pending, error } = useStreamAi(opportunityId);
  const chatRef = useRef<HTMLDivElement | null>(null);
  const scopeTriggerRef = useRef<HTMLButtonElement | null>(null);
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const scope = useInlineEditor(scopeTriggerRef, scopeRef);

  const messages = useMemo(() => conversation.data ?? [], [conversation.data]);
  const scoped = Boolean(since || until);

  useEffect(() => {
    const chat = chatRef.current;
    if (!chat) {
      return;
    }
    chat.scrollTop = chat.scrollHeight;
  }, [messages, pending, error]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || pending) {
      return;
    }
    setQuestion("");
    void ask(asked, {
      since: since || undefined,
      until: until || undefined,
    });
  }

  return (
    <aside className="ai-sidebar">
      <div className="section-heading">
        <h3>AI Agent</h3>
        <span>Read-only</span>
      </div>

      <div className="ai-chat" ref={chatRef}>
        {messages.length === 0 ? (
          <p className="empty-state">Ask a timeline question.</p>
        ) : (
          messages.map((message, index) => (
            <div className={`ai-message ${message.role}`} key={index}>
              {/* An empty streaming message is the moment between the
                  question landing and the first token: the reader needs to
                  know something is happening, and "Thinking..." under the
                  transcript would be a second place to look. */}
              <p>
                {message.body ||
                  (message.streaming ? "Thinking..." : "No answer")}
                {message.streaming && message.body ? (
                  <span className="ai-cursor" aria-hidden="true" />
                ) : null}
              </p>
              {message.referenced_entry_numbers &&
                message.referenced_entry_numbers.length > 0 && (
                  <span>
                    Entries: {message.referenced_entry_numbers.join(", ")}
                  </span>
                )}
            </div>
          ))
        )}
        {error && <p className="error">{error}</p>}
      </div>

      {/* The range the next question will be asked over. Outside the form so
          it survives asking, because a reader scoping to a quarter usually
          has more than one question about it. */}
      <div className="ai-scope">
        <button
          type="button"
          className="disclosure-button"
          ref={scopeTriggerRef}
          aria-expanded={scope.editing}
          onClick={scope.editing ? scope.close : scope.open}
        >
          <span aria-hidden="true">{scope.editing ? "-" : "+"}</span>{" "}
          {scoped ? scopeLabel(since, until) : "Limit to dates"}
        </button>
        {scope.editing && (
          <div className="ai-scope-fields" ref={scopeRef}>
            <label>
              From
              <input
                type="date"
                value={since}
                max={until || undefined}
                onChange={(event) => setSince(event.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                value={until}
                min={since || undefined}
                onChange={(event) => setUntil(event.target.value)}
              />
            </label>
            {scoped && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setSince("");
                  setUntil("");
                }}
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      <form className="ai-form" onSubmit={submit}>
        <textarea
          aria-label="Ask the read-only AI agent about this timeline"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={submitFormOnModEnter()}
          placeholder="Where do we stand?"
          rows={3}
          required
        />
        <button type="submit" className="primary-button" disabled={pending}>
          Ask
        </button>
      </form>
    </aside>
  );
}

/** The range as the trigger's own label, so the scope is legible while the
 * control is shut — the rule `TimelineFilterBar` follows (D-136 finding 5). */
function scopeLabel(since: string, until: string): string {
  if (since && until) {
    return `${since} to ${until}`;
  }
  return since ? `From ${since}` : `Up to ${until}`;
}
