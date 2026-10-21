"use client";

import { useState, type FormEvent } from "react";

import {
  type CustomField,
  type CustomFieldEntity,
  type CustomFieldType,
} from "../lib/domain";
import {
  useAllCustomFields,
  useArchiveCustomField,
  useCreateCustomField,
  useUpdateCustomField,
} from "../lib/queries";
import { Modal } from "./Modal";

/**
 * Where custom fields are defined (milestone 6.1, ADR 0006).
 *
 * `docs/FEATURES.md` §3 says "admin-defined" and this application has no
 * admin role, so **any signed-in user may define a field** (**D-171**) --
 * which makes this the widest write surface in the app, and the reason the
 * dialog says plainly that a field is shared by everybody.
 *
 * Three things the shape here is deliberate about:
 *
 * - **Archive, never delete.** The ADR requires that retiring a field leaves
 *   its values alone, so the control says Archive and an archived field is
 *   still listed with a Restore beside it. Nothing in this app offers to
 *   destroy stored values and this is not the screen to start.
 * - **A key and a type are set once.** Both are refused by the API on edit,
 *   because the key is what the stored JSON is filed under and the type is
 *   what every stored value already satisfies. The form says so rather than
 *   offering a control that would 422.
 * - **Editing and defining live here, not beside every field name** --
 *   `AGENTS.md`'s Design bar, and the same choice `ManageSavedViews` made.
 */
const FIELD_TYPES: { value: CustomFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "select", label: "Select one" },
  { value: "multi_select", label: "Select several" },
  { value: "checkbox", label: "Yes or no" },
  { value: "user", label: "Person" },
];

const ENTITIES: { value: CustomFieldEntity; label: string }[] = [
  { value: "opportunity", label: "Opportunities" },
  { value: "entry", label: "Timeline entries" },
];

/** A label typed by a person, as a key the JSON can be filed under. */
export function keyFromLabel(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^([0-9])/, "field_$1")
    .slice(0, 40);
}

export function ManageCustomFields({ onClose }: { onClose: () => void }) {
  const fields = useAllCustomFields();
  const create = useCreateCustomField();
  const archive = useArchiveCustomField();
  const [entityType, setEntityType] =
    useState<CustomFieldEntity>("opportunity");
  const [label, setLabel] = useState("");
  const [type, setType] = useState<CustomFieldType>("text");
  const [options, setOptions] = useState("");
  const [required, setRequired] = useState(false);

  const chooses = type === "select" || type === "multi_select";
  const listed = (fields.data ?? []).filter(
    (field) => field.entity_type === entityType,
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate(
      {
        entity_type: entityType,
        key: keyFromLabel(label),
        label: label.trim(),
        type,
        required,
        position: listed.length,
        options: chooses
          ? options
              .split(",")
              .map((option) => option.trim())
              .filter(Boolean)
          : [],
      },
      {
        onSuccess: () => {
          setLabel("");
          setOptions("");
          setRequired(false);
        },
      },
    );
  }

  return (
    <Modal label="Custom fields" title="Custom fields" onClose={onClose}>
      <p className="form-hint">
        A field is shared by everyone here, and appears as a table column, a
        filter and a form input wherever its records are read.
      </p>

      <label>
        These fields are on
        <select
          value={entityType}
          onChange={(event) =>
            setEntityType(event.target.value as CustomFieldEntity)
          }
        >
          {ENTITIES.map((entity) => (
            <option key={entity.value} value={entity.value}>
              {entity.label}
            </option>
          ))}
        </select>
      </label>

      {listed.length === 0 ? (
        <p className="empty-state">No fields defined here yet.</p>
      ) : (
        <ul className="custom-field-list">
          {listed.map((field) => (
            <FieldRow
              key={field.id}
              field={field}
              onToggleArchive={() =>
                archive.mutate({
                  id: field.id,
                  archived: field.archived_at !== null,
                })
              }
            />
          ))}
        </ul>
      )}

      <form className="form" onSubmit={submit}>
        <h3>Add a field</h3>
        <label>
          Label
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Region"
            required
          />
        </label>
        {/* The key is derived rather than typed: it has to satisfy a pattern
            the JSON and an expression index can both use, and asking a person
            for one is asking them to care about storage. Shown because it is
            permanent -- the API refuses to change it (ADR 0006). */}
        {label.trim() !== "" && (
          <p className="form-hint">
            Stored as <code>{keyFromLabel(label)}</code>, which cannot be
            changed later.
          </p>
        )}
        <label>
          Type
          <select
            value={type}
            onChange={(event) => setType(event.target.value as CustomFieldType)}
          >
            {FIELD_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {chooses && (
          <label>
            Options, separated by commas
            <input
              value={options}
              onChange={(event) => setOptions(event.target.value)}
              placeholder="EMEA, APAC, AMER"
              required
            />
          </label>
        )}
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={required}
            onChange={(event) => setRequired(event.target.checked)}
          />
          Required
        </label>
        <div className="form-actions">
          <button className="primary-button" type="submit">
            Add field
          </button>
        </div>
        {create.isError && (
          <p className="error-text" role="alert">
            {create.error instanceof Error
              ? create.error.message
              : "The field could not be added."}
          </p>
        )}
      </form>
    </Modal>
  );
}

/** One defined field: what it is, and the one state change it can undergo. */
function FieldRow({
  field,
  onToggleArchive,
}: {
  field: CustomField;
  onToggleArchive: () => void;
}) {
  const update = useUpdateCustomField();
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(field.label);
  const archived = field.archived_at !== null;

  return (
    <li className={`custom-field-row${archived ? " is-archived" : ""}`}>
      {editing ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate(
              {
                id: field.id,
                label,
                required: field.required,
                position: field.position,
                options: field.options,
              },
              { onSuccess: () => setEditing(false) },
            );
          }}
        >
          <label>
            Label
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit">
            Save
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setLabel(field.label);
              setEditing(false);
            }}
          >
            Cancel
          </button>
        </form>
      ) : (
        <>
          <div>
            <strong>{field.label}</strong>
            <span className="custom-field-meta">
              {FIELD_TYPES.find((option) => option.value === field.type)?.label}
              {field.required ? " - required" : ""}
              {archived ? " - archived" : ""}
            </span>
            {field.options.length > 0 && (
              <span className="custom-field-meta">
                {field.options.join(", ")}
              </span>
            )}
          </div>
          <div className="inline-actions">
            {!archived && (
              <button
                className="secondary-button"
                type="button"
                onClick={() => setEditing(true)}
              >
                Rename
              </button>
            )}
            <button
              className="secondary-button"
              type="button"
              onClick={onToggleArchive}
            >
              {archived ? "Restore" : "Archive"}
            </button>
          </div>
        </>
      )}
    </li>
  );
}
