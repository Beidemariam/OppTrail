"use client";

import { FormEvent, useState } from "react";

import type { ShareRole } from "../lib/domain";
import {
  useAddShare,
  useAuditLog,
  useRemoveShare,
  useShares,
  useUpdateShareRole,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { useConfirm } from "./ConfirmDialog";

/**
 * Sharing and the audit log, both owner-only
 * (`backend/app/permissions.py`, `require_opportunity_owner`). The panel is
 * rendered only for an owner; the server is what enforces that.
 */
export function SharingPanel({ opportunityId }: { opportunityId: number }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<ShareRole>("viewer");
  const shares = useShares(opportunityId, true);
  const auditLog = useAuditLog(opportunityId, true);
  const addShare = useAddShare(opportunityId);
  const updateRole = useUpdateShareRole(opportunityId);
  const removeShare = useRemoveShare(opportunityId);
  const confirm = useConfirm();

  const rows = shares.data ?? [];
  const failure = [addShare, updateRole, removeShare].find(
    (mutation) => mutation.isError,
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    addShare.mutate(
      { email, role },
      {
        onSuccess: () => {
          setEmail("");
          setRole("viewer");
        },
      },
    );
  }

  return (
    <section className="sharing-panel">
      <div className="section-heading">
        <h3>Sharing</h3>
        <span>{rows.length} shared</span>
      </div>

      <form className="share-form" onSubmit={submit}>
        <input
          type="email"
          placeholder="Colleague email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <select
          aria-label="Role for the colleague being invited"
          value={role}
          onChange={(event) => setRole(event.target.value as ShareRole)}
        >
          <option value="viewer">Viewer</option>
          <option value="editor">Editor</option>
        </select>
        <button className="primary-button" type="submit">
          Share
        </button>
      </form>

      {failure && <p className="error">{failure.error?.message}</p>}

      {rows.length === 0 ? (
        <p className="empty-state">No shared colleagues</p>
      ) : (
        <div className="share-list">
          {rows.map((share) => (
            <div className="share-row" key={share.user_id}>
              <div>
                <strong>{share.name}</strong>
                <p>{share.email}</p>
              </div>
              <select
                aria-label={`Role for ${share.name}`}
                value={share.role}
                onChange={(event) =>
                  updateRole.mutate({
                    userId: share.user_id,
                    role: event.target.value as ShareRole,
                  })
                }
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void confirm({
                    title: `Remove ${share.name}'s access?`,
                    description: `${share.name} loses access to this opportunity immediately. There is no undo for this one - sharing again is a new grant (D-069).`,
                    confirmLabel: "Remove access",
                  }).then((confirmed) => {
                    if (confirmed) {
                      removeShare.mutate(share.user_id);
                    }
                  });
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <details className="audit-panel">
        <summary>Audit Log</summary>
        {(auditLog.data ?? []).length === 0 ? (
          <p className="empty-state">No audit events yet</p>
        ) : (
          <div className="audit-list">
            {(auditLog.data ?? []).map((item) => (
              <div className="audit-row" key={item.id}>
                <strong>{item.action}</strong>
                <span>{formatTimestamp(item.created_at)}</span>
                <p>{item.actor_name ?? "System"}</p>
                <code>{JSON.stringify(item.detail)}</code>
              </div>
            ))}
          </div>
        )}
      </details>
    </section>
  );
}
