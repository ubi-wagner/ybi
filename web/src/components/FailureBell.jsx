import React, { useEffect, useState } from "react";
import { api, clearFailures, onFailure, recentFailures } from "../api.js";

/* What went wrong, kept where somebody can find it.
 *
 * Toasts answer "what just happened" and they are right to fade. This answers
 * a different question — "something did not work and I have moved on, what
 * was it" — and it is the question thirty-two screens could not answer at
 * all, because they load with `.catch(() => {})` and render an empty table
 * whether the data is empty or the request failed.
 *
 * It stays out of the way entirely when there is nothing to say. A permanent
 * status light that is green all day is one nobody looks at on the day it
 * turns red.
 *
 * **Two records, and they are not the same one.** The list above is what this
 * browser saw fail. `refusal` (migration 041) is what the *server* refused,
 * written by middleware rather than by each handler remembering — so it
 * carries refusals from other sessions, other people, and this one's own
 * reloads. This panel has always claimed "every one of these is also on the
 * record server-side" and had no way to show it: `GET /api/dashboard/refusals`
 * was complete and **called by nothing in the application**, found by the
 * sweep in `tests/test_every_capability_has_a_door.py`.
 */

function when(d) {
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return d.toLocaleTimeString();
}

export default function FailureBell() {
  const [items, setItems] = useState(recentFailures());
  const [refused, setRefused] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => onFailure((f) => setItems(f.slice())), []);
  /* Read once rather than on every open: a person who opens this three times
     is asking the same question three times. `.catch` to an empty list —
     somebody with a timesheet and nothing else may not read another
     person's refusals, and the panel is still worth showing them for their
     own. */
  useEffect(() => {
    api.refusals(25).then((r) => setRefused(r?.refusals || []))
       .catch(() => setRefused([]));
  }, []);

  if (!items.length && !refused.length) return null;

  const faults = items.filter((f) => f.status >= 500 || f.status === 0).length;
  const total = items.length + refused.length;

  return (
    <>
      <button className={`failbell${faults ? " fault" : ""}`}
              onClick={() => setOpen((x) => !x)}
              title="Requests that did not succeed">
        {total} {total === 1 ? "problem" : "problems"}
      </button>
      {open && (
        <>
          <div className="scrim" onClick={() => setOpen(false)} />
          <aside className="failpanel" role="dialog" aria-modal="true"
                 aria-label="Requests that did not succeed">
            <header>
              <div>
                <h3>What did not work</h3>
                <div className="rowsub">
                  Newest first. What this browser saw, and what the server
                  wrote down — they are two records and not the same one.
                </div>
              </div>
              <button className="ghost" onClick={() => setOpen(false)}
                      aria-label="Close">✕</button>
            </header>
            <div className="body">
              {items.map((f, i) => (
                <div key={i} className="failrow">
                  <div className="failhead">
                    <span className={`failcode${
                      f.status >= 500 || f.status === 0 ? " fault" : ""}`}>
                      {f.status || "—"}
                    </span>
                    <code>{f.method} {f.path}</code>
                    <span className="rowsub">{when(f.at)}</span>
                  </div>
                  <div className="failmsg">{f.message}</div>
                </div>
              ))}
              {refused.length > 0 && (
                <>
                  <div className="failsection">
                    On the server&apos;s record
                    <span className="rowsub">
                      {" "}— written whether or not a screen was watching
                    </span>
                  </div>
                  {refused.map((r, i) => (
                    <div key={`r${i}`} className="failrow">
                      <div className="failhead">
                        {/* `is_a_fault` is the server's own judgment — an
                            unhandled exception rather than a refusal — and
                            it is on the row. Deriving it from the status
                            here would be a second opinion about the same
                            fact. */}
                        <span className={`failcode${
                          r.is_a_fault ? " fault" : ""}`}>
                          {r.status || "—"}
                        </span>
                        <code>{r.method} {r.path}</code>
                        <span className="rowsub">
                          {r.actor || "anonymous"}
                        </span>
                      </div>
                      <div className="failmsg">
                        {r.detail || r.what_happened}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
            <footer>
              <button className="ghost" onClick={() => { clearFailures(); setOpen(false); }}>
                Clear the list
              </button>
            </footer>
          </aside>
        </>
      )}
    </>
  );
}
