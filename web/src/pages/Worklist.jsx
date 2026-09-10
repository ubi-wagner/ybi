import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Card, Table, Empty, Pill, Tick } from "../components/ui.jsx";

const money = (v) =>
  v === null || v === undefined
    ? "—"
    : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

/* Each class of open work says what it is, why it is open, and where it is
   resolved. A list that shows a problem without naming its remedy makes the
   reader guess, and guessing is what the whole system exists to remove. */
const KIND = {
  UNCLASSIFIED: {
    title: "Unclassified cost",
    why: "In P&L scope with no live decision. Unclassified cost is never defaulted into a pool, so the rate reads high while this list is long — the honest direction to err.",
    where: "Resolved in Classify.",
    to: "/classify",
  },
  BLOCKS_SEAL: {
    title: "Blocks the seal",
    why: "Decided, but graded unsupported or test assumption. A locked foundation may not carry either, so these prevent a rate from being sealed.",
    where: "Raise the grade in Classify once evidence exists.",
    to: "/classify",
  },
  NEEDS_EVIDENCE: {
    title: "Needs evidence",
    why: "Federally allowable or pending, with no document cited on the judgment. Attaching a document is not the same as citing it — the gate reads the citation.",
    where: "Attach and cite in Classify.",
    to: "/classify",
  },
  NEEDS_CERTIFICATION: {
    title: "Needs certification",
    why: "Effort distribution not attested by the employee or a supervisor with firsthand knowledge. 2 CFR 200.430(i) wants the person who did the work.",
    where: "Certification is not yet built.",
    to: null,
  },
  ASSET_FUNDING_UNKNOWN: {
    title: "Asset funding unknown",
    why: "No funding source recorded, so depreciation currently reads as fully allowable. That is the optimistic reading and 2 CFR 200.436 disallows the federally funded share.",
    where: "Load the asset register with funding source per asset.",
    to: "/imports",
  },
  FACILITY_UNPARTITIONED: {
    title: "Facility not partitioned",
    why: "No space schedule, so occupancy cannot be carved between tenant, program and administrative use (2 CFR 200.465).",
    where: "Load the floor plan and rent roll.",
    to: "/imports",
  },
  INVOICE_NO_INDIRECT: {
    title: "Invoice without indirect",
    why: "A cost-reimbursement invoice carrying no indirect line forgoes recovery outright, rather than under-recovering.",
    where: "Restatement is proposed in Awards.",
    to: "/awards",
  },
  INVOICE_NO_AWARD: {
    title: "Invoice without an award",
    why: "Not linked to an award, so there is no ceiling to test the claim against.",
    where: "Register the agreement in Awards.",
    to: "/awards",
  },
  STALE_DECISION: {
    title: "Stale decision",
    why: "The source line changed after the decision was made. The judgment may still be right, but it was made about different numbers.",
    where: "Re-decide in Classify.",
    to: "/classify",
  },
};

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

  const meta = KIND[kind] || { title: kind, why: "", where: "", to: null };

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
          <Table columns={["", "Item", "Detail", "Amount"]}>
            {data.items.map((r, i) => (
              <tr key={i}>
                <td>
                  <Tick state={r.severity === "BLOCKING" ? "failed" : "flagged"} />
                </td>
                <td>
                  <div className="strong ellipsis">{r.label}</div>
                  <div className="quiet small">{r.entity}</div>
                </td>
                <td className="quiet small">{r.detail}</td>
                <td className="num">{money(r.amount)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
