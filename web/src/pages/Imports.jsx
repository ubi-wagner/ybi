import React, { useCallback, useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Empty, PageHead, Pill, Stat, Table, Tick, useToast } from "../components/ui.jsx";

const REPORTS = [
  ["GENERAL_LEDGER", "General Ledger", "The spine. Accrual, all accounts, full year."],
  ["PROFIT_LOSS", "Profit & Loss", "Control totals every derived figure ties to."],
  ["BALANCE_SHEET", "Balance Sheet", "Asset basis and the depreciation question."],
  ["TIME_ACTIVITY", "Time Activities", "Makes labour contemporaneous rather than reconstructed."],
];

export default function Imports() {
  const toast = useToast();
  const [batches, setBatches] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [hot, setHot] = useState("");

  const load = useCallback(() => api.imports().then(setBatches).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const send = async (file, report) => {
    setBusy(report);
    try {
      const r = await api.importUpload(file, report);
      await api.importParse(r.batch_id);
      const p = await api.importPreview(r.batch_id);
      setPreview({ ...p, batch_id: r.batch_id, name: file.name });
      load();
    } catch (e) {
      toast(String(e.message || e), { tone: "bad", sticky: true });
    } finally {
      setBusy("");
    }
  };

  /* Promoting a batch used to be a bare `fetch(...).then(x => x.json())`
     with no status check and no `catch`. A refusal — a batch already
     accepted, a subtotal that does not tie — comes back as `{detail: "..."}`
     with a 4xx, `lines_promoted` is undefined, and the `?? 0` printed
     "0 lines added to the ledger" in the tone this screen uses for success.
     The ledger is the spine of the whole engagement; an import that did not
     happen must never read as one that did. */
  const accept = async () => {
    setBusy("accept");
    try {
      const r = await api.importAccept(preview.batch_id);
      const n = Number(r.lines_promoted ?? 0);
      if (n === 0) {
        /* The server answered, and what it did was nothing. Sticky, because
           a warning that fades while somebody is reading the preview is the
           same as no warning at all. */
        toast.warn("The batch was accepted and no line reached the ledger. "
                   + "Every line was already on it, or the batch held none. "
                   + "Check the register below before importing again.",
                   { sticky: true });
      } else {
        toast.ok(`${n.toLocaleString()} lines added to the ledger`);
      }
      setPreview(null);
      load();
    } catch (e) {
      toast.fail(String(e.message || e));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="page">
      <PageHead title="Import from QuickBooks" schedule="A">
        Export as CSV where QuickBooks offers it — the Excel path merges cells and inserts
          formatting rows. Nothing reaches the ledger until every account subtotal ties to
          QuickBooks' own printed totals.
      </PageHead>

      <div className="grid two">
        {REPORTS.map(([key, label, why]) => (
          <label key={key}
                 className={`dropzone ${hot === key ? "hot" : ""}`}
                 onDragOver={(e) => { e.preventDefault(); setHot(key); }}
                 onDragLeave={() => setHot("")}
                 onDrop={(e) => {
                   e.preventDefault(); setHot("");
                   e.dataTransfer.files[0] && send(e.dataTransfer.files[0], key);
                 }}>
            <div style={{ fontWeight: 600, color: "var(--ink)" }}>{label}</div>
            <div className="rowsub" style={{ margin: "4px 0 10px" }}>{why}</div>
            <span className="pill">{busy === key ? "Parsing…" : "Drop a file, or choose one"}</span>
            <input type="file" accept=".csv,.xlsx" style={{ display: "none" }}
                   onChange={(e) => e.target.files[0] && send(e.target.files[0], key)} />
          </label>
        ))}
      </div>

      {preview && (
        <Card variant="raised" style={{ marginTop: 18 }}
              title={`Preview — ${preview.name}`}
              aside={preview.acceptable ? "Ties to QuickBooks" : "Does not tie"}>
          <div className="stat-row" style={{ marginBottom: 14 }}>
            <Stat label="Subtotals checked" size="lg"
                  value={preview.reconciliation?.subtotal_rows ?? 0} />
            <Stat label="Mismatches" size="lg"
                  tone={preview.reconciliation?.mismatches ? "fail" : "pass"}
                  value={preview.reconciliation?.mismatches ?? 0} />
            <Stat label="Parsed" size="lg" value={money(preview.reconciliation?.parsed)} />
          </div>

          {preview.mismatches?.length > 0 && (
            <Table columns={[
              { label: "Account", align: "left" }, { label: "QuickBooks" },
              { label: "Parsed" }, { label: "Variance" },
            ]}>
              {preview.mismatches.map((m) => (
                <tr key={m.account}>
                  <td className="l">{m.account}</td>
                  <td>{money(m.printed_total)}</td>
                  <td>{money(m.parsed_total)}</td>
                  <td className="amt neg">{money(m.variance)}</td>
                </tr>
              ))}
            </Table>
          )}

          {preview.objective_hints?.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="card-title" style={{ marginBottom: 4 }}>
                Cost objectives QuickBooks already knows
              </div>
              <div className="rowsub" style={{ marginBottom: 8 }}>
                From the Customer:Job field. These become classification proposals, so nobody
                retypes what QuickBooks already recorded.
              </div>
              <Table columns={[{ label: "Objective", align: "left" }, { label: "Lines" }, { label: "Amount" }]}>
                {preview.objective_hints.slice(0, 12).map((h) => (
                  <tr key={h.objective_hint}>
                    <td className="l"><Pill tone="accent">{h.objective_hint}</Pill></td>
                    <td>{h.lines}</td>
                    <td className="amt strong">{money(h.amount)}</td>
                  </tr>
                ))}
              </Table>
            </div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 16, alignItems: "center", flexWrap: "wrap" }}>
            {/* Disabled while it runs. A second press promotes nothing and
                meets "already accepted", which is a refusal for a thing the
                person did not do. */}
            <button className="primary" onClick={accept}
                    disabled={!preview.acceptable || busy === "accept"}>
              {busy === "accept" ? "Adding to the ledger…" : "Accept import"}
            </button>
            <button onClick={() => setPreview(null)}>Discard</button>
            {!preview.acceptable && (
              <span className="rowsub" style={{ color: "var(--fail)" }}>
                Subtotals do not tie. Nothing will be written — a database trigger enforces it.
              </span>
            )}
          </div>
        </Card>
      )}

      <div style={{ marginTop: 22 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Import history</div>
        {batches.length === 0 ? (
          <Card><Empty mark="↥" title="No imports yet">
            Drop a QuickBooks General Ledger export above to begin.
          </Empty></Card>
        ) : (
          <Table columns={[
            { label: "", width: 34, align: "left" }, { label: "File", align: "left" },
            { label: "Report", align: "left" }, { label: "Status", align: "left" },
            { label: "Size" }, { label: "Uploaded", align: "left" },
          ]}>
            {batches.map((b) => (
              <tr key={b.batch_id} className="hoverable">
                <td className="l">
                  <Tick state={b.status === "ACCEPTED" ? "done" : b.status === "REJECTED" ? "failed" : "open"} />
                </td>
                <td className="l">{b.original_name}</td>
                <td className="l rowsub">{b.report.replace(/_/g, " ").toLowerCase()}</td>
                <td className="l"><Pill tone={b.status === "ACCEPTED" ? "pass" : ""}>{b.status}</Pill></td>
                <td>{(b.byte_size / 1024).toFixed(0)} KB</td>
                <td className="l rowsub">{new Date(b.uploaded_at).toLocaleString()}</td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </div>
  );
}
