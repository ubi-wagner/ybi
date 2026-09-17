import React, { useCallback, useEffect, useState } from "react";
import { api, explain, money } from "../api.js";
import { Card, Empty, Field, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

/*
  The controller's view of everyone's time.

  Reading a timesheet is review, which is Tom's job. Writing one never is, so
  there is nothing on this screen that enters an hour. What it does hold is the
  denominator: employment terms are payroll's fact, and until they are recorded
  nobody's sheet can be tested for completeness — a part-year employee measured
  against a full year can never submit.

  And one act that is not entering an hour: filing a page somebody signed.
  Thirty-seven of the forty-three have no account, so waiting for each of them
  to sign on a screen is waiting on an account somebody has to open first. A
  scan of their signature is the evidence 200.430(i) asks for, and until
  migration 120 there was nowhere on the record to put it — the register read
  0 of 43 with the pages in the library. It is deliberately not a supervisor
  signature: that is the filer asserting firsthand knowledge of the work, and
  this is the filer relaying somebody else's assertion.
*/

const hrs = (v) => v === null || v === undefined ? "—"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const pct = (v) => v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(0)}%`;

const STATUSES = [
  ["FULL_TIME", "Full time"], ["PART_TIME", "Part time"],
  ["TEMPORARY", "Temporary"], ["INTERN", "Intern"], ["CONTRACT", "Contract"],
];

export default function TimeRoster({ onOpen, actor }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [filing, setFiling] = useState(null);

  // The same portfolio the route takes, read from what the person holds
  // rather than from their rank — CONTROLLER is the name of a portfolio and
  // of a rank, and reading the rank here would hide the button from exactly
  // the person who holds the portfolio and nothing else.
  const held = actor?.portfolios || [];
  const canFile = held.includes("CONTROLLER") || held.includes("PROJECT");

  const load = useCallback(() =>
    api.timesheetRoster()
      .then((r) => { setRows(r); setError(""); })
      .catch((e) => setError(explain(e))), []);
  useEffect(() => { load(); }, [load]);

  if (error) return <Empty mark="!" title="Could not load">{error}</Empty>;
  if (!rows) return <Empty mark="…" title="Loading" />;

  const known = rows.filter((r) => r.terms_known).length;
  const withTime = rows.filter((r) => Number(r.entered_hours) > 0).length;
  const submitted = rows.filter((r) => r.submitted_at).length;
  const certified = rows.filter((r) => r.certified && !r.stale).length;

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <h1>Time</h1>
          <p className="quiet">
            Schedule G · everyone's timesheet, and the terms it is measured against
          </p>
        </div>
      </div>

      <Card variant="raised">
        <div className="stat-row">
          <Stat label="Employees" size="lg" value={rows.length} />
          <Stat label="Terms recorded" value={`${known} / ${rows.length}`}
                tone={known < rows.length ? "fail" : undefined}
                note={known < rows.length ? "no denominator without them" : "all known"} />
          <Stat label="Keeping time" value={withTime} />
          <Stat label="Submitted" value={submitted} />
          <Stat label="Certified" value={certified} />
        </div>
      </Card>

      <Card title="Roster" aside="Ordered by payroll, which is the order it matters in">
        <Table columns={[
          { label: "", width: 34, align: "left" },
          { label: "Employee", align: "left" },
          { label: "Wages" }, { label: "Terms", align: "left" },
          { label: "Expected" }, { label: "Entered" }, { label: "Coverage" },
          { label: "State", align: "left" }, { label: "", align: "left" },
        ]}>
          {rows.map((r) => (
            <tr key={r.employee_key}>
              <td className="l">
                <Tick state={r.certified && !r.stale ? "done"
                          : r.submitted_at ? "flagged"
                          : r.terms_known ? "open" : "failed"} />
              </td>
              <td className="l">
                <span className="strong">{r.employee_name || r.employee_key}</span>
                <div className="quiet small">{r.employee_key}</div>
              </td>
              <td className="num">{money(r.payroll_wages)}</td>
              <td className="l quiet small">
                {r.terms_known
                  ? <>{r.statuses.toLowerCase().replace(/_/g, " ")}, {Number(r.weekly_hours)}h
                      <div>{r.employed_from} → {r.employed_to}</div></>
                  : <span className="amt neg">not recorded</span>}
              </td>
              <td className="num">{hrs(r.expected_hours)}</td>
              <td className="num">{hrs(r.entered_hours)}</td>
              <td className="num">{pct(r.coverage)}</td>
              <td className="l">
                {r.certified && !r.stale
                  ? <Pill tone="good">{r.by_paper && !r.by_employee
                      ? "certified on paper" : "certified"}</Pill>
                  : r.stale ? <Pill tone="fail">stale</Pill>
                  : r.submitted_at ? <Pill tone="accent">submitted</Pill>
                  : Number(r.entered_hours) > 0 ? <Pill>in progress</Pill>
                  : <Pill>reconstruction</Pill>}
              </td>
              <td className="l">
                <button className="sm" onClick={() => setEditing(r)}>Terms</button>{" "}
                {Number(r.entered_hours) > 0 && (
                  <button className="sm" onClick={() => onOpen(r.employee_key)}>
                    Sheet
                  </button>
                )}{" "}
                {canFile && (
                  <button className="sm" onClick={() => setFiling(r)}>
                    {r.certified && !r.stale ? "Refile" : "File signed"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {editing && (
        <TermsDialog row={editing} onClose={() => setEditing(null)}
                     onSaved={() => { setEditing(null); load(); }} />
      )}

      {filing && (
        <FileSignedDialog row={filing} onClose={() => setFiling(null)}
                          onSaved={() => { setFiling(null); load(); }} />
      )}
    </div>
  );
}

function TermsDialog({ row, onClose, onSaved }) {
  const toast = useToast();
  const [spans, setSpans] = useState(null);
  const [status, setStatus] = useState("FULL_TIME");
  const [weekly, setWeekly] = useState("40");
  const [from, setFrom] = useState("2025-01-01");
  const [to, setTo] = useState("");
  const [source, setSource] = useState("2025 payroll register");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.employment({ employee_key: row.employee_key })
      .then(setSpans).catch(() => setSpans({ spans: [] }));
  }, [row.employee_key]);

  async function save() {
    setBusy(true);
    try {
      const r = await api.putEmployment({
        employee_key: row.employee_key, status,
        weekly_hours: Number(weekly), employed_from: from,
        employed_to: to || null, source_document: source,
      });
      toast(`${row.employee_key}: ${Number(r.expected_hours).toLocaleString()} hours expected`);
      onSaved();
    } catch (e) {
      toast(explain(e), { tone: "bad", sticky: true });
    }
    setBusy(false);
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal wide" role="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>{row.employee_name || row.employee_key}</h2>
        <p className="quiet small">
          A full-time year is 2,080 hours — fifty-two weeks at forty. Somebody
          who started in July is owed half of that, and their sheet is tested
          against half. Terms that changed mid-year are two spans, not an edit.
        </p>

        {spans?.spans?.length > 0 && (
          <ul className="span-list">
            {spans.spans.map((s) => (
              <li key={s.employment_id}>
                <span className="strong">{s.status.toLowerCase().replace(/_/g, " ")}</span>
                <span> {Number(s.weekly_hours)}h/week</span>
                <span className="quiet"> {s.employed_from} → {s.employed_to || "period end"}</span>
                <div className="quiet small">
                  {s.recorded_name} · {new Date(s.recorded_at).toLocaleDateString()}
                  {s.source_document && ` · ${s.source_document}`}
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="terms-grid">
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Hours a week">
            <input className="num" value={weekly} inputMode="decimal"
                   onChange={(e) => setWeekly(e.target.value.replace(/[^0-9.]/g, ""))} />
          </Field>
          <Field label="From">
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To" hint="Blank means still employed at period end">
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <Field label="Where this comes from">
            <input value={source} onChange={(e) => setSource(e.target.value)} />
          </Field>
        </div>

        <div className="modal-actions">
          <button className="btn primary" disabled={busy} onClick={save}>
            {busy ? "Recording…" : "Record the span"}
          </button>
          <button className="btn quiet" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

/*
  Filing a page somebody signed.

  Two calls, in the order the rules require. The scan goes through
  `POST /api/documents/upload`, which everybody signed in may use and which is
  the only place `storage.place()` decides where a file lands — a second
  bytes-writer would fail `tests/test_storage_paths.py`. Only then is the
  certification filed, naming the document that came back.

  Nothing here types a name. `signed_by` is read off the record for the
  employee whose effort it is, because a name box would let a typo put one
  person's signature against another's year and nothing downstream could catch
  it.
*/
function FileSignedDialog({ row, onClose, onSaved }) {
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [signedOn, setSignedOn] = useState("");
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  const name = row.employee_name || row.employee_key;

  async function fileIt() {
    setBusy(true);
    setProblem("");
    try {
      // One: the page. Content-addressed, so filing the same scan twice
      // files it once and answers with the id it already had.
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "certification");
      fd.append("period", "2025");
      fd.append("note", `200.430(i) certification signed by ${name}`);
      fd.append("doc_date", signedOn);
      const doc = await api.uploadDocument(fd);

      // Two: the certification, naming it.
      const r = await api.sign({
        employee_key: row.employee_key,
        on_paper: true,
        evidence_id: doc.evidence_id,
        paper_signed_on: signedOn,
        acknowledged: true,
      });
      toast(`Filed for ${r.signed_by}, signed ${r.paper_signed_on}`, { tone: "ok" });
      onSaved();
    } catch (e) {
      // Where it happened, in warm pencil, and not only in a toast that
      // fades while somebody is still reading the form.
      setProblem(explain(e));
      toast(explain(e), { tone: "bad", sticky: true });
    }
    setBusy(false);
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>File {name}'s signed certification</h2>
        <p className="quiet small">
          This records that <span className="strong">{name}</span> signed, and
          that you filed the page. It is not a statement by you about their
          work — that is a supervisor certification, which is a different act
          and says so on the record.
        </p>

        <div className="terms-grid">
          <Field label="The signed page"
                 hint="PDF or a photograph. It is filed in the library and the certification points at it.">
            <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
          </Field>
          <Field label="Date on the page"
                 hint="Not today's date unless that is what it says — the gap between the two is the filing lag.">
            <input type="date" value={signedOn} max={new Date().toISOString().slice(0, 10)}
                   onChange={(e) => setSignedOn(e.target.value)} />
          </Field>
        </div>

        <label className="cert-ack">
          <input type="checkbox" checked={read}
                 onChange={(e) => setRead(e.target.checked)} />
          <span>I have read this page and it carries {name}'s signature.</span>
        </label>

        {problem && <p className="refusal">{problem}</p>}

        <div className="modal-actions">
          <button className="btn primary"
                  disabled={busy || !file || !signedOn || !read}
                  onClick={fileIt}>
            {busy ? "Filing…" : "File it"}
          </button>
          <button className="btn quiet" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
