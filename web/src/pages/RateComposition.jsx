import React, { useEffect, useState } from "react";
import { api, explain, money, count } from "../api.js";
import { Card, Drawer, Empty, Pill, Segmented, Table, Tick } from "../components/ui.jsx";
import { fn990 } from "../functions990.js";

/* Inside the rate. What makes up the pool, the carve-outs and the base —
 * high-level first, then every transaction underneath.
 *
 * The build-up above this answers *how the rate was struck*: pool over base,
 * less what was carved out, against the seal. That is what a reviewer needs
 * to reproduce the arithmetic, and it is not what somebody walking into a
 * negotiation needs. The controller asked for this in his own words — "high
 * level amounts of what makes up the individual amounts as well as detailed
 * by transaction" — having downloaded the build-up workbook and found it was
 * the four rows he was already looking at.
 *
 * Three rules, and the first is the only one that matters:
 *
 *   - **Every partition says whether it foots.** A breakdown that does not
 *     add back to the figure on the workpaper is worse than no breakdown, in
 *     a negotiation most of all: a sponsor who adds the column up and gets a
 *     different answer stops reading. So each section prints what its rows
 *     come to *and* the figure on file, and ticks only when they are equal.
 *   - **Nothing here is computed.** The rows are the same ledger lines,
 *     carve-out rows, effort distribution and allocation the computation
 *     read, partitioned. Where a figure has to be stated it is read off the
 *     row that recorded it.
 *   - **It is a read.** No button on this screen writes anything. The rate it
 *     describes is sealed and certified, and a drill-down that could move a
 *     figure would be a rate preview on the classification screen wearing a
 *     different hat.
 */

const KINDS = [
  ["INDIRECT_COMBINED", "Indirect, combined"],
  ["OVERHEAD", "Overhead"],
  ["G&A", "G&A"],
  ["FRINGE", "Fringe"],
];

const BASE = {
  MTDC: "Modified total direct cost",
  SALARIES_WAGES: "Salaries and wages",
  TOTAL_DIRECT: "Total direct cost",
};

/* The footing line. `recorded` is the figure the rate carries and `total` is
   what the rows under it come to; both print, because a reader comparing a
   breakdown to a workpaper is comparing two numbers and one of them would
   make them take the tie on trust. */
/* Three states, not two, because `foots` is deliberately `null` where no
 * breakdown exists to draw. Reading it as a boolean renders NO DATA as a
 * failed tie and prints a variance the width of the whole base — which is
 * the thing `_part` was written to prevent, reintroduced one layer up. */
function Foots({ part, what }) {
  if (!part) return null;
  if (part.state === "NO DATA") {
    return (
      <span className="rowsub">
        <Tick state="open" />
        {" "}nothing to break the{" "}<span className="num">{money(part.recorded)}</span>
        {" on file into"}
      </span>
    );
  }
  return (
    <span className="rowsub">
      {count(part.rows.length)} {what}
      {" · "}
      <span className="num">{money(part.total)}</span>
      {part.foots ? (
        <> <Tick state="done" title="adds to the figure on file" /> ties to the rate</>
      ) : (
        <>
          {" "}<Tick state="failed" />
          {" against "}<span className="num">{money(part.recorded)}</span>
          {" on file — out by "}<span className="num">{money(part.variance)}</span>
        </>
      )}
    </span>
  );
}

/* Take this section away, at the level it is being read.
 *
 * Two formats because they are two jobs: a CSV is pasted into a sponsor's
 * model and an .xlsx is filed as a workpaper, and a figure that arrives in
 * the wrong one gets retyped. Both carry the caveat and the section's own
 * footing line on the face of the file, because a file travels further than
 * the screen that would have said so.
 *
 * Rendered only for a section the server offers, read from
 * `/export/rate/sections` — the screen keeping its own list of what is
 * exportable is the hand-kept map one register along. */
function Take({ sections, section, params }) {
  if (!sections || !sections.some((s) => s.section === section)) return null;
  const at = (format) => api.rateSectionUrl({ ...params, section, format });
  return (
    <span className="rowsub take-away">
      <a href={at("csv")} download>CSV</a>
      {" · "}
      <a href={at("xlsx")} download>Excel</a>
    </span>
  );
}

export default function RateComposition({ period = "2025" }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [kind, setKind] = useState("INDIRECT_COMBINED");
  const [open, setOpen] = useState(null);     // {pool, account}
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [more, setMore] = useState(false);
  const [sections, setSections] = useState(null);

  useEffect(() => {
    api.rateComposition(period).then(setD).catch((e) => setErr(explain(e)));
    /* A failure here loses the export links and nothing else, so it is
       swallowed deliberately rather than taking the pane down — `req()`
       has already put it on the failure panel underneath. */
    api.rateSections().then((r) => setSections(r.sections)).catch(() => {});
  }, [period]);

  /* The drawer reads the account rather than being handed it. Both lists that
     can open one carry different fields, and passing a partial row through
     printed a heading with nothing under it once already. */
  useEffect(() => {
    if (!open) { setDetail(null); return; }
    setLoading(true);
    api.rateAccount({ period, pool: open.pool, account: open.account })
      .then(setDetail)
      .catch((e) => { setErr(explain(e)); setDetail(null); })
      .finally(() => setLoading(false));
  }, [open, period]);

  /* Appends rather than replaces, which is `080`'s rule: the cursor and the
     reader's position are both places in this list. The largest account on
     this record carries 340 lines against a page of 200, and the route has
     taken `offset` since it was written — so saying "the workbook carries
     them all" and stopping was 140 transactions reachable only by
     downloading a file, in the one place somebody is checking a figure
     against a ledger. The queue could reach 80 of 757 groups the same way,
     for the same reason. */
  function fetchMore() {
    if (!open || !detail) return;
    setMore(true);
    api.rateAccount({ period, pool: open.pool, account: open.account,
                      offset: detail.lines.length })
      .then((next) => setDetail((cur) => ({
        ...cur, more: next.more, lines: [...cur.lines, ...next.lines] })))
      .catch((e) => setErr(explain(e)))
      .finally(() => setMore(false));
  }

  if (err && !d) {
    return (
      <Card style={{ marginTop: 16 }}>
        <Empty mark="!" title="Could not read the composition">{err}</Empty>
      </Card>
    );
  }
  if (!d) return null;

  const rates = d.rates || [];
  if (rates.length === 0) return null;
  const shown = rates.find((r) => r.kind === kind) || rates[0];
  const offered = KINDS.filter(([k]) => rates.some((r) => r.kind === k));
  /* What a per-rate export needs to be asked: the server refuses a section
     of one rate that does not name which, rather than exporting the first. */
  const kp = { period, kind: shown.kind };

  return (
    <>
      <Card variant="raised" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div className="card-title">Inside the rate</div>
          <span className="rowsub">
            What makes up the pool, what came out of it and what the base is —
            down to the transaction
          </span>
        </div>

        <Segmented options={offered} value={shown.kind} onChange={setKind} />


        {/* ---------------------------------------------------- the pool */}
        <div className="section-head" style={{ marginTop: 18 }}>
          <div className="section-h">
            The pool, as classified
            {shown.pools.length > 1 && (
              <span className="rowsub">
                {" — "}{shown.pools.join(" and ")}, which is what this rate is
                taken over
              </span>
            )}
          </div>
          <span className="head-aside">
            <Foots part={shown.gross} what="accounts" />
            <Take sections={sections} section="pool" params={kp} />
          </span>
        </div>
        {shown.gross.rows.length === 0 ? (
          <div className="quiet-note">
            Nothing is classified into {shown.pools.join(" or ")} yet, so there
            is no pool to break down.
          </div>
        ) : (
          <Table columns={[
            { label: "Account", align: "left" },
            ...(shown.pools.length > 1 ? [{ label: "Pool", align: "left" }] : []),
            { label: "Amount" }, { label: "Payees" }, { label: "Lines" },
            { label: "", align: "left", width: 90 },
          ]}>
            {shown.gross.rows.map((a) => (
              <tr key={`${a.pool}|${a.account}`} className="row-clickable"
                  onClick={() => setOpen({ pool: a.pool, account: a.account })}>
                <td className="l">{a.account}</td>
                {shown.pools.length > 1 && (
                  <td className="l"><Pill>{a.pool}</Pill></td>
                )}
                <td className="amt">{money(a.amount)}</td>
                <td className="amt">{count(a.payees)}</td>
                <td className="amt">{count(a.lines)}</td>
                <td className="l rowsub">transactions →</td>
              </tr>
            ))}
          </Table>
        )}

        {/* --------------------------------- what floor area actually drives */}
        {shown.driver_split && (
          <>
            <div className="section-head" style={{ marginTop: 22 }}>
              <div className="section-h">
                What floor area drives
                <span className="rowsub">
                  {" — "}the square-footage carve-out may only reach the cost
                  square footage causes
                </span>
              </div>
            </div>
            <Table columns={[{ label: "Part of the pool", align: "left" },
                             { label: "Amount" },
                             { label: "Why it matters", align: "left" }]}>
              <tr>
                <td className="l">Occupancy — floor area drives it</td>
                <td className="amt">{money(shown.driver_split.occupancy)}</td>
                <td className="l rowsub wrap">
                  The 200.465 carve-out is taken over this and not over the
                  whole pool.
                </td>
              </tr>
              <tr>
                <td className="l">Not driven by floor area</td>
                <td className="amt">{money(shown.driver_split.not_area_driven)}</td>
                <td className="l rowsub wrap">
                  T1 access, telephone, insurance and equipment. A tenant’s
                  floor area does not cause these, so no share of them leaves
                  the pool — which is the floor under the overhead rate.
                </td>
              </tr>
            </Table>
            {(d.overhead_drivers || []).length > 0 && (
              <details className="walk-detail" style={{ marginTop: 10 }}>
                <summary className="rowsub">
                  Which accounts are the exceptions, and why
                </summary>
                <Table columns={[{ label: "Account", align: "left" },
                                 { label: "Floor area drives it", align: "left" },
                                 { label: "Reason", align: "left" }]}>
                  {d.overhead_drivers.map((x, i) => (
                    <tr key={i}>
                      <td className="l mono">{x.account_fragment}</td>
                      <td className="l">{x.driven_by_area ? "yes" : "no"}</td>
                      <td className="l rowsub wrap">{x.reason}</td>
                    </tr>
                  ))}
                </Table>
                <div className="rowsub" style={{ marginTop: 8 }}>
                  The default is that floor area drives an account, so one
                  nobody has considered is carved — the conservative
                  direction. This list is a transcription somebody made of the
                  chart, not a rule derived from it.
                </div>
                <div className="take-row">
                  <Take sections={sections} section="drivers"
                        params={{ period }} />
                </div>
              </details>
            )}
          </>
        )}

        {/* ------------------------------------------------- the carve-outs */}
        <div className="section-head" style={{ marginTop: 22 }}>
          <div className="section-h">
            Carve-outs
            <span className="rowsub">
              {" — "}taken out of the pool before the rate was struck
            </span>
          </div>
          <span className="head-aside">
            <Foots part={shown.carved} what="carve-outs" />
            <Take sections={sections} section="carve-outs" params={kp} />
          </span>
        </div>
        {shown.carved.rows.length === 0 ? (
          <div className="quiet-note">
            Nothing has been taken out of this pool. Where a carve-out is
            required it is missing rather than zero, and the build-up above
            says which.
          </div>
        ) : (
          <Table columns={[{ label: "What", align: "left" },
                           { label: "Authority", align: "left" },
                           { label: "Amount" },
                           { label: "Driver", align: "left" },
                           { label: "Grade", align: "left" }]}>
            {shown.carved.rows.map((c, i) => (
              <tr key={i}>
                <td className="l">{c.name}</td>
                <td className="l rowsub">{c.citation}</td>
                <td className="amt">{money(c.amount)}</td>
                <td className="l rowsub wrap">{c.driver}</td>
                <td className="l"><Pill>{c.grade}</Pill></td>
              </tr>
            ))}
          </Table>
        )}

        {/* The two registers that size them. Neither is a figure this screen
            derives: 200.465 is sized by floor area and 200.436(b) by what
            bought the asset, and each carve-out row above names which. */}
        {shown.carved.rows.length > 0 && (d.estate || []).length > 0 && (
          <details className="walk-detail" style={{ marginTop: 10 }}>
            <summary className="rowsub">
              The estate the 200.465 share is measured on
            </summary>
            {/* Every use the view partitions by, not the five that happen
                to carry the carve-out. A building printed as 54,308 usable
                against 18,019 let and nothing else leaves a reader unable
                to see where the other 36,289 feet went — a partition short
                of its own whole. A blank is a use nobody has recorded any
                space under, which is not the same as nought feet. */}
            <Table columns={[{ label: "Building", align: "left" },
                             { label: "Usable" }, { label: "Let" },
                             { label: "Vacant" }, { label: "Committed" },
                             { label: "Programme" }, { label: "Admin" },
                             { label: "Shared lab" }, { label: "Common" },
                             { label: "Share let" }]}>
              {d.estate.map((f, i) => (
                <tr key={i}>
                  <td className="l">{f.name}</td>
                  <td className="amt">{count(f.usable_sqft)}</td>
                  <td className="amt">{count(f.tenant_sqft)}</td>
                  <td className="amt">{count(f.vacant_sqft)}</td>
                  <td className="amt">{count(f.committed_sqft)}</td>
                  <td className="amt">{count(f.program_sqft)}</td>
                  <td className="amt">{count(f.admin_sqft)}</td>
                  <td className="amt">{count(f.shared_lab_sqft)}</td>
                  <td className="amt">{count(f.common)}</td>
                  <td className="amt">
                    {(Number(f.rental_share || 0) * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </Table>
            <div className="rowsub" style={{ marginTop: 8 }}>
              Square feet, not dollars. A building’s let, vacant and committed
              space carves its share of the occupancy in the pool, weighted by
              what the building is of the whole estate.
            </div>
            <div className="take-row">
              <Take sections={sections} section="estate" params={{ period }} />
            </div>
          </details>
        )}
        {(d.federally_funded_assets || []).length > 0 && (
          <details className="walk-detail" style={{ marginTop: 10 }}>
            <summary className="rowsub">
              The assets federal money bought, which 200.436(b) is measured on
            </summary>
            <Table columns={[{ label: "Asset", align: "left" },
                             { label: "Account", align: "left" },
                             { label: "Cost" }, { label: "Depreciation" },
                             { label: "Federal" }, { label: "Federal share" },
                             { label: "Allowable" }]}>
              {d.federally_funded_assets.map((a, i) => (
                <tr key={i}>
                  <td className="l">{a.description}</td>
                  <td className="l rowsub">{a.gl_account}</td>
                  <td className="amt">{money(a.gross_cost)}</td>
                  <td className="amt">{money(a.depreciation)}</td>
                  <td className="amt">{money(a.federal_funding)}</td>
                  <td className="amt">
                    {(Number(a.federal_share || 0) * 100).toFixed(1)}%
                  </td>
                  <td className="amt">{money(a.allowable_depreciation)}</td>
                </tr>
              ))}
            </Table>
            <div className="take-row">
              <Take sections={sections} section="assets" params={{ period }} />
            </div>
          </details>
        )}

        {/* ------------------------------------------ administrative labour */}
        {shown.admin_labour && (
          <>
            <div className="section-head" style={{ marginTop: 22 }}>
              <div className="section-h">
                Administrative labour in the pool
                <span className="rowsub">
                  {" — "}{shown.admin_labour.objective}, under the{" "}
                  {shown.admin_labour.basis} basis
                </span>
              </div>
              <span className="head-aside">
              <span className="rowsub">
                wages <span className="num">{money(shown.admin_labour.wages)}</span>
                {" + fringe "}
                <span className="num">{money(shown.admin_labour.fringe_on_it)}</span>
                {" = "}
                <span className="num">{money(shown.admin_labour.recorded)}</span>
              </span>
              <Take sections={sections} section="admin-labour" params={kp} />
              </span>
            </div>
            <Table columns={[{ label: "Person", align: "left" },
                             { label: "Wages" },
                             { label: "From", align: "left" },
                             { label: "Grade", align: "left" }]}>
              {shown.admin_labour.rows.map((p, i) => (
                <tr key={i}>
                  <td className="l">{p.employee_name || p.employee_key}</td>
                  <td className="amt">{money(p.distributed_wages)}</td>
                  <td className="l rowsub">{p.source}</td>
                  <td className="l"><Pill>{p.grade}</Pill></td>
                </tr>
              ))}
            </Table>
            <div className="rowsub" style={{ marginTop: 8 }}>
              This comes from the effort distribution rather than from a
              classification, which is why it is not in the accounts above.
              The fringe on it is this rate’s own, applied in the computation.
            </div>
          </>
        )}

        {/* ---------------------------------------------------- the base */}
        <div className="section-head" style={{ marginTop: 22 }}>
          <div className="section-h">
            The base — {BASE[shown.base_type] || shown.base_type}
            <span className="rowsub">
              {" — "}what the pool is spread over, as the allocation recorded
              it
            </span>
          </div>
          <span className="head-aside">
            <Foots part={shown.base}
                   what={shown.base.by === "PERSON" ? "people" : "objectives"} />
            <Take sections={sections} section="base" params={kp} />
          </span>
        </div>
        {/* A wage base is one row per person and an MTDC base one row per
            objective. The unit is not cosmetic: the fringe denominator *is*
            the payroll register, which is the eleventh control's whole
            point, and printing it under objective headings would say the
            rate was taken over the ledger's wage accounts instead. */}
        {shown.base.rows.length === 0 ? (
          /* "Not yet, because", never an empty state that says nothing. */
          <div className="quiet-note">
            {shown.base.needs
              || "This rate carries no allocation, so there is no base to break down."}
          </div>
        ) : shown.base.by === "PERSON" ? (
          <Table columns={[{ label: "Person", align: "left" },
                           { label: "Wages in the base" },
                           { label: "Objectives" },
                           { label: "From", align: "left" },
                           { label: "Grade", align: "left" }]}>
            {shown.base.rows.map((e) => (
              <tr key={e.employee_key}>
                <td className="l">
                  {e.employee_name || e.employee_key}
                  <span className="rowsub">{" "}{e.employee_key}</span>
                </td>
                <td className="amt">{money(e.base_amount)}</td>
                <td className="num">{count(e.objectives)}</td>
                <td className="l rowsub">{e.source}</td>
                <td className="l rowsub wrap">{e.grade}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <Table columns={[{ label: "Cost objective", align: "left" },
                           { label: "Kind", align: "left" },
                           { label: "Federal", align: "left" },
                           { label: "Base" }, { label: "Indirect allocated" }]}>
            {shown.base.rows.map((o) => (
              <tr key={o.objective_id}>
                <td className="l">
                  {o.label || o.objective_id}
                  <span className="rowsub">{" "}{o.objective_id}</span>
                </td>
                <td className="l rowsub">{o.objective_type}</td>
                <td className="l">{o.is_federal ? "yes" : "no"}</td>
                <td className="amt">{money(o.base_amount)}</td>
                <td className="amt">{money(o.allocated)}</td>
              </tr>
            ))}
          </Table>
        )}

        {/* All of it, across every pool a rate is taken over. Not a section
            of one rate, which is why it sits under the card rather than
            beside a heading: it is what goes across the table. */}
        <div className="take-row rowsub" style={{ marginTop: 20 }}>
          Every transaction in every pool, in one file:{" "}
          <Take sections={sections} section="transactions"
                params={{ period }} />
        </div>
      </Card>

      {/* -------------------------------------------------- one account */}
      <Drawer open={!!open} wide
              title={open ? open.account : ""}
              subtitle={open
                ? `${open.pool} · who was paid, and every transaction`
                : ""}
              onClose={() => setOpen(null)}>
        {loading && <div className="rowsub">Reading the lines…</div>}
        {detail && (() => {
          const ap = { period, pool: open.pool, account: open.account };
          return (
          <>
            <div className="stat-row">
              <div className="stat">
                <div className="stat-label">In the pool</div>
                <div className="stat-value num">{money(detail.amount)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Transactions</div>
                <div className="stat-value num">{count(detail.lines_total)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Payees</div>
                <div className="stat-value num">{count(detail.payees.length)}</div>
              </div>
            </div>

            <div className="section-head" style={{ marginTop: 16 }}>
              <div className="section-h">Where it went</div>
              <span className="head-aside">
                <span className="rowsub">
                  every payee in this account, largest first
                </span>
                <Take sections={sections} section="payees" params={ap} />
              </span>
            </div>
            <Table columns={[{ label: "Payee", align: "left" },
                             { label: "Amount" }, { label: "Lines" }]}>
              {detail.payees.map((p, i) => (
                <tr key={i}>
                  <td className="l">{p.payee || <span className="rowsub">no payee on the line</span>}</td>
                  <td className="amt">{money(p.amount)}</td>
                  <td className="amt">{count(p.lines)}</td>
                </tr>
              ))}
            </Table>

            <div className="section-head" style={{ marginTop: 18 }}>
              <div className="section-h">Every transaction</div>
              <span className="head-aside">
                <span className="rowsub">
                  {detail.more
                    ? `${count(detail.lines.length)} of ${count(detail.lines_total)}`
                    : `all ${count(detail.lines_total)}`}
                </span>
                {/* The file carries every line, not the page on the screen:
                    a breakdown that stopped at 200 rows would not add back
                    to its own account. */}
                <Take sections={sections} section="account" params={ap} />
              </span>
            </div>
            <Table columns={[{ label: "Date", align: "left" },
                             { label: "Payee", align: "left" },
                             { label: "Description", align: "left" },
                             { label: "Amount" },
                             { label: "990 function", align: "left" },
                             { label: "Federal", align: "left" }]}>
              {detail.lines.map((l) => (
                <tr key={l.line_id}>
                  <td className="l">{l.date}</td>
                  <td className="l">{l.payee}</td>
                  <td className="l rowsub wrap">{l.description}</td>
                  <td className="amt">{money(l.amount)}</td>
                  {/* The short form. `MANAGEMENT_AND_GENERAL` is 22
                      characters and pushed the federal treatment off the
                      right edge of the drawer — and whether a cost is
                      ALLOWABLE is the thing a sponsor asks about, so
                      clipping that to print an enum in full was the wrong
                      trade twice over. */}
                  <td className="l rowsub">{fn990(l.function_990, true)}</td>
                  <td className="l rowsub">{l.federal}</td>
                </tr>
              ))}
            </Table>
            {detail.more && (
              <div style={{ marginTop: 10 }}>
                <button className="btn sm" onClick={fetchMore} disabled={more}>
                  {more ? "Reading…"
                        : `Show ${count(Math.min(200, detail.lines_total - detail.lines.length))} more`}
                </button>
                <span className="rowsub">
                  {" "}{count(detail.lines_total - detail.lines.length)} still
                  to show
                </span>
              </div>
            )}
            {/* Why these lines are in this pool at all. A transaction says
                what was spent; a sponsor asks why it is here, and the answer
                is on the judgment that put it there. */}
            {detail.lines.length > 0 && (
              <details className="walk-detail" style={{ marginTop: 12 }}>
                <summary className="rowsub">
                  The judgment these sit under
                </summary>
                {(() => {
                  const seen = new Map();
                  detail.lines.forEach((l) => {
                    const k = `${l.citation}|${l.rationale}|${l.grade}|${l.objective_id || ""}`;
                    if (!seen.has(k)) seen.set(k, { ...l, n: 0 });
                    seen.get(k).n += 1;
                  });
                  return (
                    <Table columns={[{ label: "Citation", align: "left" },
                                     { label: "Rationale", align: "left" },
                                     { label: "Objective", align: "left" },
                                     { label: "Grade", align: "left" },
                                     { label: "Lines" }]}>
                      {[...seen.values()].map((j, i) => (
                        <tr key={i}>
                          <td className="l">{j.citation}</td>
                          <td className="l rowsub wrap">{j.rationale}</td>
                          <td className="l rowsub">{j.objective_id || "—"}</td>
                          <td className="l"><Pill>{j.grade}</Pill></td>
                          <td className="amt">{count(j.n)}</td>
                        </tr>
                      ))}
                    </Table>
                  );
                })()}
              </details>
            )}
          </>
          );
        })()}
      </Drawer>
    </>
  );
}
