import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Empty, Pill, useToast } from "./ui.jsx";

/*
  The breadcrumb.

  Everything here is a forward act: walking something back writes a new record
  that names what it reversed. So the trail never shrinks, and an undo appears
  in it as its own entry — which is the point, because "who undid the
  reclassification, and why" is a question somebody will ask.
*/

const when = (t) => new Date(t).toLocaleString(undefined,
  { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export default function UndoTrail({ onClose, onChanged }) {
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [picked, setPicked] = useState(() => new Set());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() =>
    api.undoable({ limit: 25 })
      .then((r) => { setRows(r); setError(""); })
      .catch((e) => setError(String(e.message || e))), []);
  useEffect(() => { load(); }, [load]);

  const toggle = (id) => setPicked((p) => {
    const n = new Set(p);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  async function walkBack() {
    setBusy(true);
    try {
      const r = await api.undo({ entry_ids: [...picked], reason: reason.trim() });
      const done = r.undone.length;
      toast(done === 1 ? r.undone[0].result
                       : `${done} actions walked back`,
            { tone: done ? undefined : "bad" });
      r.refused.forEach((f) =>
        toast(typeof f.why === "string" ? f.why : JSON.stringify(f.why),
              { tone: "bad", sticky: true }));
      setPicked(new Set()); setReason("");
      await load();
      onChanged?.();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { detail = JSON.parse(msg).detail || msg; } catch { /* plain */ }
      toast(typeof detail === "string" ? detail : JSON.stringify(detail),
            { tone: "bad", sticky: true });
    }
    setBusy(false);
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal wide" role="dialog" aria-label="Recent actions"
           onClick={(e) => e.stopPropagation()}>
        <h2>Walk something back</h2>
        <p className="quiet small">
          Nothing is deleted. Walking an action back records a new entry that
          says what it reversed and why, so the trail reads as a statement and
          its answer.
        </p>

        {error && <div className="signin-error" role="alert">{error}</div>}
        {!rows ? <Empty mark="…" title="Loading" />
          : rows.length === 0 ? <Empty mark="—" title="Nothing to walk back" />
          : (
          <ul className="trail">
            {rows.map((r) => (
              <li key={r.entry_id} className={r.can_undo ? "" : "spent"}>
                <label>
                  <input type="checkbox" disabled={!r.can_undo}
                         checked={picked.has(r.entry_id)}
                         onChange={() => toggle(r.entry_id)} />
                  <span className="trail-what">
                    <span className="strong">{r.label}</span>
                    {r.reason && <span className="quiet"> · {r.reason}</span>}
                    <span className="quiet small trail-meta">
                      {r.actor} · {when(r.occurred_at)}
                      {!r.can_undo && r.blocked_because &&
                        <> · <span className="amt neg">{r.blocked_because}</span></>}
                    </span>
                  </span>
                  {r.already_undone && <Pill>undone</Pill>}
                </label>
              </li>
            ))}
          </ul>
        )}

        <label className="modal-label" htmlFor="undo-reason">
          Why you are walking these back
        </label>
        <input id="undo-reason" value={reason} placeholder="e.g. wrong pool applied in bulk"
               onChange={(e) => setReason(e.target.value)} />

        <div className="modal-actions">
          <button className="btn primary"
                  disabled={!picked.size || !reason.trim() || busy}
                  onClick={walkBack}>
            {busy ? "Walking back…"
                  : `Walk back ${picked.size || ""} ${picked.size === 1 ? "action" : "actions"}`}
          </button>
          <button className="btn quiet" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
