import React, { useState } from "react";
import { api, explain } from "../api.js";

/* Every account is provisioned with the same bootstrap password, which is what
   a bootstrap is. This is how it stops being the permanent one. */
export default function PasswordDialog({ onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const mismatch = again.length > 0 && next !== again;
  const ready = current && next.length >= 12 && next === again && !busy;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.changePassword({ current_password: current, new_password: next });
      setDone(true);
    } catch (err) {
      const body = explain(err);
      setError(body);
    }
    setBusy(false);
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Change password"
           onClick={(e) => e.stopPropagation()}>
        <h2>Change your password</h2>
        {done ? (
          <>
            <p className="quiet">
              Changed. Your other sessions are untouched — nothing you have open
              elsewhere was signed out.
            </p>
            <button className="btn primary" onClick={onClose}>Close</button>
          </>
        ) : (
          <form onSubmit={submit}>
            <p className="quiet small">
              At least twelve characters. Your current password is required, so a
              borrowed screen cannot lock you out of your own account.
            </p>
            <label htmlFor="pw-current">Current password</label>
            <input id="pw-current" type="password" autoComplete="current-password"
                   value={current} onChange={(e) => setCurrent(e.target.value)} />
            <label htmlFor="pw-new">New password</label>
            <input id="pw-new" type="password" autoComplete="new-password"
                   value={next} onChange={(e) => setNext(e.target.value)} />
            <label htmlFor="pw-again">New password again</label>
            <input id="pw-again" type="password" autoComplete="new-password"
                   value={again} onChange={(e) => setAgain(e.target.value)} />
            {mismatch && <div className="signin-error">The two do not match.</div>}
            {error && <div className="signin-error" role="alert">{error}</div>}
            <div className="modal-actions">
              <button className="btn primary" type="submit" disabled={!ready}>
                {busy ? "Changing…" : "Change password"}
              </button>
              <button className="btn quiet" type="button" onClick={onClose}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
