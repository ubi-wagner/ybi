import React, { useCallback, useEffect, useState } from "react";
import { api, explain, money } from "../api.js";
import {
  Card, Drawer, Empty, PageHead, Pill, Stat, Table, Tick, useToast,
} from "../components/ui.jsx";

/* Schedule G and the invoice register, as documents.
 *
 * Two things the reconciliation needs on paper rather than on a screen.
 *
 * The timesheet report is the labour evidence behind the fringe base. The
 * eleventh control compares the payroll register to the ledger's wage
 * accounts, and a reviewer who sees a difference then wants to know which
 * people it consists of — which is a workbook, not a table with a scrollbar.
 *
 * The invoice regeneration renders off the register onto the face the
 * America Makes invoices already use, because a restatement has to be issued
 * on something NCDMM's payables recognises. An invoice already issued
 * renders as a reproduction and says so on its face; that distinction is the
 * point and it is repeated here so nobody meets it for the first time on a
 * document they have already sent.
 */

function stamp() {
  return new Date().toISOString().slice(0, 10);
}

export default function Reports({ actor }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const toast = useToast();

  const load = useCallback(() => {
    api.invoicesToRender()
      .then(setData)
      .catch((e) => toast.show(explain(e), { tone: "fail" }));
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  function take(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function file(inv) {
    setBusy(inv.invoice_number);
    try {
      const r = await api.fileInvoice(inv.invoice_number);
      toast.show(r.deduplicated
        ? "That rendering was already on file."
        : `Invoice ${r.invoice_number} filed as ${r.evidence_id}`);
      load();
    } catch (e) {
      toast.show(explain(e), { tone: "fail" });
    } finally {
      setBusy("");
    }
  }

  const invoices = data?.invoices || [];
  const noIndirect = invoices.filter((i) => i.no_indirect_billed);

  return (
    <div className="page">
      <PageHead title="Reports" schedule="G">
        The two documents the reconciliation needs on paper: the labour
          evidence behind the fringe base, and the invoice register rendered
          onto the face it was issued on.
      </PageHead>

      <Card variant="raised" title="Timesheet and effort report"
            aside={<Pill>Schedule G</Pill>}>
        <p className="lede" style={{ marginTop: 0 }}>
          Coverage, the effort distribution, who has certified and every entry
          with what it was reconstructed from — with the eleventh control on
          the first sheet, so a reviewer can see whether the payroll register
          and the ledger's wage accounts agree before they read a single
          figure.
        </p>
        <div className="btn-row">
          <button className="btn primary" onClick={() => {
            take(api.timesheetReportUrl(),
                 `YBI-timesheet-report-${stamp()}.xlsx`);
            toast.show("Building the workbook…");
          }}>
            Download the whole organisation
          </button>
          {actor?.employee_key && (
            <button className="btn" onClick={() => {
              take(api.timesheetReportUrl("", actor.employee_key),
                   `YBI-timesheet-${actor.employee_key}-${stamp()}.xlsx`);
            }}>
              Just mine ({actor.employee_key})
            </button>
          )}
        </div>
      </Card>

      <Card title="Invoices on the register"
            aside={noIndirect.length
              ? <Pill tone="warn">
                  {noIndirect.length} bill no indirect
                </Pill>
              : null}>
        {!invoices.length ? (
          <Empty mark="—" title="No invoices yet">
            The invoice register is empty for this period. Load the invoices
            and they will be renderable here.
          </Empty>
        ) : (
          <Table columns={[
            { label: "", align: "left", width: "34px" },
            { label: "Invoice", align: "left" },
            { label: "Project", align: "left" },
            { label: "Billed to", align: "left" },
            { label: "Direct" },
            { label: "Indirect" },
            { label: "Total" },
            { label: "", align: "left", width: "250px" },
          ]}>
            {invoices.map((i) => (
              <tr key={i.invoice_id}>
                <td className="l">
                  <Tick state={i.evidence_id ? "done" : "open"}
                        title={i.evidence_id
                          ? "a rendering is on file"
                          : "not yet filed"} />
                </td>
                <td className="l">
                  <div style={{ fontWeight: 600 }}>#{i.invoice_number}</div>
                  <div className="rowsub">
                    {String(i.invoice_date).slice(0, 10)} · {i.status}
                  </div>
                </td>
                <td className="l rowsub">{i.objective_id}</td>
                <td className="l rowsub wrap">{i.bill_to_name || "—"}</td>
                <td className="amt">{money(i.mtdc_as_billed)}</td>
                <td className={"amt" + (i.no_indirect_billed ? " warnish" : "")}>
                  {i.no_indirect_billed ? "none" : money(i.indirect)}
                </td>
                <td className="amt"><strong>{money(i.total)}</strong></td>
                <td className="l">
                  <div className="btn-row">
                    <button className="btn sm" onClick={() => setPreview(i)}>
                      Read
                    </button>
                    <button className="btn sm ghost" onClick={() =>
                      take(api.invoicePdfUrl(i.invoice_number),
                           `YBI-invoice-${i.invoice_number}.pdf`)}>
                      Download
                    </button>
                    {actor?.may_seal && (
                      <button className="btn sm ghost"
                              disabled={busy === i.invoice_number}
                              onClick={() => file(i)}>
                        {busy === i.invoice_number ? "Filing…" : "File it"}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        )}
        <p className="rowsub" style={{ marginTop: 14 }}>
          An invoice already issued renders as a <strong>reproduction from the
          register</strong> and says so on its face — the document of record
          is the one the sponsor holds. Only a draft or a restatement renders
          as something YBI is issuing. Filing one puts it in the document
          library with a hash, where an auditor will find it without asking.
        </p>
      </Card>

      <Drawer open={Boolean(preview)} wide
              title={preview ? `Invoice ${preview.invoice_number}` : ""}
              subtitle={preview && [
                preview.objective_id,
                preview.status,
                `${money(preview.total)}`,
              ].filter(Boolean).join(" · ")}
              onClose={() => setPreview(null)}
              footer={preview && (
                <div className="btn-row">
                  <button className="btn primary" onClick={() =>
                    take(api.invoicePdfUrl(preview.invoice_number),
                         `YBI-invoice-${preview.invoice_number}.pdf`)}>
                    Download a copy
                  </button>
                  <button className="ghost" onClick={() => setPreview(null)}>
                    Close
                  </button>
                </div>
              )}>
        {preview && (
          /* No `sandbox` attribute — see the note in Library.jsx. Chromium
             will not render a PDF inside a sandboxed frame, and the
             Content-Security-Policy on the response does the same job. */
          <iframe className="doc-frame" title={`Invoice ${preview.invoice_number}`}
                  src={api.invoicePdfUrl(preview.invoice_number)} />
        )}
      </Drawer>
    </div>
  );
}
