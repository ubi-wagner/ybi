import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, Field, PageHead, Pill, Stat, Table, useToast } from "../components/ui.jsx";

const money = (v) =>
  v === null || v === undefined ? "—"
    : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const size = (b) =>
  !b ? "—" : b < 1024 ? `${b} B`
    : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`;
const when = (t) =>
  !t ? "" : new Date(t).toLocaleString(undefined,
    { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

const KINDS = [
  ["document", "Document"],
  ["invoice", "Vendor invoice"],
  ["lease", "Lease"],
  ["timesheet", "Timesheet"],
  ["policy", "Policy"],
  ["schedule", "Schedule or register"],
  ["correspondence", "Correspondence"],
];

/* The document register: what was received, what it supports, and — the part
   that makes it evidence rather than a list — the file itself, retrievable by
   anyone who can read the period, auditor included. */
export default function Evidence({ actor }) {
  /* The register is for everyone who can read the period. Filing a document
     into it is the controller's act. */
  const canWrite = actor?.role === "CONTROLLER";
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [pending, setPending] = useState(null);   // the file waiting on its description
  const [kind, setKind] = useState("document");
  const [relevance, setRelevance] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const toast = useToast();

  const load = useCallback(() =>
    api.evidenceRegister()
      .then((d) => { setRows(d); setError(""); })
      .catch((e) => setError(String(e.message || e))), []);

  useEffect(() => { load(); }, [load]);

  function take(files) {
    if (files && files.length) setPending(files[0]);
  }

  async function upload() {
    if (!pending) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", pending);
      form.append("kind", kind);
      form.append("period", "2025");
      form.append("relevance", relevance);
      const r = await api.uploadEvidence(form);
      toast(r.deduplicated
        ? `Already on file as ${r.evidence_id} — the same bytes, stored once`
        : `Filed as ${r.evidence_id}`);
      setPending(null); setRelevance("");
      await load();
    } catch (e) {
      setError(String(e.message || e));
    }
    setBusy(false);
  }

  const total = (rows || []).reduce((a, r) => a + Number(r.byte_size || 0), 0);
  const attached = (rows || []).filter((r) => r.attachments > 0).length;

  return (
    <div className="dash">
      <PageHead title="Evidence" schedule="E">
        Every document received for 2025, and what it supports.
      </PageHead>

      {canWrite && (
      <Card title="Add a document" variant="raised">
        <div
          className={`dropzone ${drag ? "on" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files); }}
          onClick={() => input.current?.click()}
        >
          <input ref={input} type="file" hidden
                 onChange={(e) => take(e.target.files)} />
          {pending ? (
            <>
              <div className="strong">{pending.name}</div>
              <div className="quiet small">{size(pending.size)} · ready to file</div>
            </>
          ) : (
            <>
              <div className="strong">Drop a file here, or click to choose one</div>
              <div className="quiet small">
                Stored by content hash — the same document filed twice is stored once.
              </div>
            </>
          )}
        </div>

        {pending && (
          <div className="upload-form">
            <Field label="What kind of document">
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="What it supports"
                   hint="Prints beside the document in the audit package.">
              <input value={relevance} onChange={(e) => setRelevance(e.target.value)}
                     placeholder="e.g. supports the janitorial allocation to overhead" />
            </Field>
            <div className="upload-actions">
              <button className="btn primary" disabled={busy} onClick={upload}>
                {busy ? "Filing…" : "File document"}
              </button>
              <button className="btn quiet" onClick={() => setPending(null)}>Cancel</button>
            </div>
          </div>
        )}
        {error && <div className="signin-error" role="alert">{error}</div>}
      </Card>
      )}

      <Card title="Register"
            aside={rows ? `${rows.length} document${rows.length === 1 ? "" : "s"}` : ""}>
        {!rows ? <Empty mark="…" title="Loading" />
          : rows.length === 0 ? (
          <Empty mark="—" title="Nothing on file yet">
            Documents uploaded here, or attached while classifying, appear in this
            register and in the audit package.
          </Empty>
        ) : (
          <>
            <div className="stat-row">
              <Stat label="Documents" value={rows.length} size="lg" />
              <Stat label="Attached to cost" value={attached} />
              <Stat label="Stored" value={size(total)} />
            </div>
            <Table columns={[
              { label: "Document", align: "left" }, { label: "Kind", align: "left" },
              { label: "Supports", align: "left" }, { label: "Attached" },
              { label: "Received", align: "left" }, { label: "Size" },
              { label: "", align: "left" },
            ]}>
              {rows.map((r) => (
                <tr key={r.evidence_id}>
                  <td className="l strong">
                    {(r.uri || "").split("/").pop().replace(/^[0-9a-f]{16}_/, "")}
                    <div className="quiet small mono-ref">{r.evidence_id}</div>
                  </td>
                  <td className="l"><Pill>{r.kind}</Pill></td>
                  <td className="l ellipsis quiet small">{r.relevance || "—"}</td>
                  <td className="num">
                    {r.attachments > 0
                      ? <>{r.attachments} line{r.attachments === 1 ? "" : "s"}
                          {Number(r.supported_amount) > 0 &&
                            <div className="quiet small">${money(r.supported_amount)}</div>}
                        </>
                      : <span className="quiet">unattached</span>}
                  </td>
                  <td className="l quiet small">{when(r.received_at)}<br />{r.received_from}</td>
                  <td className="num quiet small">{size(r.byte_size)}</td>
                  <td className="l">
                    <a className="btn sm" href={api.evidenceFileUrl(r.evidence_id)}
                       download>Download</a>
                  </td>
                </tr>
              ))}
            </Table>
            <p className="quiet small" style={{ marginTop: 12 }}>
              Downloads are recorded against the person who made them, the same way
              classifications are. The record shows who looked, not only who wrote.
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
