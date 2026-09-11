import React, { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, money } from "../api.js";
import {
  Card, Drawer, Empty, PageHead, Pill, Segmented, Stat, Table, Tick, useToast,
} from "../components/ui.jsx";

/* Schedule F — the income side.
 *
 * Everything else in this system reads a year that has already been spent.
 * This is the half that has to exist before the year is worked: a charge code
 * opened, somebody assigned to it, a deliverable with a value, an invoice
 * against the deliverable, and the money that arrives against the invoice.
 *
 * Three panes because they are three jobs. The project manager lives in
 * Charge codes; the controller lives in Contracts; the auditor lives in
 * People, which is the only path in the system that runs from a person to the
 * cost underneath the work they billed. */

const PANES = [
  ["contracts", "Contracts"],
  ["codes", "Charge codes"],
  ["people", "People"],
];

const STATE_TONE = {
  PLANNED: "", IN_PROGRESS: "", DELIVERED: "accent",
  ACCEPTED: "good", INVOICED: "accent", PAID: "good", CANCELLED: "warn",
};

const when = (d) => (d ? String(d).slice(0, 10) : "—");

export default function Contracts({ actor }) {
  const { pane } = useParams();
  const nav = useNavigate();
  const current = PANES.some(([v]) => v === pane) ? pane : "contracts";
  const canWrite = (actor?.portfolios || []).some(
    (p) => p === "PROJECT" || p === "CONTROLLER");

  return (
    <div className="page">
      <PageHead title="Contracts" schedule="F"
                aside={<Segmented options={PANES} value={current}
                                  onChange={(v) => nav(`/contracts/${v}`)} />}>
        What each contract earns, what it is spending, who may charge it, and
        the money that has actually arrived. A charge code is a cost objective
        — the same one the ledger is classified into — so an hour and a dollar
        spent on the same work land in the same place.
      </PageHead>

      {current === "contracts" && <ContractList canWrite={canWrite} />}
      {current === "codes" && <ChargeCodes canWrite={canWrite} />}
      {current === "people" && <People />}
    </div>
  );
}


/* ── contracts ─────────────────────────────────────────────────────── */

function ContractList({ canWrite }) {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => { api.contracts().then((d) => setRows(d.contracts)); }, []);
  if (!rows) return null;

  return (
    <>
      <Card title="Portfolio" aside="Earned against spent, per contract">
        {rows.length === 0 ? (
          <Empty mark="F" title="No contracts on file">
            An award is loaded with the objective it belongs to. Until one
            exists there is nothing to invoice against.
          </Empty>
        ) : (
          <Table columns={[
            { label: "Contract", align: "left" },
            { label: "Sponsor", align: "left" },
            { label: "Ceiling" }, { label: "Invoiced" }, { label: "Received" },
            { label: "Cost so far" },
            { label: "Milestones", align: "left" },
            { label: "Term ends", align: "left" },
          ]}>
            {rows.map((c) => {
              const outstanding = Number(c.invoiced || 0) - Number(c.received || 0);
              return (
                <tr key={c.award_id} className="hoverable"
                    onClick={() => setOpen(c.award_id)}>
                  <td className="l">
                    <strong>{c.award_id}</strong>
                    <div className="rowsub">{c.objective_label}</div>
                  </td>
                  <td className="l rowsub wrap">{c.sponsor}</td>
                  <td className="amt strong">
                    {Number(c.ceiling_federal || 0) === 0
                      ? <span className="rowsub">not on file</span>
                      : money(c.ceiling_federal)}
                  </td>
                  <td className="amt">{money(c.invoiced)}</td>
                  <td className="amt">
                    {money(c.received)}
                    {outstanding > 0 && (
                      <div className="rowsub warnish">
                        {money(outstanding)} out
                      </div>
                    )}
                  </td>
                  <td className="amt">{money(c.cost_classified)}</td>
                  <td className="l rowsub">
                    {c.milestones
                      ? `${c.milestones_done}/${c.milestones}`
                      : "none yet"}
                  </td>
                  <td className="l rowsub">{when(c.period_end)}</td>
                </tr>
              );
            })}
          </Table>
        )}
        <div className="rowsub" style={{ marginTop: 12 }}>
          <strong>Cost so far</strong> is what has been <em>classified</em> to
          the contract's objective, not what it cost. Classification is
          unfinished, so this understates — which is why no margin is shown
          here. A margin over an incomplete cost side flatters in exactly the
          direction nobody should be flattered.
        </div>
      </Card>

      {open && <ContractDrawer awardId={open} canWrite={canWrite}
                               onClose={() => setOpen(null)} />}
    </>
  );
}


function ContractDrawer({ awardId, canWrite, onClose }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [milestone, setMilestone] = useState(null);

  const load = useCallback(() => {
    api.contract(awardId).then(setD).catch(() => {});
  }, [awardId]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <Drawer open title={awardId} onClose={onClose}>Loading…</Drawer>;
  const c = d.contract;
  const outstanding = Number(c.invoiced || 0) - Number(c.received || 0);

  return (
    <Drawer open title={c.award_id} subtitle={c.sponsor} onClose={onClose} wide>
      <Card variant="raised">
        <div className="stat-row">
          <Stat label="Ceiling" size="md"
                value={Number(c.ceiling_federal || 0) === 0
                  ? "not on file" : money(c.ceiling_federal)} />
          <Stat label="Invoiced" size="md" value={money(c.invoiced)} />
          <Stat label="Received" size="md" value={money(c.received)} />
          <Stat label={outstanding < 0 ? "Over-collected" : "Outstanding"}
                size="md" value={money(Math.abs(outstanding))}
                tone={outstanding > 0 ? "warn" : outstanding < 0 ? "fail" : "pass"} />
        </div>
        <div className="rowsub" style={{ marginTop: 10 }}>
          {c.instrument} · {when(c.period_start)} to {when(c.period_end)}
          {c.cfda && <> · CFDA {c.cfda}</>}
          {Number(c.cost_share_required || 0) > 0 && (
            <> · cost share {money(c.cost_share_required)}</>
          )}
        </div>
      </Card>

      <Card title="Terms and conditions"
            aside="Each with the clause it came from, and the document asked"
            style={{ marginTop: 14 }}>
        {d.terms.length === 0 ? (
          <div className="rowsub">
            No provisions recorded. A ceiling is not a contract — what may be
            charged, how it is invoiced and when it is paid all live in
            clauses, and a reviewer asks for the clause.
          </div>
        ) : (
          <>
            <CitationSummary c={d.citations} />
            <Table columns={[
              { label: "Provision", align: "left" },
              { label: "What it says", align: "left" },
              { label: "Clause", align: "left" },
              { label: "In the document", align: "left" },
            ]}>
              {d.terms.map((t) => (
                <tr key={t.term_key}>
                  <td className="l"><strong>{t.term_key}</strong></td>
                  <td className="l wrap">
                    {t.term_value}
                    {t.note && (
                      <div className="rowsub warnish wrap"
                           style={{ marginTop: 4 }}>{t.note}</div>
                    )}
                  </td>
                  <td className="l rowsub wrap">
                    {t.citation || <span className="warnish">no clause cited</span>}
                  </td>
                  <td className="l"><CitationState t={t} /></td>
                </tr>
              ))}
            </Table>
          </>
        )}
        {canWrite && <TermForm awardId={awardId} onDone={() => { load(); toast("Term recorded"); }} />}
      </Card>

      <Card title="Milestones"
            aside="A deliverable, what it is worth, and what it has earned"
            style={{ marginTop: 14 }}>
        {d.milestones.length === 0 ? (
          <div className="rowsub">
            No milestones, and under this contract none is expected. It is
            cost reimbursement invoiced monthly against a budget by category,
            not against deliverables — the statement of work carries tasks
            and no CLIN, no deliverable value and no acceptance date. An
            invoice here claims a month of cost, and what a payment was for
            is answered by its service period and the categories it claimed.
          </div>
        ) : (
          <Table columns={[
            { label: "Milestone", align: "left" }, { label: "CLIN", align: "left" },
            { label: "Value" }, { label: "Due", align: "left" },
            { label: "State", align: "left" },
            { label: "Invoiced" }, { label: "Received" },
          ]}>
            {d.milestones.map((m) => (
              <tr key={m.milestone_id} className="hoverable"
                  onClick={() => setMilestone(m.milestone_id)}>
                <td className="l">
                  <strong>{m.name}</strong>
                  <div className="rowsub">{m.milestone_id}</div>
                </td>
                <td className="l rowsub">{m.clin || "—"}</td>
                <td className="amt">{money(m.value)}</td>
                <td className="l rowsub">{when(m.due_on)}</td>
                <td className="l">
                  <Pill tone={STATE_TONE[m.state] || ""}>
                    {m.state.replace("_", " ").toLowerCase()}
                  </Pill>
                </td>
                <td className="amt">{money(m.invoiced)}</td>
                <td className="amt">{money(m.received)}</td>
              </tr>
            ))}
          </Table>
        )}
        {canWrite && <MilestoneForm awardId={awardId}
                                    onDone={() => { load(); toast("Milestone opened"); }} />}
      </Card>

      <Card title="Invoices" aside="What was claimed, and what has been settled"
            style={{ marginTop: 14 }}>
        {d.invoices.length === 0 ? (
          <div className="rowsub">Nothing invoiced on this contract.</div>
        ) : (
          <Table columns={[
            { label: "Invoice", align: "left" }, { label: "Date", align: "left" },
            { label: "Direct" }, { label: "Indirect" }, { label: "Received" },
            { label: "Milestone", align: "left" },
          ]}>
            {d.invoices.map((i) => (
              <tr key={i.invoice_id}>
                <td className="l">{i.invoice_number || `#${i.seq}`}</td>
                <td className="l rowsub">{when(i.invoice_date)}</td>
                <td className="amt">{money(i.direct_claimed)}</td>
                <td className="amt">
                  {Number(i.indirect_claimed || 0) === 0
                    ? <span className="warnish">none</span>
                    : money(i.indirect_claimed)}
                </td>
                <td className="amt">{money(i.received)}</td>
                <td className="l rowsub">
                  {/* Not "unattached" — that read as missing data for as long
                      as it was there, and the only thing that ever filled
                      this column was a drive script inventing a deliverable
                      and attaching invoice 10018 to it. */}
                  {i.milestone_id || <span className="rowsub">n/a</span>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {milestone && <MilestoneDrawer id={milestone}
                                     onClose={() => { setMilestone(null); load(); }}
                                     canWrite={canWrite} />}
    </Drawer>
  );
}


/* Whether the document a provision was read out of actually contains the
   clause it cites. Only FOUND is a pass: an unreadable agreement is
   unevaluable rather than clean, the way NO CLAUSE READ is on the ceiling
   check, and a prose citation a pattern cannot check is untestable rather
   than wrong — reporting that as a failure teaches the reader the list is
   wrong, and the next real one they see they will dismiss. */
const CITATION = {
  FOUND: { tick: "done", says: "in the document",
           why: "The agreement on file contains what this cites." },
  "NOT IN DOCUMENT": { tick: "failed", says: "not in the document",
           why: "The agreement on file is readable end to end and does not " +
                "contain this clause. Either the citation points at another " +
                "document or it is a copy from one." },
  "NO TEXT LAYER": { tick: "flagged", says: "cannot be checked",
           why: "The agreement on file has pages and no text in them — a " +
                "scan. Nobody working from the file has read a clause of it." },
  "NOT READ": { tick: "flagged", says: "not read",
           why: "The document is on file and nothing has read its text yet." },
  "NO DOCUMENT": { tick: "flagged", says: "no document",
           why: "This provision names no document it was read out of." },
  UNTESTABLE: { tick: "open", says: "prose citation",
           why: "The citation names no section or attachment to look for. " +
                "Not a defect — good for a person, poor for a pattern." },
};

function CitationState({ t }) {
  const c = CITATION[t.citation_state];
  if (!c) return <span className="rowsub">—</span>;
  return (
    <span title={c.why + (t.citation_looked_for
                          ? ` Looked for: ${t.citation_looked_for}.` : "")}>
      <Tick state={c.tick} /> <span className="rowsub">{c.says}</span>
    </span>
  );
}

function CitationSummary({ c }) {
  if (!c) return null;
  if (c.agreement_is_an_image) {
    return (
      <div className="rowsub warnish" style={{ marginBottom: 10 }}>
        The agreement on file — <strong>{c.agreement}</strong> — is{" "}
        {c.page_count} pages of image with no text in it, so none of its{" "}
        {c.terms} provisions can be checked against it by anybody working
        from the file. Unevaluable is not a pass.
      </div>
    );
  }
  if (c.not_in_document > 0) {
    return (
      <div className="rowsub failish" style={{ marginBottom: 10 }}>
        <strong>{c.not_in_document} of {c.terms}</strong> cite a clause{" "}
        {c.agreement} does not contain. Recorded as they stand with a note
        rather than removed — the substance may be right and sourced
        elsewhere, which is a different answer from the citation being a copy.
      </div>
    );
  }
  if (!c.agreement) {
    return (
      <div className="rowsub warnish" style={{ marginBottom: 10 }}>
        No executed agreement is on file for this award, so no citation on it
        can be checked against anything.
      </div>
    );
  }
  return (
    <div className="rowsub" style={{ marginBottom: 10 }}>
      {c.found} of {c.terms} check out against {c.agreement}
      {c.untestable > 0 && <> · {c.untestable} cite prose a pattern cannot check</>}.
    </div>
  );
}

function TermForm({ awardId, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ term_key: "", term_value: "", citation: "" });
  const save = async () => {
    try {
      await api.putAwardTerm(awardId, f);
      setF({ term_key: "", term_value: "", citation: "" });
      onDone();
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };
  return (
    <div className="grid form" style={{ marginTop: 12 }}>
      <input placeholder="Provision — e.g. Payment terms" value={f.term_key}
             onChange={(e) => setF({ ...f, term_key: e.target.value })} />
      <input placeholder="What it says" value={f.term_value}
             onChange={(e) => setF({ ...f, term_value: e.target.value })} />
      <input placeholder="Clause — e.g. §26 Payment" value={f.citation}
             onChange={(e) => setF({ ...f, citation: e.target.value })} />
      <button className="primary" disabled={!f.term_key || !f.term_value}
              onClick={save}>Record the provision</button>
    </div>
  );
}


function MilestoneForm({ awardId, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ milestone_id: "", name: "", clin: "",
                               value: "", due_on: "" });
  const save = async () => {
    try {
      await api.createMilestone(awardId, {
        ...f, value: Number(f.value || 0), due_on: f.due_on || null });
      setF({ milestone_id: "", name: "", clin: "", value: "", due_on: "" });
      onDone();
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };
  return (
    <div className="grid form" style={{ marginTop: 12 }}>
      <input placeholder="Milestone ID" value={f.milestone_id}
             onChange={(e) => setF({ ...f, milestone_id: e.target.value })} />
      <input placeholder="Name" value={f.name}
             onChange={(e) => setF({ ...f, name: e.target.value })} />
      <input placeholder="CLIN" value={f.clin}
             onChange={(e) => setF({ ...f, clin: e.target.value })} />
      <input placeholder="Value" inputMode="decimal" value={f.value}
             onChange={(e) => setF({ ...f, value: e.target.value })} />
      <input type="date" value={f.due_on}
             onChange={(e) => setF({ ...f, due_on: e.target.value })} />
      <button className="primary" disabled={!f.milestone_id || !f.name}
              onClick={save}>Open the milestone</button>
    </div>
  );
}


/* The last step of the auditor's path: a deliverable, the invoice that
   claimed it, the money that settled it, and the cost underneath. */
function MilestoneDrawer({ id, onClose, canWrite }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const load = useCallback(() => { api.milestone(id).then(setD).catch(() => {}); }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <Drawer open title={id} onClose={onClose}>Loading…</Drawer>;
  const m = d.milestone;
  const cost = d.cost_by_pool.reduce((a, r) => a + Number(r.amount || 0), 0);
  const labor = d.labor.reduce((a, r) => a + Number(r.wages || 0), 0);
  const out = Number(m.outstanding || 0);

  return (
    <Drawer open title={m.name} subtitle={`${m.award_id} · ${m.milestone_id}`}
            onClose={onClose} wide>
      <Card variant="raised">
        <div className="stat-row">
          <Stat label="Worth" size="md" value={money(m.value)} />
          <Stat label="Invoiced" size="md" value={money(m.invoiced)} />
          <Stat label="Received" size="md" value={money(m.received)} />
          <Stat label={out < 0 ? "Over-collected" : "Outstanding"} size="md"
                value={money(Math.abs(out))}
                tone={out > 0 ? "warn" : out < 0 ? "fail" : "pass"} />
        </div>
        <div className="rowsub" style={{ marginTop: 10 }}>
          {m.state.replace("_", " ").toLowerCase()} · due {when(m.due_on)}
          {m.delivered_on && <> · delivered {when(m.delivered_on)}</>}
          {m.accepted_on && <> · accepted {when(m.accepted_on)}</>}
        </div>
        {out < 0 && (
          <div className="gate bad" style={{ marginTop: 12 }}>
            <Tick state="failed" /> More has been received than was invoiced.
            That is an advance, a duplicate payment or a misposted receipt —
            all three are worth finding before a sponsor does.
          </div>
        )}
      </Card>

      <Card title="Invoices against it" style={{ marginTop: 14 }}>
        {d.invoices.length === 0 ? (
          <div className="rowsub">Nothing claimed against this deliverable.</div>
        ) : (
          <Table columns={[
            { label: "Invoice", align: "left" }, { label: "Date", align: "left" },
            { label: "Direct" }, { label: "Indirect" }, { label: "Cost share" },
            { label: "", align: "left", width: "120px" },
          ]}>
            {d.invoices.map((i) => (
              <tr key={i.invoice_id}>
                <td className="l">{i.invoice_number || "—"}</td>
                <td className="l rowsub">{when(i.invoice_date)}</td>
                <td className="amt">{money(i.direct_claimed)}</td>
                <td className="amt">
                  {Number(i.indirect_claimed || 0) === 0
                    ? <span className="warnish">none</span>
                    : money(i.indirect_claimed)}
                </td>
                <td className="amt">{money(i.cost_share)}</td>
                <td className="l">
                  {canWrite && <ReceiptForm invoiceId={i.invoice_id}
                                            onDone={() => { load(); toast("Receipt recorded"); }} />}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Money in" style={{ marginTop: 14 }}>
        {d.receipts.length === 0 ? (
          <div className="rowsub">
            Nothing received. Invoiced and not collected is the number a
            controller chases.
          </div>
        ) : (
          <Table columns={[
            { label: "Received", align: "left" }, { label: "Amount" },
            { label: "Method", align: "left" }, { label: "Reference", align: "left" },
            { label: "Recorded by", align: "left" },
          ]}>
            {d.receipts.map((r) => (
              <tr key={r.receipt_id}>
                <td className="l">{when(r.received_on)}</td>
                <td className="amt">{money(r.amount)}</td>
                <td className="l rowsub">{r.method || "—"}</td>
                <td className="l rowsub">{r.reference || "—"}</td>
                <td className="l rowsub">{r.recorded_by}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="What it cost"
            aside="Classified cost on the objective, and distributed labour"
            style={{ marginTop: 14 }}>
        <div className="stat-row" style={{ marginBottom: 12 }}>
          <Stat label="Classified to the objective" size="md" value={money(cost)} />
          <Stat label="Labour distributed" size="md" value={money(labor)} />
        </div>
        {d.cost_by_pool.length === 0 ? (
          <div className="rowsub">
            Nothing has been classified to this objective yet, so the cost side
            reads zero. That is the queue being unfinished, not the work being
            free — no margin is shown here for exactly that reason.
          </div>
        ) : (
          <Table columns={[{ label: "Pool", align: "left" },
                           { label: "Amount" }, { label: "Lines" }]}>
            {d.cost_by_pool.map((r) => (
              <tr key={r.pool}>
                <td className="l">{r.pool}</td>
                <td className="amt">{money(r.amount)}</td>
                <td className="amt rowsub">{r.lines}</td>
              </tr>
            ))}
          </Table>
        )}
        {d.labor.length > 0 && (
          <Table columns={[{ label: "Who", align: "left" }, { label: "Wages" },
                           { label: "Evidence", align: "left" }]}>
            {d.labor.map((l) => (
              <tr key={l.employee_key}>
                <td className="l">{l.employee_name || l.employee_key}</td>
                <td className="amt">{money(l.wages)}</td>
                <td className="l"><Pill>{l.grade}</Pill></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Drawer>
  );
}


function ReceiptForm({ invoiceId, onDone }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ received_on: "", amount: "", method: "",
                               reference: "" });
  if (!open) {
    return <button className="sm" onClick={() => setOpen(true)}>Money in</button>;
  }
  const save = async () => {
    try {
      await api.addReceipt(invoiceId, { ...f, amount: Number(f.amount || 0) });
      setOpen(false); onDone();
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };
  return (
    <div className="grid form">
      <input type="date" value={f.received_on}
             onChange={(e) => setF({ ...f, received_on: e.target.value })} />
      <input placeholder="Amount" inputMode="decimal" value={f.amount}
             onChange={(e) => setF({ ...f, amount: e.target.value })} />
      <input placeholder="Method" value={f.method}
             onChange={(e) => setF({ ...f, method: e.target.value })} />
      <input placeholder="Reference" value={f.reference}
             onChange={(e) => setF({ ...f, reference: e.target.value })} />
      <button className="primary" disabled={!f.received_on || !f.amount}
              onClick={save}>Record</button>
      <button className="sm" onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}


/* ── charge codes ──────────────────────────────────────────────────── */

function ChargeCodes({ canWrite }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => { api.chargeCodes().then(setD).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;

  const loose = d.charged_without_authority || [];

  return (
    <>
      {loose.length > 0 && (
        <div className="gate bad" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>
            <Tick state="flagged" /> {loose.length} code(s) carry hours with
            nobody assigned to them
          </div>
          <div className="rowsub">
            Charging is gated only on codes that have somebody assigned — a
            code with an empty list predates the mechanism, and refusing those
            would make reconstructing 2025 impossible. Assign somebody and the
            gate turns on for that code.
          </div>
        </div>
      )}

      <Card title="Charge codes"
            aside={canWrite
              ? <button className="sm" onClick={() => setAdding(true)}>Open a code</button>
              : "Read only — the project manager or the controller opens these"}>
        <Table columns={[
          { label: "Code", align: "left" }, { label: "Contract", align: "left" },
          { label: "Assigned" }, { label: "Charging" }, { label: "Hours" },
          { label: "Wages distributed" }, { label: "Cost classified" },
        ]}>
          {d.charge_codes.map((c) => (
            <tr key={c.objective_id} className="hoverable"
                onClick={() => setOpen(c.objective_id)}>
              <td className="l">
                <strong>{c.objective_id}</strong>
                {c.is_federal && <> <Pill tone="accent">federal</Pill></>}
                <div className="rowsub">{c.label}</div>
              </td>
              <td className="l rowsub">{c.award_id || "—"}</td>
              <td className="amt">
                {c.people_authorised
                  ? c.people_authorised
                  : <span className="warnish">none</span>}
              </td>
              <td className="amt rowsub">{c.people_charging || "—"}</td>
              <td className="amt">{Number(c.hours_charged || 0).toFixed(0)}</td>
              <td className="amt">{money(c.wages_distributed)}</td>
              <td className="amt">{money(c.cost_classified)}</td>
            </tr>
          ))}
        </Table>
      </Card>

      {adding && <NewCode onClose={() => setAdding(false)}
                          onDone={() => { setAdding(false); load(); toast("Charge code opened"); }} />}
      {open && <CodeDrawer objectiveId={open} canWrite={canWrite}
                           onClose={() => { setOpen(null); load(); }} />}
    </>
  );
}


function NewCode({ onClose, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ objective_id: "", label: "",
                               objective_type: "PROGRAM", is_federal: false,
                               cfda: "", reason: "" });
  const save = async () => {
    try {
      await api.createChargeCode({ ...f, cfda: f.cfda || null });
      onDone();
    } catch (e) { toast(String(e.message || e), { tone: "bad", sticky: true }); }
  };
  return (
    <Drawer open title="Open a charge code" onClose={onClose}>
      <div className="grid form">
        <input placeholder="Code — e.g. DIG-ENG" value={f.objective_id}
               onChange={(e) => setF({ ...f, objective_id: e.target.value.toUpperCase() })} />
        <input placeholder="What it is" value={f.label}
               onChange={(e) => setF({ ...f, label: e.target.value })} />
        <label className="checkline">
          <input type="checkbox" checked={f.is_federal}
                 onChange={(e) => setF({ ...f, is_federal: e.target.checked })} />
          Federal award
        </label>
        {f.is_federal && (
          <input placeholder="CFDA number" value={f.cfda}
                 onChange={(e) => setF({ ...f, cfda: e.target.value })} />
        )}
      </div>
      <textarea rows={3} placeholder="Why this code exists — it goes on the record"
                value={f.reason} style={{ width: "100%", marginTop: 10 }}
                onChange={(e) => setF({ ...f, reason: e.target.value })} />
      <div className="rowsub" style={{ margin: "8px 0 12px" }}>
        A federal code needs its CFDA number. Without it the award cannot reach
        the SEFA, and the Single Audit scope is decided by what is on the SEFA.
      </div>
      <button className="primary" onClick={save}
              disabled={!f.objective_id || !f.label || f.reason.length < 10}>
        Open the code
      </button>
    </Drawer>
  );
}


function CodeDrawer({ objectiveId, canWrite, onClose }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [f, setF] = useState({ employee_key: "", role_on_project: "", reason: "" });
  const load = useCallback(() => {
    api.chargeCodePeople(objectiveId).then(setD).catch(() => {});
  }, [objectiveId]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <Drawer open title={objectiveId} onClose={onClose}>Loading…</Drawer>;

  const assign = async () => {
    try {
      await api.authoriseCharge(objectiveId, f);
      setF({ employee_key: "", role_on_project: "", reason: "" });
      load(); toast(`${f.employee_key} may charge ${objectiveId}`);
    } catch (e) { toast(String(e.message || e), { tone: "bad", sticky: true }); }
  };
  const revoke = async (key) => {
    const reason = window.prompt(`Why is ${key} coming off ${objectiveId}?`);
    if (!reason || reason.length < 10) {
      toast("A revocation needs a reason of its own.", { tone: "bad" }); return;
    }
    try {
      await api.revokeCharge(objectiveId, { employee_key: key, reason });
      load(); toast(`${key} removed`);
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };

  return (
    <Drawer open title={objectiveId} subtitle="Who may charge it" onClose={onClose} wide>
      <Card title="Assigned">
        {d.authorised.length === 0 ? (
          <div className="rowsub">
            Nobody is assigned, so this code is not gated — anybody with a
            timesheet can book to it. Assign one person and the gate turns on.
          </div>
        ) : (
          <Table columns={[
            { label: "Who", align: "left" }, { label: "Role", align: "left" },
            { label: "From", align: "left" }, { label: "Until", align: "left" },
            { label: "Assigned by", align: "left" },
            { label: "", align: "left", width: "90px" },
          ]}>
            {d.authorised.map((a) => (
              <tr key={a.employee_key}>
                <td className="l"><strong>{a.employee_key}</strong></td>
                <td className="l rowsub">{a.role_on_project || "—"}</td>
                <td className="l rowsub">{when(a.opens_on)}</td>
                <td className="l rowsub">{when(a.closes_on)}</td>
                <td className="l rowsub wrap">{a.granted_by}</td>
                <td className="l">
                  {canWrite && (
                    <button className="sm" onClick={() => revoke(a.employee_key)}>
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
        {canWrite && (
          <div className="grid form" style={{ marginTop: 12 }}>
            <input placeholder="Employee key" value={f.employee_key}
                   onChange={(e) => setF({ ...f, employee_key: e.target.value.toUpperCase() })} />
            <input placeholder="Role on the project" value={f.role_on_project}
                   onChange={(e) => setF({ ...f, role_on_project: e.target.value })} />
            <input placeholder="Why — it goes on the record" value={f.reason}
                   onChange={(e) => setF({ ...f, reason: e.target.value })} />
            <button className="primary"
                    disabled={!f.employee_key || f.reason.length < 10}
                    onClick={assign}>Assign</button>
          </div>
        )}
      </Card>

      <Card title="Who has charged it" style={{ marginTop: 14 }}>
        {d.charged.length === 0 ? (
          <div className="rowsub">No hours booked to this code.</div>
        ) : (
          <Table columns={[
            { label: "Who", align: "left" }, { label: "Hours" },
            { label: "Entries" }, { label: "First", align: "left" },
            { label: "Last", align: "left" }, { label: "Assigned?", align: "left" },
          ]}>
            {d.charged.map((c) => (
              <tr key={c.employee_key}>
                <td className="l">{c.employee_key}</td>
                <td className="amt">{Number(c.hours).toFixed(2)}</td>
                <td className="amt rowsub">{c.entries}</td>
                <td className="l rowsub">{when(c.first_charged)}</td>
                <td className="l rowsub">{when(c.last_charged)}</td>
                <td className="l">
                  {c.authorised
                    ? <Pill tone="good">yes</Pill>
                    : <Pill tone="warn">nobody asked</Pill>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Drawer>
  );
}


/* ── people — the auditor's path ───────────────────────────────────── */

function People() {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  useEffect(() => { api.chargingPeople().then((d) => setRows(d.employees)); }, []);
  if (!rows) return null;

  return (
    <>
      <Card title="Everybody on the payroll register"
            aside="Pick one to see everything they billed against">
        <Table columns={[
          { label: "Who", align: "left" }, { label: "Wages distributed" },
          { label: "Codes" }, { label: "Hours booked" },
          { label: "Codes assigned" },
        ]}>
          {rows.map((r) => (
            <tr key={r.employee_key} className="hoverable"
                onClick={() => setOpen(r.employee_key)}>
              <td className="l">
                <strong>{r.employee_name || r.employee_key}</strong>
                <div className="rowsub">{r.employee_key}</div>
              </td>
              <td className="amt">{money(r.wages)}</td>
              <td className="amt rowsub">{r.objectives}</td>
              <td className="amt">{Number(r.hours || 0).toFixed(0)}</td>
              <td className="amt">
                {r.authorised_codes
                  ? r.authorised_codes
                  : <span className="warnish">none</span>}
              </td>
            </tr>
          ))}
        </Table>
      </Card>
      {open && <PersonDrawer employeeKey={open} onClose={() => setOpen(null)} />}
    </>
  );
}


function PersonDrawer({ employeeKey, onClose }) {
  const [d, setD] = useState(null);
  const [milestone, setMilestone] = useState(null);
  useEffect(() => { api.employeeCharging(employeeKey).then(setD).catch(() => {}); },
            [employeeKey]);
  if (!d) return <Drawer open title={employeeKey} onClose={onClose}>Loading…</Drawer>;

  return (
    <Drawer open title={d.employee_name} subtitle={employeeKey}
            onClose={onClose} wide>
      {d.unauthorised.length > 0 && (
        <div className="gate bad" style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            <Tick state="flagged" /> Booked time to {d.unauthorised.length} code(s)
            nobody assigned them to
          </div>
          <div className="rowsub">
            {d.unauthorised.join(", ")}. For 2025 that is expected — the
            assignment mechanism did not exist while the year was worked. From
            2026 it is a question with an answer.
          </div>
        </div>
      )}

      <Card title="Charged" aside="Hours booked, and whether anybody said they could">
        {d.charged.length === 0 ? (
          <div className="rowsub">
            No timesheet hours. What this person has is a distribution — the
            controller's reconstruction of the year — shown below.
          </div>
        ) : (
          <Table columns={[
            { label: "Code", align: "left" }, { label: "Contract", align: "left" },
            { label: "Hours" }, { label: "First", align: "left" },
            { label: "Last", align: "left" }, { label: "Assigned?", align: "left" },
          ]}>
            {d.charged.map((c) => (
              <tr key={c.objective_id}>
                <td className="l">
                  <strong>{c.objective_id}</strong>
                  <div className="rowsub">{c.objective_label}</div>
                </td>
                <td className="l rowsub">{c.award_id || "—"}</td>
                <td className="amt">{Number(c.hours).toFixed(2)}</td>
                <td className="l rowsub">{when(c.first_charged)}</td>
                <td className="l rowsub">{when(c.last_charged)}</td>
                <td className="l">
                  {c.authorised
                    ? <Pill tone="good">yes</Pill>
                    : <Pill tone="warn">nobody asked</Pill>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Wages distributed" aside="The controller's reconstruction for 2025"
            style={{ marginTop: 14 }}>
        {d.distributed.length === 0 ? (
          <div className="rowsub">Nothing distributed to this person.</div>
        ) : (
          <Table columns={[{ label: "Code", align: "left" }, { label: "Wages" },
                           { label: "Evidence", align: "left" }]}>
            {d.distributed.map((x) => (
              <tr key={x.objective_id}>
                <td className="l">{x.objective_id}</td>
                <td className="amt">{money(x.wages)}</td>
                <td className="l"><Pill>{x.grade}</Pill></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Assignments on the record" style={{ marginTop: 14 }}>
        {d.authorised.length === 0 ? (
          <div className="rowsub">
            Nobody has assigned this person to any charge code.
          </div>
        ) : (
          <Table columns={[
            { label: "Code", align: "left" }, { label: "Role", align: "left" },
            { label: "Contract", align: "left" },
            { label: "Assigned by", align: "left" }, { label: "Why", align: "left" },
          ]}>
            {d.authorised.map((a) => (
              <tr key={a.objective_id}>
                <td className="l"><strong>{a.objective_id}</strong></td>
                <td className="l rowsub">{a.role_on_project || "—"}</td>
                <td className="l rowsub">{a.award_id || "—"}</td>
                <td className="l rowsub">{a.granted_by}</td>
                <td className="l rowsub wrap">{a.reason}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {milestone && <MilestoneDrawer id={milestone} canWrite={false}
                                     onClose={() => setMilestone(null)} />}
    </Drawer>
  );
}
