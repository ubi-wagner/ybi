import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, explain } from "../api.js";
import { Card, Meter, PageHead, Stat, Tick, useToast } from "../components/ui.jsx";
import Certification from "../components/Certification.jsx";
import RateReview from "./RateReview.jsx";

/* Steps 7, 8 and 9 of the walk, on one screen: seal, compute, certify.
 *
 * They were two screens, and the nav mark said `7–9` over the one where none
 * of the three happened. Tom cleared the queue, opened Rate to seal, and
 * found no way to do it — right place by every map the system gives him, and
 * every one of those maps was wrong. A fold removes nav and never
 * capability; that one removed *reach*, which is the same thing wearing a
 * different word.
 *
 * So the three acts live here, and the review screens go back to being
 * purely read-only, which is what this repository has always said they are.
 *
 * **The build-up is on this screen rather than a click away**, because the
 * working loop is iterative: seal, compute, read the rate, unseal,
 * reclassify, recompute. Sending somebody to another screen to see what
 * their own button just produced is what makes an evaluation loop feel like
 * a filing system. It is the same component the workpaper renders, not a
 * second reading of it — a figure here and the same figure at `/review/rate`
 * cannot disagree, because there is one of it.
 *
 * **And nothing downstream is blocked by any of this.** An invoice can be
 * regenerated and a workbook produced against a rate nobody has signed;
 * testing against real figures is ordinary work, and a machine that refused
 * it is one people route around. What changes is that the paper says
 * NOT CERTIFIED and why — which is the rule the invoice renderer already
 * follows for a reproduction, pointed at the one fact every output reads.
 */
export default function Rates({ actor }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [cov, setCov] = useState(null);
  const [recon, setRecon] = useState(null);
  /* The build-up below is a separate component reading a separate endpoint,
     so it has to be told when a button here has moved the record. A counter
     used as its `key` remounts it, which re-reads rather than patching a
     copy — the same reason nothing on this screen is remembered from a call
     returning. */
  const [moved, setMoved] = useState(0);

  const load = useCallback(() => {
    api.rates().then(setData).catch(() => {});
    api.coverage().then(setCov).catch(() => {});
    api.reconcile().then(setRecon).catch(() => {});
    setMoved((n) => n + 1);
  }, []);
  useEffect(() => { load(); }, [load]);

  const seal = async () => {
    try {
      // `sealed_by` is reassigned from the session server-side — a name in
      // the request is only ever a label. Sending one anyway is how the
      // next route without that reassignment gets a literal in its trail.
      const r = await api.seal({});
      toast(`Sealed — ${r.seal_hash.slice(0, 16)}…`);
      load();
    } catch (e) { toast(explain(e), { tone: "bad", sticky: true }); }
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
  const unseal = async () => {
    const reason = window.prompt(
      "Unsealing supersedes every rate computed against this seal, and the "
      + "reason goes on the audit trail. Why is it being reopened?");
    if (reason === null) return;               // cancelled, not a blank
    try {
      const r = await api.unseal(reason);
      const n = r?.superseded ?? 0;
      toast(`Unsealed — ${n} rate${n === 1 ? "" : "s"} superseded`,
            { tone: "warn", sticky: true });
      load();
    } catch (e) {
      const msg = explain(e);
      toast(msg,
            { tone: "fail", sticky: true });
    }
  };

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
      const msg = explain(e);
      toast(msg,
            { tone: "fail", sticky: true });
    }
    setComputing(false);
  };

  const pct = Number(cov?.pct_dollars || 0);
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

  /* Portfolio, never rank. CONTROLLER is the name of a portfolio *and* of a
     rank, and reading `actor.role` here would hide these buttons from the
     person who holds the portfolio and nothing else — a nav stricter than
     the API, which `Facilities.jsx` shipped once. Every write below is
     `require_portfolio(CONTROLLER)`; the reads are `require_reader`, which
     is why the auditor gets the whole screen and none of the buttons. */
  const mayAct = (actor?.portfolios || []).includes("CONTROLLER");

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

        {!mayAct && (
          /* "Not yet, because", never a screen that simply has no buttons on
             it. An auditor may read every figure here and sign nothing, and
             being told which of those two they are is the difference between
             a screen that is theirs and a screen that looks broken. */
          <div className="rowsub gate" style={{ marginBottom: 14 }}>
            Sealing, computing and certifying are the controller&apos;s acts,
            and you do not hold that portfolio. Everything on this screen is
            readable — the gates, the build-up and whether the rate carries a
            signature.
          </div>
        )}

        <div className="row-actions">
          {mayAct && !sealed && (
            <button className="primary" onClick={seal}>Seal decision set</button>
          )}
          {/* **The way back had no door either.** The runbook's own recovery
              step — a judgment turns out to be wrong after sealing — says
              unseal with a written reason, and nothing in the application
              could. The reason is required and the handler refuses a blank,
              because an unseal with no reason is a hole in the trail the
              seal exists to make. */}
          {mayAct && sealed && (
            <button className="btn" onClick={unseal}>Unseal…</button>
          )}
          {/* Offered only once something is sealed. Computing against an open
              set is refused by the trigger, and a button that answers a
              constraint violation is the nav-stricter-than-the-API defect
              pointing the other way. */}
          {mayAct && sealed && (
            <button className="btn" onClick={compute} disabled={computing}>
              {computing ? "Computing…" : "Compute the rate"}
            </button>
          )}
        </div>
        {mayAct && sealed && (
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

      {/* Step 9. The signature, and the only door to putting one there.
          It used to sit on `/review/rate`, which made the read-only
          workpaper the one screen in the system that could certify. */}
      <div style={{ marginTop: 20 }}>
        <Certification actor={actor} key={`cert-${moved}`} />
      </div>

      {/* And the rate itself, read back — the same component the workpaper
          renders, so there is one reading of it rather than two.

          It is here because the loop is iterative: compute, read what came
          out, unseal, reclassify, recompute. A rate nobody has signed is a
          working figure and says so at the top of its own build-up; an
          invoice or a workbook produced against it carries NOT CERTIFIED and
          the reason, which is what makes previewing safe rather than
          something to be protected from. */}
      <div style={{ marginTop: 20 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>
          The rate that came out
        </div>
        <RateReview embedded actsHere key={`buildup-${moved}`} />
      </div>

      {/* The three deliverables. `/review` left the audit nav when the eight
          tabs became the order of operations, and this tab is its way back
          in: the auditor's report and Form 990 are read *after* the rate and
          have nowhere else to be reached from. A fold removes nav and never
          capability. */}
      <Card variant="quiet" style={{ marginTop: 20 }}>
        <div className="card-head">
          <div className="card-title">Read it as a workpaper</div>
          <span className="rowsub">
            The three things that leave the building — the auditor&apos;s
            report, this build-up and Form 990 Part IX — read together
          </span>
        </div>
        <Link className="btn" to="/review/rate">Final review</Link>
      </Card>
    </div>
  );
}
