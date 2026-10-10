"use client";

import {
  customFieldText,
  type CustomField,
  type CustomValues,
} from "../lib/domain";

/**
 * The inputs for one entity's custom fields (milestone 6.1, ADR 0006).
 *
 * `docs/FEATURES.md` §3: "fields appear automatically in Table columns,
 * filters, and the entry form." This is the third of those, shared by the
 * opportunity dialog and the timeline entry form rather than written twice --
 * a field's control is decided by its `type`, and that decision belongs in
 * one place for the same reason `lib/domain.ts`'s `editableOpportunityFields`
 * declares a built-in field's editor once.
 *
 * Three things worth knowing:
 *
 * - **It renders nothing when there are no fields**, so a deployment that
 *   defines none sees no change to either form -- not an empty fieldset with
 *   a legend and no contents.
 * - **The value set it reports is whole**, not a patch. The API takes a whole
 *   set because a JSON column is written whole (`app/custom_fields.py`), and
 *   a control that reported only its own key would make an empty field
 *   indistinguishable from an absent one.
 * - **It does not validate.** The server owns that, against the definitions,
 *   and answers a 422 whose `fields` map names the key -- which is what the
 *   forms already render. A second copy of the rules here could disagree with
 *   it, and the one that matters is the server's.
 */
export function CustomFieldInputs({
  fields,
  values,
  onChange,
}: {
  fields: CustomField[];
  values: CustomValues;
  onChange: (values: CustomValues) => void;
}) {
  if (fields.length === 0) {
    return null;
  }

  function set(key: string, value: unknown) {
    const next = { ...values };
    // An emptied control removes the key rather than storing `""`: the server
    // treats both as cleared, and a set that carries empty strings would
    // serialise differently from one that does not, which matters because the
    // stored JSON is compared as text.
    if (
      value === "" ||
      value === null ||
      (Array.isArray(value) && value.length === 0)
    ) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  }

  return (
    <fieldset className="custom-field-inputs">
      <legend>Fields</legend>
      {fields.map((field) => {
        const held = values[field.key];
        const label = field.required
          ? `${field.label} (required)`
          : field.label;
        if (field.type === "checkbox") {
          return (
            <label className="checkbox-field" key={field.key}>
              <input
                type="checkbox"
                checked={held === true}
                onChange={(event) => set(field.key, event.target.checked)}
              />
              {label}
            </label>
          );
        }
        if (field.type === "select") {
          return (
            <label key={field.key}>
              {label}
              <select
                value={typeof held === "string" ? held : ""}
                onChange={(event) => set(field.key, event.target.value)}
              >
                <option value="">Not set</option>
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        if (field.type === "multi_select") {
          const chosen = Array.isArray(held) ? held.map(String) : [];
          return (
            <fieldset className="multi-select-field" key={field.key}>
              <legend>{label}</legend>
              {field.options.map((option) => (
                <label className="checkbox-field" key={option}>
                  <input
                    type="checkbox"
                    checked={chosen.includes(option)}
                    onChange={(event) =>
                      set(
                        field.key,
                        event.target.checked
                          ? [...chosen, option]
                          : chosen.filter((item) => item !== option),
                      )
                    }
                  />
                  {option}
                </label>
              ))}
            </fieldset>
          );
        }
        return (
          <label key={field.key}>
            {label}
            <input
              type={
                field.type === "date"
                  ? "date"
                  : field.type === "number" || field.type === "user"
                    ? "number"
                    : "text"
              }
              value={customFieldText(field, held)}
              onChange={(event) =>
                set(
                  field.key,
                  field.type === "number" || field.type === "user"
                    ? // An emptied number input reports `""`, which `set`
                      // reads as cleared; anything else is a real number, and
                      // the server refuses one that is not.
                      event.target.value === ""
                      ? ""
                      : Number(event.target.value)
                    : event.target.value,
                )
              }
            />
          </label>
        );
      })}
    </fieldset>
  );
}
