"use client";

import { FormEvent, useState } from "react";

import { useAuthenticate } from "../lib/queries";

/**
 * The signed-out shell: sign up or sign in, in one panel.
 *
 * Everything the app shows past this point needs a session, so this is the
 * gate `DashboardPage` renders instead of the dashboard when there is none.
 */
export function AuthPanel() {
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const authenticate = useAuthenticate();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    authenticate.mutate(
      { mode, email, password, name },
      { onSuccess: () => setPassword("") },
    );
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div>
          <p className="eyebrow">OppTrail</p>
          <h1>Track every sales opportunity from first touch to close.</h1>
          <p className="lede">
            Sign in to manage your opportunity dashboard and timeline notes.
          </p>
        </div>

        <form className="form" onSubmit={submit}>
          <div className="segmented">
            <button
              type="button"
              className={mode === "signup" ? "active" : ""}
              onClick={() => setMode("signup")}
            >
              Sign up
            </button>
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
          </div>

          {mode === "signup" && (
            <label>
              Name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          <button className="primary-button" type="submit">
            {mode === "signup" ? "Create account" : "Sign in"}
          </button>
          {authenticate.isPending && (
            <p className="status">
              {mode === "signup" ? "Creating account..." : "Signing in..."}
            </p>
          )}
          {authenticate.isError && (
            <p className="error">{authenticate.error.message}</p>
          )}
        </form>
      </section>
    </main>
  );
}
