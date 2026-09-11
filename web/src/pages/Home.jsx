import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money } from "../api.js";
import { Card, Empty, Meter, PageHead, Pill, Stat, Table, Tick } from "../components/ui.jsx";
import Manual from "../components/Manual.jsx";

/* Where each person lands.
 *
 * One screen, assembled from what the person actually holds, rather than
 * five screens and a switch. The order is deliberate: what is mine to do
 * today, then what I have sent in, then the state of the thing we are all
 * working on. Somebody who only keeps a timesheet sees the first two and
 * stops; the controller sees all of it.
 *
 * The rule this page follows is the same one the nav follows — never offer
 * something that will answer 403. A card is here because the person can act
 * on it. */

const PORTFOLIO_WORK = {
  CONTROLLER: {
    label: "Classification",
    to: "/classify",
    what: "Put the ledger into cost pools with evidence. The queue is ordered by money, which is the order it is worth doing in.",
  },
  FACILITIES: {
    label: "Space",
    to: "/space",
    what: "Buildings, suites and what each one would fetch at market beside what it was charged.",
  },
  INVENTORY: {
    label: "Inventory",
    to: "/inventory",
    what: "The equipment register, what its use was worth by the hour, and the lab floor it stands on.",
  },
  PROJECT: {
    label: "Awards",
    to: "/awards",
    what: "Contract ceilings, cost share and what each award will bear.",
  },
  OFFICE: {
    label: "Evidence",
    to: "/evidence",
    what: "Documents people have sent in, and what each one supports.",
  },
};

export default function Home({ actor }) {
  const [docs, setDocs] = useState(null);
  const [dash, setDash] = useState(null);
  const [inbox, setInbox] = useState(null);
  const [gaps, setGaps] = useState(null);

  useEffect(() => {
    api.myDocuments().then(setDocs).catch(() => {});
    if (actor.can_read) api.dashboard().then(setDash).catch(() => {});
    if ((actor.portfolios || []).includes("OFFICE"))
      api.documentInbox().then(setInbox).catch(() => {});
    if (actor.is_admin) api.rosterGaps().then(setGaps).catch(() => {});
  }, [actor]);

  const held = actor.portfolios || [];
  const open = dash?.controls?.filter((c) => !c.ties) || [];

  return (
    <div className="page">
      <PageHead title={`Good to see you, ${actor.display_name}`}>
        {describe(actor)}
      </PageHead>

      {/* ── Mine ─────────────────────────────────────────────── */}
      {actor.employee_key && (
        <Card variant="raised" title="Yours to do">
          <div className="grid two">
            <div>
              <h4 style={{ margin: "0 0 4px" }}>
                <Link to="/timesheet">My time</Link>
              </h4>
              <p className="rowsub">
                Build your 2025 timesheet from whatever records you have —
                a calendar, a project log, an email trail. Week by week is
                usually faster than day by day, and nothing has to be perfect
                on the first pass.
              </p>
            </div>
            <div>
              <h4 style={{ margin: "0 0 4px" }}>
                <Link to="/certify">My effort</Link>
              </h4>
              <p className="rowsub">
                When the year looks right, sign it. Only you can — a
                certification signed by somebody else is not what 2 CFR
                200.430(i) asks for.
              </p>
            </div>
          </div>
        </Card>
      )}

      <Card title="Documents">
        <div className="grid three">
          <Stat label="Sent in" value={docs?.uploaded ?? "—"} size="lg" />
          <Stat label="Put to work" value={docs?.in_use ?? "—"} size="lg"
                note="attached to a cost by somebody who holds the portfolio" />
          <Stat label="Waiting" value={docs?.waiting ?? "—"} size="lg"
                note={docs?.waiting ? "not yet attached to anything" : "nothing outstanding"} />
        </div>
        <p className="rowsub" style={{ marginTop: 12 }}>
          Receipts, invoices, project plans, photographs of a nameplate, a
          comparable lease — anything that shows what a cost was for. You do
          not have to know where it belongs; say what it relates to and
          somebody will file it.
        </p>
        <Link className="btn primary" to="/documents">Send in a document</Link>
      </Card>

      <Manual actor={actor} />

      {/* ── Portfolios ───────────────────────────────────────── */}
      {held.length > 0 && (
        <Card title={held.length === 1 ? "Your portfolio" : "Your portfolios"}
              aside={held.join(" · ")}>
          <div className="grid two">
            {held.filter((p) => PORTFOLIO_WORK[p]).map((p) => {
              const w = PORTFOLIO_WORK[p];
              return (
                <div key={p}>
                  <Link to={w.to}><strong>{w.label}</strong></Link>
                  <div className="rowsub">{w.what}</div>
                </div>
              );
            })}
          </div>
          {actor.may_seal && (
            <p className="rowsub" style={{ marginTop: 12 }}>
              You hold CONTROLLER, which is the only portfolio that can seal a
              decision set and compute a rate. No rate exists or is shown while
              classification is open — that sequence is the thing the audit file
              rests on.
            </p>
          )}
        </Card>
      )}

      {inbox?.waiting > 0 && (
        <Card title="Sent in, waiting for somebody to file it"
              aside={`${inbox.waiting} document${inbox.waiting === 1 ? "" : "s"}`}>
          <Table columns={[
            { label: "From", align: "left" },
            { label: "What they say it is", align: "left" },
            { label: "Received", align: "left" },
          ]}>
            {inbox.documents.slice(0, 8).map((d) => (
              <tr key={d.evidence_id}>
                <td className="l">{d.uploaded_by_name || d.received_from}</td>
                <td className="l">{d.suggested_for || d.note || <span className="rowsub">no description</span>}</td>
                <td className="l rowsub">{String(d.received_at).slice(0, 10)}</td>
              </tr>
            ))}
          </Table>
          <Link className="btn" to="/evidence">Open the document library</Link>
        </Card>
      )}

      {/* ── Administration ───────────────────────────────────── */}
      {actor.is_admin && (
        <Card variant="raised" title="People">
          <div className="grid three">
            <Stat label="With an account" value={gaps?.with_account ?? "—"} size="lg" />
            <Stat label="On payroll, no account"
                  value={gaps?.without_account ?? "—"} size="lg"
                  tone={gaps?.without_account ? "warn" : ""}
                  note={gaps?.without_account
                    ? "their effort has to be reconstructed for them"
                    : "everybody can sign in"} />
            <Stat label="You may create"
                  value={(actor.may_provision || []).length}
                  note={(actor.may_provision || []).join(", ") || "nobody"} />
          </div>
          <p className="rowsub" style={{ marginTop: 12 }}>
            An account is what turns a name on the payroll into somebody who
            keeps their own timesheet and sends in their own receipts. Until
            then their effort is reconstructed on their behalf, which is the
            weakest evidence in the file.
          </p>
          <Link className="btn primary" to="/people">Open the roster</Link>
        </Card>
      )}

      {/* ── The engagement ───────────────────────────────────── */}
      {actor.can_read && dash && (
        <Card title="Where the engagement stands"
              aside={open.length ? `${open.length} control open` : "every control ties"}>
          <div className="grid three">
            <Stat label="Ledger lines" value={dash.rollup?.ledger_lines ?? "—"} />
            <Stat label="Classified"
                  value={dash.coverage ? `${dash.coverage.pct_dollars ?? 0}%` : "—"}
                  note="of dollars" />
            <Stat label="Controls open" value={open.length}
                  tone={open.length ? "warn" : ""}
                  note={open.map((c) => c.control).join(", ") || "none"} />
          </div>
          {dash.coverage && <Meter pct={dash.coverage.pct_dollars ?? 0} target={80} />}
          {(dash.worklist || []).length > 0 && (
            <Table columns={[
              { label: "", align: "left", width: "34px" },
              { label: "What is left", align: "left" },
              { label: "Items" },
              { label: "Amount" },
            ]}>
              {dash.worklist.slice(0, 6).map((w, i) => (
                <tr key={i}>
                  <td className="l">
                    <Tick state={w.severity === "BLOCKING" ? "flagged" : "open"} />
                  </td>
                  <td className="l">{w.kind.replaceAll("_", " ").toLowerCase()}</td>
                  <td className="amt">{w.items}</td>
                  <td className="amt">{money(w.amount)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}

      {!actor.employee_key && held.length === 0 && !actor.is_admin && !actor.can_read && (
        <Empty mark="—" title="Nothing is assigned to this account yet">
          Ask an administrator for the portfolio you need, or for your account
          to be linked to your payroll record so you can keep a timesheet.
        </Empty>
      )}
    </div>
  );
}

function describe(actor) {
  const held = actor.portfolios || [];
  if (actor.role === "SYSTEM_ADMIN")
    return "You set up the organisation's administrator. Deliberately no portfolio: provisioning people and judging cost are different jobs, and the file reads better when they are different people.";
  if (actor.role === "ORG_ADMIN")
    return "You set up the finance accounts and hand out access. You hold no portfolio, which is on purpose — whoever grants authority should not also be exercising it.";
  if (actor.role === "AUDITOR")
    return "You can read everything and change nothing. That is not a limitation of this account; it is the point of it.";
  if (held.length === 0)
    return "Your timesheet, your certification, and anywhere you need to send a document.";
  if (held.length === 1 && held[0] === "CONTROLLER")
    return "Classification, the seal, and the rate that follows from it — in that order, which is the order the audit file rests on.";
  return `Your own time and documents, plus ${held.length} portfolios: ${held.join(", ")}.`;
}
