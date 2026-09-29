import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, explain } from "../api.js";
import FormVariability from "../components/FormVariability.jsx";
import {
  Card, Drawer, Empty, Keys, PageHead, Pill, Search, Segmented, Stat, Table,
  Tick, useToast,
} from "../components/ui.jsx";

/* The document library.
 *
 * Every other document screen answers a question about a document's *state*:
 * what did I send in, what has nobody filed yet. This one answers the
 * question an auditor actually arrives with, which is "show me the lease".
 * Until it existed, a reader could see that EV-9f2c1a4b0e77 supported the
 * less-than-arm's-length rental test and had no way to read it.
 *
 * Two things it does deliberately.
 *
 * It opens a document in the page rather than in a downloads folder. Someone
 * checking eleven attachments against eleven figures should not end the
 * afternoon with eleven files in ~/Downloads and no idea which was which. The
 * download is still one key away, because a workpaper that leaves with the
 * file is a different and equally real need.
 *
 * And it shows everything it cannot preview as exactly that, rather than
 * hiding it. A spreadsheet is not previewable here and saying so is more use
 * than a row that silently does nothing when clicked.
 */

const KIND_LABELS = {
  receipt: "Receipt", invoice: "Invoice", contract: "Contract",
  lease: "Lease", project_plan: "Project plan", market_comp: "Market comparable",
  photo: "Photograph", statement: "Statement", document: "Document",
  "grant-agreement": "Grant agreement", "closeout-letter": "Closeout letter",
  "asset-register": "Asset register", "lease-schedule": "Lease schedule",
  policy: "Policy", timesheet: "Timesheet", payroll: "Payroll",
};
const label = (k) => KIND_LABELS[k] || k;

function size(bytes) {
  const n = Number(bytes || 0);
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function Library() {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [period, setPeriod] = useState("");
  const [attached, setAttached] = useState("");
  const [cursor, setCursor] = useState(0);
  const [open, setOpen] = useState(null);
  const [loading, setLoading] = useState(true);
  const search = useRef(null);
  const toast = useToast();

  const load = useCallback(() => {
    setLoading(true);
    api.documentLibrary({ q, kind, period, attached })
      .then((d) => { setData(d); setCursor(0); })
      .catch((e) => toast.show(explain(e), { tone: "fail" }))
      .finally(() => setLoading(false));
  }, [q, kind, period, attached, toast]);

  /* Typing in a search box should not be twelve requests. A short pause is
     long enough to finish a vendor name and short enough that nobody
     notices it. */
  useEffect(() => {
    const t = setTimeout(load, q ? 220 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const rows = useMemo(() => data?.documents || [], [data]);
  const current = rows[cursor];

  const download = useCallback((doc) => {
    if (!doc) return;
    /* A link the browser follows itself, so the session cookie goes with it
       and the bytes never pass through JavaScript. */
    const a = document.createElement("a");
    a.href = api.documentDownloadUrl(doc.evidence_id);
    a.download = doc.filename || doc.evidence_id;
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast.show(`${doc.filename || doc.evidence_id} — downloading`);
  }, [toast]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") {
        if (e.key === "Escape") e.target.blur();
        return;
      }
      if (open) return;             // the drawer has its own Escape
      if (e.key === "j") setCursor((c) => Math.min(c + 1, rows.length - 1));
      else if (e.key === "k") setCursor((c) => Math.max(c - 1, 0));
      else if (e.key === "Enter" && current) {
        if (current.inline_safe) setOpen(current); else download(current);
      } else if (e.key === "d") download(current);
      else if (e.key === "/") { e.preventDefault(); search.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows.length, current, open, download]);

  const filtering = Boolean(q || kind || period || attached);

  return (
    <div className="page">
      <PageHead title="Document library" schedule="E" aside={
        <Keys hints={[["j/k", "move"], ["Enter", "open"], ["d", "download"],
                      ["/", "search"]]} />
      }>
        Everything anybody has sent in, whether or not it has been filed
          against a cost yet. Open one here to read it, or take a copy if it
          is going into a workpaper. Every open and every copy is recorded
          against your name — which is what makes it safe for this screen to
          show the whole shelf.
      </PageHead>

      <div className="grid three">
        <Stat label="Documents on file" value={data?.total ?? "—"} size="lg" />
        <Stat label="Supporting a figure" value={data?.total_attached ?? "—"}
              size="lg" note="somebody has said what these prove" />
        <Stat label="On the volume" value={size(data?.total_bytes)} size="lg" />
      </div>

      {/* Under the counts and above the shelf: it is about the whole
          collection rather than about any one document, and somebody
          looking for a single lease should not have to scroll past it. */}
      <FormVariability />

      <Card variant="raised" title="Find one" aside={
        filtering
          ? <button className="ghost" onClick={() => {
              setQ(""); setKind(""); setPeriod(""); setAttached("");
            }}>Clear</button>
          : null
      }>
        <div className="filter-row">
          <div style={{ flex: "2 1 260px" }}>
            <Search value={q} onChange={setQ}
                    placeholder="Lease, vendor, who sent it, or EV-…" />
          </div>
          <label className="field inline">
            <span className="field-label">Kind</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All kinds</option>
              {(data?.kinds || []).map((k) => (
                <option key={k.kind} value={k.kind}>
                  {label(k.kind)} ({k.n})
                </option>
              ))}
            </select>
          </label>
          <label className="field inline">
            <span className="field-label">Period</span>
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="">All periods</option>
              {(data?.periods || []).map((p) => (
                <option key={p.period} value={p.period}>
                  {p.period} ({p.n})
                </option>
              ))}
            </select>
          </label>
          <div className="field inline">
            <span className="field-label">Filed</span>
            <Segmented value={attached} onChange={setAttached} options={[
              ["", "Any"], ["yes", "Filed"], ["no", "Waiting"],
            ]} />
          </div>
        </div>
      </Card>

      <Card title={filtering ? `${data?.matched ?? 0} matching` : "Everything on file"}
            aside={data?.truncated
              ? <Pill tone="warn">showing the first {rows.length} — narrow the search</Pill>
              : null}>
        {loading && !rows.length ? (
          <Empty mark="⌛" title="Looking">Reading the shelf.</Empty>
        ) : !rows.length ? (
          <Empty mark="—" title={filtering ? "Nothing matches" : "Nothing on file"}>
            {filtering
              ? "No document matches that. Try the vendor, or the identifier from the workpaper."
              : "When somebody sends a document in, it appears here."}
          </Empty>
        ) : (
          <Table columns={[
            { label: "", align: "left", width: "34px" },
            { label: "Document", align: "left" },
            { label: "Kind", align: "left" },
            { label: "Sent in by", align: "left" },
            { label: "Received", align: "left" },
            { label: "Size", align: "right" },
            /* Wide enough for "no preview" and Download side by side.
               At 160px they wrapped, and a column where half the rows are
               one line tall and half are two reads as a rendering fault
               rather than as a distinction worth making. */
            { label: "", align: "left", width: "205px" },
          ]}>
            {rows.map((d, i) => (
              <tr key={d.evidence_id}
                  className={i === cursor ? "picked" : ""}
                  onClick={() => setCursor(i)}
                  onDoubleClick={() => d.inline_safe ? setOpen(d) : download(d)}>
                <td className="l">
                  <Tick state={d.is_attached ? "done" : "open"}
                        title={d.is_attached ? "supporting a figure" : "not yet filed"} />
                </td>
                <td className="l wrap">
                  <div style={{ fontWeight: 600 }}>
                    {d.filename || d.evidence_id}
                  </div>
                  <div className="rowsub">
                    {d.suggested_for || d.note || d.evidence_id}
                  </div>
                </td>
                <td className="l rowsub">{label(d.kind)}</td>
                <td className="l rowsub">
                  {d.uploaded_by_name || d.received_from ||
                    <span className="rowsub">—</span>}
                  {/* Paper somebody sent in, or this system's own arithmetic
                      in a nice font. A generated document corroborates
                      nothing the record does not already say, and a reader
                      going through a shelf should not have to open one to
                      find that out. */}
                  {d.is_generated && (
                    <div><Pill>generated from the record</Pill></div>
                  )}
                </td>
                <td className="l rowsub">{String(d.received_at).slice(0, 10)}</td>
                <td className="num">{size(d.byte_size)}</td>
                <td className="l">
                  <div className="btn-row">
                    {d.inline_safe ? (
                      <button className="btn sm" onClick={(e) => {
                        e.stopPropagation(); setOpen(d);
                      }}>Read</button>
                    ) : (
                      /* Said rather than hidden. A row that silently does
                         nothing when clicked is worse than one that explains
                         itself — and a spreadsheet opening in the
                         application it belongs to is the right outcome, not
                         a gap. */
                      <span className="nopreview" title={
                        `${d.mime_type || "unknown type"} — this one opens in ` +
                        `the application it belongs to`}>no preview</span>
                    )}
                    <button className="btn sm ghost" onClick={(e) => {
                      e.stopPropagation(); download(d);
                    }}>Download</button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Drawer open={Boolean(open)} wide
              title={open?.filename || open?.evidence_id || ""}
              subtitle={open && [
                label(open.kind),
                open.period,
                open.uploaded_by_name && `sent in by ${open.uploaded_by_name}`,
                size(open.byte_size),
              ].filter(Boolean).join(" · ")}
              onClose={() => setOpen(null)}
              footer={open && (
                <div className="btn-row">
                  <button className="btn primary" onClick={() => download(open)}>
                    Download a copy
                  </button>
                  <button className="ghost" onClick={() => setOpen(null)}>Close</button>
                </div>
              )}>
        {open && (
          <>
            <div className="doc-meta">
              <div><span className="field-label">Identifier</span>
                   <code>{open.evidence_id}</code></div>
              <div><span className="field-label">What it relates to</span>
                   {open.suggested_for || <span className="rowsub">not said</span>}</div>
              <div><span className="field-label">Filed against</span>
                   {open.is_attached
                     ? <Pill tone="accent">
                         {open.attachments} item{open.attachments === 1 ? "" : "s"}
                         {open.supports ? ` — ${open.supports}` : ""}
                       </Pill>
                     : <Pill>nobody has said what this proves</Pill>}</div>
              {open.note && (
                <div><span className="field-label">Note from the sender</span>
                     {open.note}</div>
              )}
            </div>
            {/* Deliberately no `sandbox` attribute, and it must stay that
                way. Chromium refuses to run its PDF viewer inside a
                sandboxed frame — every value of the attribute, `allow-scripts`
                included — and renders "This page has been blocked" where
                the lease should be. Twelve of the eighteen foundational
                documents are PDFs, so the attribute turns this panel off.

                Nothing is given up by omitting it. The sandbox that matters
                is the one the server sets in the response's
                Content-Security-Policy, which Chromium honours *and* still
                renders a PDF under; it puts the document in an opaque
                origin the same way, and being on the response it travels
                with the file even when it is opened somewhere other than
                this frame. On top of that the type is read from the bytes
                at upload, so HTML is served as text/plain under nosniff and
                never reaches a parser at all. */}
            <iframe className="doc-frame" title={open.filename || open.evidence_id}
                    src={api.documentViewUrl(open.evidence_id)} />
          </>
        )}
      </Drawer>
    </div>
  );
}
