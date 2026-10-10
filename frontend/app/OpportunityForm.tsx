"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { stages, type CustomValues, type Opportunity } from "../lib/domain";
import { useCustomFields, useSaveOpportunity } from "../lib/queries";
import { CustomFieldInputs } from "./CustomFieldInputs";

interface OpportunityFormState {
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  expected_close_date: string;
  /** The deal's custom field values (milestone 6.1). This form is where they
   * are set: the table shows them as read-only cells, because a value's
   * control is decided by its field's type and a grid cell has room for one
   * text box. */
  custom_values: CustomValues;
}

const emptyForm: OpportunityFormState = {
  name: "",
  account_name: "",
  value: "0",
  currency: "USD",
  stage: "Prospecting",
  expected_close_date: "",
  custom_values: {},
};

function formFor(opportunity: Opportunity | null): OpportunityFormState {
  if (!opportunity) {
    return emptyForm;
  }
  return {
    name: opportunity.name,
    account_name: opportunity.account_name,
    value: opportunity.value,
    currency: opportunity.currency,
    stage: opportunity.stage,
    expected_close_date: opportunity.expected_close_date ?? "",
    custom_values: (opportunity.custom_values ?? {}) as CustomValues,
  };
}

/**
 * Creates an opportunity, or edits the one the board handed it.
 *
 * It lives in a dialog from milestone 2.7 rather than in a permanent sidebar
 * column (D-079): creating an opportunity is a rare action, and the form was
 * holding a third of the dashboard open for it. The parent owns which
 * opportunity is being edited and re-keys this component on it, so the fields
 * reload without an effect watching props — and the heading is the dialog's
 * (`app/Modal.tsx`), not a second one inside the form. Nothing here cancels
 * either: the dialog's own Close, Esc and backdrop already do, and a second
 * button beside them saying the same thing is the clutter this milestone is
 * removing.
 */
export function OpportunityForm({
  editing,
  onDone,
}: {
  editing: Opportunity | null;
  onDone: () => void;
}) {
  const [form, setForm] = useState(() => formFor(editing));
  const customFields = useCustomFields("opportunity");
  const save = useSaveOpportunity();
  const nameRef = useRef<HTMLInputElement>(null);

  // The dialog opens on `c`, on Edit, and on the New opportunity button, and
  // in all three the first thing to do is name it. Radix would otherwise land
  // focus on the dialog's Close button.
  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      {
        id: editing?.id ?? null,
        payload: {
          ...form,
          expected_close_date: form.expected_close_date || null,
        },
      },
      {
        onSuccess: () => {
          setForm(emptyForm);
          onDone();
        },
      },
    );
  }

  return (
    <form className="form opportunity-form" onSubmit={submit}>
      <label>
        Opportunity
        <input
          ref={nameRef}
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          required
        />
      </label>

      <label>
        Account
        <input
          value={form.account_name}
          onChange={(event) =>
            setForm({ ...form, account_name: event.target.value })
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
            value={form.value}
            onChange={(event) =>
              setForm({ ...form, value: event.target.value })
            }
            required
          />
        </label>

        <label>
          Currency
          <input
            maxLength={3}
            minLength={3}
            value={form.currency}
            onChange={(event) =>
              setForm({ ...form, currency: event.target.value })
            }
            required
          />
        </label>
      </div>

      <label>
        Stage
        <select
          value={form.stage}
          onChange={(event) => setForm({ ...form, stage: event.target.value })}
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
          value={form.expected_close_date}
          onChange={(event) =>
            setForm({ ...form, expected_close_date: event.target.value })
          }
        />
      </label>

      {/* Whatever this team tracks that the fixed fields above do not
          (milestone 6.1). Renders nothing until somebody defines a field, so
          this form is unchanged for a deployment that uses none. */}
      <CustomFieldInputs
        fields={customFields.data ?? []}
        values={form.custom_values}
        onChange={(custom_values) => setForm({ ...form, custom_values })}
      />

      <div className="form-actions">
        <button className="primary-button" type="submit">
          {editing ? "Save changes" : "Create opportunity"}
        </button>
      </div>
      {save.isPending && (
        <p className="status">
          {editing ? "Updating opportunity..." : "Creating opportunity..."}
        </p>
      )}
      {save.isError && <p className="error">{save.error.message}</p>}
    </form>
  );
}
