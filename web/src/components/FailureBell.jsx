import React, { useEffect, useState } from "react";
import { clearFailures, onFailure, recentFailures } from "../api.js";

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
 */

function when(d) {
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return d.toLocaleTimeString();
}

export default function FailureBell() {
  const [items, setItems] = useState(recentFailures());
  const [open, setOpen] = useState(false);

  useEffect(() => onFailure((f) => setItems(f.slice())), []);

  if (!items.length) return null;

  const faults = items.filter((f) => f.status >= 500 || f.status === 0).length;

  return (
    <>
      <button className={`failbell${faults ? " fault" : ""}`}
              onClick={() => setOpen((x) => !x)}
              title="Requests that did not succeed">
        {items.length} {items.length === 1 ? "problem" : "problems"}
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
                  Newest first. Every one of these is also on the record
                  server-side if it reached the server.
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
