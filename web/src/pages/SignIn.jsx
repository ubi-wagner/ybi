import React, { useState } from "react";
import { api } from "../api.js";

/* Sign-in stays deliberately plain. It is the one screen where a wrong guess
   about what the system wants costs the user a support call, so it says what
   it needs and nothing else. The error text mirrors the server's: it never
   distinguishes an unknown account from a wrong password. */
export default function SignIn({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const actor = await api.login(email.trim(), password);
      onSignedIn(actor);
    } catch (err) {
      setError("Email or password is incorrect.");
      setBusy(false);
    }
  }

  return (
    <div className="signin-shell">
      <form className="card raised signin" onSubmit={submit}>
        <div className="signin-mark">Youngstown Business Incubator</div>
        <h1>Cost allocation</h1>
        <p className="quiet">
          Every classification, document and rate is recorded against the person
          signed in. Sign in as yourself.
        </p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && <div className="signin-error" role="alert">{error}</div>}

        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
