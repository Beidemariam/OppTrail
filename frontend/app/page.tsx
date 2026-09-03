"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const stages = [
  "Prospecting",
  "Qualification",
  "Needs Analysis",
  "Proposal",
  "Negotiation",
  "Closed Won",
  "Closed Lost",
] as const;

type User = {
  id: number;
  email: string;
  name: string;
};

type Opportunity = {
  id: number;
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  owner_name: string;
  expected_close_date: string | null;
  stalled: boolean;
};

type OpportunityForm = {
  name: string;
  account_name: string;
  value: string;
  currency: string;
  stage: string;
  expected_close_date: string;
};

const emptyOpportunityForm: OpportunityForm = {
  name: "",
  account_name: "",
  value: "0",
  currency: "USD",
  stage: "Prospecting",
  expected_close_date: "",
};

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(
      typeof error.detail === "string" ? error.detail : "Request failed",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("signup");
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [opportunityForm, setOpportunityForm] =
    useState<OpportunityForm>(emptyOpportunityForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Loading...");

  useEffect(() => {
    apiRequest<{ user: User }>("/api/auth/me")
      .then((data) => {
        setUser(data.user);
        setStatus("");
        return loadOpportunities();
      })
      .catch(() => {
        setStatus("");
      });
  }, []);

  const groupedOpportunities = useMemo(
    () =>
      stages.map((stage) => ({
        stage,
        items: opportunities.filter((opportunity) => opportunity.stage === stage),
      })),
    [opportunities],
  );

  async function loadOpportunities() {
    const data = await apiRequest<{
      stages: string[];
      opportunities: Opportunity[];
    }>("/api/opportunities");
    setOpportunities(data.opportunities);
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus(authMode === "signup" ? "Creating account..." : "Signing in...");

    try {
      const payload =
        authMode === "signup"
          ? { email: authEmail, password: authPassword, name: authName }
          : { email: authEmail, password: authPassword };
      const data = await apiRequest<{ user: User }>(`/api/auth/${authMode}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setUser(data.user);
      setAuthPassword("");
      setStatus("");
      await loadOpportunities();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed");
      setStatus("");
    }
  }

  async function logout() {
    setError("");
    await apiRequest("/api/auth/logout", { method: "POST" });
    setUser(null);
    setOpportunities([]);
    setOpportunityForm(emptyOpportunityForm);
    setEditingId(null);
  }

  async function submitOpportunity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setStatus(editingId ? "Updating opportunity..." : "Creating opportunity...");

    const payload = {
      ...opportunityForm,
      expected_close_date: opportunityForm.expected_close_date || null,
    };

    try {
      if (editingId) {
        await apiRequest(`/api/opportunities/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        await apiRequest("/api/opportunities", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setOpportunityForm(emptyOpportunityForm);
      setEditingId(null);
      setStatus("");
      await loadOpportunities();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save opportunity");
      setStatus("");
    }
  }

  function editOpportunity(opportunity: Opportunity) {
    setEditingId(opportunity.id);
    setOpportunityForm({
      name: opportunity.name,
      account_name: opportunity.account_name,
      value: opportunity.value,
      currency: opportunity.currency,
      stage: opportunity.stage,
      expected_close_date: opportunity.expected_close_date ?? "",
    });
  }

  async function deleteOpportunity(opportunityId: number) {
    setError("");
    setStatus("Deleting opportunity...");
    try {
      await apiRequest(`/api/opportunities/${opportunityId}`, { method: "DELETE" });
      setStatus("");
      await loadOpportunities();
      if (editingId === opportunityId) {
        setEditingId(null);
        setOpportunityForm(emptyOpportunityForm);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete opportunity");
      setStatus("");
    }
  }

  if (!user) {
    return (
      <main className="auth-shell">
        <section className="auth-panel">
          <div>
            <p className="eyebrow">OppTrail</p>
            <h1>Track every sales opportunity from first touch to close.</h1>
            <p className="lede">
              Sign in to manage your opportunity dashboard and keep the timeline
              work ready for the next phase.
            </p>
          </div>

          <form className="form" onSubmit={submitAuth}>
            <div className="segmented">
              <button
                type="button"
                className={authMode === "signup" ? "active" : ""}
                onClick={() => setAuthMode("signup")}
              >
                Sign up
              </button>
              <button
                type="button"
                className={authMode === "login" ? "active" : ""}
                onClick={() => setAuthMode("login")}
              >
                Sign in
              </button>
            </div>

            {authMode === "signup" && (
              <label>
                Name
                <input
                  value={authName}
                  onChange={(event) => setAuthName(event.target.value)}
                  required
                />
              </label>
            )}

            <label>
              Email
              <input
                type="email"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                required
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={authPassword}
                minLength={8}
                onChange={(event) => setAuthPassword(event.target.value)}
                required
              />
            </label>

            <button className="primary-button" type="submit">
              {authMode === "signup" ? "Create account" : "Sign in"}
            </button>
            {status && <p className="status">{status}</p>}
            {error && <p className="error">{error}</p>}
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OppTrail</p>
          <h1>Opportunities</h1>
        </div>
        <div className="user-block">
          <span>{user.name}</span>
          <button type="button" className="secondary-button" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <section className="dashboard-layout">
        <form className="form sidebar-form" onSubmit={submitOpportunity}>
          <h2>{editingId ? "Edit Opportunity" : "New Opportunity"}</h2>

          <label>
            Opportunity
            <input
              value={opportunityForm.name}
              onChange={(event) =>
                setOpportunityForm({ ...opportunityForm, name: event.target.value })
              }
              required
            />
          </label>

          <label>
            Account
            <input
              value={opportunityForm.account_name}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  account_name: event.target.value,
                })
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
                value={opportunityForm.value}
                onChange={(event) =>
                  setOpportunityForm({
                    ...opportunityForm,
                    value: event.target.value,
                  })
                }
                required
              />
            </label>

            <label>
              Currency
              <input
                maxLength={3}
                minLength={3}
                value={opportunityForm.currency}
                onChange={(event) =>
                  setOpportunityForm({
                    ...opportunityForm,
                    currency: event.target.value,
                  })
                }
                required
              />
            </label>
          </div>

          <label>
            Stage
            <select
              value={opportunityForm.stage}
              onChange={(event) =>
                setOpportunityForm({ ...opportunityForm, stage: event.target.value })
              }
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
              value={opportunityForm.expected_close_date}
              onChange={(event) =>
                setOpportunityForm({
                  ...opportunityForm,
                  expected_close_date: event.target.value,
                })
              }
            />
          </label>

          <button className="primary-button" type="submit">
            {editingId ? "Save changes" : "Create opportunity"}
          </button>
          {editingId && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setEditingId(null);
                setOpportunityForm(emptyOpportunityForm);
              }}
            >
              Cancel edit
            </button>
          )}
          {status && <p className="status">{status}</p>}
          {error && <p className="error">{error}</p>}
        </form>

        <section className="stage-board" aria-label="Opportunities grouped by stage">
          {groupedOpportunities.map(({ stage, items }) => (
            <div className="stage-column" key={stage}>
              <div className="stage-header">
                <h2>{stage}</h2>
                <span>{items.length}</span>
              </div>

              {items.length === 0 ? (
                <p className="empty-state">No opportunities</p>
              ) : (
                <div className="opportunity-list">
                  {items.map((opportunity) => (
                    <article className="opportunity-card" key={opportunity.id}>
                      <div>
                        <h3>{opportunity.name}</h3>
                        <p>{opportunity.account_name}</p>
                      </div>
                      <dl>
                        <div>
                          <dt>Value</dt>
                          <dd>
                            {opportunity.currency} {opportunity.value}
                          </dd>
                        </div>
                        <div>
                          <dt>Owner</dt>
                          <dd>{opportunity.owner_name}</dd>
                        </div>
                        <div>
                          <dt>Close</dt>
                          <dd>{opportunity.expected_close_date ?? "Not set"}</dd>
                        </div>
                      </dl>
                      <div className="card-actions">
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => editOpportunity(opportunity)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => deleteOpportunity(opportunity.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>
      </section>
    </main>
  );
}
