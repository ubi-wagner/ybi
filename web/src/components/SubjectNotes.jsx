import React, { useCallback, useEffect, useState } from "react";

import { api, explain } from "../api.js";
import { Card, Drawer, Empty, Field, Pill, Segmented, useToast } from "./ui.jsx";

/* Notes against one part of the record that is not a classification.
 *
 * `084` made a note carry a subject, so the same two kinds reach a building,
 * a space and an asset's funding — and the same rule holds: **a WORKING note
 * is undisclosed and never concealed.** Whoever may not read the body is told
 * it is there, because dropping the row would make three notes look like one.
 *
 * It exists because the register that carries them had a route and no door
 * anywhere on these screens, which is the shape the door sweep was written
 * for: the capability was complete and nothing served it to its reader.
 */
export default function SubjectNotes({ subject, subjectId, title, onClose }) {
  const toast = useToast();
  const [notes, setNotes] = useState(null);
  const [kind, setKind] = useState("RECORD");
  const [text, setText] = useState("");

  const load = useCallback(() => {
    if (!subjectId) return;
    api.subjectNotes(subject, subjectId)
       .then(setNotes).catch(() => setNotes(null));
  }, [subject, subjectId]);
  useEffect(load, [load]);

  if (!subjectId) return null;

  async function add() {
    try {
      await api.writeNote({ subject, subject_id: subjectId, kind, body: text });
      toast.ok(kind === "RECORD"
        ? "Noted on the record, where every reader of it sees it."
        : "Noted. It stays out of the audit package; its count does not.");
      setText(""); load();
    } catch (e) { toast.fail(explain(e) || "That note was refused."); }
  }

  return (
    <Drawer open onClose={onClose} title={title || subjectId}
            subtitle={subject.replace(/_/g, " ").toLowerCase()}>
      <Card title="Notes">
        {!notes || notes.notes.length === 0
          ? <Empty title="Nothing written here yet" />
          : notes.notes.map((n) => (
              <div key={n.note_id} className="card quiet">
                <Pill tone={n.kind === "WORKING" ? "warn" : ""}>{n.kind}</Pill>
                {" "}<span className="rowsub">{n.author}</span>
                <p>{n.withheld
                  ? <em className="muted">
                      A working note. You are told it is here, and not what it
                      says.
                    </em>
                  : n.body}</p>
              </div>
            ))}
        <Field label="Write a note">
          <textarea rows={3} value={text}
                    onChange={(e) => setText(e.target.value)} />
        </Field>
        <Segmented value={kind} onChange={setKind}
                   options={[["RECORD", "On the record"],
                             ["WORKING", "Working"]]} />
        <button className="primary" disabled={text.trim().length < 12}
                onClick={add}>Write it</button>
      </Card>
    </Drawer>
  );
}
