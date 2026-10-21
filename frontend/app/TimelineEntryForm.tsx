"use client";

import { ChangeEvent, FormEvent, useState, type RefObject } from "react";

import {
  entryTypes,
  type CustomValues,
  type EntryType,
  type EntryVisibility,
  type TimelineEntry,
} from "../lib/domain";
import { submitFormOnModEnter } from "../lib/keyboard";
import {
  useCreateTask,
  useCustomFields,
  useSaveTimelineEntry,
  useSession,
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
  /** Who may read it (R.1b). An entry starts private and is revealed
   * deliberately: the human's ruling was that privacy is "set upfront ...
   * with a tick box to reveal it". */
  visibility: EntryVisibility;
  /** When to come back to this, as `YYYY-MM-DD` or empty (R.1c, D-217). It is
   * a field of the entry *and* the due date of the task the tick creates. */
  follow_up_date: string;
}

function formFor(entry: TimelineEntry | null): EntryFormState {
  if (!entry) {
    return {
      type: "call",
      title: "",
      body: "",
      event_timestamp: nowDateTimeInput(),
      custom_values: {},
      visibility: "private",
      follow_up_date: "",
    };
  }
  return {
    type: entry.type,
    title: entry.title,
    body: entry.body,
    event_timestamp: toDateTimeInput(entry.event_timestamp),
    custom_values: (entry.custom_values ?? {}) as CustomValues,
    visibility: entry.visibility ?? "private",
    follow_up_date: entry.follow_up_date ?? "",
  };
}

/**
 * Adds a timeline entry, or saves the one the timeline handed it. The parent
 * re-keys this component on the entry being edited, so the fields reload
 * without an effect chasing props.
 *
 * **The "Follow up" field is back, and it makes a task** (R.1c, **D-217**,
 * the reviewer's ask: *"Follow up tick should continue to create Task by
 * default as the follow up action. However, it shouldn't be mandatory to
 * create a task so a follow up could be put just in the notes or be created
 * as a task."*)
 *
 * Milestone 4.2 removed it, and **D-144**'s reasoning for that was right: a
 * date on this form writing only `timeline_entries.follow_up_date` would land
 * on a column the task list does not read, so the two would diverge for as
 * long as both existed. What makes the field safe now is that the tick is on
 * by default and what it writes is a **task** — the thing the rest of the app
 * reads. Unticking it is the reviewer's "just in the notes": the date stays on
 * the entry, the card prints it, and nothing claims it is on anybody's list.
 *
 * Two requests in order, like the attachment path above it: the entry has to
 * exist before a task can name it. `createdId` is what keeps a retry from
 * posting a second entry.
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
  // Ticked by default, which is the reviewer's "continue to create Task by
  // default as the follow up action" (R.1c, D-217). Unticking it leaves the
  // date on the entry alone.
  const [makeTask, setMakeTask] = useState(true);
  // The task this form has already created, for the same reason `createdId`
  // exists: if the task request fails, pressing the button again must not
  // post the entry a second time -- and if it succeeded while something after
  // it failed, it must not make a second task either.
  const [taskMade, setTaskMade] = useState(false);
  const customFields = useCustomFields("entry");
  const save = useSaveTimelineEntry(opportunityId);
  const upload = useUploadAttachment();
  const createTask = useCreateTask(opportunityId);
  const session = useSession();

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
          // `null` rather than the empty string an unfilled date input holds.
          // The API coerces either to NULL, so this is about what the request
          // *says*: a cleared follow-up is an absent date, not a blank one.
          follow_up_date: form.follow_up_date || null,
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

    // The task, last: it is the only one of the three that can be retried
    // without the entry, and doing it after the file keeps the order of
    // failures the same as the order of the fields.
    if (makeTask && form.follow_up_date !== "" && !taskMade) {
      const made = await createTask
        .mutateAsync({
          // `Follow up: <title>` is revision `0010_follow_ups_to_tasks`'s own
          // wording, kept so the tasks this form makes and the ones that
          // migration wrote read as the same kind of thing.
          title: `Follow up: ${form.title}`,
          due_date: form.follow_up_date,
          entry_id: saved.id,
          // Whoever wrote the entry, which is who a follow-up belongs to
          // until somebody says otherwise. `assignee_emails` is a set since
          // 4.6; leaving it out would make the task nobody's and keep it off
          // My Tasks entirely.
          assignee_emails: session.data?.email ? [session.data.email] : [],
        })
        .then(
          () => true,
          () => false,
        );
      if (!made) {
        return;
      }
      setTaskMade(true);
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
      {/* When to come back to this (R.1c, **D-217**). The date is a field of
          the entry; the tick is what turns it into a task, which is the only
          thing the task list, My Tasks and the calendar read. Ticked by
          default — the reviewer's "continue to create Task by default as the
          follow up action" — and unticking it is their "just in the notes":
          the card still prints the date, and nothing pretends it is on
          somebody's list. The tick only appears once there is a date to act
          on, because a checkbox about an empty field is a question nobody
          asked. */}
      <label>
        Follow up (optional)
        <input
          type="date"
          name="follow_up_date"
          value={form.follow_up_date}
          onChange={(event) =>
            setForm({ ...form, follow_up_date: event.target.value })
          }
        />
      </label>
      {form.follow_up_date !== "" && (
        <>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={makeTask}
              onChange={(event) => setMakeTask(event.target.checked)}
            />
            Create a task for this follow-up
          </label>
          <p className="field-hint">
            {makeTask
              ? "It will be assigned to you, due on that date, and linked back to this entry."
              : "The date stays on this entry only. It will not appear in Tasks or on the calendar."}
          </p>
        </>
      )}
      {createTask.isError && (
        <p className="error-text" role="alert">
          The entry was saved, but the follow-up task was not:{" "}
          {createTask.error instanceof Error
            ? createTask.error.message
            : "the task could not be created."}
        </p>
      )}
      {/* The tick box that reveals it (R.1b). Off is private, which is what a
          new entry is: "privacy is set upfront ... with a tick box to reveal
          it". Phrased as what ticking it *does* rather than as a state, so the
          consequence is on the control rather than in a legend beside it. */}
      <label className="checkbox-field entry-visibility">
        <input
          type="checkbox"
          checked={form.visibility === "shared"}
          onChange={(event) =>
            setForm({
              ...form,
              visibility: event.target.checked ? "shared" : "private",
            })
          }
        />
        Reveal this entry to everyone on the deal
      </label>
      {form.visibility === "private" && (
        <p className="field-hint">
          Only you will see it. Nobody is notified, and it stays in the timeline
          for others as a sealed entry with nothing in it.
        </p>
      )}

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
