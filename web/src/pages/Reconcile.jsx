import React, { useCallback, useEffect, useState } from "react";
import { api, explain, money } from "../api.js";
import { Card, Drawer, Empty, Field, PageHead, Pill, Segmented, Stat, Table, Tick,
         useToast } from "../components/ui.jsx";

/* Schedule A-1 — the three source documents against each other.
 *
 * This page comes before classification on purpose. The question a reviewer
 * asks first is not whether the rate is right, it is whether the numbers
 * under it are the numbers in the books. The answer has to exist before
 * anybody has an interest in what it says.
 *
 * A control that does not tie is not hidden and is not red-flagged into
 * panic. It is shown with the difference, the accounts on either side, and
 * — where the system can find them — the specific ledger lines that would
 * account for it. Naming the difference is the work. */

const KIND_LABEL = {
  RECLASS_AFTER_EXPORT: "Reclassified after the export",
  TIMING: "Timing",
  PRESENTATION: "Presentation",
  ROUNDING: "Rounding",
  SOURCE_DEFECT: "Defect in the source",
};

export default function Reconcile({ actor }) {
  const [reg, setReg] = useState(null);
  const [view, setView] = useState("controls");
  const [gpl, setGpl] = useState([]);
  const [gbs, setGbs] = useState([]);
  const [items, setItems] = useState([]);
  const [aliases, setAliases] = useState([]);
  const [props, setProps] = useState(null);
  const [pay, setPay] = useState(null);
  // What is being named: a candidate ledger line, or "rounding" for the
  // residual nothing can be attributed to. null is the drawer shut.
  const [naming, setNaming] = useState(null);
  const [form, setForm] = useState({ to_account: "", kind: "SOURCE_DEFECT",
                                     explanation: "" });
  const [refusal, setRefusal] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const canWrite = actor?.role === "CONTROLLER" || actor?.role === "ADMIN";

  const load = useCallback(() => {
    api.reconcile().then(setReg).catch(() => {});
    api.reconcileGlPl().then(setGpl).catch(() => setGpl([]));
    api.reconcileGlBs().then(setGbs).catch(() => setGbs([]));
    api.reconcileItems().then(setItems).catch(() => setItems([]));
    api.reconcileAliases().then(setAliases).catch(() => setAliases([]));
    api.reconcilePayroll().then(setPay).catch(() => setPay(null));
  }, []);

  useEffect(() => { load(); }, [load]);

  const propose = async () => {
    setBusy(true);
    try {
      setProps(await api.reconcilePropose());
      setView("propose");
    } catch (e) {
      toast.show(explain(e), { tone: "fail" });
    } finally { setBusy(false); }
  };

  const record = async (p) => {
    try {
      await api.addReconcilingItem({
        control: "GL_PL_ACCOUNT",
        from_account: p.from_account,
        to_account: p.to_account,
        amount: p.amount,
        kind: "RECLASS_AFTER_EXPORT",
        explanation:
          `${p.lines.length} line${p.lines.length === 1 ? "" : "s"} sitting in ` +
          `${p.from_account} in the general ledger and in ${p.to_account} on the ` +
          `profit and loss. The two exports are two moments in the same books. ` +
          `No effect on the section total or on net income.`,
        line_ids: p.lines.map((l) => l.line_id),
      });
      toast.show(`Recorded ${money(p.amount)} as a reconciling item`);
      setProps({ ...props, proposals: props.proposals.filter((x) => x !== p) });
      load();
    } catch (e) {
      toast.show(explain(e), { tone: "fail" });
    }
  };

  /* The eleventh control. Unlike the profit-and-loss differences this one
     cannot be derived: no amount of arithmetic says a credit in an intern
     wage account is a donor's pledge rather than a payroll correction. So
     the screen finds the candidates — the route already does — and the
     wording is the controller's. `/propose` is deliberately not extended to
     it, because a proposal here would be the machine writing the judgment. */
  const openNaming = (what) => {
    setRefusal("");
    setForm({ to_account: what === "rounding" ? "the payroll register" : "",
              kind: what === "rounding" ? "ROUNDING" : "SOURCE_DEFECT",
              explanation: "" });
    setNaming(what);
  };

  const nameIt = async () => {
    const rounding = naming === "rounding";
    setBusy(true);
    setRefusal("");
    try {
      await api.addReconcilingItem({
        control: "PAYROLL_REGISTER",
        from_account: rounding ? "the ledger's wage accounts" : naming.account,
        to_account: form.to_account,
        amount: String(rounding ? -Number(pay.reconciliation.unexplained)
                                : naming.amount),
        kind: form.kind,
        explanation: form.explanation,
        line_ids: rounding ? [] : [naming.line_id],
      });
      toast.show(`Named ${money(rounding ? -Number(pay.reconciliation.unexplained)
                                         : naming.amount)}`);
      setNaming(null);
      load();
    } catch (e) {
      // A refusal fades out of a toast while somebody is still reading the
      // form, so it prints where it happened as well.
      setRefusal(explain(e));
      toast.show(explain(e), { tone: "fail" });
    } finally { setBusy(false); }
  };

  if (!reg) return <div className="page"><Empty mark="—" title="Reading the register" /></div>;

  const open = reg.controls.filter((c) => !c.ties);

  return (
    <div className="page">
      <PageHead title="Reconciliation" schedule="A-1">
        Eleven points at which the general ledger, the profit and loss, the balance
          sheet and the payroll register are required to agree. Run before anything is
          classified, because a reconciliation produced after the rate is one nobody
          can believe.
      </PageHead>

      <div className="grid three">
        <Stat label="Cross-reference points" value={reg.controls.length} size="lg" />
        <Stat label="Tying" value={reg.controls.length - open.length}
              tone={open.length ? "" : "good"} size="lg" />
        <Stat label="Open" value={reg.controls.filter((c) => c.state === "OPEN").length}
              tone={open.length ? "warn" : ""} size="lg"
              note={(reg.no_data || []).length
                ? `${reg.no_data.length} more waiting on a document`
                : open.length ? "a difference to name" : "Everything ties"} />
        <Stat label="Named reconciling items" value={items.length}
              note={items.length ? money(items.reduce((s, i) => s + Math.abs(Number(i.amount)), 0)) : "none"} />
      </div>

      <Segmented
        value={view}
        onChange={setView}
        options={[
          ["controls", "Controls"],
          ["gl-pl", `Ledger vs P&L (${gpl.length})`],
          ["gl-bs", `Ledger vs balance sheet (${gbs.length})`],
          ["items", `Reconciling items (${items.length})`],
          ...(pay ? [["payroll", "Payroll register"]] : []),
          ...(props ? [["propose", "Proposals"]] : []),
        ]}
      />

      {view === "controls" && (
        <Card variant="raised" title="The register">
          <Table columns={[
            { label: "", align: "left", width: "34px" },
            { label: "What it proves", align: "left" },
            { label: "Ledger side" },
            { label: "Statement side" },
            { label: "Left over" },
          ]}>
            {reg.controls.map((c) => (
              <React.Fragment key={c.control}>
                <tr>
                  <td>
                    <Tick state={c.state === "TIES" ? "done"
                                 : c.state === "NO DATA" ? "open" : "flagged"}
                          title={c.state === "NO DATA"
                            ? "nothing to compare yet"
                            : c.state === "TIES" ? "ties" : "open"} />
                  </td>
                  <td className="l wrap">
                    <strong>{c.description}</strong>
                    <div className="rowsub">{c.control}</div>
                  </td>
                  <td className="amt">
                    <div className="rowsub">{c.left_label}</div>
                    <strong>{money(c.left_value)}</strong>
                  </td>
                  <td className="amt">
                    <div className="rowsub">{c.right_label}</div>
                    <strong>{money(c.right_value)}</strong>
                  </td>
                  <td className={"amt strong" + (c.ties ? "" : " neg")}>
                    {c.state === "NO DATA"
                      ? <span className="rowsub">no data</span>
                      : c.basis === "VARIANCE"
                        ? money(c.variance)
                        : `${c.exceptions} exception${Number(c.exceptions) === 1 ? "" : "s"}`}
                  </td>
                </tr>
                <tr className="subrow">
                  <td />
                  <td className="l rowsub wrap" colSpan={4}>{c.note}</td>
                </tr>
              </React.Fragment>
            ))}
          </Table>
        </Card>
      )}

      {view === "gl-pl" && (
        <Card title="Where the ledger and the profit and loss disagree, account by account">
          {gpl.length === 0 ? (
            <Empty mark="✓" title="Every account agrees">
              The ledger sums to what the profit and loss prints, account by account.
            </Empty>
          ) : (
            <>
              <p className="rowsub">
                Sections can tie while accounts do not: money moved between two expense
                accounts nets to nothing at the section line. Each row is either named as
                a reconciling item or it is unexplained.
              </p>
              {canWrite && (
                <button className="btn" onClick={propose} disabled={busy}>
                  {busy ? "Searching…" : "Find the lines behind these"}
                </button>
              )}
              <Table columns={[
                { label: "Account", align: "left" },
                "Section", { label: "Ledger" }, { label: "P&L" },
                { label: "Difference" }, { label: "Named" }, { label: "Unexplained" },
              ]}>
                {gpl.map((r) => (
                  <tr key={r.account}>
                    <td className="l">{r.account}</td>
                    <td className="l">{r.section || "—"}</td>
                    <td className="amt">{money(r.gl_amount)}</td>
                    <td className="amt">{money(r.pl_amount)}</td>
                    <td className="amt">{money(r.gross_variance)}</td>
                    <td className="amt">{money(r.reconciling)}</td>
                    <td className={"amt" + (Number(r.unexplained) ? " neg" : "")}>
                      {money(r.unexplained)}
                    </td>
                  </tr>
                ))}
              </Table>
            </>
          )}
        </Card>
      )}

      {view === "gl-bs" && (
        <Card title="Opening balance plus the year's movement, against the sheet">
          <p className="rowsub">
            A balance sheet states a position and a ledger states a year of movement, so
            the two are comparable only through the balance carried in. Only accounts that
            differ, or that the sheet does not print, are listed — an account the sheet
            omits has to close at zero here.
          </p>
          {gbs.length === 0 ? (
            <Empty mark="✓" title="Every account on the sheet is proved off the ledger" />
          ) : (
            <Table columns={[
              { label: "Ledger account", align: "left" },
              { label: "Opening" }, { label: "Movement" }, { label: "Closing" },
              { label: "Balance sheet" }, { label: "Variance" },
              { label: "", align: "left" },
            ]}>
              {gbs.map((r) => (
                <tr key={r.account}>
                  <td className="l">{r.account}</td>
                  <td className="amt">{money(r.opening)}</td>
                  <td className="amt">{money(r.activity)}</td>
                  <td className="amt">{money(r.closing)}</td>
                  <td className="amt">{r.on_balance_sheet ? money(r.bs_amount) : "not printed"}</td>
                  <td className={"amt" + (Number(r.variance) ? " neg" : "")}>{money(r.variance)}</td>
                  <td className="l">
                    {r.absent_because_zero
                      ? <Pill>closed at zero</Pill>
                      : r.matched_by_alias ? <Pill tone="accent">matched by alias</Pill> : null}
                  </td>
                </tr>
              ))}
            </Table>
          )}
          {aliases.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <h4>Accounts the two documents call by different names</h4>
              <Table columns={[
                { label: "General ledger", align: "left" },
                { label: "Statement", align: "left" },
                { label: "Reason", align: "left" },
              ]}>
                {aliases.map((a) => (
                  <tr key={a.gl_account}>
                    <td className="l">{a.gl_account}</td>
                    <td className="l">{a.statement_account}</td>
                    <td className="l rowsub">{a.reason}</td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
      )}

      {view === "items" && (
        <Card title="Named differences">
          {items.length === 0 ? (
            <Empty mark="—" title="Nothing named yet">
              A difference carried on the face of the reconciliation, with the ledger
              lines behind it, is a finding. One with nothing behind it is a plug, and
              the database refuses those.
            </Empty>
          ) : (
            <Table columns={[
              { label: "Ledger puts it in", align: "left" },
              { label: "The statement puts it in", align: "left" },
              { label: "Amount" }, { label: "Lines" },
              { label: "Kind", align: "left" },
              { label: "Recorded by", align: "left" },
            ]}>
              {items.map((i) => (
                <React.Fragment key={i.item_id}>
                  <tr>
                    <td className="l">{i.from_account}</td>
                    <td className="l">{i.to_account}</td>
                    <td className="amt">{money(i.amount)}</td>
                    <td className="amt">{i.lines}</td>
                    <td className="l"><Pill>{KIND_LABEL[i.kind] || i.kind}</Pill></td>
                    <td className="l">{i.recorded_by}</td>
                  </tr>
                  <tr className="subrow">
                    <td className="l rowsub" colSpan={6}>{i.explanation}</td>
                  </tr>
                </React.Fragment>
              ))}
            </Table>
          )}
        </Card>
      )}

      {view === "propose" && props && (
        <Card variant="raised" title="What the lines say">
          <p className="rowsub">
            Proposed, not recorded. Where exactly one set of ledger lines adds to the
            difference, that set is shown. Where more than one set would, nothing is
            proposed — an attribution that could equally have been a different set of
            lines is not evidence.
          </p>
          {props.proposals.length === 0 && <Empty mark="✓" title="Nothing left to name" />}
          {props.proposals.map((p, i) => (
            <div className="card quiet" key={i} style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
                <div>
                  <div className="rowsub">Ledger</div>
                  <strong>{p.from_account}</strong>
                  <div className="rowsub" style={{ marginTop: 6 }}>Profit and loss</div>
                  <strong>{p.to_account}</strong>
                </div>
                <div className="amt strong" style={{ fontSize: 24 }}>{money(p.amount)}</div>
              </div>
              {p.proposed ? (
                <>
                  <Table columns={[
                    { label: "Date", align: "left" }, { label: "Payee", align: "left" },
                    { label: "Amount" }, { label: "Memo", align: "left" },
                  ]}>
                    {p.lines.map((l) => (
                      <tr key={l.line_id}>
                        <td className="l">{l.date}</td>
                        <td className="l">{l.payee}</td>
                        <td className="amt">{money(l.amount)}</td>
                        <td className="l rowsub">{l.memo}</td>
                      </tr>
                    ))}
                  </Table>
                  {canWrite && (
                    <button className="btn primary" onClick={() => record(p)}>
                      Record {p.lines.length === 1 ? "this line" : `these ${p.lines.length} lines`} as a reconciling item
                    </button>
                  )}
                </>
              ) : (
                <p className="rowsub">{p.why_not}</p>
              )}
            </div>
          ))}
        </Card>
      )}

      {view === "payroll" && pay && (() => {
        const r = pay.reconciliation;
        const left = Number(r.unexplained);
        return (
          <Card variant="raised" title="The payroll register against the ledger">
            <div className="stat-row">
              <Stat label="Payroll register" value={money(r.register_wages)}
                    note={`${r.people} people — the fringe base`} />
              <Stat label="The ledger's wage accounts" value={money(r.ledger_wages)}
                    note={`${r.ledger_lines} lines`} />
              <Stat label="Difference" value={money(r.gross_difference)}
                    note="named by attributing it, never by netting it" />
              <Stat label="Named" value={money(r.named)}
                    note={`${r.named_items} item${Number(r.named_items) === 1 ? "" : "s"}`} />
              <Stat label="Unexplained" value={money(left)} size="lg"
                    tone={left ? "warn" : "pass"}
                    note={left ? "a rate is refused while this stands" : "nothing left"} />
            </div>
            <p className="rowsub">
              The fringe base comes from the effort distribution, not from the ledger's
              wage accounts, so a difference between them is two denominators for one
              rate. Nothing here is proposed: which of these lines is not payroll is a
              judgment, and the wording recorded against it is yours.
            </p>

            {left === 0 ? (
              <Empty mark="✓" title="Nothing left to name">
                The register and the ledger's wage accounts are reconciled.
              </Empty>
            ) : (
              <>
                <Table columns={[
                  { label: "Date", align: "left" },
                  { label: "Account", align: "left" },
                  { label: "Payee", align: "left" },
                  { label: "Amount" }, { label: "", align: "left" },
                ]}>
                  {pay.unlike_payroll.map((l) => (
                    <React.Fragment key={l.line_id}>
                      <tr>
                        <td className="l">{l.txn_date}</td>
                        <td className="l">{(l.account || "").split(":").pop()}</td>
                        <td className="l">{l.payee || "—"}</td>
                        <td className="amt">{money(l.amount)}</td>
                        <td className="l">
                          {canWrite && (
                            <button className="btn" onClick={() => openNaming(l)}>
                              Name this
                            </button>
                          )}
                        </td>
                      </tr>
                      {l.description && (
                        <tr className="subrow">
                          <td className="l rowsub" colSpan={5}>{l.description}</td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </Table>
                <p className="rowsub">{pay.note}</p>
                {canWrite && Math.abs(left) <= 1000 && (
                  <button className="btn" onClick={() => openNaming("rounding")}>
                    Record the remaining {money(left)} as unattributable
                  </button>
                )}
              </>
            )}
          </Card>
        );
      })()}

      <Drawer
        open={!!naming}
        title={naming === "rounding" ? "A residual nobody can attribute"
                                     : "Name this difference"}
        subtitle={naming && naming !== "rounding"
          ? `${money(naming.amount)} — ${naming.payee || "no payee"}`
          : naming ? money(-Number(pay?.reconciliation?.unexplained || 0)) : ""}
        onClose={() => setNaming(null)}
        footer={
          <>
            <button className="btn" onClick={() => setNaming(null)}>Cancel</button>
            <button className="btn primary" disabled={busy} onClick={nameIt}>
              {busy ? "Recording…" : "Record it"}
            </button>
          </>
        }>
        {naming === "rounding" ? (
          <p className="rowsub">
            A rounding item is the one relaxation: it may carry no ledger lines, and
            in exchange it has to say in sixty characters or more why attribution is
            impossible, and may not exceed a thousand dollars. Both fences are in the
            database. The alternative to writing an unattributable residual down is a
            tolerance that quietly swallows it.
          </p>
        ) : (
          <>
            <Field label="Where the statement puts it" required
                   hint="The account this belongs in — 4000 Contributions Income, say.">
              <input value={form.to_account}
                     onChange={(e) => setForm({ ...form, to_account: e.target.value })} />
            </Field>
            <Field label="What kind of difference" required>
              <select value={form.kind}
                      onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {Object.entries(KIND_LABEL)
                  .filter(([k]) => k !== "ROUNDING")
                  .map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </Field>
          </>
        )}
        <Field label="Why" required
               hint={naming === "rounding"
                 ? "Sixty characters or more, saying why no line can be named."
                 : "What this line actually is, and what it does to the figures."}>
          <textarea rows={7} value={form.explanation}
                    onChange={(e) => setForm({ ...form, explanation: e.target.value })} />
        </Field>
        <p className="rowsub">
          {form.explanation.length} characters — {naming === "rounding" ? 60 : 30} needed.
        </p>
        {refusal && <p className="refusal">{refusal}</p>}
      </Drawer>
    </div>
  );
}
