import React, { useCallback, useEffect, useState } from "react";
import { api, count, explain, money } from "../api.js";
import {
  Card, Drawer, Empty, Field, PageHead, Pill, Stat, Table, Tick, useToast,
} from "../components/ui.jsx";

/* Contractor or subrecipient — 2 CFR 200.331, per party.
 *
 * The door migration 115 said it stood in for and did not build. Six parties
 * on the live record clear the 200.1 cap by $313,605.35 between them, and
 * until this screen existed the only way to answer any of them was to write
 * SQL against `party_determination`.
 *
 * Four rules, each one this application already follows somewhere:
 *
 *  1. **Nothing is computed here.** `amount`, `at_stake` and `in_mtdc` are
 *     read from `v_subaward_exposure`, which is where the cap is applied. A
 *     screen that subtracted 25,000 itself would be a second implementation
 *     of 200.1, free to disagree with the engine that allocates the rate.
 *
 *  2. **UNDETERMINED prints as NO DATA and never as a zero.** It is not a
 *     number — nobody has answered — and `in_mtdc` comes back NULL for
 *     exactly that reason. A blank is unanswered, and unanswered is a value.
 *
 *  3. **The five tests are on the page.** 200.331 turns on the substance of
 *     the relationship, so the person making the judgment should be looking
 *     at the regulation rather than recalling it. They come from the server,
 *     because a second copy of the rule in the SPA is one free to drift.
 *
 *  4. **A button that would answer 403 is not offered.** Every route here is
 *     `require_controller`, and `canWrite` reads the *portfolio* rather than
 *     the rank — CONTROLLER is the name of both, and reading the rank is the
 *     defect `Facilities.jsx` shipped, which hid the write forms from the
 *     one person holding the portfolio and nothing else.
 */

const SAYS = {
  CONTRACTOR: {
    tone: "solid", tick: "done",
    says: "MTDC takes the payment whole",
    rule: "200.331(b) — services within normal business operations, ancillary "
        + "to the federal programme, not subject to its compliance "
        + "requirements as a result of the agreement.",
  },
  SUBRECIPIENT: {
    tone: "accent", tick: "flagged",
    says: "MTDC takes the first $25,000 and no more",
    rule: "200.331(a) — carries out part of the federal programme in its own "
        + "right, with programmatic decision making and performance measured "
        + "against the programme's objectives.",
  },
  UNDETERMINED: {
    tone: "warn", tick: "open",
    says: "nobody has answered, so what MTDC takes is open",
    rule: "The substance of the relationship governs, not the form. Neither "
        + "the invoice category nor the account name settles it — every one "
        + "of these is booked as CONSULTANT.",
  },
};

export default function Parties({ actor }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [err, setErr] = useState("");

  const canWrite = (actor?.portfolios || []).includes("CONTROLLER");

  const load = useCallback(async () => {
    setData(await api.parties());
  }, []);
  useEffect(() => { load().catch((e) => setErr(explain(e))); }, [load]);

  if (!data) return <PageHead title="Contractor or subrecipient" schedule="B" />;

  const t = data.totals || {};
  const openCount = Number(t.undetermined || 0);

  return (
    <>
      <PageHead
        title="Contractor or subrecipient"
        schedule="B"
        aside={<Pill tone={openCount ? "warn" : "solid"}>
          {openCount ? `${count(openCount)} undetermined` : "all determined"}
        </Pill>}
      >
        2 CFR 200.1 takes the first {money(data.cap)} of each <b>subaward</b>
        {" "}into modified total direct cost and a contract for services whole.
        So the same payment sits almost entirely in the base or almost entirely
        outside it, and which it is turns on a 200.331 determination — a
        judgment about the substance of the relationship, read off an
        agreement. Nothing here is computed: the figures are read from the row
        the register recorded them in.
      </PageHead>

      {err ? <p className="refusal">{err}</p> : null}

      <div className="stat-row">
        <Stat label="Parties over the cap" value={count(t.parties || 0)} />
        <Stat label="Paid" value={money(t.paid)}
              note="on federal objectives, judged DIRECT" />
        <Stat label="Turning on a determination" value={money(t.at_stake)}
              size="lg"
              note="the part above the cap, on the ones nobody has answered" />
      </div>

      <Card title="The register"
            aside={<span className="quiet">unanswered first, then by what
              turns on it</span>}>
        {!(data.parties || []).length ? (
          <Empty title="No party clears the cap">
            A determination below {money(data.cap)} cannot change what MTDC
            takes, so nothing is opened for one.
          </Empty>
        ) : (
          <Table columns={["", "Payee", "Objective", "Paid", "In MTDC",
                           "At stake", "Determination", ""]}>
            {data.parties.map((p) => {
              const s = SAYS[p.determination] || SAYS.UNDETERMINED;
              const key = `${p.objective_id}|${p.payee}`;
              return (
                <tr key={key}>
                  <td><Tick state={s.tick} title={s.says} /></td>
                  <td className="l">{p.payee || <span className="quiet">no payee on
                    the ledger line</span>}</td>
                  <td className="l">{p.objective_id}</td>
                  <td className="num">{money(p.amount)}</td>
                  <td className="num">{p.in_mtdc === null
                    ? <span className="quiet">—</span> : money(p.in_mtdc)}</td>
                  <td className="num">{money(p.at_stake)}</td>
                  <td className="l"><Pill tone={s.tone}>{p.determination}</Pill></td>
                  <td className="l">
                    <button className="btn sm" onClick={() => setOpen(p)}>
                      {canWrite
                        ? (p.determination === "UNDETERMINED"
                            ? "Determine" : "Revisit")
                        : "Read"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>

      {openCount ? (
        <Card variant="quiet">
          <p>
            <b>UNDETERMINED is NO DATA and never a pass.</b> Every computation
            run while these are open leaves each payment in MTDC whole, which
            is the <i>contractor</i> answer applied by omission. The rate is
            not wrong — it is uncarried: a determination somebody signs is what
            moves it, and nothing is defaulted in either direction.
          </p>
        </Card>
      ) : null}

      <Determine open={open} onClose={() => setOpen(null)} canWrite={canWrite}
                 tests={data.tests} cap={data.cap} toast={toast}
                 onDone={async () => { setOpen(null); await load(); }} />
    </>
  );
}

/* One party, the two tests side by side, and the box that has to be filled in.
 *
 * The panel reads the row it was handed and nothing else, so a figure on it
 * cannot disagree with the figure on the line it was opened from. */
function Determine({ open, onClose, canWrite, tests, cap, toast, onDone }) {
  const [value, setValue] = useState("");
  const [basis, setBasis] = useState("");
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState("");

  useEffect(() => {
    // An already-open party opens on *unchosen*, not on UNDETERMINED. Seeding
    // it from the row made the panel offer "Withdraw" on something nobody had
    // ever determined — the primary button reading as the wrong verb, for an
    // act that would change nothing. Only a party that carries an answer
    // starts with that answer selected.
    setValue(open?.determination === "UNDETERMINED"
      ? "" : (open?.determination || ""));
    setBasis(open?.basis || "");
    setRef(open?.agreement_ref || "");
    setRefusal("");
  }, [open]);

  if (!open) return null;
  const name = open.payee || "(no payee on the ledger line)";
  const short = value && value !== "UNDETERMINED" && basis.trim().length < 40;

  async function save() {
    setBusy(true);
    setRefusal("");
    try {
      const r = await api.putDetermination({
        objective_id: open.objective_id, payee: open.payee,
        determination: value, basis, agreement_ref: ref,
      });
      toast.ok(`${name} — ${r.note}`);
      await onDone();
    } catch (e) {
      // A refusal prints where it happened, in warm pencil, and not only in a
      // toast that fades while somebody is still reading the form.
      setRefusal(explain(e));
    } finally { setBusy(false); }
  }

  return (
    <Drawer open wide title={name}
            subtitle={`${open.objective_id} · ${money(open.amount)} paid · `
                    + `${money(open.at_stake)} of MTDC turns on this`}
            onClose={onClose}
            footer={canWrite ? (
              <>
                <button className="btn" onClick={onClose}>Close</button>
                <button className="btn primary" disabled={busy || !value || short}
                        onClick={save}>
                  {value === "UNDETERMINED" ? "Withdraw" : "Record"}
                </button>
              </>
            ) : <button className="btn" onClick={onClose}>Close</button>}>

      <p>
        {SAYS[open.determination]?.says}. A contractor puts{" "}
        {money(open.amount)} in the base; a subaward puts {money(cap)}, and the
        difference — {money(open.at_stake)} — is what this decides.
      </p>

      {["SUBRECIPIENT", "CONTRACTOR"].map((k) => (
        <Card key={k} variant="quiet" title={
          k === "SUBRECIPIENT" ? "200.331(a) — a subrecipient"
                               : "200.331(b) — a contractor"}>
          <ul className="tests">
            {(tests?.[k] || []).map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </Card>
      ))}

      <p className="quiet">
        Not all of the characteristics need be present, and the substance of
        the relationship is what governs. Where the judgment is finely
        balanced, say so in the basis — a reviewer asking about this is asking
        which way it was close.
      </p>

      {canWrite ? (
        <>
          <Field label="Determination" required>
            <select value={value} onChange={(e) => setValue(e.target.value)}>
              <option value="">Choose…</option>
              <option value="CONTRACTOR">CONTRACTOR — MTDC takes it whole</option>
              <option value="SUBRECIPIENT">
                SUBRECIPIENT — MTDC takes the first {money(cap)}
              </option>
              <option value="UNDETERMINED">
                UNDETERMINED — withdraw, and leave it open
              </option>
            </select>
          </Field>
          <Field label="Which of the tests carried it"
                 required={value && value !== "UNDETERMINED"}
                 hint={value === "UNDETERMINED"
                   ? "Withdrawing clears the basis and the name with it: a "
                   + "determination that has been withdrawn and still carries "
                   + "who made it is half a determination."
                   : "At least forty characters. The schema holds the same "
                   + "floor, because a determination with no reasoning is the "
                   + "next person's puzzle."}>
            <textarea rows={4} value={basis}
                      disabled={value === "UNDETERMINED"}
                      onChange={(e) => setBasis(e.target.value)} />
          </Field>
          {short ? (
            <p className="refusal">
              {40 - basis.trim().length} more character
              {40 - basis.trim().length === 1 ? "" : "s"}.
            </p>
          ) : null}
          <Field label="The agreement"
                 hint={"Where the substance was read from — a subaward "
                     + "agreement, a purchase order, a statement of work."}>
            <input value={ref} onChange={(e) => setRef(e.target.value)}
                   disabled={value === "UNDETERMINED"} />
          </Field>
          {refusal ? <p className="refusal">{refusal}</p> : null}
        </>
      ) : (
        <>
          <Field label="Determination">
            <p><Pill tone={SAYS[open.determination]?.tone}>
              {open.determination}</Pill></p>
          </Field>
          {open.basis ? <Field label="Why"><p>{open.basis}</p></Field> : null}
          {open.decided_by
            ? <p className="quiet">Determined by {open.decided_by}.</p>
            : <p className="quiet">This one is the controller's to answer.</p>}
        </>
      )}
    </Drawer>
  );
}
