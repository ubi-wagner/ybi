import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Card, Stat, Pill, Tick, Meter, Table, Empty } from "../components/ui.jsx";
import { forKind } from "../worklistKinds.js";

const money = (v) =>
  v === null || v === undefined
    ? "—"
    : Number(v).toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      });

const when = (t) =>
  !t ? "" : new Date(t).toLocaleString(undefined,
    { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

const SEV = { BLOCKING: "fail", HIGH: "warn", MEDIUM: "" };

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    api.dashboard()
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  if (error) return <Empty mark="!" title="Could not load">{error}</Empty>;
  if (!data) return <Empty mark="…" title="Loading" />;

  const { rollup = {}, coverage = {}, controls = [], worklist = [], activity = [] } = data;
  const blocking = worklist.filter((w) => w.severity === "BLOCKING");
  /* The bottom line of the P&L, not net operating income: other income of
     116,948.46 is the difference between a 112,619.18 operating loss and net
     income of 4,329.28. */
  const netIncome = Number(rollup.net_income || 0);

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <h1>{data.actor.name}</h1>
          <p className="quiet">
            {data.actor.role === "CONTROLLER"
              ? "Controller · you may classify, seal and restate"
              : data.actor.role === "AUDITOR"
              ? "Auditor · read only, by design"
              : data.actor.role}
            {" · period "}{data.period}
          </p>
        </div>
        <div className="dash-seal">
          {/* The reviewer's copy. A plain link rather than a fetch: the browser
              streams it and names it, and the download is recorded server-side
              against whoever asked for it. */}
          <a className="btn" href={api.auditPackageUrl(data.period)} download>
            Download audit package
          </a>
          {rollup.sealed_at ? (
            <Pill tone="good">Sealed {when(rollup.sealed_at)}</Pill>
          ) : (
            <Pill tone={blocking.length ? "fail" : ""}>
              {blocking.length ? `${blocking.length} blocking` : "Not sealed"}
            </Pill>
          )}
        </div>
      </div>

      {/* ── Finances ─────────────────────────────────────────────── */}
      <Card title="Where the finances stand" variant="raised">
        <div className="stat-row">
          <Stat label="Income" value={money(rollup.income)} size="lg" />
          <Stat label="Expenses" value={money(rollup.expense)} size="lg" />
          <Stat label="Cost of goods" value={money(rollup.cogs)} />
          <Stat label="Other income" value={money(rollup.other_income)} />
          <Stat
            label="Net"
            value={money(netIncome)}
            tone={netIncome < 0 ? "fail" : undefined}
          />
        </div>
        <div className="stat-row quiet-row">
          <Stat label="Ledger lines" value={money(rollup.ledger_lines)} note="all accounts" />
          <Stat label="In P&L scope" value={money(rollup.scope_lines)} note="classifiable" />
          <Stat label="Decisions" value={money(rollup.decisions)} />
          <Stat label="Segments" value={money(rollup.segments)} />
          <Stat label="Documents" value={money(rollup.documents)} />
          <Stat label="Invoices" value={money(rollup.invoices)} />
          <Stat label="Assets" value={money(rollup.assets)} />
          <Stat label="Facilities" value={money(rollup.facilities)} />
        </div>

        <div className="dash-coverage">
          <div>
            <Stat
              label="Dollar coverage"
              value={`${coverage.pct_dollars ?? 0}%`}
              size="lg"
              note={`${money(coverage.decided_dollars)} of ${money(coverage.dollars)}`}
            />
          </div>
          <Meter pct={coverage.pct_dollars ?? 0} target={80} />
        </div>
      </Card>

      {/* ── Controls ─────────────────────────────────────────────── */}
      <Card title="Controls" aside="Every derived figure ties, or it does not ship">
        <Table columns={[
          { label: "", width: 34, align: "left" },
          { label: "Control", align: "left" },
          { label: "Variance" },
        ]}>
          {controls.map((c, i) => (
            <tr key={i}>
              <td className="l"><Tick state={c.ties ? "done" : "failed"} /></td>
              <td className="l">{c.control}</td>
              <td className="num">{Number(c.variance ?? 0).toFixed(2)}</td>
            </tr>
          ))}
        </Table>
      </Card>

      {/* ── What is left ─────────────────────────────────────────── */}
      <Card
        title="What is left"
        aside="Ordered by money, which is the order it is worth doing in"
      >
        {worklist.length === 0 ? (
          <Empty mark="✓" title="Nothing open">
            No unclassified cost, no missing evidence, no blocking items.
          </Empty>
        ) : (
          <Table columns={[
              { label: "", width: 34, align: "left" },
              { label: "Class", align: "left" },
              { label: "Items" }, { label: "Amount" },
              { label: "", align: "left" },
            ]}>
            {worklist.map((w) => {
              const { title, short: sub } = forKind(w.kind);
              return (
                <tr
                  key={w.kind}
                  className="row-clickable"
                  onClick={() => nav(`/worklist/${w.kind}`)}
                >
                  <td className="l"><Tick state={w.severity === "BLOCKING" ? "failed" : "flagged"} /></td>
                  <td className="l">
                    <div className="strong">{title}</div>
                    <div className="quiet small">{sub}</div>
                  </td>
                  <td className="num">{w.items}</td>
                  <td className="num">{money(w.amount)}</td>
                  <td className="l"><Pill tone={SEV[w.severity]}>{w.severity}</Pill></td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>

      {/* ── The spine ────────────────────────────────────────────── */}
      <Card title="Recent activity" aside="Read from the records themselves">
        {activity.length === 0 ? (
          <Empty mark="—" title="Nothing recorded yet" />
        ) : (
          <Table columns={[
            { label: "When", align: "left" }, { label: "What", align: "left" },
            { label: "Who", align: "left" }, { label: "Item", align: "left" },
            { label: "Amount" },
          ]}>
            {activity.map((a, i) => (
              <tr key={i}>
                <td className="l quiet small">{when(a.occurred_at)}</td>
                <td className="l"><Pill>{a.kind}</Pill></td>
                <td className="l">{a.actor}</td>
                <td className="l">
                  <div className="strong ellipsis">{a.label || a.entity_id}</div>
                  {a.detail && <div className="quiet small ellipsis">{a.detail}</div>}
                </td>
                <td className="num">{a.amount == null ? "" : money(a.amount)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
