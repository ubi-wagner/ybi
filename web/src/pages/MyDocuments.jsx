import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, Drawer, Empty, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

/* The module everybody gets.
 *
 * Two questions this screen has to answer, and the second one matters more:
 * how do I send a document in, and what became of the ones I already sent.
 * Somebody who uploads three receipts and never learns whether they were
 * used stops uploading, and then the evidence goes back to living in a
 * drawer, which is where this system found it.
 *
 * Deliberately no "which cost does this support" field. That is a judgment,
 * it belongs to whoever holds the portfolio, and asking a person to guess it
 * produces a confident wrong answer that somebody then has to unpick. What
 * is asked for instead is what they actually know: what it is, and what it
 * relates to in their own words. */

const KINDS = [
  ["receipt", "Receipt"],
  ["invoice", "Invoice"],
  ["contract", "Contract or agreement"],
  ["project_plan", "Project plan or scope"],
  ["market_comp", "Market rate comparable"],
  ["photo", "Photograph"],
  ["statement", "Statement or report"],
  ["document", "Something else"],
];

export default function MyDocuments({ actor }) {
  const [data, setData] = useState(null);
  const [file, setFile] = useState(null);
  const [kind, setKind] = useState("receipt");
  const [suggested, setSuggested] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [open, setOpen] = useState(null);
  const input = useRef(null);
  const toast = useToast();

  /* A link the browser follows itself, so the session cookie goes
     with it and the bytes never pass through JavaScript. */
  function take(d) {
    const a = document.createElement("a");
    a.href = api.documentDownloadUrl(d.evidence_id);
    a.download = d.filename || d.evidence_id;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const load = useCallback(() => {
    api.myDocuments().then(setData).catch(() => setData({ documents: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function send(e) {
    e?.preventDefault();
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("suggested_for", suggested);
    form.append("note", note);
    try {
      const r = await api.uploadDocument(form);
      toast.show(r.deduplicated
        ? (r.message || "That document was already on file.")
        : `${r.filename} sent in`);
      setFile(null);
      setSuggested("");
      setNote("");
      if (input.current) input.current.value = "";
      load();
    } catch (err) {
      toast.show(String(err.message || err).replace(/^\d+:\s*/, ""), { tone: "fail" });
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) setFile(f);
  }

  return (
    <div className="page">
      <PageHead title="My documents" schedule="E">
        Anything that shows what a cost was for — a receipt, an invoice, a
          project plan, a photograph of a machine's nameplate, a lease you were
          quoted. You do not have to know where it belongs in the books. Say
          what it relates to in your own words and somebody with the right
          portfolio will file it against the right cost.
      </PageHead>

      <div className="grid three">
        <Stat label="Sent in" value={data?.uploaded ?? "—"} size="lg" />
        <Stat label="Put to work" value={data?.in_use ?? "—"} size="lg"
              note="attached to a cost" />
        <Stat label="Waiting" value={data?.waiting ?? "—"} size="lg"
              note={data?.waiting ? "nobody has filed these yet" : "nothing outstanding"} />
      </div>

      <Card variant="raised" title="Send one in">
        <form onSubmit={send}>
          <div
            className={"card quiet" + (dragging ? " picked" : "")}
            style={{ padding: 22, textAlign: "center", cursor: "pointer" }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => input.current?.click()}
          >
            <input ref={input} type="file" style={{ display: "none" }}
                   onChange={(e) => setFile(e.target.files?.[0] || null)} />
            {file ? (
              <>
                <div style={{ fontWeight: 600 }}>{file.name}</div>
                <div className="rowsub">
                  {(file.size / 1024).toFixed(0)} KB — click to choose a different one
                </div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600 }}>Drop a file here, or click to choose</div>
                <div className="rowsub">
                  A photo of a paper receipt is fine. Up to 40 MB.
                </div>
              </>
            )}
          </div>

          <div className="grid two" style={{ marginTop: 14 }}>
            <label className="field">
              <span className="field-label">What kind of thing is it</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">What does it relate to</span>
              <input value={suggested} placeholder="Drive AM travel, June — Detroit trip"
                     onChange={(e) => setSuggested(e.target.value)} />
            </label>
          </div>

          <label className="field">
            <span className="field-label">
              Anything else worth knowing (optional)
            </span>
            <input value={note}
                   placeholder="Split between two projects — Barb has the breakdown"
                   onChange={(e) => setNote(e.target.value)} />
          </label>

          <button className="btn primary" type="submit" disabled={!file || busy}>
            {busy ? "Sending…" : "Send it in"}
          </button>
        </form>
      </Card>

      <Card title="What I have sent in">
        {!data?.documents?.length ? (
          <Empty mark="—" title="Nothing yet">
            Documents you send in will be listed here, along with whether
            anybody has put them to work yet.
          </Empty>
        ) : (
          <Table columns={[
            { label: "", align: "left", width: "34px" },
            { label: "What it relates to", align: "left" },
            { label: "Kind", align: "left" },
            { label: "Sent", align: "left" },
            { label: "Status", align: "left" },
            { label: "", align: "left", width: "150px" },
          ]}>
            {data.documents.map((d) => (
              <tr key={d.evidence_id}>
                <td className="l">
                  <Tick state={d.is_attached ? "done" : "open"}
                        title={d.is_attached ? "in use" : "waiting"} />
                </td>
                <td className="l">
                  {d.suggested_for || <span className="rowsub">no description</span>}
                  {d.note && <div className="rowsub">{d.note}</div>}
                </td>
                <td className="l rowsub">{d.kind}</td>
                <td className="l rowsub">{String(d.received_at).slice(0, 10)}</td>
                <td className="l">
                  {d.is_attached
                    ? <Pill tone="accent">supporting {d.attachments} item{d.attachments === 1 ? "" : "s"}</Pill>
                    : <Pill>waiting to be filed</Pill>}
                </td>
                {/* Your own document, always — the route allows the uploader
                    whatever else they hold. Somebody who sent in a receipt
                    six weeks ago and wants to check which one it was should
                    not have to ask the controller. */}
                <td className="l">
                  <div className="btn-row">
                    {d.inline_safe && (
                      <button className="btn sm" onClick={() => setOpen(d)}>
                        Read
                      </button>
                    )}
                    <button className="btn sm ghost" onClick={() => take(d)}>
                      Download
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Drawer open={Boolean(open)} wide
              title={open?.filename || open?.evidence_id || ""}
              subtitle={open && [open.kind, open.period,
                                 String(open.received_at).slice(0, 10)]
                                .filter(Boolean).join(" · ")}
              onClose={() => setOpen(null)}
              footer={open && (
                <div className="btn-row">
                  <button className="btn primary" onClick={() => take(open)}>
                    Download a copy
                  </button>
                  <button className="ghost" onClick={() => setOpen(null)}>Close</button>
                </div>
              )}>
        {/* No `sandbox` attribute on the frame below — see the note in
            Library.jsx. It stops Chromium rendering a PDF, and the
            Content-Security-Policy the server puts on the response does the
            same job without that cost. */}
        {open && (
          <iframe className="doc-frame" title={open.filename || open.evidence_id}
                  src={api.documentViewUrl(open.evidence_id)} />
        )}
      </Drawer>
    </div>
  );
}
