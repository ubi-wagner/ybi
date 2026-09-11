import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, Field, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

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
     into it, and saying what one is of, take the OFFICE portfolio — which is
     what `/api/evidence/upload` and `/api/documents/propose` actually ask
     for.

     This read `actor?.role === "CONTROLLER"`, which is a *rank*, so somebody
     holding the OFFICE portfolio — whose whole job this screen is — was
     shown the register and no way to add to it, while the API would have
     accepted them. A screen stricter than the API is the same defect as one
     looser: both mean the screen and the server disagree about who you are. */
  const held = actor?.portfolios || [];
  const canWrite = held.includes("OFFICE") || held.includes("CONTROLLER");
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [pending, setPending] = useState([]);    // the files waiting on a description
  const [kind, setKind] = useState("document");
  const [relevance, setRelevance] = useState("");
  const [facts, setFacts] = useState({ doc_amount: "", doc_date: "", vendor_name: "" });
  const [busy, setBusy] = useState(false);
  const [proposals, setProposals] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [showUnread, setShowUnread] = useState(false);
  const input = useRef(null);
  const toast = useToast();

  const load = useCallback(() =>
    api.evidenceRegister()
      .then((d) => { setRows(d); setError(""); })
      .catch((e) => setError(String(e.message || e))), []);

  useEffect(() => { load(); }, [load]);

  function take(files) {
    const list = Array.from(files || []);
    if (list.length) setPending(list);
  }

  /* One document at a time carries the amount, date and vendor from the
     form; a folder does not, because they differ per document. So a folder
     lands with its kind and its relevance, and the facts are read onto each
     afterwards from the matching queue — which is where somebody has the
     document open in front of them anyway. */
  const several = pending.length > 1;

  async function upload() {
    if (!pending.length) return;
    setBusy(true);
    let filed = 0, already = 0;
    try {
      for (const file of pending) {
        const form = new FormData();
        form.append("file", file);
        form.append("kind", kind);
        form.append("period", "2025");
        form.append("relevance", relevance);
        if (!several) {
          /* A blank stays blank. "There is no amount on this document" and
             "nobody has read it off yet" are different facts, and the
             second must never be written as a zero. */
          for (const [k, v] of Object.entries(facts)) if (v) form.append(k, v);
        }
        const r = await api.uploadEvidence(form);
        if (r.deduplicated) already += 1; else filed += 1;
      }
      toast.ok(
        [filed && `${filed} document${filed === 1 ? "" : "s"} filed`,
         already && `${already} already on file — the same bytes, stored once`]
          .filter(Boolean).join("; "));
      setPending([]); setRelevance("");
      setFacts({ doc_amount: "", doc_date: "", vendor_name: "" });
      await load();
      await loadProposals();
    } catch (e) {
      setError(String(e.message || e));
      toast.fail(String(e.message || e));
    }
    setBusy(false);
  }

  const loadProposals = useCallback(() => {
    if (!canWrite) return Promise.resolve();
    return api.documentProposals()
      .then((d) => { setProposals(d); setPicked(new Set(
        d.documents.filter((x) => x.proposes).map((x) => x.evidence_id))); })
      .catch((e) => setError(String(e.message || e)));
  }, [canWrite]);

  useEffect(() => { loadProposals(); }, [loadProposals]);

  async function confirmPicked() {
    const rows = (proposals?.documents || [])
      .filter((d) => d.proposes && picked.has(d.evidence_id));
    if (!rows.length) return;
    setBusy(true);
    try {
      await api.attachDocuments(rows.map((d) => ({
        evidence_id: d.evidence_id,
        target_type: d.target.target_type,
        target_id: d.target.target_id,
        relevance: d.target.because,
      })));
      toast.ok(`${rows.length} document${rows.length === 1 ? "" : "s"} attached. `
               + `Citing one on a judgment is what raises its grade.`);
      await load();
      await loadProposals();
    } catch (e) {
      toast.fail(String(e.message || e));
    }
    setBusy(false);
  }

  /* Three groups, because "no proposal" covers two different situations and
     collapsing them buried the proposals. */
  const docs = proposals?.documents || [];
  const matched = docs.filter((d) => d.proposes);
  const ambiguous = docs.filter((d) => !d.proposes && d.doc_amount);
  const unread = docs.filter((d) => !d.proposes && !d.doc_amount);

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
          <input ref={input} type="file" hidden multiple
                 onChange={(e) => take(e.target.files)} />
          {pending.length ? (
            <>
              <div className="strong">
                {several ? `${pending.length} files` : pending[0].name}
              </div>
              <div className="quiet small">
                {size(pending.reduce((a, f) => a + f.size, 0))} · ready to file
                {several && " · drop a folder and they all land together"}
              </div>
            </>
          ) : (
            <>
              <div className="strong">
                Drop files here, or click to choose them
              </div>
              <div className="quiet small">
                A whole folder at once. Stored by content hash — the same
                document filed twice is stored once.
              </div>
            </>
          )}
        </div>

        {pending.length > 0 && (
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
            {!several && (
              <div className="facts-row">
                <Field label="Amount on the face of it"
                       hint="What lets it be matched to a cost. Leave blank if there is none — a blank stays unanswered, it does not become a zero.">
                  <input value={facts.doc_amount} inputMode="decimal"
                         onChange={(e) => setFacts({ ...facts, doc_amount: e.target.value })}
                         placeholder="1,234.56" />
                </Field>
                <Field label="Date on it">
                  <input value={facts.doc_date} type="date"
                         onChange={(e) => setFacts({ ...facts, doc_date: e.target.value })} />
                </Field>
                <Field label="Who it is from">
                  <input value={facts.vendor_name}
                         onChange={(e) => setFacts({ ...facts, vendor_name: e.target.value })}
                         placeholder="Vendor as it appears on the letterhead" />
                </Field>
              </div>
            )}
            {several && (
              <p className="quiet small">
                Amount, date and vendor differ per document, so they are read
                on afterwards — in Matching below, with the document open.
              </p>
            )}
            <div className="upload-actions">
              <button className="btn primary" disabled={busy} onClick={upload}>
                {busy ? "Filing…" : "File document"}
              </button>
              <button className="btn quiet" onClick={() => setPending([])}>Cancel</button>
            </div>
          </div>
        )}
        {error && <div className="signin-error" role="alert">{error}</div>}
      </Card>
      )}

      {canWrite && proposals && proposals.documents.length > 0 && (
      <Card title="Matching"
            variant="raised"
            aside={`${proposals.proposed} proposed of ${proposals.documents.length} unattached`}>
        <p className="quiet small" style={{ marginTop: -4, marginBottom: 12 }}>
          What each unattached document looks like it is for, and why. Nothing
          here has been applied — a proposal is never a decision. Where two
          costs fit a document equally well, neither is proposed: an
          attribution that could equally have been something else is not
          evidence.
        </p>

        {matched.length === 0 ? (
          <Empty mark="—" title="Nothing to propose">
            Every unattached document either has no amount read off it yet, or
            its amount matches no cost in the period.
          </Empty>
        ) : (
          <Table columns={[
            { label: "", align: "left" },
            { label: "Document", align: "left" },
            { label: "Says", align: "left" },
            { label: "Proposed for", align: "left" },
          ]}>
            {matched.map((d) => (
              <tr key={d.evidence_id}>
                <td className="l">
                  <input type="checkbox" checked={picked.has(d.evidence_id)}
                         aria-label={`Attach ${d.filename}`}
                         onChange={() => {
                           const next = new Set(picked);
                           next.has(d.evidence_id)
                             ? next.delete(d.evidence_id) : next.add(d.evidence_id);
                           setPicked(next);
                         }} />
                </td>
                <td className="l strong">
                  {d.filename || d.evidence_id}
                  <div className="quiet small mono-ref">{d.evidence_id}</div>
                </td>
                <td className="l small">
                  <span className="num">${money(d.doc_amount)}</span>
                  {d.doc_date && <> · {d.doc_date}</>}
                  {d.vendor_name && <div className="quiet">{d.vendor_name}</div>}
                </td>
                <td className="l wrap">
                  <div className="strong">{d.target.label}</div>
                  <div className="quiet small">{d.target.because}</div>
                </td>
              </tr>
            ))}
          </Table>
        )}

        {matched.length > 0 && (
          <div className="upload-actions" style={{ marginTop: 14 }}>
            <button className="btn primary" disabled={busy || picked.size === 0}
                    onClick={confirmPicked}>
              {busy ? "Attaching…"
                    : `Attach ${picked.size} document${picked.size === 1 ? "" : "s"}`}
            </button>
            <span className="quiet small">
              Each one is recorded under your name with its own reason.
              Attaching is not citing: a judgment is graded VERIFIED by citing
              the document in Classify, not by the document sitting beside it.
            </span>
          </div>
        )}

        {/* Two ways of not matching, and they mean different things. One is a
            document nobody has read the face of yet — work to do, and the
            same sentence thirty-two times. The other is a document that says
            what it is and finds no cost at that amount, which is worth
            reading one by one. Printing them in one list buried three
            proposals under thirty-two identical rows. */}
        {ambiguous.length > 0 && (
          <>
            <h4 className="section-h">Says what it is, and nothing fits</h4>
            <Table columns={[
              { label: "Document", align: "left" },
              { label: "Says", align: "left" },
              { label: "Why not", align: "left" },
            ]}>
              {ambiguous.map((d) => (
                <tr key={d.evidence_id} className="unmatched">
                  <td className="l strong">
                    {d.filename || d.evidence_id}
                    <div className="quiet small mono-ref">{d.evidence_id}</div>
                  </td>
                  <td className="l small">
                    <span className="num">${money(d.doc_amount)}</span>
                    {d.doc_date && <> · {d.doc_date}</>}
                    {d.vendor_name && <div className="quiet">{d.vendor_name}</div>}
                  </td>
                  <td className="l wrap quiet small">
                    {d.why_not}
                    {d.also_fits.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {d.also_fits.map((a) => a.label).join(" · ")}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          </>
        )}

        {unread.length > 0 && (
          <div className="unread-note">
            <button className="btn quiet sm" onClick={() => setShowUnread(!showUnread)}>
              {showUnread ? "−" : "+"} {unread.length} document
              {unread.length === 1 ? "" : "s"} nobody has read the face of yet
            </button>
            <span className="quiet small">
              {" "}Nothing is guessed from a filename. Record an amount — and a
              date and vendor where they are on it — and each can be matched.
            </span>
            {showUnread && (
              <ul className="quiet small unread-list">
                {unread.map((d) => (
                  <li key={d.evidence_id}>
                    {d.filename || d.evidence_id}
                    <span className="mono-ref"> {d.evidence_id}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
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
