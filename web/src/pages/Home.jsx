import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money } from "../api.js";
import { Card, Empty, Meter, PageHead, Pill, Stat, Table, Tick } from "../components/ui.jsx";
import Manual from "../components/Manual.jsx";
import { forKind } from "../worklistKinds.js";

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

export default function Home({ actor, product }) {
  const [docs, setDocs] = useState(null);
  const [dash, setDash] = useState(null);
  const [lib, setLib] = useState(null);
  const [inbox, setInbox] = useState(null);
  const [gaps, setGaps] = useState(null);
  const [guides, setGuides] = useState(null);

  useEffect(() => {
    api.myDocuments().then(setDocs).catch(() => {});
    api.guides().then(setGuides).catch(() => {});
    if (actor.can_read) {
      api.dashboard("2025", product).then(setDash).catch(() => {});
      // Only the counts are wanted here; the rows stay on the library
      // screen, where there is room to read them.
      api.documentLibrary({ limit: 1 }).then(setLib).catch(() => {});
    }
    if ((actor.portfolios || []).includes("OFFICE"))
      api.documentInbox().then(setInbox).catch(() => {});
    if (actor.is_admin) api.rosterGaps().then(setGaps).catch(() => {});
  }, [actor, product]);

  const held = actor.portfolios || [];
  const open = dash?.controls?.filter((c) => !c.ties) || [];

  return (
    <div className="page">
      <PageHead title={`Good to see you, ${actor.display_name}`}>
        {describe(actor)}
      </PageHead>

      <MyWork actor={actor} product={product} />

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

      {/* ── The record, in document form ─────────────────────── */}
      {actor.can_read && (
        <Card title="The papers behind the numbers"
              aside={lib ? `${lib.total} on file` : null}>
          <p className="lede" style={{ marginTop: 0 }}>
            Every document anybody has sent in — the agreements, the leases,
            the invoices, the register — readable here rather than only
            downloadable. Open one to read it in the page, or take a copy if
            it is going into a workpaper.
          </p>
          {lib && (
            <div className="grid three">
              <Stat label="On file" value={lib.total} />
              <Stat label="Supporting a figure" value={lib.total_attached}
                    note="somebody has said what these prove" />
              <Stat label="Waiting to be filed"
                    value={lib.total - lib.total_attached}
                    tone={lib.total - lib.total_attached ? "warn" : ""}
                    note={lib.total - lib.total_attached
                      ? "nobody has said what these prove yet" : "nothing outstanding"} />
            </div>
          )}
          <Link className="btn primary" to="/library">Open the library</Link>
        </Card>
      )}

      {/* Quiet when there is nothing in it. An auditor sends no
          documents in, so for them this was three zeroes at the
          top of the page, above the work — a card that teaches
          people to scroll past the first card. */}
      <Card title="What I have sent in"
            variant={docs?.uploaded ? "" : "quiet"}>
        {docs?.uploaded ? (
          <div className="grid three">
            <Stat label="Sent in" value={docs.uploaded} size="lg" />
            <Stat label="Put to work" value={docs.in_use} size="lg"
                  note="attached to a cost by somebody who holds the portfolio" />
            <Stat label="Waiting" value={docs.waiting} size="lg"
                  note={docs.waiting ? "not yet attached to anything" : "nothing outstanding"} />
          </div>
        ) : null}
        <p className="rowsub" style={{ marginTop: 12 }}>
          Receipts, invoices, project plans, photographs of a nameplate, a
          comparable lease — anything that shows what a cost was for. You do
          not have to know where it belongs; say what it relates to and
          somebody will file it.
        </p>
        <Link className="btn primary" to="/documents">Send in a document</Link>
      </Card>

      {/* ── How to use the thing ─────────────────────────────── */}
      {/* Not gated. The everybody manual is written for somebody with a
          timesheet and no portfolio, and until this shelf existed they
          could not reach it at all: the manuals were files in the
          repository and rows in a library an employee may not read. Quiet
          when there is nothing on it, because a card that is three zeroes
          at the top of the page is one people learn to scroll past. */}
      {Boolean(guides?.total) && (
        <Card title="Your guidebook" variant="quiet"
              aside={`${guides.yours} for your job · ${guides.total} on the shelf`}>
          <p className="lede" style={{ marginTop: 0 }}>
            The manuals and the printed walk-throughs, readable in the page.
            Yours first; everybody else's is there too, because knowing what
            the auditor is working from is worth as much as your own chapter.
          </p>
          <ul className="plain-list">
            {guides.guides.filter((g) => g.yours).slice(0, 4).map((g) => (
              <li key={g.evidence_id}>
                <Link to="/guidebook"><strong>{g.title}</strong></Link>
                <span className="rowsub"> — {g.note}</span>
              </li>
            ))}
          </ul>
          <Link className="btn" to="/guidebook">Open the guidebook</Link>
        </Card>
      )}

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
          {/* This goes to Evidence, which is where a document is filed
              against a cost — not to the Library, which is where one is
              read. They were both called "the document library". */}
          <Link className="btn" to="/evidence">Open the filing queue</Link>
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
                  {/* `forKind` is the one place a kind's meaning is written
                      down, and it was imported at the top of this file and
                      used by the list below while this one lowercased the
                      raw database name. A fourth copy of the defect
                      worklistKinds.js exists to end: a screen that starts
                      speaking SQL. */}
                  <td className="l">{forKind(w.kind).plural}</td>
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


/* What this person owes, rather than what is outstanding in general.
 *
 * The worklist has always known what is undone and never whose job it is, so
 * every screen showed everybody the same list. That is a dashboard, not a
 * morning. Heidi should open the application and see that the buildings have
 * no square footage against them; Stephanie should see which of the people on
 * her projects have not signed for their own effort.
 *
 * A CONTROLLER holds every portfolio, so they see everything. That is what
 * the portfolio means rather than a special case — and it is why the card
 * says whose work each row is, even to somebody who holds all of them. */

const SEV = { BLOCKING: "fail", HIGH: "warn", MEDIUM: "" };

function MyWork({ actor, product }) {
  const [d, setD] = useState(null);
  /* `require_own_work` admits somebody who holds a portfolio *or* reads the
     record, and nobody else — so for an employee with a timesheet and
     nothing else this call is a 403 every time the page loads, which rings
     the failure bell about a card they were never going to see. It never
     showed while every account in the record held a portfolio or a rank;
     self-registration makes that class of person real, and a bell that
     rings on every page load for a whole class of user is the "green all
     day" defect inverted — they learn to ignore it before the day it
     matters. Never offer something that will answer 403. */
  const mine = Boolean((actor.portfolios || []).length) || actor.can_read;
  useEffect(() => {
    if (mine) api.myWorklist("2025", product).then(setD).catch(() => {});
  }, [mine, product]);
  if (!mine) return null;
  /* The chase list is the certification question in another shape — who has
     not signed, on whose work — and a controller cannot sign any of it.
     It moved behind the ongoing-system door with NEEDS_CERTIFICATION and
     EMPLOYMENT_UNKNOWN; leaving it on the audit home would have been the
     same defect one component further down. */
  const chase = product === "audit" ? [] : (d?.certification_chase || []);

  if (!d || (!d.groups.length && !chase.length)) return null;

  const everything = (actor.portfolios || []).includes("CONTROLLER");

  return (
    <Card variant="raised" title="What is waiting on you"
          aside={everything
            ? "You hold CONTROLLER, so this is everything — each row says whose work it is"
            : `Routed to ${d.portfolios.join(", ")}`}>
      <Table columns={[
        { label: "", align: "left", width: "28px" },
        { label: "What", align: "left" },
        { label: "Items" }, { label: "Amount" },
        { label: "Whose", align: "left" },
        { label: "", align: "left", width: "110px" },
      ]}>
        {d.groups.map((g) => {
          const { plural: label, short: note } = forKind(g.kind);
          return (
            <tr key={g.kind}>
              <td className="l">
                <Tick state={g.severity === "BLOCKING" ? "failed"
                             : g.severity === "HIGH" ? "flagged" : "open"} />
              </td>
              <td className="l">
                <strong>{label}</strong>
                <div className="rowsub">{note}</div>
              </td>
              <td className="amt">{g.items}</td>
              <td className="amt">
                {Number(g.amount || 0) ? money(g.amount)
                                       : <span className="rowsub">—</span>}
              </td>
              <td className="l"><Pill>{g.owner_portfolio}</Pill></td>
              <td className="l">
                <Link className="btn sm" to={g.goes_to}>Open</Link>
              </td>
            </tr>
          );
        })}
      </Table>

      {chase.length > 0 && (
        <>
          <div className="card-title" style={{ margin: "18px 0 4px" }}>
            People to chase
          </div>
          <div className="rowsub" style={{ marginBottom: 10 }}>
            You cannot sign these — 2 CFR 200.430(i) wants the signature of
            the person whose effort it was. What you can do is go and ask,
            and this is who, on which work.
          </div>
          <Table columns={[
            { label: "Work", align: "left" }, { label: "Contract", align: "left" },
            { label: "People" }, { label: "Wages" }, { label: "Stale" },
          ]}>
            {chase.map((c) => (
              <tr key={c.objective_id}>
                <td className="l">
                  <strong>{c.objective_id}</strong>
                  <div className="rowsub">{c.objective_label}</div>
                </td>
                <td className="l rowsub">{c.award_id || "—"}</td>
                <td className="amt">{c.people}</td>
                <td className="amt">{money(c.wages)}</td>
                <td className="amt">
                  {c.stale ? <span className="warnish">{c.stale}</span>
                           : <span className="rowsub">—</span>}
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </Card>
  );
}
