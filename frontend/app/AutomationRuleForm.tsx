"use client";

import { useState, type FormEvent } from "react";

import {
  automationActions,
  automationSentence,
  automationTriggers,
  conditionFieldOptions,
  conditionOperators,
  automationEntryTypes,
  stages,
  type ActionParameter,
  type AutomationAction,
  type AutomationCondition,
  type AutomationRule,
  type AutomationTrigger,
  type ConditionOperator,
  type CustomField,
  type TriggerParameter,
} from "../lib/domain";
import {
  useCreateAutomationRule,
  useUpdateAutomationRule,
} from "../lib/queries";
import { ApiError } from "../lib/api";
import { invalidFields } from "../lib/formErrors";
import { Modal } from "./Modal";

/**
 * One input's reason for being refused, under the input it belongs to.
 *
 * Keyed by the API's own field name (`"action.title"`), so the two sides stay
 * in agreement without a translation table: `errors.py` builds the key from
 * the location Pydantic reports, which is the schema's own field path.
 */
function FieldError({
  reasons,
  field,
}: {
  reasons: Record<string, string>;
  field: string;
}) {
  const reason = reasons[field];
  return reason ? <p className="field-error">{reason}</p> : null;
}

/** The field keys this form draws a `FieldError` under. Anything else the API
 * names -- a condition's value, a parameter of a kind the reader has since
 * changed -- has no input on screen to sit beside, so the summary line shows
 * it instead. */
const SHOWN_FIELDS = new Set(["name", "trigger.days", "action.title"]);

/**
 * What the summary line says, or nothing.
 *
 * Nothing is the common case once a field reason is on screen: printing it
 * twice, once under the input and once at the bottom, is the duplication the
 * first version of this shipped with. So the line carries a whole-rule
 * failure (`_`), or a reason whose input is not drawn, or -- for every
 * failure that is not a 422 at all -- the envelope's own sentence.
 */
function summaryReason(
  reasons: Record<string, string>,
  message: string,
): string | undefined {
  if (reasons["_"]) {
    return reasons["_"];
  }
  const unshown = Object.entries(reasons).find(
    ([field]) => !SHOWN_FIELDS.has(field),
  );
  if (unshown) {
    return unshown[1];
  }
  return Object.keys(reasons).length === 0 && message !== ""
    ? message
    : undefined;
}

/**
 * Writing one rule (milestone 6.3, `docs/FEATURES.md` §11).
 *
 * §11 asks for a builder that is **legible**, and three choices here are what
 * that means in practice:
 *
 * - **The rule is shown as a sentence above the controls**, from
 *   `lib/domain.ts`'s `automationSentence`, and it updates as the selects
 *   change. A column of dropdowns tells somebody what the options are and not
 *   what they have built; §11's whole objection to a workflow engine is that
 *   nobody can read one back.
 * - **Only the parameters the chosen kind takes are rendered**, from the same
 *   `fields` lists the API validates against (`schemas.py`'s
 *   `TRIGGER_*_KEYS`). A form offering a parameter the API refuses produces a
 *   422 nobody can act on, and one that silently ignores it produces a rule
 *   that does not mean what was typed.
 * - **Conditions are a flat list with an Add button and no grouping
 *   control**, because they are ANDed and cannot be nested. The screen cannot
 *   express what the model cannot store.
 *
 * A dialog rather than a panel, like the opportunity form (D-079) and the
 * custom field screen beside it: this is a thing somebody does occasionally
 * and then leaves.
 */
interface FormState {
  name: string;
  trigger_type: AutomationTrigger;
  to_stage: string;
  from_stage: string;
  trigger_entry_type: string;
  field: string;
  days: string;
  conditions: AutomationCondition[];
  action_type: AutomationAction;
  title: string;
  body: string;
  recipient: "owner" | "rule_creator";
  due_in_days: string;
  action_entry_type: string;
  stage: string;
  enabled: boolean;
}

const emptyForm: FormState = {
  name: "",
  trigger_type: "no_activity",
  to_stage: "",
  from_stage: "",
  trigger_entry_type: "",
  field: "stage",
  days: "14",
  conditions: [],
  action_type: "create_task",
  title: "",
  body: "",
  recipient: "owner",
  due_in_days: "3",
  action_entry_type: "other",
  stage: stages[0],
  enabled: true,
};

function formFor(rule: AutomationRule | null): FormState {
  if (!rule) {
    return emptyForm;
  }
  return {
    ...emptyForm,
    name: rule.name,
    trigger_type: rule.trigger_type,
    to_stage: rule.trigger.to_stage ?? "",
    from_stage: rule.trigger.from_stage ?? "",
    trigger_entry_type: rule.trigger.entry_type ?? "",
    field: rule.trigger.field ?? "stage",
    days: rule.trigger.days === null ? "14" : String(rule.trigger.days),
    conditions: rule.conditions,
    action_type: rule.action_type,
    title: rule.action.title ?? "",
    body: rule.action.body ?? "",
    recipient: rule.action.recipient ?? "owner",
    due_in_days:
      rule.action.due_in_days === null ? "" : String(rule.action.due_in_days),
    action_entry_type: rule.action.entry_type ?? "other",
    stage: rule.action.stage ?? stages[0],
    enabled: rule.enabled,
  };
}

/** The `trigger` object the API takes, carrying only this kind's keys.
 *
 * Built by filtering rather than by a switch, so the one list in
 * `lib/domain.ts` decides what is sent and what is rendered. An extra key
 * here is a 422 (`AutomationRuleBase.config_matches_the_kind`), which is
 * deliberate on the server's side and would be this function's bug. */
function triggerPayload(form: FormState) {
  const fields = new Set<TriggerParameter>(
    automationTriggers.find((item) => item.value === form.trigger_type)!.fields,
  );
  return {
    to_stage: fields.has("to_stage") && form.to_stage ? form.to_stage : null,
    from_stage:
      fields.has("from_stage") && form.from_stage ? form.from_stage : null,
    entry_type:
      fields.has("entry_type") && form.trigger_entry_type
        ? (form.trigger_entry_type as "call")
        : null,
    field: fields.has("field") ? form.field : null,
    days: fields.has("days") ? Number(form.days) : null,
  };
}

function actionPayload(form: FormState) {
  const fields = new Set<ActionParameter>(
    automationActions.find((item) => item.value === form.action_type)!.fields,
  );
  return {
    title: fields.has("title") ? form.title.trim() : null,
    body: fields.has("body") && form.body.trim() ? form.body.trim() : null,
    // `recipient` has a server-side default rather than being nullable, so an
    // action that does not take one sends the default it would have received.
    recipient: fields.has("recipient") ? form.recipient : ("owner" as const),
    due_in_days:
      fields.has("due_in_days") && form.due_in_days !== ""
        ? Number(form.due_in_days)
        : null,
    entry_type: fields.has("entry_type")
      ? (form.action_entry_type as "other")
      : null,
    stage: fields.has("stage") ? form.stage : null,
  };
}

export function AutomationRuleForm({
  rule,
  customFields,
  onClose,
}: {
  rule: AutomationRule | null;
  customFields: CustomField[];
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => formFor(rule));
  const create = useCreateAutomationRule();
  const update = useUpdateAutomationRule();
  const saving = create.isPending || update.isPending;
  const error = create.error ?? update.error;
  // A 422's per-field reasons (6.3a, **D-180**). The envelope has always
  // carried them; nothing read them, so a refused save said only "The request
  // could not be validated" -- which is what reached the human at the 6.3
  // review, with no indication of which part of the rule was wrong.
  // What the *browser* refused, keyed exactly as the API keys its own
  // refusals (6.5a). Held separately so a server answer replaces it rather
  // than merging with it: a submit either never left, or came back.
  const [blocked, setBlocked] = useState<Record<string, string>>({});
  const refused = error instanceof ApiError ? error.fields : blocked;
  const summary = Object.keys(blocked).length
    ? summaryReason(blocked, "")
    : error
      ? summaryReason(refused, error.message)
      : undefined;

  const trigger = automationTriggers.find(
    (item) => item.value === form.trigger_type,
  )!;
  const action = automationActions.find(
    (item) => item.value === form.action_type,
  )!;
  const fieldOptions = conditionFieldOptions(customFields);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  const payload = {
    name: form.name.trim(),
    trigger_type: form.trigger_type,
    trigger: triggerPayload(form),
    conditions: form.conditions,
    action_type: form.action_type,
    action: actionPayload(form),
    enabled: form.enabled,
  };

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Asked ourselves rather than left to the browser, because the browser's
    // answer is a tooltip that vanishes and a submit that silently does not
    // happen (6.5a, **D-184**). `noValidate` below is what hands us the
    // question.
    const stopped = invalidFields(event.currentTarget);
    setBlocked(stopped);
    if (Object.keys(stopped).length > 0) {
      return;
    }
    const done = { onSuccess: onClose };
    if (rule) {
      update.mutate({ id: rule.id, ...payload }, done);
    } else {
      create.mutate(payload, done);
    }
  }

  return (
    <Modal
      label={rule ? "Edit rule" : "New rule"}
      title={rule ? "Edit rule" : "New rule"}
      onClose={onClose}
    >
      {/* The sentence, above the controls that build it. */}
      <p className="automation-sentence">{automationSentence(payload)}</p>

      <form className="form" onSubmit={submit} noValidate>
        <label>
          Name
          <input
            name="name"
            value={form.name}
            onChange={(event) => set("name", event.target.value)}
            placeholder="Nudge the quiet ones"
            aria-invalid={"name" in refused}
            required
          />
        </label>
        <FieldError reasons={refused} field="name" />

        <h3>When</h3>
        <label>
          Trigger
          <select
            aria-label="Trigger"
            value={form.trigger_type}
            onChange={(event) =>
              set("trigger_type", event.target.value as AutomationTrigger)
            }
          >
            {automationTriggers.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {trigger.fields.includes("days") && (
          <>
            <label>
              Days
              <input
                name="trigger.days"
                type="number"
                min={1}
                max={365}
                value={form.days}
                onChange={(event) => set("days", event.target.value)}
                aria-invalid={"trigger.days" in refused}
                required
              />
            </label>
            <FieldError reasons={refused} field="trigger.days" />
          </>
        )}
        {trigger.fields.includes("to_stage") && (
          <label>
            Moved to
            <select
              aria-label="Moved to stage"
              value={form.to_stage}
              onChange={(event) => set("to_stage", event.target.value)}
            >
              <option value="">Any stage</option>
              {stages.map((stage) => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </select>
          </label>
        )}
        {trigger.fields.includes("from_stage") && (
          <label>
            Moved from
            <select
              aria-label="Moved from stage"
              value={form.from_stage}
              onChange={(event) => set("from_stage", event.target.value)}
            >
              <option value="">Any stage</option>
              {stages.map((stage) => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </select>
          </label>
        )}
        {trigger.fields.includes("entry_type") && (
          <label>
            Entry type
            <select
              aria-label="Trigger entry type"
              value={form.trigger_entry_type}
              onChange={(event) =>
                set("trigger_entry_type", event.target.value)
              }
            >
              <option value="">Any type</option>
              {automationEntryTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {trigger.fields.includes("field") && (
          <label>
            Field
            <select
              aria-label="Watched field"
              value={form.field}
              onChange={(event) => set("field", event.target.value)}
            >
              {fieldOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        )}

        <h3>Only if</h3>
        <ConditionList
          conditions={form.conditions}
          fieldOptions={fieldOptions}
          onChange={(conditions) => set("conditions", conditions)}
        />

        <h3>Then</h3>
        <label>
          Action
          <select
            aria-label="Action"
            value={form.action_type}
            onChange={(event) =>
              set("action_type", event.target.value as AutomationAction)
            }
          >
            {automationActions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {action.fields.includes("title") && (
          <>
            <label>
              {form.action_type === "notify_user" ? "Message" : "Title"}
              <input
                name="action.title"
                value={form.title}
                onChange={(event) => set("title", event.target.value)}
                placeholder="Follow up on this deal"
                aria-invalid={"action.title" in refused}
                required
              />
            </label>
            <FieldError reasons={refused} field="action.title" />
          </>
        )}
        {action.fields.includes("body") && (
          <label>
            Details, optional
            <textarea
              value={form.body}
              onChange={(event) => set("body", event.target.value)}
              rows={2}
            />
          </label>
        )}
        {action.fields.includes("recipient") && (
          <label>
            For
            <select
              aria-label="Recipient"
              value={form.recipient}
              onChange={(event) =>
                set("recipient", event.target.value as FormState["recipient"])
              }
            >
              <option value="owner">The deal&apos;s owner</option>
              <option value="rule_creator">Me</option>
            </select>
          </label>
        )}
        {action.fields.includes("due_in_days") && (
          <label>
            Due in days, optional
            <input
              type="number"
              min={0}
              max={365}
              value={form.due_in_days}
              onChange={(event) => set("due_in_days", event.target.value)}
            />
          </label>
        )}
        {action.fields.includes("entry_type") && (
          <label>
            Entry type
            <select
              aria-label="New entry type"
              value={form.action_entry_type}
              onChange={(event) => set("action_entry_type", event.target.value)}
            >
              {automationEntryTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {action.fields.includes("stage") && (
          <label>
            New stage
            <select
              aria-label="New stage"
              value={form.stage}
              onChange={(event) => set("stage", event.target.value)}
            >
              {stages.map((stage) => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => set("enabled", event.target.checked)}
          />
          Enabled
        </label>

        {/* What a rule can and cannot reach, said once where it is written
            rather than discovered from a skipped run (D-173). */}
        <p className="form-hint">
          This rule runs on the deals you can see, and does only what you could
          do yourself. A rule never triggers another rule.
          {trigger.scheduled
            ? " It is checked on a schedule, and you can run it here at any time."
            : " It runs when somebody makes that change."}
        </p>

        {summary && <p className="error">{summary}</p>}

        <div className="form-actions">
          <button type="submit" disabled={saving}>
            {rule ? "Save rule" : "Create rule"}
          </button>
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * The ANDed condition list.
 *
 * No grouping, no OR, no nesting: §11 rules all three out, and a screen that
 * offered them would be a screen the model cannot store. "and" is printed
 * between the rows rather than being a control, which is the honest rendering
 * of a list that has exactly one joiner.
 */
function ConditionList({
  conditions,
  fieldOptions,
  onChange,
}: {
  conditions: AutomationCondition[];
  fieldOptions: { value: string; label: string }[];
  onChange: (conditions: AutomationCondition[]) => void;
}) {
  function replace(index: number, next: Partial<AutomationCondition>) {
    onChange(
      conditions.map((condition, position) =>
        position === index ? { ...condition, ...next } : condition,
      ),
    );
  }

  return (
    <>
      {conditions.length === 0 && (
        <p className="form-hint">
          No conditions: the rule applies to every deal the trigger matches.
        </p>
      )}
      <ul className="condition-list">
        {conditions.map((condition, index) => (
          <li key={index}>
            {index > 0 && <span className="condition-joiner">and</span>}
            <select
              aria-label={`Condition ${index + 1} field`}
              value={condition.field}
              onChange={(event) =>
                replace(index, { field: event.target.value })
              }
            >
              {fieldOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              aria-label={`Condition ${index + 1} operator`}
              value={condition.op}
              onChange={(event) =>
                replace(index, { op: event.target.value as ConditionOperator })
              }
            >
              {conditionOperators.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              aria-label={`Condition ${index + 1} value`}
              value={condition.value}
              onChange={(event) =>
                replace(index, { value: event.target.value })
              }
            />
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                onChange(conditions.filter((_, position) => position !== index))
              }
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      {conditions.length < 5 && (
        <button
          type="button"
          className="secondary-button"
          onClick={() =>
            onChange([...conditions, { field: "stage", op: "eq", value: "" }])
          }
        >
          Add a condition
        </button>
      )}
    </>
  );
}
