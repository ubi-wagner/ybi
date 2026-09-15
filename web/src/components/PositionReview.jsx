import React, { useCallback, useEffect, useState } from "react";

import { api, count, explain, money } from "../api.js";
import { Card, Drawer, Empty, Field, PageHead, Pill, Segmented, Table,
         useToast } from "./ui.jsx";

/* The controller's review of a restaged year.
 *
 * 757 judgments were written by `scripts/classification_log.py --apply` in six
 * seconds under Tom's credentials. That is the right way for a script to
 * write — every one carries a person's name and an audit row — and it leaves
 * the record making a claim nobody should make on his behalf. This is the
 * screen where he takes them one at a time, and where what everybody else has
 * noticed arrives.
 *
 * Three rules, each one this system already keeps somewhere:
 *
 *  - **Nothing is computed here.** Every figure and every state is read from
 *    `v_controller_review`. A screen that worked out for itself whether a
 *    position was adopted would be a second definition of adopted.
 *  - **The proposal sits beside what is there now.** A recommendation the
 *    controller has to hold in his head against a second screen is one he will
 *    accept without comparing.
 *  - **"Overtaken" is shown, not hidden.** A recommendation written against a
 *    classification that has since moved says so on its own row. Accepting it
 *    would apply a proposal to something it was never about, and the server
 *    refuses — so the screen must not offer it as though it would work.
 */
/* What a recommendation actually proposes.
 *
 * A judgment is four dimensions — pool, 990 function, federal treatment and
 * cost objective — and a recommendation may move any of them. Printing only
 * the pool produced rows reading "OVERHEAD → OVERHEAD" on a real proposal
 * that moved the 990 function: the screen showing a column where the reader
 * needs a change. Everything that differs is named; nothing that does not is
 * shown, because a list of four where three are identical is the same defect
 * wearing the opposite sign.
 */
const SUBJECT = {
  CLASSIFICATION: { label: "Classification", where: "/classify" },
  FACILITY:       { label: "Building",       where: "/classify/space" },
  SPACE_UNIT:     { label: "Space",          where: "/classify/space" },
  ASSET_FUNDING:  { label: "Asset funding",  where: "/classify/assets" },
};

const FIELD = {
  pool: "pool", function_990: "990 function", federal: "federal treatment",
  objective_id: "objective", grade: "grade",
  name: "name", usable_sqft: "usable sq ft", rentable_sqft: "rentable sq ft",
  address: "address", owned: "owned", landlord: "landlord",
  facility_id: "building", label: "name", use: "use", status: "status",
  occupant: "occupant", floor: "floor",
  kind: "source", amount: "amount", award_reference: "award", funder: "funder",
};

/* A figure on this screen is printed by the one formatter, like every other
 * figure in the application. A proposal is `jsonb`, so its values arrive as
 * strings and `String(v)` put `5594162.00` on a card beside `$1,835,047.17`
 * elsewhere — the eight-spellings defect in the one place a controller is
 * about to press Accept. Which keys are money and which are area is a fact
 * about the registers, so it is written down beside `FIELD` rather than
 * guessed from the value.
 */
const MONEY = new Set(["amount"]);
const AREA = new Set(["usable_sqft", "rentable_sqft", "gross_sqft"]);

/* What a recommendation actually proposes.
 *
 * A judgment is four dimensions and a building is five, so printing one
 * column produced rows reading "OVERHEAD → OVERHEAD" on a real proposal that
 * moved the 990 function: the screen showing a column where the reader needs
 * a change. Everything that differs is named, nothing that does not is shown,
 * and where the row is not on the record at all there is nothing to differ
 * from — so the whole proposal is the change, which is the normal case for
 * space and assets.
 */
function changes(r) {
  const proposed = r.proposal || {};
  const current = r.current || {};
  /* `true` is what JSON calls it and not what a person does. A blank stays a
     blank, because there is no amount and nobody has read one off are
     different facts everywhere else in this system. */
  const shown = (v, k) => v === null || v === undefined || v === ""
    ? "\u2014" : v === true ? "yes" : v === false ? "no"
    : MONEY.has(k) ? money(v) : AREA.has(k) ? count(v) : String(v);
  return Object.keys(proposed)
    .filter((k) => r.is_new || shown(current[k], k) !== shown(proposed[k], k))
    .map((k) => ({ what: FIELD[k] || k,
                   from: r.is_new ? null : shown(current[k], k),
                   to: shown(proposed[k], k) }));
}


export default function PositionReview({ actor }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState({});
  const [panel, setPanel] = useState(null);
  const [adopted, setAdopted] = useState(null);
  const [showing, setShowing] = useState(25);

  const load = useCallback(() => {
    api.positionReview().then(setData).catch(() => setData(null));
  }, []);
  useEffect(load, [load]);

  const loadAdopted = useCallback(() => {
    api.positions({ state: "adopted", limit: 50 })
       .then(setAdopted).catch(() => setAdopted(null));
  }, []);
  useEffect(loadAdopted, [loadAdopted]);

  async function unadopt(decision_id) {
    const wy = window.prompt(
      "Why is the signature coming off? A withdrawal with no reason is the " +
      "position changing with nobody accountable for it.");
    if (!wy) return;
    try {
      await api.withdrawConfirmation(decision_id, wy);
      toast.ok("Signature withdrawn, with the reason on the record.");
      load(); loadAdopted();
    } catch (e) { toast.fail(explain(e) || "That was refused."); }
  }

  const mayDecide = (actor?.portfolios || []).includes("CONTROLLER");

  async function adopt(ids, note) {
    setBusy(true);
    try {
      const r = await api.confirmPositions(ids, note || "");
      toast.ok(`Adopted ${count(r.confirmed)} working position` +
               (r.confirmed === 1 ? "" : "s") + ".");
      load();
    } catch (e) {
      // A batch where everything was already adopted answers 409 and changed
      // nothing. It is never reported in the tone used for success.
      toast.fail(explain(e) || "Nothing was adopted.");
    } finally { setBusy(false); }
  }

  async function dispose(rec, how) {
    const why = (reason[rec.item_id] || "").trim();
    setBusy(true);
    try {
      if (how === "accept") {
        await api.acceptRecommendation(rec.item_id, { rationale: why });
        toast.ok("Recorded, under your name, citing the recommendation.");
      } else {
        await api.declineRecommendation(rec.item_id, why);
        toast.ok("Declined, with the reason on the record.");
      }
      load();
    } catch (e) {
      toast.fail(explain(e) || "That was refused.");
    } finally { setBusy(false); }
  }

  if (!data) return <Card title="Review">Loading.</Card>;

  const recs = data.recommendations || [];
  const open = data.unconfirmed || [];

  return (
    <>
      <PageHead title="Review" schedule="B Classify"
                aside={`${count(recs.length)} recommendation${recs.length === 1 ? "" : "s"} · ` +
                       `${count(open.length)} position${open.length === 1 ? "" : "s"} to adopt`} />

      <Card title="What people have asked for"
            variant={recs.length ? "raised" : "quiet"}>
        {recs.length === 0 ? (
          <p className="muted">
            Nothing is outstanding. A recommendation is somebody who may read
            the cost record saying this group is classified wrong, what it
            should be, and why — it writes nothing, and it arrives here.
          </p>
        ) : (
          <Table columns={[
            { label: "What", align: "left" },
            { label: "Proposed change", align: "left" },
            { label: "Raised by", align: "left" },
            { label: "", width: 200, align: "left" },
          ]}>
            {recs.map((r) => (
              <React.Fragment key={r.item_id}>
              <tr>
                <td className="l">
                  <Pill>{(SUBJECT[r.subject] || {}).label || r.subject}</Pill>
                  <div><strong>{r.title}</strong></div>
                  {r.detail && <div className="rowsub">{r.detail}</div>}
                  {r.is_new && (
                    <div className="rowsub">
                      not on the record — this would put it there
                    </div>)}
                </td>
                <td className="l">
                  {changes(r).map((c) => (
                    <div key={c.what}>
                      {c.from !== null && (
                        <><Pill>{c.from}</Pill><span className="rowsub"> → </span></>)}
                      <Pill tone="warn">{c.to}</Pill>
                      <span className="rowsub"> {c.what}</span>
                    </div>))}
                </td>
                <td className="l rowsub">{r.raised_by}</td>
                <td className="l">
                  {mayDecide ? (
                    <>
                      <button className="sm" disabled={busy || !r.still_agrees}
                              onClick={() => dispose(r, "accept")}>Accept</button>
                      {" "}
                      <button className="sm" disabled={busy}
                              onClick={() => dispose(r, "decline")}>Decline</button>
                    </>
                  ) : (
                    <span className="rowsub">the controller answers this</span>
                  )}
                </td>
              </tr>
              {/* The reason goes on a row of its own rather than in a column.
                  A table sizes its columns to their content, so a sentence
                  beside a figure pushes the figure off the edge — which is
                  exactly what `v_gl_accounted`'s screen did to the two rows
                  whose whole job was to say why. A row cannot overlap a row. */}
              <tr className="sub">
                <td className="l wrap" colSpan={4}>
                  <div className="rowsub">{r.note}</div>
                  {!r.still_agrees && (
                    <div className="rowsub warnish">
                      Overtaken — the record has moved since this was written,
                      so accepting it would apply a proposal to something it was
                      never about. Decline it and ask for a fresh one.
                    </div>
                  )}
                  {mayDecide && (
                    <Field label="Your reason, which the change or the refusal carries">
                      <input value={reason[r.item_id] || ""}
                             onChange={(e) => setReason(
                               { ...reason, [r.item_id]: e.target.value })} />
                    </Field>
                  )}
                </td>
              </tr>
              </React.Fragment>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Working positions nobody has adopted">
        <p className="muted">
          Each of these was proposed by the classification log and recorded
          under the controller's credentials. Adopting one makes it his
          judgment; it moves no figure, so the rate is the same before and
          after and does not depend on who got round to reviewing.
        </p>
        {open.length === 0 ? (
          <Empty title="Every position has been adopted">
            The classification is the controller's own, group by group.
          </Empty>
        ) : (
          <Table columns={[
            { label: "Group", align: "left" },
            { label: "Pool", align: "left" },
            { label: "", width: 90, align: "left" },
          ]}>
            {open.slice(0, showing).map((p) => (
              <React.Fragment key={p.item_id}>
              <tr>
                <td className="l">
                  <a href="#" onClick={(e) => {
                       e.preventDefault();
                       setPanel(p.decision_id);
                     }}><strong>{p.title}</strong></a>
                  {p.detail && <div className="rowsub">{p.detail}</div>}
                </td>
                <td className="l"><Pill>{(p.current || {}).pool}</Pill></td>
                <td className="l">
                  {mayDecide && (
                    <button className="sm" disabled={busy}
                            onClick={() => adopt([p.decision_id], "")}>Adopt</button>
                  )}
                </td>
              </tr>
              <tr className="sub">
                <td className="l wrap" colSpan={3}>
                  <div className="rowsub">{p.note}</div>
                </td>
              </tr>
              </React.Fragment>
            ))}
          </Table>
        )}
        {open.length > 0 && (
          <div className="row-actions">
            {open.length > showing && (
              <button onClick={() => setShowing(showing + 25)}>
                Show 25 more
              </button>
            )}
            {mayDecide && (
              /* Adopting 756 positions one at a time is not a job anybody
                 does, and a screen that only offers that is one people route
                 around — by sealing without reviewing, which is the thing
                 this whole exercise is against. So the page can be adopted
                 as a page, after it has been read: the button says how many
                 and the list above it is what they are. */
              <button className="primary" disabled={busy}
                      onClick={() => adopt(
                        open.slice(0, showing).map((p) => p.decision_id),
                        "Read on the review screen and adopted as a page.")}>
                Adopt the {count(Math.min(showing, open.length))} shown
              </button>
            )}
            <span className="rowsub">
              {count(Math.min(showing, open.length))} of {count(open.length)}{" "}
              shown. The count is read from the record rather than from this
              page.
            </span>
          </div>
        )}
      </Card>

      <Card title="Adopted" variant="quiet">
        {!adopted || adopted.total === 0 ? (
          <Empty title="Nothing has been adopted yet">
            A position the controller has read and made his own appears here,
            with the way to take the signature back off it.
          </Empty>
        ) : (
          <Table columns={[
            { label: "Group", align: "left" },
            { label: "Pool", align: "left" },
            { label: "Adopted by", align: "left" },
            { label: "", width: 110, align: "left" },
          ]}>
            {adopted.positions.map((p) => (
              <tr key={p.decision_id}>
                <td className="l">
                  <a href="#" onClick={(e) => { e.preventDefault(); setPanel(p.decision_id); }}>
                    <strong>{p.account}</strong>
                  </a>
                  {p.payee && <div className="rowsub">{p.payee}</div>}
                </td>
                <td className="l"><Pill tone="ok">{p.pool}</Pill></td>
                <td className="l rowsub">{p.confirmed_by}</td>
                <td className="l">
                  {mayDecide && (
                    <button className="sm"
                            onClick={() => unadopt(p.decision_id)}>Withdraw</button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
        {adopted && adopted.total > adopted.shown && (
          <p className="muted small">
            {count(adopted.shown)} of {count(adopted.total)} shown.
          </p>
        )}
      </Card>

      <PositionPanel decisionId={panel} onClose={() => { setPanel(null); load(); }} />
    </>
  );
}


/* Everything written against one group, and the two things anybody can add to
 * it. Notes and recommendations are `require_reader` on the server — the same
 * gate as the library, which admits the auditor, who holds no portfolio and
 * whose observations are the reason this register exists.
 *
 * A note whose body the caller may not read comes back with the body withheld
 * and everything else intact. That is disclosure without contents, and the
 * screen prints it as such rather than dropping the row: three notes looking
 * like one is concealment, and this is deliberately not that.
 */
function PositionPanel({ decisionId, onClose }) {
  const toast = useToast();
  const [position, setPosition] = useState(null);
  const [notes, setNotes] = useState(null);
  const [kind, setKind] = useState("RECORD");
  const [text, setText] = useState("");
  const [pool, setPool] = useState("");
  const [why, setWhy] = useState("");

  const load = useCallback(() => {
    if (!decisionId) return;
    // The panel reads the position from the record rather than taking what
    // the parent had to hand. Both lists that open it carry different
    // fields, and a component that works out which one it was given is one
    // that will be wrong about it.
    api.positions({ decision_id: decisionId, limit: 1 })
       .then((d) => setPosition(d.positions[0] || null)).catch(() => {});
    api.positionNotes(decisionId).then(setNotes).catch(() => setNotes(null));
  }, [decisionId]);
  useEffect(load, [load]);

  if (!decisionId || !position) return null;

  async function addNote() {
    try {
      await api.writeNote({ decision_id: position.decision_id, kind, body: text });
      toast.ok(kind === "RECORD"
        ? "Noted on the cost record, where every reader of it sees it."
        : "Noted. It stays out of the audit package; its count does not.");
      setText(""); load();
    } catch (e) { toast.fail(explain(e) || "That note was refused."); }
  }

  async function flip(n) {
    const reason = window.prompt(
      "Why is this changing what it discloses? The reason is kept, and so is " +
      "who changed it and when.");
    if (!reason) return;
    try {
      await api.redesignateNote(
        n.note_id, n.kind === "RECORD" ? "WORKING" : "RECORD", reason);
      toast.ok("Changed, and the change is on the record.");
      load();
    } catch (e) { toast.fail(explain(e) || "That was refused."); }
  }

  async function recommend() {
    try {
      await api.recommendReclass({
        decision_id: decisionId,
        pool,
        function_990: pool === "G&A" ? "MANAGEMENT_AND_GENERAL" : "PROGRAM",
        federal: "PENDING",
        note: why,
      });
      toast.ok("Raised. It is on the controller's list, and nothing on the "
               + "record has moved.");
      setWhy(""); setPool("");
    } catch (e) { toast.fail(explain(e) || "That was refused."); }
  }

  return (
    <Drawer open onClose={onClose} wide title={position.account}
            subtitle={`${position.pool} · ${
              position.origin === "MACHINE_PROPOSAL"
                ? "a working position a script proposed"
                : "judged by a person"}`}>
      <Card title="Why it is the working position" variant="quiet">
        <p>{position.rationale}</p>
        {position.citation && <p className="muted small">{position.citation}</p>}
      </Card>

      <Card title="Notes">
        {!notes || notes.notes.length === 0
          ? <Empty title="Nothing written here yet" />
          : notes.notes.map((n) => (
              <div key={n.note_id} className="card quiet">
                <Pill tone={n.kind === "WORKING" ? "warn" : ""}>{n.kind}</Pill>
                {" "}<span className="muted small">{n.author}</span>
                <p>{n.withheld
                  ? <em className="muted">
                      A working note. You are told it is here, and not what it
                      says.
                    </em>
                  : n.body}</p>
                {n.redesignated_at && (
                  <p className="muted small">
                    Re-designated by {n.redesignated_by}: {n.redesignated_reason}
                  </p>
                )}
                {!n.withheld && (
                  <button onClick={() => flip(n)}>
                    Make it {n.kind === "RECORD" ? "working" : "part of the record"}
                  </button>
                )}
              </div>
            ))}
        <Field label="Write a note">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
        </Field>
        <Segmented value={kind} onChange={setKind}
                   options={[["RECORD", "On the record"],
                             ["WORKING", "Working"]]} />
        <button disabled={text.trim().length < 12} onClick={addNote}>Write it</button>
      </Card>

      <Card title="Recommend a different classification">
        <p className="muted">
          It writes nothing to the cost record. It goes on the controller's
          list with what you propose, who you are, and why.
        </p>
        <Field label="Pool">
          <select value={pool} onChange={(e) => setPool(e.target.value)}>
            <option value="">—</option>
            {["DIRECT", "FRINGE", "OVERHEAD", "G&A", "RENTAL_DIRECT",
              "FUNDRAISING", "UNALLOWABLE", "EXCLUDED"]
              .filter((x) => x !== position.pool)
              .map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </Field>
        <Field label="Why">
          <textarea value={why} onChange={(e) => setWhy(e.target.value)} rows={3} />
        </Field>
        <button disabled={!pool || why.trim().length < 12} onClick={recommend}>
          Recommend it
        </button>
      </Card>
    </Drawer>
  );
}
