import React, { useEffect, useState } from "react";

import { api, money } from "../api.js";
import { Card, Table, Tick } from "./ui.jsx";

/* Whether everything this system publishes ties to the financials.
 *
 * The system carries twenty-two control-shaped views and, until `103`,
 * nothing that collected them — so the question a reviewer actually arrives
 * with had twenty-two answers on twenty-two screens and *the reader kept the
 * list*. That is the hand-kept map at its purest, and it is the shape this
 * repository has been wrong about most often.
 *
 * Three rules, each one already kept somewhere here:
 *
 *  - **Nothing is computed.** Every state, variance and sentence is read
 *    from the row the control recorded it in, like the review screens
 *    underneath this band. A panel that decided for itself whether something
 *    ties would be a twenty-third opinion.
 *  - **The open ones are shown and the rest are folded**, because a reader
 *    handed twenty green rows scrolls past the two that matter — which is
 *    the evidence screen's own lesson about thirty-two unread workbooks
 *    burying three real proposals.
 *  - **`NO DATA` is never drawn as a pass.** A control that cannot be
 *    evaluated has not passed, and an empty set matching an empty set
 *    perfectly is the oldest defect in this file.
 */

/* The register's three words, in the tick vocabulary. Written down once
 * rather than inlined at each use: `worklistKinds.js` is the argument. */
const TICKS = { TIES: "done", OPEN: "flagged", "NO DATA": "open" };

export default function ReportTies({ period = "2025" }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);

  useEffect(() => {
    let live = true;
    api.reportTies(period)
      .then((d) => { if (live) setData(d); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [period]);

  // A failed read is not "everything ties". Rendering nothing would say the
  // second, which is the generous assumption a reader makes when a panel is
  // silent — `CertificationBand` takes the same care one component away.
  if (failed) {
    return (
      <Card title="Do the reports tie to the financials?" variant="quiet">
        <div className="rowsub">
          The register could not be read just now, so nothing here should be
          taken as tying.
        </div>
      </Card>
    );
  }
  if (!data) return null;

  const s = data.summary || {};
  const rows = data.anchors || [];
  const open = rows.filter((r) => r.state !== "TIES");
  const shown = all ? rows : open;

  const title = s.state === "TIES"
    ? `All ${s.anchors} anchors tie to the financials`
    : `${s.ties} of ${s.anchors} anchors tie to the financials`;

  return (
    <Card variant="quiet" style={{ marginTop: 16 }}
          title={<><Tick state={TICKS[s.state] || "open"} title={s.state} /> {title}</>}
          aside={s.no_data > 0
            ? `${s.no_data} cannot be evaluated, which is not a pass`
            : "Every row is read from the control that owns its figure"}>

      {shown.length === 0 ? (
        <div className="rowsub">Nothing outstanding.</div>
      ) : (
        <Table columns={[
          { label: "", width: 28 },
          { label: "Report", align: "left" },
          { label: "Anchor", align: "left" },
          { label: "Against", align: "left" },
          { label: "Difference" },
        ]}>
          {shown.map((r) => (
            <React.Fragment key={`${r.report}-${r.anchor}`}>
              <tr>
                <td className="l"><Tick state={TICKS[r.state] || "open"} title={r.state} /></td>
                <td className="l rowsub">{r.report.replace(/_/g, " ")}</td>
                <td className="l wrap">{r.anchor}</td>
                <td className="l wrap rowsub">{r.ties_to}</td>
                {/* A blank is a blank: several anchors are a state with no
                    amount behind them, and 0.00 would say the difference is
                    nothing rather than that there is no figure to give. */}
                <td className="amt num">
                  {r.variance === null || r.variance === undefined
                    ? "—" : money(r.variance)}
                </td>
              </tr>
              {/* A sentence in a column pushes the figures off the edge —
                  `tbody td` is nowrap, which is right for a figure and wrong
                  for a reason. Its own row, so a row cannot overlap a row. */}
              {r.needs && r.state !== "TIES" && (
                <tr className="subrow">
                  <td></td>
                  <td className="l rowsub wrap" colSpan={4}>{r.needs}</td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </Table>
      )}

      {rows.length > open.length && (
        <button className="ghost" style={{ marginTop: 10 }}
                onClick={() => setAll(!all)}>
          {all ? "Show only what is outstanding"
               : `Show all ${rows.length}, including the ${s.ties} that tie`}
        </button>
      )}
    </Card>
  );
}
