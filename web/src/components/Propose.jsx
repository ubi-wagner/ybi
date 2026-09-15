import React, { useState } from "react";

import { api, explain } from "../api.js";
import { Card, Field, Pill, useToast } from "./ui.jsx";

/* Proposing a measurement, for any part of the record.
 *
 * Heidi holds FACILITIES and INVENTORY and is the person who will go and
 * measure; Tom signs the rate those measurements feed. So the act she wants
 * most of the time is *put this in front of Tom*, not *write it* — and the
 * two figures at stake are the largest unmeasured things in the model: the
 * 200.465 carve-out is sized by square footage, and 200.436(b) cannot be
 * answered on $850,383 of depreciation without a funding source per asset.
 *
 * Three rules:
 *
 *  - **It writes nothing.** The recommendation goes on the controller's list
 *    with what is proposed, who proposed it and why. Accepting records the
 *    change through the route that owns that register, under his name.
 *  - **The refusal is the useful part.** Every rule the target register
 *    enforces is enforced here too, so what comes back is "programme space
 *    names the cost objective it serves" rather than a constraint name. The
 *    form prints it where it happened instead of only in a toast, because a
 *    toast fades and a form is where somebody is looking.
 *  - **It never hides the direct route.** Whoever holds the portfolio may
 *    still write the row; the screens keep those forms. A screen that offered
 *    only the slower path would be a nav stricter than the API, which is the
 *    same defect as one that is looser.
 */
export default function Propose({ subject, title, hint, fields, subjectLabel,
                                  presetId = "", startOpen = false, onDone }) {
  const toast = useToast();
  const [open, setOpen] = useState(startOpen);
  /* A row that says "answer this one" should not then ask which one. The
     parent remounts on the id it is answering for, so the form opens knowing
     what it is about — and the field stays editable, because the id somebody
     arrived with is a starting point and not a fact about the answer. */
  const [id, setId] = useState(presetId);
  const [values, setValues] = useState({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState("");

  /* The reference is the one field nobody knows the answer to, and it was
     first — so the form opened on a box somebody has to invent something for.
     It is derived from what they are typing anyway (the name, or the building
     and the label) and stays editable, because an id that has to match
     something already on file is a real case and guessing at it would be
     worse than asking. */
  const suggested = (() => {
    const slug = (v) => String(v || "").toUpperCase().replace(/[^A-Z0-9]+/g, "-")
      .replace(/^-|-$/g, "").slice(0, 24);
    const base = slug(values.name || values.label || "");
    if (!base) return "";
    return values.facility_id ? `${values.facility_id}-${base}` : base;
  })();
  const reference = id || suggested;

  const set = (k, v) => setValues((p) => ({ ...p, [k]: v }));
  const missing = fields.filter((f) => f.required
    && (values[f.name] === undefined || values[f.name] === ""));
  const ready = reference.trim() && note.trim().length >= 12
    && missing.length === 0;

  async function send() {
    setBusy(true); setRefusal("");
    try {
      const proposal = {};
      for (const f of fields) {
        const v = values[f.name];
        if (v === undefined || v === "") continue;
        proposal[f.name] = f.type === "number" ? Number(v)
          : f.type === "bool" ? v === "yes" : v;
      }
      const r = await api.recommend({ subject, subject_id: reference.trim(),
                                      proposal, note });
      toast.ok(r.is_new
        ? "Proposed. It is on the controller's list; nothing on the record has moved."
        : "Proposed as a change to what is already recorded.");
      setId(""); setValues({}); setNote(""); setOpen(false);
      onDone && onDone();
    } catch (e) {
      // Where it happened, not only in a toast: the message names the rule,
      // and the rule is usually the thing the person needs to go and settle.
      setRefusal(explain(e) || "That was refused.");
      toast.fail(explain(e) || "That was refused.");
    } finally { setBusy(false); }
  }

  if (!open) {
    return (
      <div className="propose-bar">
        <button className="primary" onClick={() => setOpen(true)}>
          Propose {title}
        </button>
        <span className="rowsub">{hint}</span>
      </div>
    );
  }

  return (
    <Card title={`Propose ${title}`} variant="raised" className="propose">
      <p className="muted">{hint}</p>
      <div className="form-grid">
        <Field label={subjectLabel || "Reference"}
               hint={suggested && !id
                 ? `Filled in from what you typed. Change it if this has an id already on file.`
                 : "A short id you will recognise again."}>
          <input value={reference}
                 placeholder={suggested || "\u2014"}
                 onChange={(e) => setId(e.target.value)} />
        </Field>
        {fields.map((f) => (
          <Field key={f.name} label={f.label} required={f.required}
                 hint={f.hint}>
            {f.type === "select" ? (
              <select value={values[f.name] ?? ""}
                      onChange={(e) => set(f.name, e.target.value)}>
                <option value="">—</option>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : f.type === "bool" ? (
              <select value={values[f.name] ?? ""}
                      onChange={(e) => set(f.name, e.target.value)}>
                <option value="">—</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            ) : f.type === "suggest" ? (
              /* Offered, never imposed: a `datalist` puts the known names one
                 keystroke away and still takes anything typed, which is the
                 right shape where the list is what somebody else's document
                 happens to say rather than the set of legal answers. */
              <>
                <input list={`sug-${subject}-${f.name}`}
                       value={values[f.name] ?? ""}
                       onChange={(e) => set(f.name, e.target.value)} />
                <datalist id={`sug-${subject}-${f.name}`}>
                  {(f.options || []).map((o) => <option key={o} value={o} />)}
                </datalist>
              </>
            ) : (
              <input type={f.type === "number" ? "number" : "text"}
                     value={values[f.name] ?? ""}
                     onChange={(e) => set(f.name, e.target.value)} />
            )}
          </Field>
        ))}
      </div>
      <Field label="Why, and what you measured it from"
             hint="Twelve characters or more. It travels with the proposal and
                   the controller reads it before he accepts.">
        <textarea rows={3} value={note}
                  onChange={(e) => setNote(e.target.value)} />
      </Field>
      {refusal && (
        <p className="refusal">{refusal}</p>
      )}
      <div className="row-actions">
        <button className="primary" disabled={!ready || busy} onClick={send}>
          {busy ? "Sending" : "Put it to the controller"}
        </button>
        <button onClick={() => { setOpen(false); setRefusal(""); }}>
          Cancel
        </button>
        {!ready && !busy && (
          <span className="rowsub">
            {missing.length ? `Needs ${missing.map((m) => m.label.toLowerCase()).join(", ")}.`
              : !reference.trim() ? "Needs a reference."
              : "Needs a sentence saying why."}
          </span>
        )}
      </div>
      <Pill>writes nothing</Pill>
    </Card>
  );
}
