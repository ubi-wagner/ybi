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

export default function ClassifyQueue({ actor }) {
  /* A reader who is offered a button that will 403 has been told the wrong
     thing about their own access. The auditor sees the queue and everything
     behind each decision; the affordances that write are simply not there. */
  const canWrite = actor?.role === "CONTROLLER";
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
        decided_by: actor?.display_name || "",
        /* What this screen believed was live when it was drawn. Two people
           work this queue at once; if one of them judges a group while the
           other's list is still showing it as it was, the server refuses
           rather than letting the second judgment silently replace a
           judgment nobody saw. */
        based_on: Object.fromEntries(
          groups.map((g) => [g.group_key, g.live_decision || "none"])),
      });
      const label = groups.length === 1
        ? `${groups[0].account} → ${decision.pool}`
        : `${groups.length} groups → ${decision.pool}`;
      /* The undo here reverses the decision that was just recorded. It used
         to show a message saying a reversal had been recorded while recording
         nothing at all, which is worse than having no undo: it told somebody
         their mistake was fixed. */
      toast(`Recorded ${label}`, {
        onUndo: async () => {
          try {
            const trail = await api.undoable({ limit: 5 });
            const mine = trail.find((t) => t.action === "CLASSIFY" && t.can_undo);
            if (!mine) {
              toast("That decision has already been superseded.", { tone: "bad" });
              return;
            }
            const r = await api.undo({
              entry_ids: [mine.entry_id],
              reason: "Walked back immediately after recording it.",
            });
            toast(r.undone.length ? r.undone[0].result
                                  : "Nothing was walked back", { tone: r.undone.length ? undefined : "bad" });
            await load();
          } catch (e) {
            toast(String(e.message || e), { tone: "bad", sticky: true });
          }
        },
      });
      setPicked(new Set());
      setEditing(null);
      await load();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad", sticky: true });
      /* A refusal because the record moved is the one error where the right
         next step is automatic: redraw the queue so the person is looking at
         what is actually there before they decide again. */
      if (/changed while this screen was open/.test(String(e.message || e))) {
        await load();
      }
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
      } else if (e.key === "f") {
        e.preventDefault(); setMode((m) => (m === "focus" ? "sweep" : "focus"));
      } else if (!canWrite) {
        return;
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
  }, [rows, current, editing, canWrite, acceptProposal, openEditor]);

  const pct = Number(cov?.pct_dollars || 0);

  return (
    <div className="page">
      <PageHead title="Classification" schedule="B"
                aside={!canWrite ? <Pill>read only</Pill> : null}>
        {canWrite
            ? "Largest groups first. Accept a proposal with one key, or open a group when it needs real thought. Progress is measured in dollars — the rate is computed only once this set is sealed."
            : "Every group, every decision and the reasoning behind it. Nothing on this screen can be changed from your account — classification is the controller's, and the record shows whose it was."}
      </PageHead>

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
        <Keys hints={!canWrite
          ? [["j/k", "move"], ["f", mode === "focus" ? "sweep" : "focus"], ["/", "search"]]
          : mode === "focus"
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
                   canWrite={canWrite} onSplit={load}
                   onAccept={() => acceptProposal(current)}
                   onEdit={() => openEditor([current])}
                   onPrev={() => setCursor((i) => Math.max(0, i - 1))}
                   onNext={() => setCursor((i) => Math.min(rows.length - 1, i + 1))} />
      )}

      {!loading && rows.length > 0 && mode === "sweep" && (
        <Table columns={[
          ...(canWrite ? [{ label: "", width: 40, align: "left" }] : []),
          { label: "", width: 34, align: "left" },
          { label: "Account", align: "left" },
          { label: "Vendor", align: "left" },
          { label: "Lines" },
          { label: "Amount" },
          { label: "Proposal", align: "left" },
          ...(canWrite ? [{ label: "", width: 170, align: "left" }] : []),
        ]}>
          {rows.map((r, i) => (
            <tr key={r.group_key}
                className={`hoverable ${picked.has(r.group_key) ? "picked" : ""} ${i === cursor ? "cursor" : ""}`}
                onClick={() => setCursor(i)}>
              {canWrite && (
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
              )}
              <td className="l">
                <Tick state={r.stale ? "flagged" : r.decided ? "done" : "open"}
                      title={r.stale ? "Amended in QuickBooks since it was classified" : undefined} />
              </td>
              <td className="l trunc">{r.account}</td>
              <td className="l trunc" style={{ color: "var(--graphite)" }}>{r.payee || "—"}</td>
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
              {canWrite && (
                <td className="l">
                  {r.proposal && !r.decided && (
                    <button className="sm primary" disabled={busy}
                            onClick={(e) => { e.stopPropagation(); acceptProposal(r); }}>Accept</button>
                  )}{" "}
                  <button className="sm" onClick={(e) => { e.stopPropagation(); openEditor([r]); }}>
                    {r.decided ? "Revise" : "Classify"}
                  </button>
                </td>
              )}
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

function FocusCard({ row, index, total, busy, canWrite, onAccept, onEdit, onPrev, onNext,
                    onSplit }) {
  const p = row.proposal;
  const [splitting, setSplitting] = useState(false);
  useEffect(() => { setSplitting(false); }, [row.group_key]);
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
        {canWrite && p && (
          <button className="primary" onClick={onAccept} disabled={busy}>Accept proposal</button>
        )}
        {canWrite && <button onClick={onEdit} disabled={busy}>Classify differently</button>}
        {canWrite && (
          <button onClick={() => setSplitting(!splitting)} disabled={busy}>
            {splitting ? "Cancel split" : "Split this group"}
          </button>
        )}
        <div style={{ flex: 1 }} />
        <span className="rowsub">Every decision records who, when and why.</span>
      </div>

      {splitting && (
        <Splitter row={row}
                  onDone={() => { setSplitting(false); onSplit?.(); }} />
      )}

      <Advice groupKey={row.group_key} />

      <GroupRecord row={row} canWrite={canWrite} />
    </div>
  );
}

/* ----------------------------------------------------------------- advice */

/* What is worth thinking about before deciding — the thing that is obvious at
   nine in the morning and gone by the six hundredth group. Advice, never a
   decision, and every item carries the rule it rests on. */
function Advice({ groupKey }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    let live = true;
    api.advice(groupKey)
      .then((d) => live && setItems(d.advice))
      .catch(() => live && setItems([]));
    return () => { live = false; };
  }, [groupKey]);

  if (!items?.length) return null;
  return (
    <div className="advice">
      {items.map((a, i) => (
        <div key={i} className={`advice-item k-${a.kind.toLowerCase()}`}>
          <span className="advice-kind">{a.kind}</span>
          <div>
            <div className="strong">{a.headline}</div>
            <div className="quiet small">{a.detail}</div>
            {a.citation && <span className="mono-ref">{a.citation}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ split */

/* A booked entry is often not one thing. Splitting it records the parts and
   the reasoning for each; the ledger underneath is never touched, and every
   line reconciles to the cent or the whole split is refused. */
function Splitter({ row, onDone }) {
  const toast = useToast();
  const [parts, setParts] = useState([
    { label: "", share: "", rationale: "", citation: "" },
    { label: "", share: "", rationale: "", citation: "" },
  ]);
  const [busy, setBusy] = useState(false);

  const set = (i, k, v) =>
    setParts((ps) => ps.map((p, j) => (j === i ? { ...p, [k]: v } : p)));

  const total = parts.reduce((a, p) => a + (Number(p.share) || 0), 0);
  const ready = parts.length >= 2 &&
    parts.every((p) => p.label.trim() && p.rationale.trim() && Number(p.share) > 0) &&
    Math.abs(total - 100) < 0.005;

  async function apply() {
    setBusy(true);
    try {
      const r = await api.segment({
        group_key: row.group_key,
        created_by: "",
        parts: parts.map((p) => ({
          label: p.label.trim(),
          share: String(Number(p.share) / 100),
          rationale: p.rationale.trim(),
          citation: p.citation.trim() || null,
        })),
      });
      toast(`Split into ${r.by_part.length} parts across ` +
            `${r.lines_segmented} lines · ${r.segments_created} segments`);
      onDone?.();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad", sticky: true });
    }
    setBusy(false);
  }

  return (
    <div className="splitter">
      <div className="splitter-head">
        <span className="strong">Split into parts</span>
        <span className="rowsub">
          Each part carries its own share and its own reasoning. Every line
          reconciles to the cent, or the whole split is refused.
        </span>
      </div>

      {parts.map((p, i) => (
        <div className="split-part" key={i}>
          <input placeholder="What this part is" value={p.label}
                 onChange={(e) => set(i, "label", e.target.value)} />
          <input className="split-share num" placeholder="%" value={p.share}
                 inputMode="decimal"
                 onChange={(e) => set(i, "share", e.target.value)} />
          <input placeholder="Why this share, and on what driver" value={p.rationale}
                 onChange={(e) => set(i, "rationale", e.target.value)} />
          <input className="split-cite" placeholder="Citation" value={p.citation}
                 onChange={(e) => set(i, "citation", e.target.value)} />
          {parts.length > 2 && (
            <button className="sm" aria-label="Remove part"
                    onClick={() => setParts((ps) => ps.filter((_, j) => j !== i))}>−</button>
          )}
        </div>
      ))}

      <div className="splitter-foot">
        <button className="sm"
                onClick={() => setParts((ps) => [...ps,
                  { label: "", share: "", rationale: "", citation: "" }])}>
          Add a part
        </button>
        <span className={`rowsub ${Math.abs(total - 100) < 0.005 ? "" : "amt neg"}`}>
          {total.toFixed(2)}% of {money(row.amount)}
        </span>
        <div style={{ flex: 1 }} />
        <button className="primary sm" disabled={!ready || busy} onClick={apply}>
          {busy ? "Splitting…" : "Record the split"}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------- notes and papers */

/* The reasoning that does not fit in a rationale field, and the document it
   rests on, recorded where the judgment is actually made. Attaching from here
   fans the document out to every line in the group, so it supports the
   dollars rather than the screen. */
function GroupRecord({ row, canWrite }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [body, setBody] = useState("");
  const [workpaper, setWorkpaper] = useState(true);
  const [busy, setBusy] = useState(false);
  const file = useRef(null);

  const load = useCallback(() => {
    if (!row?.group_key) return;
    api.evidenceForGroup(row.group_key).then(setData).catch(() => setData(null));
  }, [row?.group_key]);

  useEffect(() => { setOpen(false); setData(null); setBody(""); }, [row?.group_key]);
  useEffect(() => { if (open) load(); }, [open, load]);

  async function addNote() {
    if (!body.trim()) return;
    setBusy(true);
    try {
      await api.addNote({ target_type: "LEDGER_GROUP", target_id: row.group_key,
                          body: body.trim(), author: "", is_workpaper: workpaper });
      setBody("");
      toast("Note recorded");
      load();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad" });
    }
    setBusy(false);
  }

  async function attach(files) {
    if (!files?.length) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", files[0]);
      form.append("kind", "document");
      form.append("period", "2025");
      form.append("target_type", "LEDGER_GROUP");
      form.append("target_id", row.group_key);
      form.append("relevance", `supports ${row.account}`);
      const r = await api.uploadEvidence(form);
      toast(`Attached to ${r.attached_to} line${r.attached_to === 1 ? "" : "s"}`);
      load();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad" });
    }
    setBusy(false);
  }

  const notes = data?.notes || [];
  const docs = data?.documents || [];

  return (
    <div className="group-record">
      <button className="linkish" onClick={() => setOpen(!open)}>
        {open ? "−" : "+"} Notes and documents
        {(row.note_count > 0 || row.evidence_count > 0) && !open &&
          ` · ${row.note_count || 0} note${row.note_count === 1 ? "" : "s"}, ` +
          `${row.evidence_count || 0} document${row.evidence_count === 1 ? "" : "s"}`}
      </button>

      {open && (
        <div className="group-record-body">
          {notes.length > 0 && (
            <ul className="note-list">
              {notes.map((n) => (
                <li key={n.note_id}>
                  <div>{n.body}</div>
                  <div className="quiet small">
                    {n.author} · {new Date(n.created_at).toLocaleString()}
                    {n.is_workpaper && " · workpaper"}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {docs.length > 0 && (
            <ul className="doc-list">
              {docs.map((d) => (
                <li key={d.evidence_id}>
                  <a href={api.evidenceFileUrl(d.evidence_id)} download>
                    {(d.uri || "").split("/").pop().replace(/^[0-9a-f]{16}_/, "")}
                  </a>
                  <span className="quiet small">
                    {" "}· {d.kind} · {d.lines} line{d.lines === 1 ? "" : "s"}
                    {d.relevance ? ` · ${d.relevance}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {canWrite && (
            <>
          <textarea className="note-input" rows={2} value={body}
                    placeholder="Why this cost is what you say it is — the part that does not fit in the rationale."
                    onChange={(e) => setBody(e.target.value)} />
          <div className="group-record-actions">
            <button className="sm" disabled={busy || !body.trim()} onClick={addNote}>
              Add note
            </button>
            <label className="note-flag">
              <input type="checkbox" checked={workpaper}
                     onChange={(e) => setWorkpaper(e.target.checked)} />
              prints in the audit package
            </label>
            <div style={{ flex: 1 }} />
            <input ref={file} type="file" hidden
                   onChange={(e) => attach(e.target.files)} />
            <button className="sm" disabled={busy} onClick={() => file.current?.click()}>
              Attach a document
            </button>
          </div>
            </>
          )}
          {!canWrite && notes.length === 0 && docs.length === 0 && (
            <div className="rowsub">Nothing recorded against this group yet.</div>
          )}
        </div>
      )}
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
