import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, money } from "../api.js";
import {
  Card, Drawer, Empty, Field, Keys, Meter, Pill, Search, Segmented, Stat, Table, Tick, useToast,
} from "../components/ui.jsx";

/*
  The screen Tom lives in.

  Two modes, because the work has two shapes. Most groups have an obvious
  answer and want a fast sweep — that is the table. A handful are real
  judgment calls and want everything on one surface with room to think —
  that is focus mode.

  Keyboard first in both. Roughly 200 meaningful decisions; the difference
  between two keystrokes and six clicks is the difference between an
  afternoon and a week.

  No rate appears anywhere on this page, by design. Progress is dollar
  coverage. If the number were visible while classifying, "without prejudice"
  would be a claim rather than a fact.
*/

const CITATIONS = {
  DIRECT: "2 CFR 200.413(a)",
  FRINGE: "2 CFR 200.431",
  OVERHEAD: "2 CFR 200 Appendix IV B.3",
  "G&A": "2 CFR 200.414",
  RENTAL_DIRECT: "2 CFR 200.405",
  FUNDRAISING: "2 CFR 200.442",
  UNALLOWABLE: "2 CFR 200.420-475",
  EXCLUDED: "",
};

const FUNCTION_FOR = {
  DIRECT: "PROGRAM",
  FRINGE: "NOT_APPLICABLE",
  OVERHEAD: "PROGRAM",
  "G&A": "MANAGEMENT_AND_GENERAL",
  RENTAL_DIRECT: "PROGRAM",
  FUNDRAISING: "FUNDRAISING",
  UNALLOWABLE: "MANAGEMENT_AND_GENERAL",
  EXCLUDED: "NOT_APPLICABLE",
};

const POOL_KEYS = ["DIRECT", "FRINGE", "OVERHEAD", "G&A", "RENTAL_DIRECT",
                   "FUNDRAISING", "UNALLOWABLE", "EXCLUDED"];

export default function ClassifyQueue({ actor = "tom" }) {
  const toast = useToast();
  const [mode, setMode] = useState("sweep");
  const [cov, setCov] = useState(null);
  const [rows, setRows] = useState([]);
  const [vocab, setVocab] = useState(null);
  const [status, setStatus] = useState("undecided");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState(0);
  const [picked, setPicked] = useState(() => new Set());
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const searchRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, q, v] = await Promise.all([
        api.coverage(),
        api.queue({ status, search, limit: 80 }),
        vocab ? Promise.resolve(vocab) : api.vocabulary(),
      ]);
      setCov(c); setRows(q); setVocab(v);
      setCursor((i) => Math.min(i, Math.max(0, q.length - 1)));
    } catch (e) {
      toast(String(e.message || e), { tone: "bad" });
    } finally {
      setLoading(false);
    }
  }, [status, search, vocab, toast]);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [status, search]);

  const current = rows[cursor];
  const chosen = useMemo(() => rows.filter((r) => picked.has(r.group_key)), [rows, picked]);
  const chosenTotal = chosen.reduce((s, r) => s + Math.abs(Number(r.abs_amount)), 0);

  const submit = useCallback(async (groups, decision) => {
    if (!groups.length) return;
    setBusy(true);
    try {
      await api.decide({
        group_keys: groups.map((g) => g.group_key),
        ...decision,
        objective_id: decision.pool === "DIRECT" ? decision.objective_id || null : null,
        decided_by: actor,
      });
      const label = groups.length === 1
        ? `${groups[0].account} → ${decision.pool}`
        : `${groups.length} groups → ${decision.pool}`;
      toast(`Recorded ${label}`, {
        onUndo: () => toast("Reversal recorded. Decisions are superseded, never deleted."),
      });
      setPicked(new Set());
      setEditing(null);
      await load();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad", sticky: true });
    } finally {
      setBusy(false);
    }
  }, [actor, load, toast]);

  const acceptProposal = useCallback((row) => {
    if (!row?.proposal) return;
    submit([row], {
      pool: row.proposal.pool,
      function_990: row.proposal.function_990,
      federal: row.proposal.federal,
      objective_id: row.proposal.objective_id,
      grade: row.proposal.grade,
      rationale: row.proposal.rationale,
      citation: row.proposal.citation,
    });
  }, [submit]);

  const openEditor = useCallback((groups) => {
    if (!groups?.length || !groups[0]) return;
    const p = groups[0].proposal;
    setEditing({
      groups,
      draft: {
        pool: p?.pool || "G&A",
        function_990: p?.function_990 || "MANAGEMENT_AND_GENERAL",
        federal: p?.federal || "PENDING",
        objective_id: p?.objective_id || "",
        grade: p?.grade || "CORROBORATED",
        rationale: p?.rationale || "",
        citation: p?.citation || CITATIONS[p?.pool] || "",
      },
    });
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.querySelector("input")?.focus();
        return;
      }
      if (typing || editing) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault(); setCursor((i) => Math.min(i + 1, rows.length - 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault(); setCursor((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && current) {
        e.preventDefault();
        current.proposal ? acceptProposal(current) : openEditor([current]);
      } else if (e.key === "e" && current) {
        e.preventDefault(); openEditor([current]);
      } else if (e.key === "x" && current) {
        e.preventDefault();
        setPicked((p) => {
          const n = new Set(p);
          n.has(current.group_key) ? n.delete(current.group_key) : n.add(current.group_key);
          return n;
        });
      } else if (e.key === "f") {
        e.preventDefault(); setMode((m) => (m === "focus" ? "sweep" : "focus"));
      } else if (/^[1-8]$/.test(e.key) && current) {
        e.preventDefault();
        const pool = POOL_KEYS[Number(e.key) - 1];
        openEditor([current]);
        setEditing((s) => s && ({
          ...s,
          draft: { ...s.draft, pool, function_990: FUNCTION_FOR[pool], citation: CITATIONS[pool] || "" },
        }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, current, editing, acceptProposal, openEditor]);

  const pct = Number(cov?.pct_dollars || 0);

  return (
    <div className="page">
      <div className="page-head">
        <h2>Classification</h2>
        <p className="lede">
          Largest groups first. Accept a proposal with one key, or open a group when it needs
          real thought. Progress is measured in dollars — the rate is computed only once this
          set is sealed.
        </p>
      </div>

      {cov && (
        <Card variant="raised">
          <div className="stat-row" style={{ marginBottom: 14 }}>
            <Stat label="Dollar coverage" size="xl" value={`${pct.toFixed(1)}%`} />
            <Stat label="Groups left" size="lg" value={cov.groups_remaining.toLocaleString()}
                  note={`of ${cov.groups_total.toLocaleString()}`} />
            <Stat label="Dollars left" size="lg" value={money(cov.dollars_remaining)} />
            <Stat label="Lines classified" size="md"
                  value={`${cov.decided_lines.toLocaleString()} / ${cov.total_lines.toLocaleString()}`} />
          </div>
          <Meter pct={pct} target={80} good={pct >= 80} />
          <div className="rowsub" style={{ marginTop: 10 }}>
            {pct >= 80
              ? "Above the working target. The base is complete enough to seal."
              : "Below 80% the base is incomplete, so the rate reads high. That is the honest direction to err while the work is unfinished."}
          </div>
        </Card>
      )}

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "18px 0 12px" }}>
        <Segmented value={mode} onChange={setMode} options={[["sweep", "Sweep"], ["focus", "Focus"]]} />
        <Segmented value={status} onChange={setStatus}
                   options={[["undecided", "Open"], ["decided", "Done"], ["stale", "Amended"], ["all", "All"]]} />
        <div ref={searchRef}>
          <Search value={search} onChange={setSearch} placeholder="Account or vendor   /" />
        </div>
        <div style={{ flex: 1 }} />
        <Keys hints={mode === "focus"
          ? [["Enter", "accept"], ["e", "edit"], ["j/k", "move"], ["f", "sweep"]]
          : [["j/k", "move"], ["Enter", "accept"], ["x", "select"], ["1-8", "pool"], ["f", "focus"]]} />
      </div>

      {loading && <Card variant="quiet"><span className="rowsub">Loading…</span></Card>}

      {!loading && rows.length === 0 && (
        <Card>
          <Empty mark="✓" title={status === "undecided" ? "Queue is clear" : "Nothing in this view"}>
            {status === "undecided"
              ? "Every group in this filter has a decision. Seal the set when you are ready for the rate."
              : "Try a different filter, or import a general ledger to begin."}
          </Empty>
        </Card>
      )}

      {!loading && rows.length > 0 && mode === "focus" && current && (
        <FocusCard row={current} index={cursor} total={rows.length} busy={busy}
                   onAccept={() => acceptProposal(current)}
                   onEdit={() => openEditor([current])}
                   onPrev={() => setCursor((i) => Math.max(0, i - 1))}
                   onNext={() => setCursor((i) => Math.min(rows.length - 1, i + 1))} />
      )}

      {!loading && rows.length > 0 && mode === "sweep" && (
        <Table columns={[
          { label: "", width: 40, align: "left" },
          { label: "", width: 34, align: "left" },
          { label: "Account", align: "left" },
          { label: "Vendor", align: "left" },
          { label: "Lines" },
          { label: "Amount" },
          { label: "Proposal", align: "left" },
          { label: "", width: 170, align: "left" },
        ]}>
          {rows.map((r, i) => (
            <tr key={r.group_key}
                className={`hoverable ${picked.has(r.group_key) ? "picked" : ""} ${i === cursor ? "cursor" : ""}`}
                onClick={() => setCursor(i)}>
              <td className="l">
                <input type="checkbox" checked={picked.has(r.group_key)}
                       onChange={() => setPicked((p) => {
                         const n = new Set(p);
                         n.has(r.group_key) ? n.delete(r.group_key) : n.add(r.group_key);
                         return n;
                       })}
                       onClick={(e) => e.stopPropagation()}
                       aria-label={`Select ${r.account}`} />
              </td>
              <td className="l">
                <Tick state={r.stale ? "flagged" : r.decided ? "done" : "open"}
                      title={r.stale ? "Amended in QuickBooks since it was classified" : undefined} />
              </td>
              <td className="l">{r.account}</td>
              <td className="l" style={{ color: "var(--graphite)" }}>{r.payee || "—"}</td>
              <td>{r.line_count}</td>
              <td className={`amt strong ${Number(r.amount) < 0 ? "neg" : ""}`}>{money(r.amount)}</td>
              <td className="l wrap">
                {r.proposal ? (
                  <>
                    <Pill tone={r.proposal.confidence === "high" ? "accent" : ""}>
                      {r.proposal.pool}{r.proposal.objective_id ? ` · ${r.proposal.objective_id}` : ""}
                    </Pill>{" "}
                    <span className="rowsub">{r.proposal.rationale}</span>
                  </>
                ) : (
                  <span className="rowsub">No signal — needs a judgment</span>
                )}
              </td>
              <td className="l">
                {r.proposal && !r.decided && (
                  <button className="sm primary" disabled={busy}
                          onClick={(e) => { e.stopPropagation(); acceptProposal(r); }}>Accept</button>
                )}{" "}
                <button className="sm" onClick={(e) => { e.stopPropagation(); openEditor([r]); }}>
                  {r.decided ? "Revise" : "Classify"}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {picked.size > 0 && (
        <div className="bulkbar">
          <span className="count num">{picked.size}</span>
          <span>group{picked.size === 1 ? "" : "s"} selected · {money(chosenTotal)}</span>
          <div style={{ flex: 1 }} />
          <button className="primary" onClick={() => openEditor(chosen)}>Classify together</button>
          <button onClick={() => setPicked(new Set())}>Clear</button>
        </div>
      )}

      <Editor state={editing} setState={setEditing} vocab={vocab} busy={busy}
              onApply={(d) => submit(editing.groups, d)} />
    </div>
  );
}

/* ------------------------------------------------------------------ focus */

function FocusCard({ row, index, total, busy, onAccept, onEdit, onPrev, onNext }) {
  const p = row.proposal;
  return (
    <div className="focus">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
        <div style={{ minWidth: 260 }}>
          <div className={`focus-amount ${Number(row.amount) < 0 ? "amt neg" : ""}`}>{money(row.amount)}</div>
          <div className="focus-account">{row.account}</div>
          <div className="focus-meta">
            {row.payee || "no vendor recorded"} · {row.line_count} line{row.line_count === 1 ? "" : "s"}
            {row.evidence_count > 0 && ` · ${row.evidence_count} document${row.evidence_count === 1 ? "" : "s"}`}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="rowsub num">{index + 1} of {total}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button className="sm" onClick={onPrev} disabled={index === 0} aria-label="Previous">↑</button>
            <button className="sm" onClick={onNext} disabled={index === total - 1} aria-label="Next">↓</button>
          </div>
        </div>
      </div>

      {row.sample_memos?.length > 0 && (
        <ul className="memo-list">
          {row.sample_memos.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      )}

      <div className={`proposal ${p ? "" : "none"}`}>
        {p ? (
          <>
            <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
              <Pill tone="solid">{p.pool}</Pill>
              {p.objective_id && <Pill tone="accent">{p.objective_id}</Pill>}
              {p.citation && <span className="mono-ref">{p.citation}</span>}
            </div>
            <div className="proposal-why">{p.rationale}</div>
          </>
        ) : (
          <div className="proposal-why">
            Nothing in the account name, the Customer:Job field or last year points anywhere.
            This is a judgment call, and it stays in the queue until you make it rather than
            being defaulted into a pool.
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 18, alignItems: "center", flexWrap: "wrap" }}>
        {p && <button className="primary" onClick={onAccept} disabled={busy}>Accept proposal</button>}
        <button onClick={onEdit} disabled={busy}>Classify differently</button>
        <div style={{ flex: 1 }} />
        <span className="rowsub">Every decision records who, when and why.</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- editor */

function Editor({ state, setState, vocab, busy, onApply }) {
  if (!state) return null;
  const { groups, draft } = state;
  const total = groups.reduce((s, g) => s + Math.abs(Number(g.abs_amount)), 0);
  const lines = groups.reduce((s, g) => s + g.line_count, 0);

  const set = (k, v) =>
    setState((s) => {
      const d = { ...s.draft, [k]: v };
      if (k === "pool") {
        d.function_990 = FUNCTION_FOR[v] || d.function_990;
        d.citation = CITATIONS[v] || "";
        if (v !== "DIRECT") d.objective_id = "";
      }
      return { ...s, draft: d };
    });

  const needsObjective = draft.pool === "DIRECT";
  const needsRationale = !["UNSUPPORTED", "TEST_ASSUMPTION"].includes(draft.grade);
  const problem = needsObjective && !draft.objective_id
    ? "Direct cost has to name a final cost objective."
    : needsRationale && !draft.rationale.trim()
      ? "This evidence grade needs a rationale — it prints in the audit package."
      : null;

  return (
    <Drawer
      open
      title={groups.length === 1 ? groups[0].account : `${groups.length} groups`}
      subtitle={`${money(total)} · ${lines} ledger line${lines === 1 ? "" : "s"}`}
      onClose={() => setState(null)}
      footer={
        <>
          <button className="primary" disabled={busy || !!problem} onClick={() => onApply(draft)}>
            Record decision
          </button>
          <button onClick={() => setState(null)}>Cancel</button>
          {problem && <span className="rowsub" style={{ color: "var(--warn)" }}>{problem}</span>}
        </>
      }
    >
      <Card variant="quiet" title="Why four fields and not one">
        <span className="rowsub">
          Form 990 Part IX and 2 CFR 200 Subpart E ask different questions. Interest is
          federally unallowable and a reportable 990 expense; lobbying is unallowable and
          triggers Schedule C. One field cannot answer both, so each is recorded separately
          and both reports derive from the same judgment.
        </span>
      </Card>

      <div className="grid form" style={{ marginTop: 16 }}>
        <Field label="Cost pool">
          <select value={draft.pool} onChange={(e) => set("pool", e.target.value)}>
            {vocab?.pools.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Form 990 function">
          <select value={draft.function_990} onChange={(e) => set("function_990", e.target.value)}>
            {vocab?.functions.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Federal treatment">
          <select value={draft.federal} onChange={(e) => set("federal", e.target.value)}>
            {vocab?.federal.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        {needsObjective && (
          <Field label="Cost objective" required>
            <select value={draft.objective_id} onChange={(e) => set("objective_id", e.target.value)}>
              <option value="">Choose…</option>
              {vocab?.objectives.map((o) => (
                <option key={o.objective_id} value={o.objective_id}>
                  {o.objective_id}{o.is_federal ? " · federal" : ""}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Evidence grade" hint="quality is earned">
          <select value={draft.grade} onChange={(e) => set("grade", e.target.value)}>
            {vocab?.grades.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Citation">
          <input value={draft.citation} onChange={(e) => set("citation", e.target.value)} />
        </Field>
      </div>

      <div style={{ marginTop: 16 }}>
        <Field label="Rationale" required={needsRationale}>
          <textarea rows={3} value={draft.rationale}
                    onChange={(e) => set("rationale", e.target.value)}
                    placeholder="Why this treatment? A reviewer reads this, so write it for them." />
        </Field>
      </div>

      {groups.length > 1 && (
        <div style={{ marginTop: 16 }}>
          <Card variant="quiet" title="Applies to">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--graphite)" }}>
              {groups.slice(0, 12).map((g) => (
                <li key={g.group_key}>{g.account} — {money(g.amount)}</li>
              ))}
              {groups.length > 12 && <li className="rowsub">and {groups.length - 12} more</li>}
            </ul>
          </Card>
        </div>
      )}
    </Drawer>
  );
}
