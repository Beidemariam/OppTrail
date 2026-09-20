"use client";

import { FormEvent, useState, type RefObject } from "react";

import { entryTypes, type EntryType, type TimelineEntry } from "../lib/domain";
import { submitFormOnModEnter } from "../lib/keyboard";
import { useSaveTimelineEntry } from "../lib/queries";
import {
  localInputToUtc,
  nowDateTimeInput,
  toDateTimeInput,
} from "../lib/time";

interface EntryFormState {
  type: EntryType;
  title: string;
  body: string;
  event_timestamp: string;
  follow_up_date: string;
}

function formFor(entry: TimelineEntry | null): EntryFormState {
  if (!entry) {
    return {
      type: "call",
      title: "",
      body: "",
      event_timestamp: nowDateTimeInput(),
      follow_up_date: "",
    };
  }
  return {
    type: entry.type,
    title: entry.title,
    body: entry.body,
    event_timestamp: toDateTimeInput(entry.event_timestamp),
    follow_up_date: entry.follow_up_date ?? "",
  };
}

/**
 * Adds a timeline entry, or saves the one the timeline handed it. The parent
 * re-keys this component on the entry being edited, so the fields reload
 * without an effect chasing props.
 */
export function TimelineEntryForm({
  opportunityId,
  editing,
  titleRef,
  onDone,
}: {
  opportunityId: number;
  editing: TimelineEntry | null;
  /** Where `c` puts the cursor while a timeline is open (milestone 2.4a). */
  titleRef?: RefObject<HTMLInputElement | null>;
  onDone: () => void;
}) {
  const [form, setForm] = useState(() => formFor(editing));
  const save = useSaveTimelineEntry(opportunityId);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      {
        entryId: editing?.id ?? null,
        payload: {
          ...form,
          // `datetime-local` is always local wall-clock time; the API stores
          // canonical UTC (`lib/time.ts`).
          event_timestamp: localInputToUtc(form.event_timestamp),
          follow_up_date: form.follow_up_date || null,
        },
      },
      { onSuccess: () => onDone() },
    );
  }

  return (
    <form
      className="timeline-form"
      onSubmit={submit}
      // Ctrl Enter submits from anywhere in the form, including the textarea,
      // where a bare Enter is a newline.
      onKeyDown={submitFormOnModEnter()}
    >
      <div className="timeline-form-grid">
        <label>
          Type
          <select
            value={form.type}
            onChange={(event) =>
              setForm({ ...form, type: event.target.value as EntryType })
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
            value={form.event_timestamp}
            onChange={(event) =>
              setForm({ ...form, event_timestamp: event.target.value })
            }
            required
          />
        </label>
        <label>
          Follow up
          <input
            type="date"
            value={form.follow_up_date}
            onChange={(event) =>
              setForm({ ...form, follow_up_date: event.target.value })
            }
          />
        </label>
      </div>
      <label>
        Title
        <input
          ref={titleRef}
          value={form.title}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
          required
        />
      </label>
      <label>
        Body
        <textarea
          value={form.body}
          onChange={(event) => setForm({ ...form, body: event.target.value })}
          rows={3}
        />
      </label>
      <div className="inline-actions">
        <button className="primary-button" type="submit">
          {editing ? "Save Entry" : "Add Entry"}
        </button>
        {editing && (
          <button className="secondary-button" type="button" onClick={onDone}>
            Cancel
          </button>
        )}
      </div>
      {save.isPending && (
        <p className="status">
          {editing ? "Updating entry..." : "Adding entry..."}
        </p>
      )}
      {save.isError && <p className="error">{save.error.message}</p>}
    </form>
  );
}
