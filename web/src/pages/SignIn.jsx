import React, { useState } from "react";
import { api, explain } from "../api.js";

/* Sign-in stays deliberately plain. It is the one screen where a wrong guess
   about what the system wants costs the user a support call, so it says what
   it needs and nothing else. The sign-in error text mirrors the server's: it
   never distinguishes an unknown account from a wrong password.
 *
 * Two doors, because there were two situations and only one door. Thirty-
 * seven of the forty-three people on the 2025 payroll have no account, every
 * one of them has to sign their own 200.430(i) certification, and the only
 * way to an account was an administrator typing in an address and handing
 * out a password. Somebody arriving at this screen with no account had
 * nothing to do here except guess.
 *
 * Registering is deliberately **not** a third field on the sign-in form.
 * "Sign in" and "open an account" want the same two boxes and mean opposite
 * things by the password — yours, against the organisation's — and a form
 * that quietly does one or the other depending on whether a row exists is a
 * form that tells somebody they registered when they signed in as a
 * colleague. Two tabs, one heading each, saying which password it wants.
 */
export default function SignIn({ onSignedIn }) {
  const [mode, setMode] = useState("in");        // "in" | "new"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const registering = mode === "new";

  function switchTo(next) {
    setMode(next);
    setError("");
    setPassword("");
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const actor = registering
        ? await api.register(email.trim(), password, name.trim())
        : await api.login(email.trim(), password);
      onSignedIn(actor);
    } catch (err) {
      /* Registering says why and signing in does not, and that asymmetry is
         on purpose. A sign-in error that distinguished an unknown account
         from a wrong password would enumerate the organisation. A
         registration refusal is the opposite case: the person is standing
         at a door that did not open and the only useful thing to tell them
         is which of three reasons it was — wrong password, wrong domain, or
         a name the payroll register does not carry. Each one leads
         somewhere different, and "could not register" leads nowhere. */
      setError(registering
        ? (explain(err) || "That did not work.")
        : "Email or password is incorrect.");
      setBusy(false);
    }
  }

  return (
    <div className="signin-shell">
      <form className="card raised signin" onSubmit={submit}>
        <div className="signin-mark">Youngstown Business Incubator</div>
        <h1>Cost allocation</h1>

        <div className="signin-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={!registering}
                  className={`signin-tab ${registering ? "" : "on"}`}
                  onClick={() => switchTo("in")}>I have an account</button>
          <button type="button" role="tab" aria-selected={registering}
                  className={`signin-tab ${registering ? "on" : ""}`}
                  onClick={() => switchTo("new")}>I need one</button>
        </div>

        <p className="quiet">
          {registering
            ? <>Open your own account with your <code>@ybi.org</code> address
                and the password the organisation sent you. You will choose
                your own the moment you are in — and everything you record
                after that is against your name, which is the point.</>
            : <>Every classification, document and rate is recorded against
                the person signed in. Sign in as yourself.</>}
        </p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          placeholder={registering ? "surname@ybi.org" : undefined}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />

        {registering && (
          <>
            <label htmlFor="name">
              Your name <span className="quiet">— optional</span>
            </label>
            <input
              id="name"
              type="text"
              autoComplete="name"
              /* Optional because the payroll register already carries it,
                 and a blank is better than a guess: leaving it empty takes
                 the name the books have rather than whatever was typed in a
                 hurry. Every audit row is recorded under this. */
              placeholder="taken from the payroll register if left blank"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </>
        )}

        <label htmlFor="password">
          {registering ? "The organisation's password" : "Password"}
        </label>
        <input
          id="password"
          type="password"
          autoComplete={registering ? "one-time-code" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && <div className="signin-error" role="alert">{error}</div>}

        <button className="btn primary" type="submit" disabled={busy}>
          {busy
            ? (registering ? "Opening your account…" : "Signing in…")
            : (registering ? "Open my account" : "Sign in")}
        </button>

        {registering && (
          <p className="signin-foot quiet">
            Registering opens a timesheet and an inbox and nothing else. Being
            able to classify cost, seal a decision set or read the ledger is
            granted by the organisation's administrator, one person at a time,
            and is recorded when it is.
          </p>
        )}
      </form>
    </div>
  );
}
