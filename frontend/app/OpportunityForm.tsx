"use client";

import { FormEvent, useState } from "react";

import { stages, type Opportunity } from "../lib/domain";
import { useSaveOpportunity } from "../lib/queries";

interface OpportunityFormState {
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  expected_close_date: string;
}

const emptyForm: OpportunityFormState = {
  name: "",
  account_name: "",
  value: "0",
  currency: "USD",
  stage: "Prospecting",
  expected_close_date: "",
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
  };
}

/**
 * The sidebar form, which creates an opportunity or edits the one the board
 * handed it. The parent owns which opportunity is being edited and re-keys
 * this component on it, so the fields reload without an effect watching props.
 */
export function OpportunityForm({
  editing,
  onDone,
}: {
  editing: Opportunity | null;
  onDone: () => void;
}) {
  const [form, setForm] = useState(() => formFor(editing));
  const save = useSaveOpportunity();

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
    <form className="form sidebar-form" onSubmit={submit}>
      <h2>{editing ? "Edit Opportunity" : "New Opportunity"}</h2>

      <label>
        Opportunity
        <input
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

      <button className="primary-button" type="submit">
        {editing ? "Save changes" : "Create opportunity"}
      </button>
      {editing && (
        <button className="secondary-button" type="button" onClick={onDone}>
          Cancel edit
        </button>
      )}
      {save.isPending && (
        <p className="status">
          {editing ? "Updating opportunity..." : "Creating opportunity..."}
        </p>
      )}
      {save.isError && <p className="error">{save.error.message}</p>}
    </form>
  );
}
