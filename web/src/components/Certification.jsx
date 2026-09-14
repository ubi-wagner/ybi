import React, { useCallback, useEffect, useState } from "react";

import { api } from "../api.js";
import { Card, Field, useToast } from "./ui.jsx";

/* Whether the rate carries the controller's signature — and the one place he
 * puts it there.
 *
 * Everything upstream is free-order: fill in, classify, upload, seal, in
 * whatever order the work arrives. **Nothing downstream is blocked** — an
 * invoice can be regenerated and a workbook produced at any time, because
 * testing and evaluating the system is ordinary work and a machine that
 * refused it is one people route around. What changes is whether the paper
 * says it is certified: uncertified output carries NOT CERTIFIED, which is the
 * rule the invoice renderer already follows for a reproduction, pointed at the
 * one fact every output depends on.
 *
 * Three rules it keeps:
 *
 *  - **It states what the signature covers.** Tom may sign with the square
 *    footage still missing; refusing would stop him signing for as long as a
 *    document somebody else holds is outstanding. So the certificate records
 *    the walk's unfinished steps as they stood, and they are shown here
 *    before he signs, not after.
 *  - **Nothing is remembered.** The state is read from `v_rate_certified` on
 *    every load — a flag set when the call returns is wrong the moment
 *    somebody reloads, or the moment the other controller recomputes.
 *  - **"Not yet, because", never a disabled button with no explanation.**
 *    Where the rate cannot be signed the card is the same size and prints the
 *    server's reason.
 */
export default function Certification({ actor }) {
  const toast = useToast();
  const [state, setState] = useState(null);
  const [signature, setSignature] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  const load = useCallback(() => {
    api.certification("2025")
       .then(setState)
       .catch((e) => toast.fail(String(e.message || e)));
  }, [toast]);
  useEffect(load, [load]);

  const mayCertify = (actor?.portfolios || []).includes("CONTROLLER");

  if (!state) return null;

  if (state.certified) {
    const open = state.outstanding || [];
    return (
      <Card title="Certified" variant="raised"
            aside={<span className="cert-chip is-on">signed</span>}>
        <p style={{ margin: "0 0 10px" }}>
          <strong>{state.signature}</strong>
          <span className="rowsub"> — {state.certified_by}, {" "}
            {new Date(state.certified_at).toLocaleDateString(undefined,
              { day: "numeric", month: "long", year: "numeric" })}
          </span>
        </p>
        {state.note && <p className="rowsub" style={{ marginTop: -4 }}>{state.note}</p>}
        <p className="quiet small">
          Anything issued from here — a regenerated invoice, a workbook, the
          return — says it is certified and names this signature.
        </p>

        {open.length > 0 && (
          <div className="cert-covers">
            <strong className="small">What the signature covers</strong>
            <p className="rowsub" style={{ margin: "2px 0 6px" }}>
              These were outstanding when it was made, and travel with it.
            </p>
            <ul className="rowsub" style={{ margin: 0, paddingLeft: 18 }}>
              {open.map((o) => (
                <li key={o.seq}>{o.step} — {o.state.toLowerCase()}</li>
              ))}
            </ul>
          </div>
        )}

        {mayCertify && (
          !withdrawing ? (
            <button className="btn quiet" style={{ marginTop: 12 }}
                    onClick={() => setWithdrawing(true)}>
              Withdraw my signature
            </button>
          ) : (
            <div style={{ marginTop: 12 }}>
              <Field label="Why it is being withdrawn"
                     hint="On the record, and at least twenty characters — a
                           signature taken back with no reason is the next
                           person's puzzle.">
                <input value={reason} onChange={(e) => setReason(e.target.value)}
                       placeholder="The square footage arrived and the carve-out changes the rate" />
              </Field>
              <button className="btn" disabled={busy || reason.trim().length < 20}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          await api.withdrawCertification(reason, "2025");
                          toast.ok("Signature withdrawn. Anything issued from "
                                   + "now on says NOT CERTIFIED.");
                          setWithdrawing(false); setReason(""); load();
                        } catch (e) { toast.fail(String(e.message || e)); }
                        finally { setBusy(false); }
                      }}>
                {busy ? "Withdrawing…" : "Withdraw"}
              </button>
              <button className="btn quiet" onClick={() => setWithdrawing(false)}>
                Cancel
              </button>
            </div>
          )
        )}
      </Card>
    );
  }

  const canSign = /nobody has put their name/i.test(state.why_not || "")
               || /sign the new one/i.test(state.why_not || "");

  return (
    <Card title="Not certified" variant="raised"
          aside={<span className="cert-chip">unsigned</span>}>
      <p className="quiet" style={{ marginTop: -2 }}>{state.why_not}</p>
      <p className="quiet small">
        Nothing is blocked by this. An invoice regenerated or a workbook
        produced now carries <strong>NOT CERTIFIED</strong> on its face, which
        is what makes it safe to test and evaluate against real figures.
      </p>

      {mayCertify && canSign && (
        <div style={{ marginTop: 12 }}>
          <Field label="Type your name to sign"
                 hint="Your signature on this build-up. It can be withdrawn
                       again by you, and the withdrawal is on the record.">
            <input value={signature} onChange={(e) => setSignature(e.target.value)}
                   placeholder={actor?.display_name || "Your name"} />
          </Field>
          <Field label="Note (optional)">
            <input value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="2025 indirect rate build-up" />
          </Field>
          <button className="btn primary" disabled={busy || signature.trim().length < 2}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const r = await api.certify(signature, note, "2025");
                      toast.ok(`Rate certified. ${r.outstanding.length} step(s) `
                               + "were outstanding and are recorded with it.");
                      setSignature(""); setNote(""); load();
                    } catch (e) { toast.fail(String(e.message || e)); }
                    finally { setBusy(false); }
                  }}>
            {busy ? "Signing…" : "Certify this rate"}
          </button>
        </div>
      )}
    </Card>
  );
}
