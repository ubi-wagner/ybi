import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, explain, money } from "../api.js";
import { Card, Empty, PageHead, Pill, Stat, Table, Tick } from "../components/ui.jsx";

/* The auditor's screen.
 *
 * Assembled in the order a reviewer actually works: do the books agree with
 * themselves, what was judged and on what evidence, where the standard bent
 * and why, what the rate came to, and what is still open. Everything on it is
 * read-only — this account writes nothing, which is the point of it — and the
 * whole record is downloadable, because a reviewer who has to ask the person
 * being reviewed for a copy is not independent of them. */

const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;
const when = (t) => (!t ? "" : String(t).slice(0, 10));

const STATE = { TIES: "done", OPEN: "failed", "NO DATA": "flagged" };

export default function Auditor({ embedded = false }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.auditorsReport().then(setD).catch((e) => setErr(explain(e)));
  }, []);

  if (err) return <div className="page"><Card><Empty mark="!" title="Could not read the record">{err}</Empty></Card></div>;
  if (!d) return <div className="page" />;

  const { controls = [], asset_control, exceptions = [], coverage,
          evidence_coverage = [], rates = [], reconciling_items = [] } = d;
  const open = controls.filter((c) => !c.ties);
  const covered = Number(coverage?.pct_dollars_covered || 0);
  const live = rates.filter((r) => r.status !== "SUPERSEDED");

  return (
    <div className={embedded ? "" : "page"}>
      {!embedded && (
      <PageHead title="Auditor's report" schedule="A-1"
                aside={<a className="btn" href={api.auditorsReportUrl()} download>
                         Download the report
                       </a>}>
        What the engagement asserts, and what proves each assertion. Nothing on
        this screen can be changed from it — reading the record is logged, which
        is your side of the same guarantee it gives everybody else.
      </PageHead>
      )}

      {(open.length > 0 || covered < 100) && (
        <div className="gate bad" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>
            <Tick state="failed" /> The record is not complete
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
            {covered < 100 && (
              <li>
                <strong>Classification is {covered}% complete by dollars</strong>
                <span className="rowsub">
                  {" — "}unclassified cost sits in no pool and is never
                  defaulted into one, so any rate below reads high. That is
                  the honest direction to err, and it is not a final figure.
                </span>
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="grid four">
        <Stat label="Cross-reference points" size="lg"
              value={`${controls.length - open.length}/${controls.length}`}
              tone={open.length ? "warn" : "pass"}
              note={open.length ? `${open.length} not settled` : "all tie"} />
        <Stat label="Classified" size="lg" value={`${covered}%`}
              tone={covered >= 80 ? "pass" : "warn"} note="of dollars" />
        <Stat label="Exceptions" size="lg" value={exceptions.length}
              note="each carries a reason" />
        <Stat label="Rates on file" size="lg" value={live.length || rates.length}
              note={live.length ? "live" : "all superseded"} />
      </div>

      <Card title="The books against themselves"
            aside="Run before anything was classified — the only order in which it is worth anything"
            style={{ marginTop: 16 }}>
        <Table columns={[
          { label: "", align: "left", width: "30px" },
          { label: "Control", align: "left" },
          { label: "What it proves", align: "left" },
          { label: "Ledger" }, { label: "Statement" },
          { label: "Left over" }, { label: "State", align: "left" },
        ]}>
          {controls.map((c) => (
            <tr key={c.control}>
              <td className="l"><Tick state={STATE[c.state] || "open"} title={c.state} /></td>
              <td className="l"><strong>{c.control}</strong></td>
              <td className="l rowsub wrap">{c.description}</td>
              <td className="amt">{money(c.left_value)}</td>
              <td className="amt">{money(c.right_value)}</td>
              <td className="amt">{c.exceptions > 0 ? `${c.exceptions} exc.` : money(c.variance)}</td>
              <td className="l">
                <Pill tone={c.state === "TIES" ? "good" : c.state === "NO DATA" ? "warn" : "fail"}>
                  {c.state}
                </Pill>
              </td>
            </tr>
          ))}
          {asset_control && (
            <tr>
              <td className="l"><Tick state={STATE[asset_control.state] || "open"} /></td>
              <td className="l"><strong>ASSET_REGISTER</strong></td>
              <td className="l rowsub wrap">
                {asset_control.needs
                  ? `Not evaluated — this needs ${asset_control.needs}.`
                  : "Asset register agrees with the ledger"}
              </td>
              <td className="amt">{money(asset_control.register_depreciation)}</td>
              <td className="amt">{money(asset_control.ledger_depreciation)}</td>
              <td className="amt">{money(asset_control.variance)}</td>
              <td className="l">
                <Pill tone={asset_control.state === "TIES" ? "good" : "warn"}>
                  {asset_control.state}
                </Pill>
              </td>
            </tr>
          )}
        </Table>
      </Card>

      <Card title="Differences, named"
            aside="Each carries the ledger lines it consists of — that is what separates an item from a plug"
            style={{ marginTop: 16 }}>
        {reconciling_items.length === 0 ? (
          <div className="rowsub">Nothing has needed naming.</div>
        ) : (
          <Table columns={[
            { label: "Control", align: "left" },
            { label: "Ledger puts it in", align: "left" },
            { label: "The statement puts it in", align: "left" },
            { label: "Amount" }, { label: "Lines" },
            { label: "Kind", align: "left" },
          ]}>
            {reconciling_items.map((it, i) => (
              <React.Fragment key={i}>
                <tr>
                  <td className="l rowsub">{it.control}</td>
                  <td className="l wrap">{it.from_account}</td>
                  <td className="l wrap">{it.to_account}</td>
                  <td className="amt">{money(it.amount)}</td>
                  <td className="amt">{it.lines}</td>
                  <td className="l"><Pill tone={it.kind === "ROUNDING" ? "warn" : ""}>{it.kind}</Pill></td>
                </tr>
                <tr className="subrow">
                  <td className="l rowsub wrap" colSpan={6}>{it.explanation}</td>
                </tr>
              </React.Fragment>
            ))}
          </Table>
        )}
      </Card>

      <div className="grid two" style={{ marginTop: 16 }}>
        <Card title="Documented cost by pool"
              aside="What proportion has a document behind it">
          {evidence_coverage.length === 0 ? (
            <div className="rowsub">No pool has been measured for evidence yet.</div>
          ) : (
            <Table columns={[
              { label: "Pool", align: "left" }, { label: "Dollars" },
              { label: "Documented" }, { label: "%" },
            ]}>
              {evidence_coverage.map((e, i) => (
                <tr key={i}>
                  <td className="l">{e.pool}</td>
                  <td className="amt">{money(e.dollars)}</td>
                  <td className="amt">{money(e.documented)}</td>
                  <td className="amt">{Number(e.pct_documented || 0).toFixed(1)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="Where the standard bent"
              aside="Every departure, with the reason given at the time">
          {exceptions.length === 0 ? (
            <div className="rowsub">Nothing has been recorded as an exception.</div>
          ) : (
            <Table columns={[
              { label: "Kind", align: "left" }, { label: "Subject", align: "left" },
              { label: "Amount" }, { label: "When", align: "left" },
            ]}>
              {exceptions.map((e, i) => (
                <React.Fragment key={i}>
                  <tr>
                    <td className="l">{e.kind}</td>
                    <td className="l wrap">{e.subject}</td>
                    <td className="amt">{e.amount === null ? "—" : money(e.amount)}</td>
                    <td className="l rowsub">{when(e.occurred_at)}</td>
                  </tr>
                  {e.reason && (
                    <tr className="subrow">
                      <td className="l rowsub wrap" colSpan={4}>{e.reason}</td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card variant="quiet" title="Take the record away"
            aside="Every download is recorded, including this one"
            style={{ marginTop: 16 }}>
        <div className="btn-row">
          <a className="btn" href={api.auditorsReportUrl()} download>Auditor's report (.xlsx)</a>
          <a className="btn" href={api.auditPackageUrl()} download>Whole cost record (.xlsx)</a>
          <a className="btn" href={api.rateBuildupUrl()} download>Indirect rate build-up (.xlsx)</a>
          <a className="btn" href={api.form990Url()} download>Form 990 Part IX (.xlsx)</a>
        </div>
        <div className="rowsub" style={{ marginTop: 10 }}>
          Also on screen: <Link to="/reconcile">Schedule A-1</Link>,{" "}
          <Link to="/review/rate">the rate build-up</Link> and{" "}
          <Link to="/review/form-990">the functional allocation</Link>.
        </div>
      </Card>
    </div>
  );
}
