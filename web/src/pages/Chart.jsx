import React, { useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Empty, Pill, Search, Segmented, Stat, Table, Tick } from "../components/ui.jsx";

const POOL_TONE = {
  DIRECT: "accent", FRINGE: "", OVERHEAD: "", "G&A": "",
  FUNDRAISING: "warn", UNALLOWABLE: "fail", RENTAL_DIRECT: "warn",
};

export default function Chart() {
  const [view, setView] = useState("chart");
  const [sum, setSum] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [xw, setXw] = useState(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.chartSummary().then(setSum).catch(() => {});
    api.chartAccounts().then(setAccounts).catch(() => {});
    api.chartCrosswalk().then(setXw).catch(() => {});
  }, []);

  const match = (s) => !q || String(s).toLowerCase().includes(q.toLowerCase());
  const rows = accounts.filter((a) => match(a.account_name) || match(a.account_number) || match(a.pool));
  const xrows = (xw?.rows || []).filter((r) => match(r.account_2025) || match(r.account_2026));

  return (
    <div className="page">
      <div className="page-head">
        <h2>Chart of accounts</h2>
        <p className="lede">
          The 2025 chart bakes program identity into account names — Drive AM, LTM Grant,
          Rising Tides Expense. Eighty-five expense accounts, a new one for every award, and
          a single account mixing consulting, travel and materials. The 2026 chart moves
          program identity to Customer:Job and lets the account number carry the cost pool.
        </p>
      </div>

      <Card variant="raised" title="Four dimensions, straight off the transaction">
        <div className="grid form">
          {[
            ["Account number", "Cost pool", "5xxx direct · 6xxx fringe · 7xxx facilities · 8xxx G&A · 91xx fundraising · 92xx unallowable · 93xx rental"],
            ["Class", "Form 990 function", "Program · Management & General · Fundraising"],
            ["Customer:Job", "Cost objective", "The award or program the cost serves"],
            ["Location", "Facility", "Which building, for the space allocation"],
          ].map(([field, carries, detail]) => (
            <div key={field}>
              <Pill tone="accent">{field}</Pill>
              <div style={{ fontWeight: 600, marginTop: 6 }}>{carries}</div>
              <div className="rowsub">{detail}</div>
            </div>
          ))}
        </div>
        <div className="rowsub" style={{ marginTop: 14 }}>
          These are the same four dimensions the classification queue records by hand for
          2025. From 2026 the books produce them directly — 2025 is remediation, 2026 onward
          is bookkeeping.
        </div>
      </Card>

      {sum && (
        <Card style={{ marginTop: 14 }}>
          <div className="stat-row">
            <Stat label="Accounts" size="lg" value={sum.accounts} />
            <Stat label="Classes" size="lg" value={sum.classes} />
            <Stat label="Customer:Jobs" size="lg" value={sum.customer_jobs} />
            <div style={{ flex: 1 }} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[["accounts", "Chart of accounts"], ["classes", "Classes"], ["customers", "Customers & jobs"]].map(
                ([k, label]) => (
                  <a key={k} className="btn" href={`/api/chart/export/${k}`} download>{label} CSV</a>
                ))}
            </div>
          </div>
          <div className="rowsub" style={{ marginTop: 12 }}>
            Import order in QuickBooks: enable account numbers first under Settings →
            Advanced → Chart of accounts, or the numbers that carry the pool assignment are
            discarded. Then accounts, then classes, then customers.
          </div>
        </Card>
      )}

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "20px 0 12px" }}>
        <Segmented value={view} onChange={setView}
                   options={[["chart", "2026 chart"], ["crosswalk", "2025 crosswalk"]]} />
        <Search value={q} onChange={setQ} placeholder="Account or pool" />
        {view === "crosswalk" && xw?.tieout && (
          <>
            <div style={{ flex: 1 }} />
            <Pill tone={Number(xw.tieout.variance) === 0 ? "pass" : "fail"}>
              {Number(xw.tieout.variance) === 0 ? "Ties to the 2025 ledger" : "Does not tie"}
            </Pill>
            <Pill tone="warn">{xw.tieout.splits_requiring_a_driver} splits need a driver</Pill>
          </>
        )}
      </div>

      {view === "chart" && (
        <Table columns={[
          { label: "No.", align: "left", width: 70 }, { label: "Account", align: "left" },
          { label: "Pool", align: "left" }, { label: "990 function", align: "left" },
          { label: "Federal", align: "left" }, { label: "MTDC", align: "left", width: 60 },
          { label: "Citation", align: "left" },
        ]}>
          {rows.map((a) => (
            <tr key={a.account_number} className="hoverable">
              <td className="l num" style={{ fontWeight: 600 }}>{a.account_number}</td>
              <td className="l">{a.account_name}</td>
              <td className="l">{a.pool ? <Pill tone={POOL_TONE[a.pool] ?? ""}>{a.pool}</Pill> : <span className="rowsub">—</span>}</td>
              <td className="l rowsub">{a.function_990.replace(/_/g, " ").toLowerCase()}</td>
              <td className="l">
                {a.federal === "UNALLOWABLE" ? <Pill tone="fail">unallowable</Pill>
                  : a.federal === "ALLOWABLE" ? <Pill tone="pass">allowable</Pill>
                  : <span className="rowsub">—</span>}
              </td>
              <td className="l">{a.in_mtdc_base === "N" ? <Tick state="flagged" title="Excluded from MTDC" /> : a.in_mtdc_base === "Y" ? <Tick state="done" title="In the MTDC base" /> : ""}</td>
              <td className="l mono-ref">{a.citation}</td>
            </tr>
          ))}
        </Table>
      )}

      {view === "crosswalk" && (
        !xw?.rows?.length ? (
          <Card><Empty mark="⇄" title="No 2025 ledger to tie against">
            {xw?.note || "Import the reconciled general ledger and the crosswalk will prove the new chart carries every dollar."}
          </Empty></Card>
        ) : (
          <Table
            columns={[
              { label: "2025 account", align: "left" }, { label: "Amount" }, { label: "Lines" },
              { label: "2026 account", align: "left" }, { label: "", width: 34, align: "left" },
              { label: "Note", align: "left" },
            ]}
            footer={
              <tr>
                <td className="l">Total</td>
                <td>{money(xw.tieout.total)}</td>
                <td />
                <td className="l">mapped {money(xw.tieout.mapped)}</td>
                <td />
                <td className="l">variance {money(xw.tieout.variance)}</td>
              </tr>
            }>
            {xrows.map((r) => (
              <tr key={r.account_2025} className="hoverable">
                <td className="l">{r.account_2025}</td>
                <td className="amt strong">{money(r.amount_2025)}</td>
                <td>{r.lines}</td>
                <td className="l num">{r.account_2026 || <span className="rowsub">unmapped</span>}</td>
                <td className="l">{r.split && <Tick state="flagged" title="Needs a documented split driver" />}</td>
                <td className="l wrap rowsub">{r.note}</td>
              </tr>
            ))}
          </Table>
        )
      )}
    </div>
  );
}
