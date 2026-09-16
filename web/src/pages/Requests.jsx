import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, count, explain, money } from "../api.js";
import { Card, Empty, Field, PageHead, Pill, Stat, Table, Tick, useToast }
  from "../components/ui.jsx";

/* Asking for what is missing.
 *
 * Three things are missing from the record and none of them can be inferred:
 * which assets federal money paid for, who uses which square foot, and an
 * address for the thirty-seven people who have to sign their own effort. All
 * three live in somebody else's filing cabinet, and each has a lead time in
 * weeks.
 *
 * The API for this has been complete and proved end to end since it was
 * built. There was no screen, so issuing a workbook or chasing a reply was
 * an API call, and nobody at YBI could see what was outstanding — which is
 * the whole point of a thing with a lead time in weeks.
 *
 * The shape of the screen follows the shape of the cycle, because that is
 * what somebody is holding in their head: what we asked for, what has come
 * back, what it says, and only then what it will do.
 *
 * Reading it takes `require_reader`, which is what the router asks for.
 * Accepting takes the portfolio that owns the data — INVENTORY, FACILITIES,
 * the administrator for the roster — so the Accept button is offered only to
 * somebody who holds it. The nav is not stricter than the API and not
 * looser: a person who may read this page but not accept can see everything
 * on it, and is told whose judgment the last step is. */

const when = (t) =>
  !t ? "—" : new Date(t).toLocaleDateString(undefined,
    { year: "numeric", month: "short", day: "numeric" });

const STATE = {
  ISSUED: ["open", "Asked for"],
  RECEIVED: ["flagged", "Came back"],
  ACCEPTED: ["done", "On the record"],
  WITHDRAWN: ["open", "Withdrawn"],
};

/* Which portfolio may write each form's answers into the record. The gates
   themselves are in requests.py; this decides whether to offer the button,
   and a mismatch shows as a 403 the person could not have predicted. */
const OWNS = {
  ASSET_REGISTER: "INVENTORY",
  SPACE_INVENTORY: "FACILITIES",
  PEOPLE_ROSTER: "admin",
};

function mayAccept(actor, form) {
  const needs = OWNS[form];
  if (!needs) return false;
  if (needs === "admin") return Boolean(actor?.is_admin);
  const held = actor?.portfolios || [];
  return held.includes(needs) || held.includes("CONTROLLER");
}

export default function Requests({ actor }) {
  const [forms, setForms] = useState(null);
  const [data, setData] = useState(null);
  const [checks, setChecks] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);        // request_id whose preview is open
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(null);    // form name being issued
  const [sentTo, setSentTo] = useState("");
  const [note, setNote] = useState("");
  const replyTo = useRef(null);
  const file = useRef(null);
  const toast = useToast();

  const load = useCallback(() =>
    Promise.all([api.requestForms(), api.requests(), api.verificationStatus()])
      .then(([f, d, v]) => { setForms(f); setData(d); setChecks(v); setError(""); })
      .catch((e) => setError(explain(e))), []);

  useEffect(() => { load(); }, [load]);

  async function issue(form) {
    if (!sentTo.trim()) { toast.warn("Say who it is going to."); return; }
    setBusy(true);
    try {
      const r = await api.issueRequest(form, { sent_to: sentTo, note });
      toast.ok(`Asked. Request ${r.request_id} — download the workbook and `
               + `send it to ${sentTo}.`);
      setAsking(null); setSentTo(""); setNote("");
      await load();
      window.location.href = api.requestWorkbookUrl(r.request_id);
    } catch (e) { toast.fail(explain(e)); }
    setBusy(false);
  }

  async function sendBack(id, f) {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", f);
      await api.replyToRequest(id, form);
      toast.ok("Filed. Read the preview before accepting — it says what will "
               + "be written and what will not.");
      replyTo.current = null;
      await load();
      await show(id);
    } catch (e) { toast.fail(explain(e)); }
    setBusy(false);
  }

  const show = useCallback(async (id) => {
    if (open === id) { setOpen(null); setPreview(null); return; }
    setOpen(id); setPreview(null);
    try { setPreview(await api.requestPreview(id)); }
    catch (e) { toast.fail(explain(e)); setOpen(null); }
  }, [open, toast]);

  async function accept(id) {
    setBusy(true);
    try {
      const r = await api.acceptRequest(id);
      /* Accepting is one-way — the request moves to ACCEPTED and a second
         acceptance is a 409 — so a reply that wrote nothing is the end of
         that request, not a step in it. "0 rows written" in green is the
         shape this system keeps finding: an honest number in a sentence that
         reads as success. Every count it held back is named, because that is
         the work: `held_back` is what came with a problem, `untouched` is
         what nobody filled in, and the two lead somewhere different. */
      const left = [r.held_back && `${r.held_back} held back and named`,
                    r.untouched && `${r.untouched} left blank`]
        .filter(Boolean).join(", ");
      if (!r.written) {
        toast.warn(`Nothing was written from this reply${left ? ` — ${left}` : ""}. `
                   + "The request is closed; issue a new one to ask again.",
                   { sticky: true });
      } else {
        toast.ok(`${r.written} row${r.written === 1 ? "" : "s"} written`
                 + (left ? `, ${left}` : ""));
      }
      setOpen(null); setPreview(null);
      await load();
    } catch (e) { toast.fail(explain(e)); }
    setBusy(false);
  }

  const rows = data?.requests || [];
  const outstanding = rows.filter((r) => r.state === "ISSUED");
  const waiting = rows.filter((r) => r.state === "RECEIVED");
  const overdue = outstanding.filter((r) => r.overdue);

  return (
    <div className="dash">
      <PageHead title="Requests" schedule="E">
        What is missing from the record, who was asked for it, and what came
        back.
      </PageHead>

      {error && <div className="signin-error" role="alert">{error}</div>}

      <div className="stat-row">
        <Stat label="Asked for, not back" value={outstanding.length} size="lg" />
        <Stat label="Waiting on a judgment" value={waiting.length}
              note={waiting.length ? "read the preview" : ""} />
        <Stat label="Over two weeks" value={overdue.length}
              tone={overdue.length ? "warn" : ""} />
      </div>

      {/* ── What can be asked for ───────────────────────────────────── */}
      <Card title="Ask for something" variant="raised"
            aside="Each goes out pre-filled from what YBI already has on file">
        {!forms ? <Empty mark="…" title="Loading" /> : (
          <div className="ask-grid">
            {forms.map((f) => (
              <div key={f.name} className="card quiet ask">
                <div className="strong">{f.title}</div>
                <div className="quiet small">For {f.for_whom}</div>
                <p className="small">{f.purpose}</p>
                <p className="quiet small"><em>{f.consequence}</em></p>
                <div className="quiet small">
                  {f.columns} columns · {f.required.length} required:{" "}
                  {f.required.join(", ")}
                </div>
                {asking === f.name ? (
                  <div className="upload-form">
                    <Field label="Who it is going to">
                      <input value={sentTo} autoFocus
                             onChange={(e) => setSentTo(e.target.value)}
                             placeholder="e.g. Facilities, or a person's name" />
                    </Field>
                    <Field label="Anything to say with it"
                           hint="Goes on the record beside the ask.">
                      <input value={note} onChange={(e) => setNote(e.target.value)} />
                    </Field>
                    <div className="upload-actions">
                      <button className="btn primary" disabled={busy}
                              onClick={() => issue(f.name)}>
                        {busy ? "Asking…" : "Ask, and download the workbook"}
                      </button>
                      <button className="btn quiet" onClick={() => setAsking(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button className="btn sm" onClick={() => {
                    setAsking(f.name); setSentTo(""); setNote("");
                  }}>Ask for this</button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── Where the nineteen stand ────────────────────────────────── */}
      {checks && (
      <Card title="What the record cannot settle on its own"
            aside={`${checks.settled} of ${checks.total} settled`}>
        <p className="quiet small" style={{ marginTop: -4, marginBottom: 12 }}>
          Each of these was found by a control rather than by somebody
          reading, and none can be resolved from what is on file. They are
          ordered by how much each moves the rate. An item with no answer is
          unanswered, which is a different fact from <em>still checking</em>:
          one means nobody has looked and the other means somebody has and
          cannot say yet.
        </p>

        <Table columns={[
          { label: "", align: "left" },
          { label: "Ref", align: "left" },
          { label: "What it is", align: "left" },
          { label: "Amount", align: "left" },
          { label: "Where it stands", align: "left" },
        ]}>
          {checks.items
            .filter((i) => showAll || !i.settled)
            .map((i) => (
            <tr key={i.ref} className={i.settled ? "unmatched" : ""}>
              <td className="l">
                <Tick state={i.settled ? "done" : i.status ? "flagged" : "open"} />
              </td>
              <td className="l mono-ref">{i.ref}</td>
              <td className="l wrap">
                <div className="strong">{i.title}</div>
                <div className="quiet small">{i.area} · {i.moves}</div>
              </td>
              <td className="l num small">{i.figure}</td>
              <td className="l wrap">
                {i.status ? (
                  <>
                    <div className="small">{i.status}</div>
                    <div className="quiet small">{i.answer}</div>
                    <div className="quiet small">
                      {i.answered_by}
                      {i.accepted_by && i.accepted_by !== i.answered_by
                        && <> · accepted by {i.accepted_by}</>}
                      {i.evidence_id && <> · <a
                        href={api.documentDownloadUrl(i.evidence_id)}>
                        {i.evidence_filename || "the workbook"}</a></>}
                      {i.answers > 1 && <> · answered {i.answers} times</>}
                    </div>
                  </>
                ) : (
                  <span className="quiet small">{i.asks}</span>
                )}
              </td>
            </tr>
          ))}
        </Table>

        <div className="upload-actions" style={{ marginTop: 12 }}>
          <button className="btn quiet sm" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Hide the settled ones"
                     : `Show the ${checks.settled} already settled`}
          </button>
          <span className="quiet small">
            Answers come back through the workbook above, and each carries the
            file it was given in. Nothing here is edited — a second answer
            supersedes the first and both stay, because several of these are
            expected to change answer and the sequence is what an auditor is
            reconstructing.
          </span>
        </div>
      </Card>
      )}

      {/* ── The chase list ──────────────────────────────────────────── */}
      <Card title="What we have asked for"
            aside={rows.length ? `${rows.length} in ${data.period}` : ""}>
        {!data ? <Empty mark="…" title="Loading" />
          : rows.length === 0 ? (
          <Empty mark="—" title="Nothing asked for yet">
            Each of these has a lead time in weeks, so the ask is the long
            pole. Nothing above can be inferred from the record.
          </Empty>
        ) : (
          <Table columns={[
            { label: "", align: "left" },
            { label: "What", align: "left" },
            { label: "Of whom", align: "left" },
            { label: "Asked", align: "left" },
            { label: "Days" },
            { label: "Came back with", align: "left" },
            { label: "", align: "left" },
          ]}>
            {rows.map((r) => {
              const [tick, label] = STATE[r.state] || ["open", r.state];
              const mine = mayAccept(actor, r.form);
              return (
                <React.Fragment key={r.request_id}>
                  <tr>
                    <td className="l"><Tick state={tick} /></td>
                    <td className="l strong">
                      {(forms || []).find((f) => f.name === r.form)?.title || r.form}
                      <div className="quiet small">
                        <Pill>{label}</Pill>{" "}
                        <span className="mono-ref">#{r.request_id}</span>
                      </div>
                    </td>
                    <td className="l">{r.sent_to || "—"}
                      <div className="quiet small">by {r.issued_by}</div>
                    </td>
                    <td className="l quiet small">{when(r.issued_at)}</td>
                    <td className={`num ${r.overdue ? "fail" : ""}`}>
                      {r.days === null ? "—" : r.days}
                    </td>
                    <td className="l quiet small">
                      {r.reply_filename
                        ? <>{r.reply_filename}<br />from {r.received_from}</>
                        : r.state === "ACCEPTED"
                          ? `${r.rows_accepted} written, ${r.rows_held_back} held back`
                          : "—"}
                    </td>
                    <td className="l">
                      {r.state === "ISSUED" && (
                        <>
                          <a className="btn sm"
                             href={api.requestWorkbookUrl(r.request_id)}>Workbook</a>{" "}
                          <button className="btn sm" onClick={() => {
                            replyTo.current = r.request_id; file.current?.click();
                          }}>Reply came back</button>
                        </>
                      )}
                      {r.state === "RECEIVED" && (
                        <button className="btn sm primary"
                                onClick={() => show(r.request_id)}>
                          {open === r.request_id ? "Hide" : "What it says"}
                        </button>
                      )}
                      {r.state === "ACCEPTED" && (
                        <button className="btn sm" onClick={() => show(r.request_id)}>
                          {open === r.request_id ? "Hide" : "What it said"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {open === r.request_id && (
                    <tr className="subrow">
                      <td className="l" colSpan={7}>
                        <Preview preview={preview} busy={busy} mine={mine}
                                 state={r.state} form={r.form}
                                 onAccept={() => accept(r.request_id)} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </Table>
        )}
        <input ref={file} type="file" hidden
               accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
               onChange={(e) => {
                 const f = e.target.files?.[0];
                 if (f && replyTo.current) sendBack(replyTo.current, f);
                 e.target.value = "";
               }} />
        <p className="quiet small" style={{ marginTop: 12 }}>
          Anybody signed in may send a reply back, exactly as anybody may send
          a document in. Writing it into the cost record takes the portfolio
          that owns the data — that is the same judgment as typing it in by
          hand.
        </p>
      </Card>
    </div>
  );
}

/* What the reply says, what is wrong with it, and what it will do — all at
   once, because somebody correcting a workbook should make one pass rather
   than discover the next problem on each upload. */
function Preview({ preview, busy, mine, state, form, onAccept }) {
  if (!preview) return <div className="quiet small">Reading it…</div>;
  const done = state === "ACCEPTED";
  return (
    <div className="preview">
      <div className="stat-row">
        <Stat label="Rows that will land" value={preview.usable} size="lg" />
        <Stat label="Held back" value={preview.incomplete}
              note={preview.incomplete ? "a required cell would not read" : ""} />
        <Stat label="Nobody touched" value={preview.untouched}
              note="pre-filled, left as it was" />
        <Stat label="Problems" value={preview.problem_count}
              tone={preview.problem_count ? "warn" : ""} />
      </div>

      {preview.missing_columns.length > 0 && (
        <p className="fail small">
          Columns the form asks for and this workbook does not have:{" "}
          {preview.missing_columns.join(", ")}. Columns are found by their
          heading, so one that has been renamed is one that cannot be read.
        </p>
      )}

      {preview.controls.length > 0 && (
        <>
          <h4 className="section-h">What it has to add up to</h4>
          <Table columns={[
            { label: "", align: "left" }, { label: "Control", align: "left" },
            { label: "Expected" }, { label: "Reported" }, { label: "Difference" },
          ]}>
            {preview.controls.map((c, i) => (
              <tr key={i}>
                <td className="l"><Tick state={c.ties ? "done" : "flagged"} /></td>
                <td className="l">{c.label}
                  {c.note && <div className="quiet small">{c.note}</div>}</td>
                <td className="num">{c.expect ?? "—"}</td>
                <td className="num">{c.got}</td>
                <td className={`num ${c.ties ? "" : "fail"}`}>{c.variance ?? "—"}</td>
              </tr>
            ))}
          </Table>
        </>
      )}

      {(preview.lands_on ?? []).length > 0 && (
        <>
          <h4 className="section-h">What it will land on</h4>
          <p className="quiet small">
            Accepting <em>adds</em> these rows to whatever the register already
            holds for each building — it does not put them in their place. A
            building named under a spelling the record does not hold is created
            beside the one meant, and its area becomes the sum of the rows just
            written, so it ties by construction and can check nothing.
          </p>
          <Table columns={[
            { label: "", align: "left" }, { label: "Building", align: "left" },
            { label: "Rows" }, { label: "Sq ft" }, { label: "Already there", align: "left" },
          ]}>
            {preview.lands_on.map((b, i) => (
              <tr key={i}>
                <td className="l">
                  <Tick state={!b.on_the_record || b.already ? "flagged" : "done"} />
                </td>
                <td className="l">{b.building}</td>
                <td className="num">{count(b.rows)}</td>
                <td className="num">{money(b.sqft)}</td>
                <td className="l"><span className="quiet small">{b.says}</span></td>
              </tr>
            ))}
          </Table>
        </>
      )}

      {preview.problems.length > 0 && (
        <>
          <h4 className="section-h">
            {done ? "Every cell that would not read" : "Every cell that will not read"}
          </h4>
          <p className="quiet small" style={{ marginTop: -4 }}>
            Nothing is coerced into validity. A bad cell in an optional column
            costs that cell and the row still lands; a bad cell in a required
            one holds the row back, because a figure somebody guessed is worse
            than one nobody recorded.
          </p>
          <ul className="problems">
            {preview.problems.slice(0, 60).map((p, i) => (
              <li key={i} className="small">{p.text}</li>
            ))}
          </ul>
          {preview.problem_count > 60 && (
            <p className="quiet small">
              …and {preview.problem_count - 60} more.
            </p>
          )}
        </>
      )}

      {preview.sample.length > 0 && (
        <>
          <h4 className="section-h">
            {done ? "The first few rows as they landed"
                  : "The first few rows as they will land"}
          </h4>
          <ul className="problems">
            {preview.sample.map((r) => (
              <li key={r.row} className="small quiet">
                Row {r.row}:{" "}
                {Object.entries(r.values).map(([k, v]) => `${k} = ${v}`).join(" · ")}
              </li>
            ))}
          </ul>
        </>
      )}

      {!done && (
        <div className="upload-actions" style={{ marginTop: 14 }}>
          {mine ? (
            <button className="btn primary" disabled={busy || !preview.usable}
                    onClick={onAccept}>
              {busy ? "Writing…" : `Write ${preview.usable} row`
                + (preview.usable === 1 ? "" : "s") + " onto the record"}
            </button>
          ) : (
            <span className="quiet small">
              Writing this onto the record is {OWNS[form] === "admin"
                ? "the organisation's administrator's"
                : `the ${OWNS[form]} portfolio's`} judgment, not yours. You can
              read all of it.
            </span>
          )}
          <span className="quiet small">{preview.caveat}</span>
        </div>
      )}
    </div>
  );
}
