"use client";

import { ChangeEvent, FormEvent, useState, type RefObject } from "react";

import {
  entryTypes,
  type CustomValues,
  type EntryType,
  type TimelineEntry,
} from "../lib/domain";
import { submitFormOnModEnter } from "../lib/keyboard";
import {
  useCustomFields,
  useSaveTimelineEntry,
  useUploadAttachment,
} from "../lib/queries";
import {
  localInputToUtc,
  nowDateTimeInput,
  toDateTimeInput,
} from "../lib/time";
import { CustomFieldInputs } from "./CustomFieldInputs";
import { RichTextEditor } from "./RichTextEditor";

interface EntryFormState {
  type: EntryType;
  title: string;
  body: string;
  event_timestamp: string;
  /** The entry's custom field values (milestone 6.1). A whole set, posted
   * with the entry -- see `app/CustomFieldInputs.tsx`. */
  custom_values: CustomValues;
}

function formFor(entry: TimelineEntry | null): EntryFormState {
  if (!entry) {
    return {
      type: "call",
      title: "",
      body: "",
      event_timestamp: nowDateTimeInput(),
      custom_values: {},
    };
  }
  return {
    type: entry.type,
    title: entry.title,
    body: entry.body,
    event_timestamp: toDateTimeInput(entry.event_timestamp),
    custom_values: (entry.custom_values ?? {}) as CustomValues,
  };
}

/**
 * Adds a timeline entry, or saves the one the timeline handed it. The parent
 * re-keys this component on the entry being edited, so the fields reload
 * without an effect chasing props.
 *
 * **No "Follow up" field since milestone 4.2.** A follow-up is a task now
 * (`app/TaskPanel.tsx`), and the existing dates were migrated into tasks by
 * revision `0010_follow_ups_to_tasks`. Leaving the field here would have been
 * the worst of the three states: new follow-ups would keep landing on a column
 * the task list does not read, so the two would diverge for as long as both
 * existed (**D-144**). `timeline_entries.follow_up_date` itself stays until
 * Phase 6 per `docs/ROADMAP.md`'s breaking-changes table, holding the values the
 * migration copied.
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
  const [file, setFile] = useState<File | null>(null);
  // The entry this form has already created, if the save succeeded and the
  // upload after it did not. Without it, pressing the button again would post
  // a second entry rather than retrying the file (milestone 4.3a).
  const [createdId, setCreatedId] = useState<number | null>(null);
  const customFields = useCustomFields("entry");
  const save = useSaveTimelineEntry(opportunityId);
  const upload = useUploadAttachment();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const saved = await save
      .mutateAsync({
        entryId: createdId ?? editing?.id ?? null,
        payload: {
          ...form,
          // `datetime-local` is always local wall-clock time; the API stores
          // canonical UTC (`lib/time.ts`).
          event_timestamp: localInputToUtc(form.event_timestamp),
        },
      })
      .then(
        (entry) => entry,
        () => null,
      );
    // `save.isError` renders below; the draft stays where it is.
    if (!saved) {
      return;
    }
    setCreatedId(saved.id);

    if (file) {
      // The entry has to exist before its file can hang off it, so this is one
      // request after the other rather than one request carrying both. That is
      // also why the failure below has its own sentence: the entry is already
      // posted by the time a refused file is known about, and telling somebody
      // their entry failed when it did not is worse than telling them nothing.
      const attached = await upload
        .mutateAsync({ entryId: saved.id, file })
        .then(
          () => true,
          () => false,
        );
      if (!attached) {
        return;
      }
    }
    onDone();
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  return (
    <form
      className="timeline-form"
      onSubmit={submit}
      // Ctrl Enter submits from anywhere in the form, including the body
      // composer, where a bare Enter is a new paragraph.
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
      {/* The body is the rich composer (milestone 3.1), so its name is an
          `aria-label` on the editable region rather than a `<label>` — a
          contenteditable element cannot be a label's target. The caption is
          still on screen, the way the filter bars carry both. */}
      <div className="field">
        <span className="field-caption">Body</span>
        <RichTextEditor
          label="Body"
          placeholder="What happened?"
          value={form.body}
          onChange={(body) => setForm({ ...form, body })}
        />
      </div>
      {/* Whatever this team decided to track that nobody anticipated
          (milestone 6.1, `docs/FEATURES.md` §3). Renders nothing when no entry
          fields are defined, which is every deployment until somebody defines
          one. */}
      <CustomFieldInputs
        fields={customFields.data ?? []}
        values={form.custom_values}
        onChange={(custom_values) => setForm({ ...form, custom_values })}
      />
      {/* Attaching where a person writes (milestone 4.3a). 4.3 put the control
          on the posted card only, which is where a file is *read*; the human
          looked for it in this form twice -- "I can't find the attach button
          on any entry when I edit or try to create new" -- and that is the
          moment a proposal is actually to hand. The card keeps its own
          control, because a file that arrives later (the signed copy) should
          not require editing the entry to add. */}
      <label className="entry-file">
        Attach a file (optional)
        <input type="file" onChange={chooseFile} />
      </label>
      <div className="inline-actions">
        <button className="primary-button" type="submit">
          {editing ? "Save Entry" : "Add Entry"}
        </button>
        {/* Unconditional since milestone 3.7: the compose form is collapsed
            behind a trigger now (`app/OpportunityPanel.tsx`), so closing it
            without posting is a thing a reader needs in both modes. */}
        <button className="secondary-button" type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      {save.isPending && (
        <p className="status">
          {editing ? "Updating entry..." : "Adding entry..."}
        </p>
      )}
      {upload.isPending && <p className="status">Attaching {file?.name}...</p>}
      {save.isError && <p className="error">{save.error.message}</p>}
      {upload.isError && (
        <p className="error">
          The entry was saved. The file was not attached: {upload.error.message}
        </p>
      )}
    </form>
  );
}
