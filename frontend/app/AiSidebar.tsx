"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { submitFormOnModEnter } from "../lib/keyboard";
import { useAiConversation, useAskAi } from "../lib/queries";

/**
 * The read-only AI agent (`backend/app/routes_ai.py`).
 *
 * Read-only is enforced by the server — a read-only connection and no tool
 * surface — not by anything here. Viewers may ask questions too.
 */
export function AiSidebar({ opportunityId }: { opportunityId: number }) {
  const [question, setQuestion] = useState("");
  const conversation = useAiConversation(opportunityId);
  const ask = useAskAi(opportunityId);
  const chatRef = useRef<HTMLDivElement | null>(null);

  const messages = useMemo(() => conversation.data ?? [], [conversation.data]);

  useEffect(() => {
    const chat = chatRef.current;
    if (!chat) {
      return;
    }
    chat.scrollTop = chat.scrollHeight;
  }, [messages, ask.isPending, ask.isError]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || ask.isPending) {
      return;
    }
    setQuestion("");
    ask.mutate(asked);
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
              <p>{message.body}</p>
              {message.referenced_entry_numbers &&
                message.referenced_entry_numbers.length > 0 && (
                  <span>
                    Entries: {message.referenced_entry_numbers.join(", ")}
                  </span>
                )}
            </div>
          ))
        )}
        {ask.isPending && <p className="status">Thinking...</p>}
        {ask.isError && <p className="error">{ask.error.message}</p>}
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
        <button
          type="submit"
          className="primary-button"
          disabled={ask.isPending}
        >
          Ask
        </button>
      </form>
    </aside>
  );
}
