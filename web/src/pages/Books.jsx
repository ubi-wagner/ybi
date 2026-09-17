import React from "react";
import { useNavigate, useParams } from "react-router-dom";

import Imports from "./Imports.jsx";
import Reconcile from "./Reconcile.jsx";
import { PageHead } from "../components/ui.jsx";

/* Getting the books in, and making them agree with themselves.
 *
 * Import and Reconcile were two tabs and are one job, done once, in order:
 * nothing downstream may start until the ledger is loaded and the eleven
 * cross-reference points tie — `POST /api/rates/compute` answers 409 while any
 * of them is open, because a rate over a ledger that does not match its own
 * statements is a rate over the wrong numbers.
 *
 * As two tabs they were two errands that are both finished five minutes into
 * the engagement and then sit in the nav for the rest of it. As one tab with
 * two panes the order is on the screen: load, then tie.
 *
 * **Nothing here is new.** Both panes are the existing screens, unchanged and
 * still answering at `/imports` and `/reconcile` — a bookmark, a link from the
 * worklist and the runbook's own addresses all still land. This is a nav
 * change, and a nav change that quietly moved a capability would be the thing
 * the fold was supposed to prevent.
 */
const PANES = [
  ["reconcile", "Reconcile", "A-1",
   "The general ledger, the profit and loss, the balance sheet and the "
   + "payroll register against each other. Eleven points, and a rate is "
   + "refused while any of them is open."],
  ["import", "Import", "A",
   "QuickBooks exports in. Nothing reaches the ledger until its printed "
   + "subtotals equal what sits under them."],
];

export default function Books({ actor }) {
  const { pane } = useParams();
  const nav = useNavigate();
  /* Reconcile first, because that is the one with outstanding work on it for
     the whole engagement; the import is done. Opening on Import would put the
     finished half in front of somebody every time. */
  const active = PANES.some(([k]) => k === pane) ? pane : "reconcile";
  const here = PANES.find(([k]) => k === active);

  return (
    <div className="page">
      <PageHead title="The books" schedule="A · A-1">
        The ledger as it arrived, and the four documents it has to agree with
        before anything is judged.
      </PageHead>

      <div className="seg" role="tablist" style={{ marginBottom: 18 }}>
        {PANES.map(([key, label, sched]) => (
          <button key={key} role="tab" aria-selected={key === active}
                  className={key === active ? "on" : ""}
                  onClick={() => nav(key === "reconcile" ? "/books" : `/books/${key}`)}>
            {label} <span className="rowsub">{sched}</span>
          </button>
        ))}
      </div>

      <p className="quiet small" style={{ marginTop: -8, marginBottom: 16 }}>
        {here[3]}
      </p>

      {active === "import" ? <Imports /> : <Reconcile actor={actor} />}
    </div>
  );
}
