import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, explain, money } from "../api.js";
import { Card, Empty, PageHead, Pill, Stat, Table, Tick } from "../components/ui.jsx";
import Certification from "../components/Certification.jsx";

/* Schedule D — the indirect rate, built up rather than asserted.
 *
 * A rate on its own is a number a sponsor has to take on trust. What they
 * actually ask for is the build-up: what went into the pool, what came out of
 * it and under what authority, what the base was, and which sealed set of
 * judgments the whole thing hangs off.
 *
 * This screen never computes anything. Every figure is read from the rate on
 * file, because a figure derived twice is a figure that can disagree with
 * itself, and the one on the workpaper would be the one nobody could
 * reproduce. */

const pct = (v) => `${(Number(v || 0) * 100).toFixed(4)}%`;

const BASE = {
  MTDC: "Modified total direct cost",
  SALARIES_WAGES: "Salaries and wages",
  TOTAL_DIRECT: "Total direct cost",
};

const KIND = {
  FRINGE: ["Fringe", "Over the wage base"],
  OVERHEAD: ["Overhead", "Facilities and related occupancy"],
  "G&A": ["General and administrative", "Benefits the whole body"],
  INDIRECT_COMBINED: ["Indirect, combined", "Overhead and G&A, one base"],
};

export default function RateReview({ embedded = false, actor }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.reviewRate().then(setD).catch((e) => setErr(explain(e)));
  }, []);

  if (err) return <div className="page"><Card><Empty mark="!" title="Could not read the rate">{err}</Empty></Card></div>;
  if (!d) return <div className="page" />;

  /* The endpoint returns live rates only — a recomputation or an unseal
     supersedes what it replaces rather than sitting beside it, so an empty
     list means there is no rate, not that the screen failed to find one. */
  const { rates: shown = [], carve_outs = [], coverage,
          open_controls = [], final } = d;
  const covered = Number(coverage?.pct_dollars_covered || 0);

  return (
    <div className={embedded ? "" : "page"}>
      {!embedded && (
      <PageHead title="Indirect rate" schedule="D"
                aside={final
                  ? <Pill tone="good">Final</Pill>
                  : <Pill tone="warn">Working figure</Pill>}>
        The pool, what was taken out of it and under what authority, the base,
        and the seal it hangs off. Nothing here is recomputed — it is the rate
        on file, read back.
      </PageHead>
      )}

      {/* The signature, and the only door to putting one there. Above the
          figures, because whether the rate is certified is the first thing a
          reader needs and the last thing they should have to scroll for. */}
      <Certification actor={actor} />

      {!final && (
        <div className="gate bad" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>
            <Tick state="failed" /> This is not a final rate
          </div>
          <ul className="gate-list">
            {open_controls.map((c) => (
              <li key={c.control}>
                <strong>{c.control}</strong>
                <span className="rowsub">{" — "}{c.state === "NO DATA" ? c.note : c.description}</span>
              </li>
            ))}
            {covered < 100 && (
              <li>
                <strong>Classification is {covered}% complete by dollars</strong>
                <span className="rowsub">
                  {" — "}cost nobody has judged sits in no pool, so the rate
                  reads high. That is the honest direction to err, and it is
                  not a rate to quote.
                </span>
              </li>
            )}
          </ul>
          <Link className="btn sm" to="/classify">Open the queue</Link>
        </div>
      )}

      {shown.length === 0 ? (
        <Card>
          <Empty mark="%" title="No rate on file">
            Seal the decision set and compute a rate, and the build-up appears
            here. If there was one, unsealing superseded it — a rate cannot
            outlive the judgments it was computed from.
          </Empty>
        </Card>
      ) : (
        <>
          <div className="grid two">
            {shown.map((r) => {
              const [label, note] = KIND[r.kind] || [r.kind, ""];
              return (
                <Card key={r.kind} variant="raised" title={label} aside={note}>
                  <div className="rate-figure num">{pct(r.rate)}</div>
                  <table className="buildup">
                    <tbody>
                      <tr>
                        <th>Pool</th>
                        <td className="amt">{money(r.pool_amount)}</td>
                      </tr>
                      {r.pool_gross !== null && r.pool_gross !== undefined && (
                        <>
                          <tr className="sub">
                            <th>gross, as classified</th>
                            <td className="amt">{money(r.pool_gross)}</td>
                          </tr>
                          <tr className="sub">
                            <th>less carve-outs ({r.carve_outs})</th>
                            <td className="amt">{money(r.pool_carved)}</td>
                          </tr>
                        </>
                      )}
                      <tr>
                        <th>Base — {BASE[r.base_type] || r.base_type}</th>
                        <td className="amt">{money(r.base_amount)}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div className="rowsub seal-line">
                    Sealed by {r.sealed_by} · set “{r.decision_set}” ·{" "}
                    <span className="mono" title={r.seal_hash}>
                      {String(r.seal_hash || "").slice(0, 16)}…
                    </span>
                    {r.status !== "PROPOSED" && <> · <Pill>{r.status}</Pill></>}
                  </div>
                </Card>
              );
            })}
          </div>

          <Card title="Carve-outs"
                aside="What was removed from a pool before the rate was struck"
                style={{ marginTop: 16 }}>
            {carve_outs.length === 0 ? (
              <div className="rowsub">
                Nothing has been carved out of any pool. Where a carve-out is
                required — the facilities share attributable to tenants, for
                one — it is missing rather than zero.
              </div>
            ) : (
              <Table columns={[
                { label: "Pool", align: "left" }, { label: "What", align: "left" },
                { label: "Authority", align: "left" }, { label: "Amount" },
                { label: "Driver", align: "left" }, { label: "Grade", align: "left" },
              ]}>
                {carve_outs.map((c, i) => (
                  <tr key={i}>
                    <td className="l">{c.pool}</td>
                    <td className="l">{c.name}</td>
                    <td className="l rowsub">{c.citation}</td>
                    <td className="amt">{money(c.amount)}</td>
                    <td className="l rowsub wrap">{c.driver}</td>
                    <td className="l"><Pill>{c.grade}</Pill></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          <Card variant="quiet" style={{ marginTop: 16 }}>
            <div className="card-head">
              <div className="card-title">Take it away</div>
              <span className="rowsub">
                The same figures, in a workbook that says on its first sheet
                what is unfinished
              </span>
            </div>
            <a className="btn" href={api.rateBuildupUrl()} download>
              Rate build-up (.xlsx)
            </a>
          </Card>
        </>
      )}
    </div>
  );
}
