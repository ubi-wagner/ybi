import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money } from "../api.js";
import { Card, Empty, PageHead, Pill, Stat, Table, Tick } from "../components/ui.jsx";

/* Form 990 Part IX — the Statement of Functional Expenses, and the documents
 * behind it.
 *
 * The classification queue records the 990 function on every judgment, so the
 * return is an aggregation of decisions already made rather than a second
 * exercise done from memory in the spring. That is the whole reason the
 * function is captured there.
 *
 * One rule this screen will not bend: cost nobody has judged is a column of
 * its own and is never spread across the three the return prints. The totals
 * are short by that amount, on purpose, and the screen says so at the top.
 * An allocation that quietly distributes unjudged cost is one nobody can
 * support in fieldwork. */

const FN = {
  PROGRAM: "Program services",
  MANAGEMENT_AND_GENERAL: "Management and general",
  FUNDRAISING: "Fundraising",
};

export default function Form990({ embedded = false }) {
  const [d, setD] = useState(null);
  const [docs, setDocs] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.reviewForm990().then(setD).catch((e) => setErr(String(e.message || e)));
    api.reviewAttachments().then(setDocs).catch(() => {});
  }, []);

  if (err) return <div className="page"><Card><Empty mark="!" title="Could not read the allocation">{err}</Empty></Card></div>;
  if (!d) return <div className="page" />;

  const { functions = [], categories = [], totals = {}, readiness } = d;
  const unallocated = Number(readiness?.unallocated || 0);
  const allocated = Number(readiness?.allocated || 0);
  const fileable = unallocated === 0 && Number(readiness?.controls_open || 0) === 0;
  const share = allocated + unallocated
    ? (allocated / (allocated + unallocated)) * 100 : 0;

  return (
    <div className={embedded ? "" : "page"}>
      {!embedded && (
      <PageHead title="Form 990, Part IX" schedule="G"
                aside={fileable
                  ? <Pill tone="good">Complete</Pill>
                  : <Pill tone="fail">Not fileable</Pill>}>
        The Statement of Functional Expenses, as the classification queue
        recorded it. Natural category down the side, function across the top —
        an aggregation of judgments already made, not a second exercise.
      </PageHead>
      )}

      {!fileable && (
        <div className="gate bad" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 5 }}>
            <Tick state="failed" /> The allocation is incomplete
          </div>
          <ul className="gate-list">
            {unallocated > 0 && (
              <li>
                <strong>{money(unallocated)} not classified to a function</strong>
                <span className="rowsub">
                  {" — "}it appears in its own column and is never spread
                  across the three the return prints. The totals below are
                  short by that amount, on purpose.
                </span>
              </li>
            )}
            {Number(readiness?.controls_open || 0) > 0 && (
              <li>
                <strong>{readiness.controls_open} cross-reference point(s) open</strong>
                <span className="rowsub">
                  {" — "}the ledger does not yet agree with its own statements.
                </span>
              </li>
            )}
            {Number(readiness?.uncertified_allocations || 0) > 0 && (
              <li>
                <strong>{readiness.uncertified_allocations} effort allocation(s) uncertified</strong>
                <span className="rowsub">
                  {" — "}2 CFR 200.430(i) wants the signature of the person
                  whose effort it was.
                </span>
              </li>
            )}
          </ul>
          <Link className="btn sm" to="/classify">Open the queue</Link>
        </div>
      )}

      <div className="grid four">
        <Stat label="Allocated to a function" size="lg" value={money(allocated)}
              tone={unallocated ? "warn" : "pass"} note={`${share.toFixed(1)}% of expense`} />
        <Stat label="Not yet classified" size="lg" value={money(unallocated)}
              tone={unallocated ? "fail" : "pass"} note="in no function" />
        <Stat label="Natural categories" size="lg" value={categories.length} />
        <Stat label="Documents on file" size="lg"
              value={docs ? docs.documents.length : "—"}
              note={docs ? `${docs.unattached} support nothing yet` : ""} />
      </div>

      <Card title="Statement of functional expenses"
            aside="Part IX" style={{ marginTop: 16 }}>
        {categories.length === 0 ? (
          <Empty mark="IX" title="Nothing in scope">
            Import the profit and loss, and the expense side appears here.
          </Empty>
        ) : (
          <Table columns={[
            { label: "Natural category", align: "left" },
            { label: "Lines" },
            ...functions.map((f) => ({ label: FN[f] || f })),
            { label: "Not yet classified" },
            { label: "Total" },
          ]}>
            {categories.map((c) => (
              <tr key={c.natural_category}>
                <td className="l">{c.natural_category}</td>
                <td className="amt rowsub">{c.lines}</td>
                {functions.map((f) => (
                  <td key={f} className="amt">
                    {Number(c[f] || 0) === 0
                      ? <span className="rowsub">—</span> : money(c[f])}
                  </td>
                ))}
                <td className="amt">
                  {Number(c.NOT_YET_CLASSIFIED || 0) === 0
                    ? <span className="rowsub">—</span>
                    : <span className="warnish">{money(c.NOT_YET_CLASSIFIED)}</span>}
                </td>
                <td className="amt strong">{money(c.total)}</td>
              </tr>
            ))}
            <tr className="total-row">
              <td className="l"><strong>Total</strong></td>
              <td />
              {functions.map((f) => (
                <td key={f} className="amt strong">{money(totals[f])}</td>
              ))}
              <td className="amt strong">
                <span className="warnish">{money(totals.NOT_YET_CLASSIFIED)}</span>
              </td>
              <td className="amt strong">{money(totals.total)}</td>
            </tr>
          </Table>
        )}
      </Card>

      <Card title="Attachments"
            aside="What the return rests on"
            style={{ marginTop: 16 }}>
        {!docs || docs.documents.length === 0 ? (
          <div className="rowsub">
            No documents on file for this period. A return with no supporting
            file behind it is a set of assertions.
          </div>
        ) : (
          <Table columns={[
            { label: "Document", align: "left" },
            { label: "Kind", align: "left" },
            { label: "Supports" },
            { label: "From", align: "left" },
            { label: "Received", align: "left" },
            { label: "", align: "left", width: "96px" },
          ]}>
            {docs.documents.map((f) => (
              <tr key={f.evidence_id}>
                <td className="l wrap">{f.filename}</td>
                <td className="l rowsub">{f.kind}</td>
                <td className="amt">
                  {f.supports ? f.supports
                    : <span className="rowsub" title="On file, attached to nothing">—</span>}
                </td>
                <td className="l rowsub">{f.from_whom}</td>
                <td className="l rowsub">{String(f.received_at || "").slice(0, 10)}</td>
                <td className="l">
                  <a className="btn sm" href={api.evidenceFileUrl(f.evidence_id)} download>
                    Open
                  </a>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card variant="quiet" title="Take it away"
            aside="Part IX and the attachment register, in one workbook that says on its first sheet what is unfinished"
            style={{ marginTop: 16 }}>
        <div className="btn-row">
          <a className="btn" href={api.form990Url()} download>Form 990 Part IX (.xlsx)</a>
          <a className="btn" href={api.auditPackageUrl()} download>Whole cost record (.xlsx)</a>
        </div>
      </Card>
    </div>
  );
}
