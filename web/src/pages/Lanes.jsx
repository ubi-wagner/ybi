import React, { useCallback, useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Drawer, Empty, Field, Pill, Table, useToast } from "../components/ui.jsx";

export default function Lanes() {
  const toast = useToast();
  const [lanes, setLanes] = useState([]);
  const [buildup, setBuildup] = useState(null);
  const [creating, setCreating] = useState(null);

  const load = useCallback(() => api.lanes().then(setLanes).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      await api.createLane(creating);
      toast(`Lane "${creating.name}" created as a sandbox`);
      setCreating(null);
      load();
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h2>Testing lanes</h2>
        <p className="lede">
          Fork a lane to test alternative classifications without touching the baseline.
          Changing an assumption is free. Changing a classification carries a reason and
          appears in the audit package, so exploration stays visible rather than quiet.
        </p>
      </div>

      <Card variant="quiet" title="Two different things that look alike">
        <div className="grid two">
          <div>
            <Pill tone="accent">Assumption</Pill>
            <div className="rowsub" style={{ marginTop: 6 }}>
              Tenant share at 40% rather than 55%. Evidence-neutral, changes no judgment,
              and exactly what sensitivity analysis is for. Unrestricted.
            </div>
          </div>
          <div>
            <Pill tone="warn">Classification override</Pill>
            <div className="rowsub" style={{ marginTop: 6 }}>
              Reclassify Portfolio consulting and see what happens. Legitimate analysis, and
              also the behaviour that would hollow out the seal if nobody could see it. Reason
              required, counted, disclosed.
            </div>
          </div>
        </div>
      </Card>

      <div style={{ display: "flex", justifyContent: "flex-end", margin: "16px 0 10px" }}>
        <button className="primary"
                onClick={() => setCreating({ name: "", purpose: "", created_by: "tom" })}>
          New lane
        </button>
      </div>

      {lanes.length === 0 ? (
        <Card><Empty mark="⑂" title="No lanes yet">
          The baseline is created with the first decision set. Fork it when you want to test
          an alternative treatment.
        </Empty></Card>
      ) : (
        <Table columns={[
          { label: "Lane", align: "left" }, { label: "Kind", align: "left" },
          { label: "Purpose", align: "left" }, { label: "Overrides" },
          { label: "Assumptions" }, { label: "Created by", align: "left" }, { label: "", width: 110, align: "left" },
        ]}>
          {lanes.map((l) => (
            <tr key={l.lane_id} className="hoverable">
              <td className="l" style={{ fontWeight: 600 }}>{l.name}</td>
              <td className="l">
                <Pill tone={l.kind === "BASELINE" ? "solid" : l.kind === "CANDIDATE" ? "accent" : ""}>
                  {l.kind}
                </Pill>
              </td>
              <td className="l wrap rowsub">{l.purpose}</td>
              <td style={{ color: l.classification_overrides > 0 ? "var(--warn)" : undefined }}>
                {l.classification_overrides}
              </td>
              <td>{l.assumption_variants}</td>
              <td className="l rowsub">{l.created_by}</td>
              <td className="l">
                <button className="sm" onClick={() => api.laneBuildup(l.lane_id)
                  .then((b) => setBuildup({ lane: l, rows: b }))}>Build-up</button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Drawer open={!!buildup} onClose={() => setBuildup(null)}
              title={buildup?.lane.name} subtitle="Pool build-up — read only, no rate computed here">
        {buildup && (
          <Table columns={[
            { label: "Pool", align: "left" }, { label: "Amount" },
            { label: "Lines" }, { label: "Overridden" },
          ]}>
            {buildup.rows.map((b) => (
              <tr key={b.pool}>
                <td className="l">{b.pool}</td>
                <td className="amt strong">{money(b.amount)}</td>
                <td>{b.lines}</td>
                <td>{b.overridden_decisions}</td>
              </tr>
            ))}
          </Table>
        )}
      </Drawer>

      <Drawer open={!!creating} onClose={() => setCreating(null)} title="New lane"
              subtitle="Starts as a sandbox — a sandbox can never produce a submitted rate"
              footer={
                <>
                  <button className="primary" disabled={!creating?.name || !creating?.purpose}
                          onClick={create}>Create lane</button>
                  <button onClick={() => setCreating(null)}>Cancel</button>
                </>
              }>
        {creating && (
          <>
            <Field label="Name">
              <input value={creating.name} placeholder="2025-portfolio-direct"
                     onChange={(e) => setCreating({ ...creating, name: e.target.value })} />
            </Field>
            <div style={{ marginTop: 14 }}>
              <Field label="Purpose" required>
                <textarea rows={3} value={creating.purpose}
                          placeholder="What question is this lane meant to answer?"
                          onChange={(e) => setCreating({ ...creating, purpose: e.target.value })} />
              </Field>
            </div>
            <div className="rowsub" style={{ marginTop: 10 }}>
              The purpose prints in the audit package next to how many classification
              overrides the lane carried. Write it for a reviewer.
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
