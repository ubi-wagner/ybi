import React, { useEffect, useState } from "react";
import { api, count } from "../api.js";
import { Card, Empty, Pill, Stat, Table, Tick } from "./ui.jsx";

/* How much the documents in each family differ in form.
 *
 * The question behind it is whether the parsers survive next year's exports.
 * Every one of them was written against a single instance and three have
 * already been caught by the second: the asset schedule that prints a system
 * number only when it changes, the two agreements with no numbered clause
 * anywhere, and the one that is thirty-six pages and seventy characters.
 *
 * Nothing here is computed. Every figure is read from `v_document_
 * variability`, which is the view that owns it — a second reading in the
 * screen is one that can disagree with the register and the drive.
 */

const STATE = {
  VARIES:    ["flagged", "warn",    "the documents in this family are not the same shape"],
  UNIFORM:   ["done",    "good",    "every one has been the same shape so far"],
  "NO DATA": ["open",    "plain",   "one document — nothing has been read twice"],
};

export default function FormVariability() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.documentVariability().then(setD).catch((e) => setErr(String(e?.message || e)));
  }, []);

  if (err) return null;                 // the bell already holds the failure
  if (!d) return null;

  const c = d.coverage || {};
  const families = d.families || [];
  const shown = showAll ? families : families.filter((f) => f.state !== "NO DATA");

  return (
    <Card variant="quiet" title="What these papers look like"
          aside={<Pill tone="plain">form, not content</Pill>}>
      <p className="rowsub" style={{ marginTop: 0 }}>
        Every parser here was written against one instance of its document.
        This is whether a second one has ever been the same shape — the
        question that decides whether next year's exports load or break.
      </p>

      <div className="grid three">
        <Stat label="Families that vary" value={count(c.families_varying)}
              size="lg" note="a parser can be wrong about each difference" />
        <Stat label="Families of one" value={count(c.families_of_one)}
              size="lg"
              note="never met a second document, so nothing is ruled out" />
        <Stat label="Not readable as text" value={count(c.without_usable_text)}
              size="lg" note="no clause of these can be checked" />
      </div>

      {families.length === 0 ? (
        <Empty mark="?" title="No document has been read yet">
          The form is read at the door as a document arrives. For papers filed
          before that, <code>scripts/read_shapes.py</code> goes back for them.
        </Empty>
      ) : (
        <Table columns={["Family", "On file", "", "What differs"]}>
          {shown.map((f) => {
            const [tick, tone, why] = STATE[f.state] || ["open", "plain", ""];
            return (
              <tr key={f.family}>
                <td className="l">
                  {f.family}
                  <div className="rowsub">{why}</div>
                </td>
                <td className="num">{count(f.instances)}</td>
                <td className="l"><Tick state={tick} /> <Pill tone={tone}>{f.state}</Pill></td>
                <td className="l">
                  {f.varies_on?.length
                    ? f.varies_on.join(", ")
                    : <span className="rowsub">—</span>}
                </td>
              </tr>
            );
          })}
        </Table>
      )}

      {/* A family of one is the honest state and it is also most of the
          list, so it is collapsed rather than dropped: hiding it would say
          the record has been checked for variability when eight of its
          families cannot be. */}
      {families.some((f) => f.state === "NO DATA") && (
        <button className="btn sm" onClick={() => setShowAll(!showAll)}>
          {showAll
            ? "Hide the families holding one document"
            : `Show ${count(families.filter((f) => f.state === "NO DATA").length)} family(ies) holding one document`}
        </button>
      )}

      {d.thin?.length > 0 && (
        <>
          <h4 style={{ marginBottom: 4 }}>On file and not readable as text</h4>
          <p className="rowsub" style={{ marginTop: 0 }}>
            A citation into one of these cannot be checked against the
            document. That is a fact about the paper, not a gap in the record.
          </p>
          <Table columns={["Document", "Pages", "Characters a page", ""]}>
            {d.thin.map((t) => (
              <tr key={t.evidence_id}>
                <td className="l">{t.filename}</td>
                <td className="num">{count(t.pages)}</td>
                <td className="num">{t.chars_per_page}</td>
                <td className="l"><Pill tone="warn">{t.text_layer}</Pill></td>
              </tr>
            ))}
          </Table>
        </>
      )}

      {d.unreadable?.length > 0 && (
        <>
          <h4 style={{ marginBottom: 4 }}>Could not be read at all</h4>
          <Table columns={["Document", "Why"]}>
            {d.unreadable.map((u) => (
              <tr key={u.evidence_id}>
                <td className="l">{u.filename}</td>
                <td className="l">{u.why}</td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </Card>
  );
}
