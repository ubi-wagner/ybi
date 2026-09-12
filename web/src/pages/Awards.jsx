import React, { useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Drawer, Empty, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

/* A ceiling of zero is not a ceiling of zero. Two of the three awards on file
   carry no ceiling because nobody has read one off the agreement yet, and the
   table printed a bold 0 against them — which says the award may bear nothing,
   the opposite of what is true. An amount nobody has established is not an
   amount, and the cell should say so.

   Cost share is the same shape of question with a different answer: zero is a
   real and common term, and the ICAM agreement states it explicitly. So a
   nil cost share reads as nil, and only a missing one reads as missing. */
const money0 = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

function ceiling(v) {
  const n = money0(v);
  if (n === null || n === 0) {
    return <span className="rowsub" title="No ceiling has been read off the agreement">not on file</span>;
  }
  return money(v);
}

function costShare(v) {
  const n = money0(v);
  if (n === null) return <span className="rowsub">—</span>;
  if (n === 0) return <span className="rowsub">none</span>;
  return money(v);
}

/* The instrument as a person would say it. Where the agreement's own words
   are on file they are used; otherwise the enum is unpicked rather than
   shown, because COOPERATIVE_SUB is a column value and not a sentence. */
const INSTRUMENTS = {
  COOPERATIVE_SUB: "Subaward under a cooperative agreement",
  COST_REIMBURSEMENT: "Cost reimbursement",
  COST_REIMBURSEMENT_NO_FEE: "Cost reimbursement, no fee",
  FIXED_PRICE: "Fixed price",
  GRANT: "Grant",
};

function instrument(v) {
  if (!v) return <span className="rowsub">—</span>;
  if (INSTRUMENTS[v]) return INSTRUMENTS[v];
  if (/^[A-Z0-9_]+$/.test(v)) {
    const t = v.replace(/_/g, " ").toLowerCase();
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  return v;
}

export default function Awards() {
  const toast = useToast();
  const [awards, setAwards] = useState([]);
  const [detail, setDetail] = useState(null);

  useEffect(() => { api.awards().then(setAwards).catch(() => {}); }, []);

  /* Both of these were bare `fetch(...).then(r => r.json())` with no status
     check and no `catch`, which failed in the two worst ways at once. A 403
     or a 500 parses to `{detail: "..."}`, and the drawer then calls
     `.map` on it — so a refusal took the page down rather than saying
     anything. A network error rejected a promise nobody was awaiting, so the
     row simply did not open: a click that does nothing, tells nobody, and
     leaves no trace on the failure list. Through `api` both answer with the
     sentence the server gave, and `FailureBell` sees them. */
  const open = async (a) => {
    try {
      const [constraints, trueup] = await Promise.all([
        api.awardConstraints(a.award_id),
        api.awardTrueup(a.award_id),
      ]);
      setDetail({ award: a, constraints, trueup });
    } catch (e) {
      setDetail(null);
      toast.fail(String(e.message || e));
    }
  };

  return (
    <div className="page">
      <PageHead title="Awards and true-up" schedule="F">
        An invoice is issuable only when every blocking constraint passes. Where one fails
          the system records an acknowledged deficiency instead — both are states, and
          neither is silence.
      </PageHead>

      {awards.length === 0 ? (
        <Card><Empty mark="§" title="No awards loaded">
          Award terms are seeded from executed agreements. Add one to test claims against
          its ceiling, period of performance and cost share.
        </Empty></Card>
      ) : (
        <Table columns={[
          { label: "Award", align: "left" }, { label: "Objective", align: "left" },
          { label: "Instrument", align: "left" }, { label: "Ceiling" },
          { label: "Cost share" }, { label: "Term ends", align: "left" }, { label: "", width: 120, align: "left" },
        ]}>
          {awards.map((a) => (
            <tr key={a.award_id} className="hoverable" onClick={() => open(a)}>
              <td className="l" style={{ fontWeight: 600 }}>{a.award_id}</td>
              <td className="l">{a.objective_label}</td>
              <td className="l rowsub">{instrument(a.instrument)}</td>
              <td className="amt strong">{ceiling(a.ceiling_federal)}</td>
              <td className="amt">{costShare(a.cost_share_required)}</td>
              <td className="l rowsub">{a.period_end}</td>
              <td className="l"><button className="sm">Constraints</button></td>
            </tr>
          ))}
        </Table>
      )}

      <Drawer open={!!detail} onClose={() => setDetail(null)}
              title={detail?.award.award_id}
              subtitle={detail?.award.sponsor}>
        {detail && (
          <>
            <Card variant="raised">
              <div className="stat-row">
                <Stat label="Disposition" size="md"
                      tone={detail.trueup.issuable ? "pass" : "fail"}
                      value={detail.trueup.disposition.replace(/_/g, " ").toLowerCase()} />
                <Stat label="Blocking failures" size="lg"
                      tone={detail.trueup.blocking_failures ? "fail" : "pass"}
                      value={detail.trueup.blocking_failures} />
              </div>
            </Card>

            <div style={{ marginTop: 16 }}>
              <Table columns={[
                { label: "", width: 34, align: "left" }, { label: "Constraint", align: "left" },
                { label: "Citation", align: "left" }, { label: "Detail", align: "left" },
              ]}>
                {detail.constraints.map((c, i) => (
                  <tr key={i}>
                    <td className="l">
                      <Tick state={c.passed ? "done" : c.blocking ? "failed" : "flagged"} />
                    </td>
                    <td className="l">
                      <div style={{ fontWeight: 600 }}>{c.code.replace(/_/g, " ")}</div>
                      <div className="rowsub">{c.description}</div>
                    </td>
                    <td className="l mono-ref">{c.citation}</td>
                    <td className="l wrap rowsub">{c.detail}</td>
                  </tr>
                ))}
              </Table>
              {detail.constraints.length === 0 && (
                <Card variant="quiet">
                  <span className="rowsub">
                    No constraints evaluated yet. They run when a rate is computed.
                  </span>
                </Card>
              )}
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
