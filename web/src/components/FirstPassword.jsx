import React, { useState } from "react";
import { api, explain } from "../api.js";

/* The first screen a new person sees, and the only one until it is done.
 *
 * Not a nag. The API genuinely refuses to record anything from an account
 * still on a password somebody else picked, because a classification or a
 * certification made from such an account identifies two people rather than
 * one. Putting the rest of the application behind this is more honest than
 * showing somebody a set of screens that will refuse them. */

export default function FirstPassword({ actor, onDone, onSignOut }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const short = next.length > 0 && next.length < 12;
  const mismatch = again.length > 0 && next !== again;
  const ready = current && next.length >= 12 && next === again && !busy;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.changePassword({ current_password: current, new_password: next });
      onDone();
    } catch (err) {
      setError(explain(err)
        || "That did not work.");
      setBusy(false);
    }
  }

  return (
    <div className="signin-shell">
      <form className="card raised signin" onSubmit={submit}>
        <div className="signin-mark">Youngstown Business Incubator</div>
        <h1>Choose your own password</h1>
        {/* Two different facts, and the stronger one must not be softened
            into the weaker. A password an administrator picked for one person
            is known to two; the organisation's shared first-login password is
            known to everybody who was sent it. `holds_bootstrap_password`
            comes off the record rather than being inferred here. */}
        <p className="quiet">
          Welcome, {actor.display_name}.{" "}
          {actor.holds_bootstrap_password
            ? "You signed in with the password the whole organisation was " +
              "given, so it says nothing about who you are."
            : "The password you signed in with was issued to you, so two " +
              "people know it."}{" "}
          Everything you record here
          carries your name — a classification, a timesheet, a certification —
          and until the password is yours alone your name on a record would not
          mean much. This is the only step.
        </p>

        <label htmlFor="cur">
          {actor.holds_bootstrap_password
            ? "The password you were sent"
            : "The password you were given"}
        </label>
        <input id="cur" type="password" autoComplete="current-password" autoFocus
               value={current} onChange={(e) => setCurrent(e.target.value)} required />

        <label htmlFor="new">Your new password</label>
        <input id="new" type="password" autoComplete="new-password"
               value={next} onChange={(e) => setNext(e.target.value)} required />
        <div className="rowsub">
          {short
            ? "At least twelve characters."
            : "At least twelve characters. A phrase you will remember beats a short scramble you will write down."}
        </div>

        <label htmlFor="again">And again</label>
        <input id="again" type="password" autoComplete="new-password"
               value={again} onChange={(e) => setAgain(e.target.value)} required />
        {mismatch && <div className="signin-error">Those two do not match.</div>}

        {error && <div className="signin-error">{error}</div>}

        <button className="btn primary" type="submit" disabled={!ready}>
          {busy ? "Setting…" : "Set my password and continue"}
        </button>
        <button className="btn quiet" type="button" onClick={onSignOut}>
          Sign out instead
        </button>
      </form>
    </div>
  );
}
