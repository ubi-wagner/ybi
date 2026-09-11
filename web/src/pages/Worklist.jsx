import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Card, Table, Empty, Pill, Tick } from "../components/ui.jsx";
import { forKind } from "../worklistKinds.js";

const money = (v) =>
  v === null || v === undefined
    ? "—"
    : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

export default function Worklist() {
  const { kind } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api.worklist({ kind, limit: 200 })
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, [kind]);

  const meta = forKind(kind);

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <button className="btn quiet" onClick={() => nav("/")}>← Dashboard</button>
          <h1>{meta.title}</h1>
          <p className="quiet">{meta.why}</p>
        </div>
      </div>

      <Card
        title={data ? `${data.total} item${data.total === 1 ? "" : "s"}`
                     + (data.shown < data.total ? ` · showing ${data.shown}` : "")
                     : "Loading"}
        aside={
          meta.to ? (
            <button className="btn" onClick={() => nav(meta.to)}>{meta.where}</button>
          ) : (
            <span className="quiet small">{meta.where}</span>
          )
        }
      >
        {error && <Empty mark="!" title="Could not load">{error}</Empty>}
        {data && data.total === 0 && (
          <Empty mark="✓" title="Nothing open in this class" />
        )}
        {data && data.items.length > 0 && (
          <Table columns={[
            { label: "", width: 34, align: "left" },
            { label: "Item", align: "left" }, { label: "Detail", align: "left" },
            { label: "Amount" },
          ]}>
            {data.items.map((r, i) => (
              <tr key={i}>
                <td className="l">
                  <Tick state={r.severity === "BLOCKING" ? "failed" : "flagged"} />
                </td>
                <td className="l">
                  <div className="strong ellipsis">{r.label}</div>
                  <div className="quiet small">{r.entity}</div>
                </td>
                <td className="l quiet small">{r.detail}</td>
                <td className="num">{money(r.amount)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
