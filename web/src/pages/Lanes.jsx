import React, { useCallback, useEffect, useState } from "react";
import { api, money } from "../api.js";
import { Card, Drawer, Empty, Field, PageHead, Pill, Table, Tick, useToast } from "../components/ui.jsx";
import { POOLS, PoolChip } from "../components/pool.jsx";

export default function Lanes() {
  const toast = useToast();
  const [lanes, setLanes] = useState([]);
  const [buildup, setBuildup] = useState(null);
  const [creating, setCreating] = useState(null);
  const [picked, setPicked] = useState([]);
  const [comparison, setComparison] = useState(null);

  const load = useCallback(() => api.lanes().then(setLanes).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  /* The baseline goes first if it is in the selection, because it is what a
     reviewer reads the others against — a delta measured from a sandbox is
     a comparison between two things nobody has committed to. */
  const order = (ids) => {
    const base = lanes.find((l) => l.kind === "BASELINE")?.lane_id;
    return base && ids.includes(base) ? [base, ...ids.filter((i) => i !== base)] : ids;
  };

  const compare = async () => {
    try {
      setComparison(await api.compareLanes(order(picked)));
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  const toggle = (id) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id)
                                     : p.length >= 4 ? p : [...p, id]));

  const openLane = async (l) => {
    const [rows, overrides, assumptions] = await Promise.all([
      api.laneBuildup(l.lane_id), api.laneOverrides(l.lane_id),
      api.laneAssumptions(l.lane_id),
    ]);
    setBuildup({ lane: l, rows, overrides, assumptions });
  };
  const reopen = () => buildup && openLane(buildup.lane).then(load);

  const create = async () => {
    try {
      await api.createLane(creating);
      toast(`Lane "${creating.name}" created as a sandbox`);
      setCreating(null);
      load();
    } catch (e) { toast(String(e.message || e), { tone: "bad" }); }
  };

  return (
    <div className="page">
      <PageHead title="Testing lanes" schedule="C">
        Fork a lane to test alternative classifications without touching the baseline.
          Changing an assumption is free. Changing a classification carries a reason and
          appears in the audit package, so exploration stays visible rather than quiet.
      </PageHead>

      <Card variant="quiet" title="Two different things that look alike">
        <div className="grid two">
          <div>
            <Pill tone="accent">Assumption</Pill>
            <div className="rowsub" style={{ marginTop: 6 }}>
              Tenant share at 40% rather than 55%. Evidence-neutral, changes no judgment,
              and exactly what sensitivity analysis is for. Unrestricted.
            </div>
          </div>
          <div>
            <Pill tone="warn">Classification override</Pill>
            <div className="rowsub" style={{ marginTop: 6 }}>
              Reclassify Portfolio consulting and see what happens. Legitimate analysis, and
              also the behaviour that would hollow out the seal if nobody could see it. Reason
              required, counted, disclosed.
            </div>
          </div>
        </div>
      </Card>

      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center",
                    gap: 10, margin: "16px 0 10px" }}>
        {picked.length > 0 && (
          <span className="rowsub">
            {picked.length} selected{picked.length < 2 && " — pick one more to compare"}
          </span>
        )}
        <button disabled={picked.length < 2} onClick={compare}>
          Compare side by side
        </button>
        <button className="primary"
                onClick={() => setCreating({ name: "", purpose: "", created_by: "tom" })}>
          New lane
        </button>
      </div>

      {comparison && (
        <Comparison c={comparison} onClose={() => setComparison(null)} />
      )}

      {lanes.length === 0 ? (
        <Card><Empty mark="⑂" title="No lanes yet">
          The baseline is created with the first decision set. Fork it when you want to test
          an alternative treatment.
        </Empty></Card>
      ) : (
        <Table columns={[
          { label: "", width: 34, align: "left" },
          { label: "Lane", align: "left" }, { label: "Kind", align: "left" },
          { label: "Purpose", align: "left" }, { label: "Overrides" },
          { label: "Assumptions" }, { label: "Created by", align: "left" }, { label: "", width: 110, align: "left" },
        ]}>
          {lanes.map((l) => (
            <tr key={l.lane_id} className="hoverable">
              <td className="l">
                <input type="checkbox" checked={picked.includes(l.lane_id)}
                       onChange={() => toggle(l.lane_id)}
                       aria-label={`Compare ${l.name}`} />
              </td>
              <td className="l" style={{ fontWeight: 600 }}>{l.name}</td>
              <td className="l">
                <Pill tone={l.kind === "BASELINE" ? "solid" : l.kind === "CANDIDATE" ? "accent" : ""}>
                  {l.kind}
                </Pill>
              </td>
              <td className="l wrap rowsub">{l.purpose}</td>
              <td style={{ color: l.classification_overrides > 0 ? "var(--warn)" : undefined }}>
                {l.classification_overrides}
              </td>
              <td>{l.assumption_variants}</td>
              <td className="l rowsub">{l.created_by}</td>
              <td className="l">
                <button className="sm" onClick={() => openLane(l)}>Open</button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Drawer open={!!buildup} onClose={() => setBuildup(null)}
              title={buildup?.lane.name}
              subtitle="Pool build-up, and the readings behind it — no rate computed here">
        {buildup && (
          <>
            <Table columns={[
              { label: "Pool", align: "left" }, { label: "Amount" },
              { label: "Lines" }, { label: "Overridden" },
              { label: "Of which unjudged" },
            ]}>
              {buildup.rows.map((b) => (
                <tr key={b.pool}>
                  <td className="l"><PoolChip pool={b.pool} /></td>
                  <td className="amt strong">{money(b.amount)}</td>
                  <td>{b.lines}</td>
                  <td>{b.overridden_decisions || ""}</td>
                  {/* Cost the lane pulled out of the queue, kept apart from
                      cost it moved between pools. Only the first changes how
                      much there is left to judge. */}
                  <td className="amt">
                    {Number(b.from_unjudged) ? money(b.from_unjudged) : ""}
                  </td>
                </tr>
              ))}
            </Table>

            <Overrides lane={buildup.lane} rows={buildup.overrides}
                       onChange={reopen} toast={toast} />
            <Assumptions lane={buildup.lane} rows={buildup.assumptions}
                         onChange={reopen} toast={toast} />
          </>
        )}
      </Drawer>

      <Drawer open={!!creating} onClose={() => setCreating(null)} title="New lane"
              subtitle="Starts as a sandbox — a sandbox can never produce a submitted rate"
              footer={
                <>
                  <button className="primary" disabled={!creating?.name || !creating?.purpose}
                          onClick={create}>Create lane</button>
                  <button onClick={() => setCreating(null)}>Cancel</button>
                </>
              }>
        {creating && (
          <>
            <Field label="Name">
              <input value={creating.name} placeholder="2025-portfolio-direct"
                     onChange={(e) => setCreating({ ...creating, name: e.target.value })} />
            </Field>
            <div style={{ marginTop: 14 }}>
              <Field label="Purpose" required>
                <textarea rows={3} value={creating.purpose}
                          placeholder="What question is this lane meant to answer?"
                          onChange={(e) => setCreating({ ...creating, purpose: e.target.value })} />
              </Field>
            </div>
            <div className="rowsub" style={{ marginTop: 10 }}>
              The purpose prints in the audit package next to how many classification
              overrides the lane carried. Write it for a reviewer.
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}


/* ── Side by side ───────────────────────────────────────────────────────
   Every figure here is read from `v_lane_buildup`; the only arithmetic is a
   difference between two recorded amounts, done in the database. There is
   deliberately no rate: a lane is not sealed, and a rate needs a seal.
   Showing one here would put a figure on a screen with nothing behind it,
   which is the mistake the whole classification queue is built to avoid. */
function Comparison({ c, onClose }) {
  const wide = c.lanes.length;
  return (
    <Card title="Side by side"
          aside={`${wide} readings · deltas against ${c.lanes[0].name}`}
          style={{ marginBottom: 16 }}>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${wide}, 1fr)`,
                                     gap: 12, marginBottom: 12 }}>
        {c.lanes.map((l, i) => (
          <div key={l.lane_id}>
            <Pill tone={l.kind === "BASELINE" ? "solid" : l.kind === "CANDIDATE" ? "accent" : ""}>
              {l.kind}
            </Pill>{" "}
            <strong>{l.name}</strong>
            <div className="rowsub wrap" style={{ marginTop: 4 }}>{l.purpose}</div>
            <div className="rowsub" style={{ marginTop: 4 }}>
              {l.overrides} override{l.overrides === 1 ? "" : "s"} ·{" "}
              {l.assumptions} assumption{l.assumptions === 1 ? "" : "s"}
              {i === 0 && " · the base"}
            </div>
          </div>
        ))}
      </div>

      {/* Said, not left to be inferred from a column of zeroes. Every lane
          read identically for as long as nothing could record an override,
          and a reader seeing that would reasonably assume the screen was
          broken rather than that the lanes agree. */}
      {c.identical_to_base.length > 0 && (
        <div className="rowsub warnish" style={{ marginBottom: 10 }}>
          {c.identical_to_base.length === c.lanes.length - 1
            ? "Every lane here reads exactly as the base does."
            : `${c.identical_to_base.length} of these read exactly as the base does.`}{" "}
          A lane differs only where it records an override — open it and try one.
        </div>
      )}

      <Table columns={[
        { label: "Pool", align: "left" },
        ...c.lanes.flatMap((l, i) => (i === 0
          ? [{ label: l.name }]
          : [{ label: l.name }, { label: "vs base" }])),
      ]}>
        {c.pools.map((row) => (
          <tr key={row.pool}>
            <td className="l"><PoolChip pool={row.pool} /></td>
            {row.cells.map((cell, i) => (
              <React.Fragment key={cell.lane_id}>
                <td className="amt">{money(cell.amount)}</td>
                {i > 0 && (
                  <td className={"amt " + (Number(cell.delta) < 0 ? "neg" : "")}>
                    {Number(cell.delta) === 0
                      ? <span className="rowsub">—</span>
                      : <>{Number(cell.delta) > 0 ? "+" : ""}{money(cell.delta)}</>}
                  </td>
                )}
              </React.Fragment>
            ))}
          </tr>
        ))}
      </Table>
      <div style={{ marginTop: 12 }}>
        <button className="sm" onClick={onClose}>Close</button>
      </div>
    </Card>
  );
}


/* ── The readings a lane has tried ─────────────────────────────────────── */
function Overrides({ lane, rows, onChange, toast }) {
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [groups, setGroups] = useState([]);
  const [f, setF] = useState({ pool: "G&A", grade: "TEST_ASSUMPTION", reason: "" });
  const [chosen, setChosen] = useState(null);
  const baseline = lane.kind === "BASELINE";

  const search = async (text) => {
    setQ(text);
    if (text.trim().length < 2) { setGroups([]); return; }
    try {
      setGroups(await api.queue({ search: text.trim(), limit: 8 }));
    } catch { setGroups([]); }
  };

  const add = async () => {
    try {
      const got = await api.addLaneOverride(lane.lane_id, {
        pool: f.pool, grade: f.grade, reason: f.reason,
        account: chosen.account, payee: chosen.payee,
        function_990: f.pool === "G&A" ? "MANAGEMENT_AND_GENERAL" : "NOT_APPLICABLE",
      });
      toast.ok(`Tried on ${got.lines} lines, ${money(got.amount)}`
               + (got.departs_from ? " — departing from a live judgment" : ""));
      setAdding(false); setChosen(null); setQ(""); setGroups([]);
      setF({ pool: "G&A", grade: "TEST_ASSUMPTION", reason: "" });
      onChange();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  const drop = async (id) => {
    try {
      await api.removeLaneOverride(lane.lane_id, id);
      toast.ok("Withdrawn");
      onChange();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  return (
    <Card variant="quiet" title="Classification overrides"
          aside="Counted, reasoned, disclosed" style={{ marginTop: 16 }}>
      {baseline ? (
        <div className="rowsub">
          This is the baseline — the classifications that will be submitted.
          Changing those goes through the queue and the seal, in front of the
          trigger that refuses a rate whose seal does not match. Fork a
          sandbox to try something.
        </div>
      ) : rows.length === 0 ? (
        <div className="rowsub">
          Nothing tried yet, so this lane reads exactly as the baseline does.
        </div>
      ) : (
        <Table columns={[
          { label: "Reading", align: "left" }, { label: "Amount" },
          { label: "Lines" }, { label: "Why", align: "left" },
          { label: "", width: 90, align: "left" },
        ]}>
          {rows.map((o) => (
            <tr key={o.override_id}>
              <td className="l"><PoolChip pool={o.pool} objective={o.objective_id} /></td>
              <td className="amt strong">{money(o.amount)}</td>
              <td>{o.lines}</td>
              <td className="l wrap rowsub">
                {o.reason}
                <div style={{ marginTop: 3 }}>{o.grade} · {o.created_by}</div>
              </td>
              <td className="l">
                <button className="sm" onClick={() => drop(o.override_id)}>Withdraw</button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {!baseline && !adding && (
        <button className="sm" style={{ marginTop: 10 }}
                onClick={() => setAdding(true)}>Try a reading</button>
      )}

      {!baseline && adding && (
        <div style={{ marginTop: 12 }}>
          <Field label="Which cost">
            <input value={q} placeholder="Search the queue — account or payee"
                   onChange={(e) => search(e.target.value)} />
          </Field>
          {chosen ? (
            <div className="rowsub" style={{ marginTop: 6 }}>
              {chosen.account} · {chosen.payee || "no payee"} ·{" "}
              {money(chosen.amount)} over {chosen.line_count} lines{" "}
              <button className="sm" onClick={() => setChosen(null)}>change</button>
            </div>
          ) : groups.map((g) => (
            <div key={g.account + g.payee} className="rowsub hoverable"
                 style={{ cursor: "pointer", padding: "3px 0" }}
                 onClick={() => { setChosen(g); setGroups([]); }}>
              {g.account} · {g.payee || "no payee"} · {money(g.amount)}
              {g.decided ? " · already judged" : " · not judged yet"}
            </div>
          ))}

          <div className="grid two" style={{ marginTop: 12 }}>
            <Field label="Read it as">
              <select value={f.pool} onChange={(e) => setF({ ...f, pool: e.target.value })}>
                {Object.keys(POOLS).filter((p) => p !== "DIRECT").map((p) => (
                  <option key={p} value={p}>{POOLS[p].label}</option>
                ))}
              </select>
            </Field>
            <Field label="On what">
              <select value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })}>
                <option value="TEST_ASSUMPTION">Test assumption</option>
                <option value="MANAGEMENT_RECONSTRUCTION">Management reconstruction</option>
                <option value="CORROBORATED">Corroborated</option>
              </select>
            </Field>
          </div>
          {/* DIRECT is absent from the list on purpose: it needs an objective,
              and a lane picking one from a dropdown would be choosing what a
              cost is direct *to* without the evidence that makes it so. */}
          <div className="rowsub" style={{ marginTop: 4 }}>
            Direct is not offered here — it names the objective the cost is
            direct to, and that is a judgment for the queue.
          </div>
          <div style={{ marginTop: 12 }}>
            <Field label="Why this reading is worth trying" required>
              <textarea rows={3} value={f.reason}
                        placeholder="A reviewer reads this next to the number it moved."
                        onChange={(e) => setF({ ...f, reason: e.target.value })} />
            </Field>
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button className="primary" disabled={!chosen || !f.reason.trim()}
                    onClick={add}>Try it</button>
            <button onClick={() => { setAdding(false); setChosen(null); }}>Cancel</button>
          </div>
        </div>
      )}
    </Card>
  );
}


/* ── And the assumptions, which need no paper trail but do carry a grade ── */
function Assumptions({ lane, rows, onChange, toast }) {
  const [f, setF] = useState({ key: "", value: "", basis: "", grade: "TEST_ASSUMPTION" });
  const baseline = lane.kind === "BASELINE";

  const save = async () => {
    try {
      await api.setLaneAssumption(lane.lane_id, { ...f, value: f.value });
      toast.ok(`${f.key} set`);
      setF({ key: "", value: "", basis: "", grade: "TEST_ASSUMPTION" });
      onChange();
    } catch (e) { toast.fail(String(e.message || e)); }
  };

  return (
    <Card variant="quiet" title="Assumption variants"
          aside="Free to vary — still says what each rests on" style={{ marginTop: 16 }}>
      {rows.length === 0 ? (
        <div className="rowsub">None set.</div>
      ) : (
        <Table columns={[
          { label: "Assumption", align: "left" }, { label: "Value" },
          { label: "On what", align: "left" }, { label: "Basis", align: "left" },
        ]}>
          {rows.map((a) => (
            <tr key={a.key}>
              <td className="l"><strong>{a.key}</strong></td>
              <td className="amt">{a.value}</td>
              <td className="l rowsub">{a.grade}</td>
              <td className="l wrap rowsub">{a.basis}</td>
            </tr>
          ))}
        </Table>
      )}
      {!baseline && (
        <div className="grid two" style={{ marginTop: 12, alignItems: "end" }}>
          <Field label="Assumption">
            <input value={f.key} placeholder="tenant_share"
                   onChange={(e) => setF({ ...f, key: e.target.value })} />
          </Field>
          <Field label="Value">
            <input value={f.value} placeholder="0.40" inputMode="decimal"
                   onChange={(e) => setF({ ...f, value: e.target.value })} />
          </Field>
          <Field label="What it rests on">
            <input value={f.basis} placeholder="Square footage from the space book"
                   onChange={(e) => setF({ ...f, basis: e.target.value })} />
          </Field>
          <div>
            <button className="sm" disabled={!f.key.trim() || !f.value.trim()}
                    onClick={save}>Set</button>
          </div>
        </div>
      )}
    </Card>
  );
}
