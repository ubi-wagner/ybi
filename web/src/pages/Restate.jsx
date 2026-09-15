import React, { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, explain, money } from "../api.js";
import {
  Card, Drawer, Empty, Field, PageHead, Pill, Stat, Table, Tick, useToast,
} from "../components/ui.jsx";

/* Restating the America Makes invoices — the point of the whole system, and
   the screen it never had. Five routes have been complete since they were
   written and there was no page, no route in App.jsx and no call in api.js,
   so nobody could reach the thing everything upstream exists to produce.

   The three rules the handler opens with are the three this screen has to
   carry, because a screen that breaks one of them breaks it for everybody:

   1. Nothing is computed here. Every figure is read from the row the
      restatement was recorded in, like the review screens. The rate carries
      a seal and the restatement carries the same one.

   2. An over-collection is never netted against an under-recovery. They are
      two different conversations — money to ask for, and money to give back
      — and one figure hides both. `v_restatement` carried exactly that
      figure as `net_movement` until migration 061 took it away; it was
      never read because this screen did not exist, which is the only reason
      the trap was never sprung.

   3. A proposal is not a position. Neither agreement was billed under a
      provisional rate, so moving off the de minimis election is a change of
      basis needing a written modification under §4.4. Everything is PROPOSED
      until a sponsor says otherwise, and accepting one without naming the
      modification is refused — by the schema, and by this form. */

const STATUS = {
  PROPOSED:   { tone: "",       says: "a proposal, not a claim" },
  SUBMITTED:  { tone: "accent", says: "with the sponsor" },
  ACCEPTED:   { tone: "solid",  says: "accepted in writing" },
  REJECTED:   { tone: "warn",   says: "rejected" },
  SUPERSEDED: { tone: "",       says: "superseded by a later computation" },
};

export default function Restate({ actor }) {
  const { restatementId } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [cand, setCand] = useState(null);
  const [rows, setRows] = useState([]);
  const [detail, setDetail] = useState(null);
  const [proposing, setProposing] = useState(null);

  const canWrite = (actor?.portfolios || []).includes("CONTROLLER");

  const load = useCallback(async () => {
    const [c, r] = await Promise.all([api.restateCandidates(), api.restatements()]);
    setCand(c);
    setRows(r || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const open = useCallback(async (id) => setDetail(await api.restatement(id)), []);
  useEffect(() => { if (restatementId) open(restatementId); }, [restatementId, open]);

  if (!cand) return null;
  const blocked = cand.blocked_because || [];
  /* The rate the restatement will actually apply, not whichever sorted
     first. `candidates` returns every live rate ordered by when it was
     computed, and the first draft of this took `rates[0]` — which was
     FRINGE at 0.00% while the restatement measured against
     INDIRECT_COMBINED at 40.64%. A screen showing a different number from
     the one the server uses is the same defect as a nav stricter than the
     API: the two disagree about what is true. */
  const rate = (cand.rates || []).find((r) => r.kind === "INDIRECT_COMBINED")
            || (cand.rates || [])[0];

  return (
    <div className="page">
      <PageHead title="Restatement" schedule="F">
        Every invoice on an objective measured against the sealed rate, in the
        direction the difference actually runs. Everything upstream — the
        classification, the seal, the rate, the allocation — exists so that a
        number put in front of NCDMM can be traced back to a judgment somebody
        signed their name to.
      </PageHead>

      {/* "Not yet, because" rather than an empty list. The reasons are the
          work — the same answer the candidates route gives. */}
      {blocked.length > 0 ? (
        <Card><Empty mark="—" title="Not yet">
          {blocked.map((b) => <div key={b} className="wrap">{b}</div>)}
        </Empty></Card>
      ) : (
        <Card variant="quiet" title="What it will be measured against"
              aside="A restatement is a consequence of the rate, and the rate of the judgments">
          <div className="grid three">
            <Stat label={rate.kind.replace(/_/g, " ").toLowerCase()}
                  value={`${(Number(rate.rate) * 100).toFixed(2)}%`}
                  note={`computed ${new Date(rate.computed_at).toLocaleDateString()}`} />
            <Stat label="Status" value={rate.status}
                  note="a superseded rate cannot carry a restatement" />
            <Stat label="Seal" value={String(rate.seal_hash).slice(0, 10)}
                  note="the restatement carries the same one" />
          </div>
        </Card>
      )}

      <Card title="The invoices as billed"
            aside="What NCDMM has already been sent" style={{ marginTop: 14 }}>
        {cand.objectives.length === 0 ? (
          <div className="rowsub">No invoices on file for this period.</div>
        ) : (
          <Table columns={[
            { label: "Objective", align: "left" },
            { label: "Contract", align: "left" },
            { label: "Invoices" },
            { label: "Billed" },
            { label: "Indirect billed" },
            { label: "Billed under", align: "left" },
            { label: "", width: 110, align: "left" },
          ]}>
            {cand.objectives.map((o) => {
              const done = rows.find((r) => r.objective_id === o.objective_id
                                         && r.status !== "SUPERSEDED");
              return (
                <tr key={o.objective_id}>
                  <td className="l"><strong>{o.label || o.objective_id}</strong>
                    <div className="rowsub">{o.objective_id}</div></td>
                  <td className="l rowsub">{o.award_id || "—"}</td>
                  <td>{o.invoices}</td>
                  <td className="amt">{money(o.billed)}</td>
                  {/* A zero here is the whole case. Drive AM's Schedule B
                      carries no indirect line at all against $583,594 of
                      budgeted labour, and the invoice YBI issued is itself
                      the record of what it was never budgeted to claim. */}
                  <td className={Number(o.indirect_billed) === 0 ? "amt warnish" : "amt"}>
                    {Number(o.indirect_billed) === 0 ? "none" : money(o.indirect_billed)}
                  </td>
                  <td className="l rowsub">{o.billed_under}</td>
                  <td className="l">
                    {done ? (
                      <button className="sm"
                              onClick={() => nav(`/restate/${done.restatement_id}`)}>
                        Open
                      </button>
                    ) : canWrite && blocked.length === 0 ? (
                      <button className="sm"
                              onClick={() => setProposing({ o, basis: "" })}>
                        Measure it
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>

      <Card title="Proposals" aside={`${rows.length} on the record`}
            style={{ marginTop: 14 }}>
        {rows.length === 0 ? (
          <div className="rowsub">
            Nothing measured yet. A restatement is a proposal with its
            arithmetic attached, per invoice, and it stays a proposal until a
            sponsor says otherwise in writing.
          </div>
        ) : rows.map((r) => (
          <div key={r.restatement_id} className="hoverable"
               style={{ padding: "10px 0", borderTop: "1px solid var(--rule)",
                        cursor: "pointer" }}
               onClick={() => nav(`/restate/${r.restatement_id}`)}>
            <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
              <Tick state={r.status === "ACCEPTED" ? "done"
                           : r.status === "REJECTED" ? "failed"
                           : r.status === "SUPERSEDED" ? "open" : "flagged"} />
              <strong>{r.objective_id}</strong>
              <Pill tone={STATUS[r.status]?.tone}>{r.status}</Pill>
              <span className="rowsub">{STATUS[r.status]?.says}</span>
              <span className="rowsub" style={{ marginLeft: "auto" }}>
                {r.invoices} invoice(s) · rate {(Number(r.rate_applied) * 100).toFixed(2)}%
              </span>
            </div>
            <Movement r={r} />
          </div>
        ))}
      </Card>

      <Drawer open={!!detail} onClose={() => { setDetail(null); nav("/restate"); }}
              title={detail ? `${detail.restatement.objective_id} restated` : ""}
              subtitle={detail ? `${detail.restatement.invoices} invoice(s) against `
                + `${(Number(detail.restatement.rate_applied) * 100).toFixed(2)}% `
                + `${detail.restatement.rate_kind}` : ""}>
        {detail && (
          <Detail d={detail} canWrite={canWrite} toast={toast}
                  onChange={async () => {
                    await open(detail.restatement.restatement_id);
                    load();
                  }} />
        )}
      </Drawer>

      <Drawer open={!!proposing} onClose={() => setProposing(null)}
              title={`Measure ${proposing?.o.objective_id || ""}`}
              subtitle="Against the sealed rate, per invoice, in the direction the difference runs">
        {proposing && (
          <ProposeForm p={proposing} rate={rate} onDone={async (basis) => {
            try {
              const got = await api.restate({
                objective_id: proposing.o.objective_id, basis,
              });
              toast.ok(`${got.invoices} invoice(s) measured — `
                + `${money(got.under_recovered)} under-recovered, `
                + `${money(got.over_collected)} over-collected`);
              setProposing(null);
              await load();
              nav(`/restate/${got.restatement_id}`);
            } catch (e) { toast.fail(explain(e)); }
          }} />
        )}
      </Drawer>
    </div>
  );
}


/* ── The two figures, side by side and never subtracted ────────────────
   `v_restatement` offered `under_recovered - over_collected` as one column
   until migration 061 removed it. Money to ask a sponsor for and money to
   give back are two conversations, and $120,000 each way is not a quiet
   year. */
function Movement({ r }) {
  const under = Number(r.under_recovered);
  const over = Number(r.over_collected);
  return (
    <div className="grid two" style={{ marginTop: 6 }}>
      <div>
        <span className="rowsub">To ask for</span>{" "}
        <strong className={under > 0 ? "" : "rowsub"}>
          {money(r.under_recovered)}
        </strong>
        {r.capped_by_ceiling && (
          <div className="rowsub warnish wrap">
            More than the ceiling leaves. That is not a bigger claim, it is a
            modification conversation — {money(r.ceiling_headroom)} of headroom.
          </div>
        )}
      </div>
      <div>
        <span className="rowsub">To give back</span>{" "}
        <strong className={over > 0 ? "failish" : "rowsub"}>
          {money(r.over_collected)}
        </strong>
      </div>
    </div>
  );
}


function Detail({ d, canWrite, toast, onChange }) {
  const r = d.restatement;
  const [deciding, setDeciding] = useState(null);
  return (
    <>
      <Movement r={r} />

      <div className="grid three" style={{ margin: "14px 0" }}>
        <Stat label="Billed" value={money(r.billed_total)}
              note={`${r.invoices} invoice(s)`} />
        <Stat label="Indirect billed" value={money(r.indirect_billed)}
              note={`on a base of ${money(r.base_total)}`} />
        <Stat label="Indirect supported" value={money(r.indirect_supported)}
              note={`at ${(Number(r.rate_applied) * 100).toFixed(2)}%`} />
      </div>

      <div className="rowsub wrap" style={{ marginBottom: 12 }}>
        Measured by {r.computed_by} on{" "}
        {new Date(r.computed_at).toLocaleDateString()}, against the rate
        carrying seal <code>{String(r.seal_hash).slice(0, 12)}</code> — so it
        is provably a consequence of the classifications rather than of
        somebody's preferred answer. Billed under {r.billed_under}.
      </div>
      <div className="wrap" style={{ marginBottom: 14 }}>{r.basis}</div>

      <Card variant="quiet" title="Per invoice"
            aside="In the direction the difference runs">
        {d.lines.map((l) => (
          <div key={l.invoice_id}
               style={{ padding: "8px 0", borderTop: "1px solid var(--rule)" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
              <strong>{l.invoice_number || String(l.invoice_id).slice(0, 8)}</strong>
              <span className="rowsub">{l.invoice_date}</span>
              <span style={{ marginLeft: "auto" }}
                    className={l.direction === "OVER" ? "failish" : ""}>
                {l.direction === "EVEN" ? "even"
                  : `${l.direction === "UNDER" ? "under-recovered by"
                                               : "over-collected by"} ${money(Math.abs(Number(l.variance)))}`}
              </span>
            </div>
            <div className="rowsub">
              base {money(l.base_as_billed)} · billed{" "}
              {Number(l.indirect_billed) === 0
                ? <span className="warnish">no indirect line at all</span>
                : money(l.indirect_billed)}{" "}
              · supported {money(l.indirect_supported)}
            </div>
            {l.finding && <div className="rowsub wrap">{l.finding}</div>}
          </div>
        ))}
      </Card>

      <Card variant="quiet" title="Where it stands" style={{ marginTop: 14 }}>
        <div className="rowsub wrap" style={{ marginBottom: 10 }}>
          <Pill tone={STATUS[r.status]?.tone}>{r.status}</Pill>{" "}
          {STATUS[r.status]?.says}.
          {r.modification_ref
            ? <> Authorised by <strong>{r.modification_ref}</strong>.</>
            : <> Neither America Makes agreement was billed under a
                provisional rate, so moving off the de minimis election is a
                change of basis and needs a written modification under §4.4.
                Accepting one without naming it is refused by the schema.</>}
          {r.decided_note && <div className="wrap">{r.decided_note}</div>}
        </div>
        {canWrite && r.status !== "SUPERSEDED" && (
          <div style={{ display: "flex", gap: 8 }}>
            {["SUBMITTED", "ACCEPTED", "REJECTED"]
              .filter((s) => s !== r.status)
              .map((s) => (
                <button key={s} className={s === "ACCEPTED" ? "primary" : "sm"}
                        onClick={() => setDeciding(s)}>
                  {s === "SUBMITTED" ? "Send to the sponsor"
                    : s === "ACCEPTED" ? "Accepted in writing" : "Rejected"}
                </button>
              ))}
          </div>
        )}
      </Card>

      <Drawer open={!!deciding} onClose={() => setDeciding(null)}
              title={deciding === "ACCEPTED" ? "Accepted in writing"
                     : deciding === "SUBMITTED" ? "Send it to the sponsor"
                     : "Rejected"}
              subtitle={deciding === "ACCEPTED"
                ? "Which modification authorised the change of basis"
                : "What happened, for the record"}>
        {deciding && (
          <DecideForm status={deciding} onDone={async (body) => {
            try {
              await api.restateStatus(r.restatement_id, { status: deciding, ...body });
              toast.ok(`Moved to ${deciding.toLowerCase()}`);
              setDeciding(null);
              onChange();
            } catch (e) { toast.fail(explain(e)); }
          }} />
        )}
      </Drawer>
    </>
  );
}


function ProposeForm({ p, rate, onDone }) {
  const [basis, setBasis] = useState("");
  return (
    <>
      <div className="rowsub wrap" style={{ marginBottom: 12 }}>
        {p.o.invoices} invoice(s) on {p.o.objective_id} totalling{" "}
        {money(p.o.billed)}, of which{" "}
        {Number(p.o.indirect_billed) === 0
          ? <strong className="warnish">no indirect at all</strong>
          : <>{money(p.o.indirect_billed)} is indirect</>}
        . Each will be measured against{" "}
        {(Number(rate.rate) * 100).toFixed(2)}% and the difference recorded in
        the direction it runs — nothing is netted.
      </div>
      <Field label="What this rests on" required>
        <textarea rows={4} value={basis}
                  placeholder="The rate, the seal behind it, and why the basis is being restated. A reviewer reads this beside the figure it produced."
                  onChange={(e) => setBasis(e.target.value)} />
      </Field>
      {/* The route asks for 21 characters. A reviewer asks for more. */}
      <div className="rowsub" style={{ marginTop: 4 }}>
        {basis.trim().length < 21
          ? `${21 - basis.trim().length} more character(s) — the schema asks for a sentence.`
          : "It goes onto the record beside the arithmetic."}
      </div>
      <div style={{ marginTop: 12 }}>
        <button className="primary" disabled={basis.trim().length < 21}
                onClick={() => onDone(basis.trim())}>Measure it</button>
      </div>
    </>
  );
}


function DecideForm({ status, onDone }) {
  const [ref, setRef] = useState("");
  const [note, setNote] = useState("");
  const needsRef = status === "ACCEPTED";
  return (
    <>
      {needsRef && (
        <>
          <Field label="Modification" required>
            <input value={ref} placeholder="Modification 002, 14 March 2026"
                   onChange={(e) => setRef(e.target.value)} />
          </Field>
          <div className="rowsub wrap" style={{ marginTop: 4, marginBottom: 12 }}>
            The single omission most likely to become a finding. A restatement
            accepted without naming the modification that authorised the change
            of basis is refused by the schema, not just by this form.
          </div>
        </>
      )}
      <Field label="What happened">
        <textarea rows={3} value={note}
                  onChange={(e) => setNote(e.target.value)} />
      </Field>
      <div style={{ marginTop: 12 }}>
        <button className="primary" disabled={needsRef && !ref.trim()}
                onClick={() => onDone({ modification_ref: ref.trim(), note })}>
          Record it
        </button>
      </div>
    </>
  );
}
