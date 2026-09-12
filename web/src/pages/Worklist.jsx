import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Card, Table, Empty, Drawer, Field, Pill, Tick, useToast }
  from "../components/ui.jsx";
import { forKind } from "../worklistKinds.js";

const money = (v) =>
  v === null || v === undefined
    ? "—"
    : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

/* Recommending an item.
 *
 * The helper recommends; the controller verifies and seals. This raises a
 * job against the outstanding item and nothing else — never a row in the
 * register the item points at, because `PROPOSED` on a restatement already
 * means *the sponsor has not answered* and a second meaning in one word is
 * how a reader stops being able to tell a position from a suggestion.
 *
 * The reason is required and the button says so before it is pressed. A
 * recommendation with no reason is the machine's own list with a person's
 * name on it, which is worth less than the machine's list: the reader now
 * has to work out whether a human added anything. */
function Recommend({ item, onDone, onClose }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [handTo, setHandTo] = useState("");
  const [busy, setBusy] = useState(false);
  const short = reason.trim().length < 15;

  return (
    <Drawer
      open={!!item}
      onClose={onClose}
      title="Recommend this to somebody"
      subtitle={item ? item.label : ""}
      footer={
        <button className="btn primary" disabled={short || busy}
          onClick={async () => {
            setBusy(true);
            try {
              const got = await api.recommend({
                kind: item.kind, entity_id: item.entity_id,
                reason: reason.trim(),
                hand_to: handTo.trim() || null,
              });
              /* `assigned: false` is a real outcome, not a failure — more
                 than one candidate means no candidate, and the answer says
                 which of the two happened rather than leaving it to be
                 guessed from a silent success. */
              (got.assigned ? toast.ok : toast.warn)(
                got.assigned
                  ? `Recommended to ${got.to_whom}`
                  : `On the list, unassigned — ${got.to_whom}`);
              onDone();
            } catch (e) {
              toast.fail(String(e.message || e));
            } finally { setBusy(false); }
          }}>
          {short ? "Say why first" : "Recommend"}
        </button>
      }>
      {item && (
        <>
          <p className="rowsub" style={{ marginTop: 0 }}>
            This raises a job against <strong>{item.label}</strong> and
            changes nothing else. Whoever it reaches decides what to do
            about it — a recommendation is not a decision, and nothing here
            touches a classification, a rate or a claim on a sponsor.
          </p>
          <Field label="Why this one"
                 hint="What you noticed. This is the half of the record that
                       says who spotted it, beside the half that says who
                       decided." required>
            <textarea rows={4} value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="e.g. Schedule B budgets no indirect at all
                                   against $583,594 of labour — worth
                                   measuring against the sealed rate." />
          </Field>
          <Field label="Who should look at it"
                 hint="An email address or an account id. Left blank it goes
                       to whoever holds CONTROLLER — and to nobody, with the
                       reason on it, when more than one person does.">
            <input value={handTo} onChange={(e) => setHandTo(e.target.value)}
                   placeholder="Leave blank for whoever holds CONTROLLER" />
          </Field>
        </>
      )}
    </Drawer>
  );
}

export default function Worklist({ actor }) {
  const { kind } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [recommending, setRecommending] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    setData(null);
    api.worklist({ kind, limit: 200 })
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, [kind, nonce]);

  const meta = forKind(kind);

  /* Offered to whoever could actually do it, the way the Requests screen
     offers Accept. The auditor reads every one of these rows and holds no
     portfolio, so a Recommend button on their screen is a 403 they could not
     have predicted — and the rule cuts the other way too, which is why it
     asks for *any* portfolio rather than the item's: the handler decides
     whose list a given item is on, and a second copy of that rule here is
     one free to drift from it. */
  const held = new Set(actor?.portfolios || []);
  const mayRecommend = held.size > 0;

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <button className="btn quiet" onClick={() => nav("/")}>← Dashboard</button>
          <h1>{meta.title}</h1>
          <p className="quiet">{meta.why}</p>
        </div>
      </div>

      <Card
        title={data ? `${data.total} item${data.total === 1 ? "" : "s"}`
                     + (data.shown < data.total ? ` · showing ${data.shown}` : "")
                     : "Loading"}
        aside={
          meta.to ? (
            <button className="btn" onClick={() => nav(meta.to)}>{meta.where}</button>
          ) : (
            <span className="quiet small">{meta.where}</span>
          )
        }
      >
        {error && <Empty mark="!" title="Could not load">{error}</Empty>}
        {data && data.total === 0 && (
          <Empty mark="✓" title="Nothing open in this class" />
        )}
        {data && data.items.length > 0 && (
          <Table columns={[
            { label: "", width: 34, align: "left" },
            { label: "Item", align: "left" }, { label: "Detail", align: "left" },
            { label: "Amount" },
            ...(mayRecommend
                ? [{ label: "", align: "left", width: "130px" }] : []),
          ]}>
            {data.items.map((r, i) => (
              <tr key={i}>
                <td className="l">
                  <Tick state={r.severity === "BLOCKING" ? "failed" : "flagged"} />
                </td>
                <td className="l">
                  <div className="strong ellipsis">{r.label}</div>
                  <div className="quiet small">
                    {r.entity}
                    {r.owner_portfolio && <> · <Pill>{r.owner_portfolio}</Pill></>}
                  </div>
                </td>
                <td className="l quiet small">{r.detail}</td>
                <td className="num">{money(r.amount)}</td>
                {mayRecommend && (
                  <td className="l">
                    <button className="btn sm"
                            onClick={() => setRecommending(r)}>Recommend</button>
                  </td>
                )}
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Recommend item={recommending} onClose={() => setRecommending(null)}
                 onDone={() => { setRecommending(null); setNonce((n) => n + 1); }} />
    </div>
  );
}
