import React, { useEffect, useState } from "react";

import { api } from "../api.js";

/* Whether the rate under this screen's figures carries a signature.
 *
 * `082` put this on a rendered invoice and gave the rule: *fill in and
 * classify and upload and seal anywhere and anytime, but anything after
 * rates has to have everything up to rates locked and Tom certify the rates
 * — and anything used to test or evaluate without his seal just says NOT
 * CERTIFIED on the footer.*
 *
 * The paper said it and the screens did not. `Certification.jsx` is the
 * panel where Tom signs, on the rate screen; this is the one-line statement
 * that belongs on every screen that *produces* something — the reports, the
 * restatement, the return, the auditor's report. A controller who downloads
 * a workbook from a screen carrying no band and opens it to find NOT
 * CERTIFIED has learned the screen and the paper disagree.
 *
 * Three rules, each one this repository already keeps:
 *
 *  - **It prints in both directions.** Silent-when-certified is the same
 *    defect as silent-when-not: a reader left to assume assumes generously.
 *  - **Nothing is blocked by it.** The band is a statement, never a gate.
 *    Every button beside it still works, because testing against real
 *    figures is ordinary work and a machine that refused it is one people
 *    route around.
 *  - **It is read from the record, not remembered.** A flag set when the
 *    certify call returned is wrong the moment somebody reloads or the other
 *    controller withdraws.
 */
export default function CertificationBand({ period = "2025" }) {
  const [state, setState] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api.certification(period)
      .then((d) => { if (live) setState(d); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [period]);

  // Nothing read is not the same as nothing to say. A band that renders
  // empty on a failed read is a screen quietly dropping the one sentence it
  // exists to carry, which is `FailureBell`'s whole argument.
  if (failed) {
    return (
      <div className="cert-band cert-band-unknown">
        <strong>CERTIFICATION UNKNOWN</strong>
        <span>
          The signature could not be read just now, so treat anything produced
          from this screen as unsigned.
        </span>
      </div>
    );
  }
  if (!state) return null;

  if (state.certified) {
    const when = state.certified_at
      ? new Date(state.certified_at).toLocaleDateString(undefined,
          { day: "numeric", month: "short", year: "numeric" })
      : "";
    const open = (state.outstanding || []).length;
    return (
      <div className="cert-band cert-band-ok">
        <strong>CERTIFIED</strong>
        <span>
          {state.certified_by}{when ? ` · ${when}` : ""}
          {open > 0 && (
            <> · the signature records {open} step
              {open === 1 ? "" : "s"} still open, and they travel with it</>
          )}
        </span>
      </div>
    );
  }

  return (
    <div className="cert-band cert-band-no">
      <strong>NOT CERTIFIED</strong>
      <span>
        {state.why_not || "The rate carries no signature."}{" "}
        Everything here still works — anything produced now simply says so on
        its face.
      </span>
    </div>
  );
}
