import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Card, Empty, Meter, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

export default function Rates() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [cov, setCov] = useState(null);
  const [recon, setRecon] = useState(null);

  const load = useCallback(() => {
    api.rates().then(setData).catch(() => {});
    api.coverage().then(setCov).catch(() => {});
    api.reconcile().then(setRecon).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const seal = async () => {
    try {
      const r = await api.seal({ sealed_by: "tom" });
      toast(`Sealed — ${r.seal_hash.slice(0, 16)}…`);
      load();
    } catch (e) { toast(String(e.message || e), { tone: "bad", sticky: true }); }
  };

  /* **The rate had no door.** `POST /api/rates/compute` was complete on the
     server and named in the comment below, and nothing in the SPA had ever
     called it — so the one figure the whole engagement exists to produce
     could only be made by somebody running a script. That is the
     restatement's defect and the timesheet draft's, in the place it costs
     most.

     It sends `{}`. Every field on the body is a policy with a default, and
     a screen that invented one would be refused — which is the behaviour
     that is wanted, not a thing to work around. */
  const [computing, setComputing] = useState(false);
  /* **The basis is a choice and the screen has to make it.** Migration 068
     records it on the rate, the way `base_type` records which base a rate was
     taken over, and it is worth ~9 points of combined rate on the same sealed
     judgments. The first version of this button sent `{}` and computed
     OBJECTIVE — the default, correctly, and *not* the basis this engagement
     settled on. That is the defect `ComputeIn`'s `extra="forbid"` exists to
     stop one level up: the ordinary failure is not "ignore something
     harmless", it is "apply a policy the caller did not choose".

     OBJECTIVE stays the default, because nothing may change by default. */
  const [basis, setBasis] = useState("OBJECTIVE");
  const compute = async () => {
    setComputing(true);
    try {
      const r = await api.computeRate({ admin_labour: basis });
      const n = (r.rates || []).length;
      toast(n ? `Computed ${n} rate${n === 1 ? "" : "s"} on the ${basis} basis, `
                + `against the seal`
              : "The computation returned no rate", { tone: n ? "ok" : "warn",
                                                      sticky: !n });
      load();
    } catch (e) {
      /* A 409 here is the system working: the books do not agree, or the set
         moved under the read. It carries the reason, so it is shown rather
         than replaced with a tone. */
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { detail = JSON.parse(msg).detail || msg; } catch { /* plain text */ }
      toast(typeof detail === "string" ? detail : JSON.stringify(detail),
            { tone: "fail", sticky: true });
    }
    setComputing(false);
  };

  const pct = Number(cov?.pct_dollars || 0);
  const rates = data?.rates || [];
  /* Read from the record, never remembered. A flag set when the seal
     call returns is wrong the moment somebody reloads — or the moment
     the other controller unseals. */
  const sealed = Boolean(data?.sealed);

  /* Two gates stand in front of a rate and only one of them is coverage.
     The books have to agree with themselves first — POST /api/rates/compute
     answers 409 while any cross-reference point is open — and this screen
     used to say coverage was the only gate that mattered. It is the softer
     of the two: sealing below 80% is a judgment, while an open control is a
     refusal. Somebody could seal, ask for a rate, and meet a 409 explaining
     a condition no screen had mentioned. */
  const open = (recon?.controls || []).filter((c) => !c.ties);

  return (
    <div className="page">
      <PageHead title="Rates" schedule="D">
        Sealing hashes every live classification and freezes the set. Only then can a rate
          be computed, and the rate carries the seal — so it can be shown to be a consequence
          of the judgments rather than a target they were fitted to.
      </PageHead>

      <Card variant="raised">
        <div className="card-head">
          {/* The heading is read from the record like everything else here.
              It said "Before sealing" over a sealed set carrying four rates,
              which is a screen contradicting the row beneath it. */}
          <div className="card-title">
            {sealed ? "Sealed" : "Before sealing"}
          </div>
          <span className="rowsub">
            {sealed
              ? `Sealed${data?.sealed_by ? ` by ${data.sealed_by}` : ""} — `
                + "classifications can now change only by unsealing, which "
                + "supersedes the rate"
              : "Two gates: the books must agree, and the queue should be "
                + "finished"}
          </span>
        </div>
        <div className="stat-row" style={{ marginBottom: 14 }}>
          <Stat label="Dollar coverage" size="xl" value={`${pct.toFixed(1)}%`}
                tone={pct >= 80 ? "pass" : "warn"} />
          <Stat label="Groups left" size="lg" value={cov?.groups_remaining ?? "—"} />
        </div>
        <Meter pct={pct} target={80} good={pct >= 80} />
        <div className="rowsub" style={{ margin: "12px 0 14px" }}>
          {pct >= 80
            ? "The base is complete enough to seal."
            : "Sealing below 80% is allowed — an unfinished build should overstate rather than flatter — but finish the queue first if you can."}
        </div>

        {recon && (
          open.length === 0 ? (
            <div className="rowsub gate ok" style={{ marginBottom: 14 }}>
              <Tick state="done" /> The books agree with themselves — all{" "}
              {(recon.controls || []).length} cross-reference points tie.
            </div>
          ) : (
            <div className="gate bad" style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                <Tick state="failed" /> No rate can be computed yet
              </div>
              <div className="rowsub">
                {open.length === 1 ? "One cross-reference point is" : `${open.length} cross-reference points are`}{" "}
                not settled. A rate over a ledger that does not agree with its
                own statements is a rate over the wrong numbers, so the
                computation refuses rather than producing one.
              </div>
              <ul className="gate-list">
                {open.map((c) => (
                  <li key={c.control}>
                    <strong>{c.control}</strong>
                    <span className="rowsub">
                      {" — "}{c.state === "NO DATA" ? c.note : c.description}
                    </span>
                  </li>
                ))}
              </ul>
              <Link className="btn sm" to="/reconcile">Open Schedule A-1</Link>
            </div>
          )
        )}

        <div className="row-actions">
          <button className="primary" onClick={seal}>Seal decision set</button>
          {/* Offered only once something is sealed. Computing against an open
              set is refused by the trigger, and a button that answers a
              constraint violation is the nav-stricter-than-the-API defect
              pointing the other way. */}
          {sealed && (
            <button className="btn" onClick={compute} disabled={computing}>
              {computing ? "Computing…" : "Compute the rate"}
            </button>
          )}
        </div>
        {sealed && (
          <div className="rowsub" style={{ marginTop: 8 }}>
            <p style={{ margin: "0 0 8px" }}>
              Computing reads the sealed judgments and writes the rate against
              that seal. It is arithmetic, not a judgment — the judgment was
              sealing. Recomputing supersedes the rate on file rather than
              editing it.
            </p>
            {/* Stated on the screen rather than defaulted silently: it is
                recorded on the rate and it moves the combined figure by
                about nine points on the same judgments. */}
            <label className="ts-basis">
              <span>Administrative labour —</span>
              <select value={basis} onChange={(e) => setBasis(e.target.value)}>
                <option value="OBJECTIVE">
                  a cost objective (YBI-GA bears indirect)
                </option>
                <option value="POOL">
                  in the G&amp;A pool (it is the indirect)
                </option>
              </select>
            </label>
            <p style={{ margin: "6px 0 0" }}>
              2 CFR 200 Appendix IV B puts the director&apos;s office,
              accounting and personnel administration <em>in</em> the G&amp;A
              pool. Treating it as an objective allocates the indirect pool to
              its own administration, which recovers from nobody. It is
              recorded on the rate either way, so the workpaper says which was
              chosen.
            </p>
          </div>
        )}
      </Card>

      <div style={{ marginTop: 20 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Computed rates</div>
        {rates.length === 0 ? (
          <Card><Empty mark="%" title="No rate yet">
            Seal the decision set to unlock the rate phase. A database trigger refuses any
            rate whose seal does not match a sealed set.
          </Empty></Card>
        ) : (
          <Table columns={[
            { label: "Rate", align: "left" }, { label: "Pool" }, { label: "Base", align: "left" },
            { label: "Base amount" }, { label: "Rate" }, { label: "Status", align: "left" },
            { label: "Seal", align: "left" },
          ]}>
            {rates.map((r, i) => (
              <tr key={i} className="hoverable">
                <td className="l" style={{ fontWeight: 600 }}>{r.kind.replace(/_/g, " ")}</td>
                <td>{Number(r.pool_amount).toLocaleString()}</td>
                <td className="l rowsub">{r.base_type}</td>
                <td>{Number(r.base_amount).toLocaleString()}</td>
                <td style={{ fontWeight: 700, fontSize: 14 }}>{(Number(r.rate) * 100).toFixed(2)}%</td>
                <td className="l"><Pill tone={r.status === "ACCEPTED" ? "pass" : ""}>{r.status}</Pill></td>
                <td className="l mono-ref">{String(r.seal_hash).slice(0, 12)}…</td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </div>
  );
}
