import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api.js";
import { Card, Tick } from "./ui.jsx";

/* The 2025 audit as the one ordered journey it is.
 *
 * The door opened on the generic dashboard — a worklist, a document count, a
 * manual panel — which answers *what is outstanding* and never *where am I in
 * this*. Those are different questions and the second is the one a controller
 * closing a year actually holds: the file is closed in an order, each step
 * depends on the one before it, and **the order is the whole guarantee**.
 * Classification is sealed before any rate is computed; a landing page that
 * listed those as two items on a to-do list said nothing about that.
 *
 * Nothing on this screen is computed. `v_audit_walk` owns every figure and
 * each of its steps reads the view that already holds it — the reconciliation
 * from `v_statement_reconciliation`, the coverage from
 * `v_classification_coverage`, the partitions from `v_partition_coverage`.
 *
 * Four states, and the fourth is what a task list usually gets wrong:
 *
 *   DONE      finished
 *   OPEN      work outstanding that somebody here can do
 *   NO DATA   cannot be evaluated; it needs something from outside, and an
 *             empty set matching an empty set perfectly is not a pass
 *   WAITING   an earlier step is not done, so this one cannot honestly be
 *             called open — offering it would offer work the server refuses
 */
const TICK = { DONE: "done", OPEN: "open", "NO DATA": "flagged", WAITING: "" };

const SAYS = {
  DONE: "done",
  OPEN: "to do",
  "NO DATA": "waiting on a document",
  WAITING: "not yet",
};

export default function Walk({ period = "2025" }) {
  const [steps, setSteps] = useState(null);
  const [failed, setFailed] = useState(null);

  useEffect(() => {
    let live = true;
    api.walk(period)
       .then((r) => live && setSteps(r))
       /* A failed read and an empty walk are different facts. Thirty-two
          screens once loaded with `.catch(() => {})` and printed "nothing
          yet" for both; `req()` records it underneath, and this says so
          rather than rendering an empty page. */
       .catch((e) => live && setFailed(String(e.message || e)));
    return () => { live = false; };
  }, [period]);

  if (failed) {
    return (
      <Card variant="raised" title="The walk">
        <p className="quiet">
          The steps could not be read: {failed}
        </p>
      </Card>
    );
  }
  if (!steps) return <Card variant="quiet"><span className="rowsub">Loading…</span></Card>;

  const done = steps.filter((s) => s.state === "DONE").length;
  /* The next thing to do is the first step that is not finished and is not
     waiting on an earlier one — which is what makes this a walk rather than a
     list. A step blocked on a document somebody else holds is named too,
     because "go and get it" is the work. */
  const next = steps.find((s) => s.state === "OPEN")
            || steps.find((s) => s.state === "NO DATA");

  return (
    <Card variant="raised" title="Closing 2025"
          aside={<span className="rowsub">{done} of {steps.length} steps done</span>}>
      <p className="quiet small" style={{ marginTop: -6, marginBottom: 14 }}>
        The file is closed in this order and each step rests on the one before
        it. No rate exists until the classifications are sealed — that sequence
        is the answer to whether the rate was reverse-engineered, so it is the
        shape of this page rather than a note at the bottom of it.
      </p>

      <ol className="walk">
        {steps.map((s) => (
          <li key={s.seq} className={`walk-step ${s.state === "DONE" ? "is-done" : ""}`}>
            <span className="walk-mark"><Tick state={TICK[s.state] || ""} /></span>
            <span className="walk-body">
              <Link to={s.goes_to} className="walk-title">{s.step}</Link>
              <span className="walk-what">{s.what}</span>
              <span className="walk-detail">{s.detail}</span>
            </span>
            <span className={`walk-state s-${s.state.replace(" ", "-").toLowerCase()}`}>
              {SAYS[s.state] || s.state.toLowerCase()}
            </span>
          </li>
        ))}
      </ol>

      {next && (
        <div className="walk-next">
          Next: <Link to={next.goes_to}>{next.step}</Link>
          <span className="rowsub"> — {next.detail}</span>
        </div>
      )}
    </Card>
  );
}
