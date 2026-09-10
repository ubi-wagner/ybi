import React, { useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Drawer, Empty, Pill, Stat, Table, Tick } from "../components/ui.jsx";

export default function Awards() {
  const [awards, setAwards] = useState([]);
  const [detail, setDetail] = useState(null);

  useEffect(() => { api.awards().then(setAwards).catch(() => {}); }, []);

  const open = async (a) => {
    const [constraints, trueup] = await Promise.all([
      fetch(`/api/awards/${a.award_id}/constraints`).then((r) => r.json()),
      fetch(`/api/awards/${a.award_id}/trueup`).then((r) => r.json()),
    ]);
    setDetail({ award: a, constraints, trueup });
  };

  return (
    <div className="page">
      <div className="page-head">
        <h2>Awards and true-up</h2>
        <p className="lede">
          An invoice is issuable only when every blocking constraint passes. Where one fails
          the system records an acknowledged deficiency instead — both are states, and
          neither is silence.
        </p>
      </div>

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
              <td className="l rowsub">{a.instrument}</td>
              <td className="amt strong">{money(a.ceiling_federal)}</td>
              <td className="amt">{money(a.cost_share_required)}</td>
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
