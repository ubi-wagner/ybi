import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, Meter, Pill, Stat, Table, useToast } from "../components/ui.jsx";

export default function Rates() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [cov, setCov] = useState(null);

  const load = useCallback(() => {
    api.rates().then(setData).catch(() => {});
    api.coverage().then(setCov).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const seal = async () => {
    try {
      const r = await api.seal({ sealed_by: "tom" });
      toast(`Sealed — ${r.seal_hash.slice(0, 16)}…`);
      load();
    } catch (e) { toast(String(e.message || e), { tone: "bad", sticky: true }); }
  };

  const pct = Number(cov?.pct_dollars || 0);
  const rates = data?.rates || [];

  return (
    <div className="page">
      <div className="page-head">
        <h2>Rates</h2>
        <p className="lede">
          Sealing hashes every live classification and freezes the set. Only then can a rate
          be computed, and the rate carries the seal — so it can be shown to be a consequence
          of the judgments rather than a target they were fitted to.
        </p>
      </div>

      <Card variant="raised">
        <div className="card-head">
          <div className="card-title">Before sealing</div>
          <span className="rowsub">Coverage is the only gate that matters here</span>
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
        <button className="primary" onClick={seal}>Seal decision set</button>
      </Card>

      <div style={{ marginTop: 20 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Computed rates</div>
        {rates.length === 0 ? (
          <Card><Empty mark="%" title="No rate yet">
            Seal the decision set to unlock the rate phase. A database trigger refuses any
            rate whose seal does not match a sealed set.
          </Empty></Card>
        ) : (
          <Table columns={[
            { label: "Rate", align: "left" }, { label: "Pool" }, { label: "Base", align: "left" },
            { label: "Base amount" }, { label: "Rate" }, { label: "Status", align: "left" },
            { label: "Seal", align: "left" },
          ]}>
            {rates.map((r, i) => (
              <tr key={i} className="hoverable">
                <td className="l" style={{ fontWeight: 600 }}>{r.kind.replace(/_/g, " ")}</td>
                <td>{Number(r.pool_amount).toLocaleString()}</td>
                <td className="l rowsub">{r.base_type}</td>
                <td>{Number(r.base_amount).toLocaleString()}</td>
                <td style={{ fontWeight: 700, fontSize: 14 }}>{(Number(r.rate) * 100).toFixed(2)}%</td>
                <td className="l"><Pill tone={r.status === "ACCEPTED" ? "pass" : ""}>{r.status}</Pill></td>
                <td className="l mono-ref">{String(r.seal_hash).slice(0, 12)}…</td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </div>
  );
}
