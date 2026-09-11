import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, Field, PageHead, Pill, Segmented, Stat, Table, Tick, useToast } from "../components/ui.jsx";

/*
  Five buildings, the space in them, and what it is all worth.

  The subsidy column is the one nobody has ever added up: an incubator lets
  space below market and lends equipment for nothing, and that gap is the
  mission. It is deliberately shown next to a standing line about what it is
  not — forgone rent on your own building is not cost share, and the moment a
  big number appears on a screen somebody will want to put it on a federal
  report.
*/

const money = (v) => v === null || v === undefined ? "—"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const sqft = (v) => v === null || v === undefined ? "—"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const pct = (v) => v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(0)}%`;

const USES = ["TENANT", "PROGRAM", "ADMINISTRATIVE", "SHARED_LAB", "COMMON",
              "VACANT", "COMMITTED"];
const STATUSES = ["OCCUPIED", "VACANT", "INTERNAL", "COMMITTED", "COMMON"];

export default function Facilities({ actor }) {
  const canWrite = actor?.role === "CONTROLLER";
  const [tab, setTab] = useState("buildings");
  const [data, setData] = useState(null);
  const [space, setSpace] = useState(null);
  const [kit, setKit] = useState(null);
  const [inKind, setInKind] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [f, s, e, k] = await Promise.all([
        api.facilities(), api.spaceUnits({}), api.equipment(), api.inKind(),
      ]);
      setData(f); setSpace(s); setKit(e); setInKind(k); setError("");
    } catch (err) { setError(String(err.message || err)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <Empty mark="!" title="Could not load">{error}</Empty>;
  if (!data) return <Empty mark="…" title="Loading" />;

  const f = data.facilities || [];
  const totals = space?.totals || {};
  const kitTotals = kit?.totals || {};

  return (
    <div className="dash">
      <PageHead title="Facilities and equipment" schedule="E">
        {f.length} building{f.length === 1 ? "" : "s"} — what the space is used
        for, and what it is worth.
      </PageHead>

      <Card variant="raised">
        <div className="stat-row">
          <Stat label="Usable area" size="lg"
                value={sqft(f.reduce((a, r) => a + Number(r.usable_sqft || 0), 0))}
                note="square feet" />
          <Stat label="Charged" value={money(totals.charged)} note="rent billed" />
          <Stat label="At market" value={money(totals.market_value)} />
          <Stat label="Subsidy" size="lg" value={money(totals.subsidy)}
                note="mission value, not cost share" />
          <Stat label="Equipment given" value={money(kitTotals.subsidy)}
                note={`${sqft(kitTotals.hours)} hours`} />
        </div>
        <p className="quiet small" style={{ marginTop: 14 }}>
          Letting YBI's own space and equipment below market is the mission and
          it is worth counting — for the board, the 990 narrative and the state.
          It is <strong>not</strong> cost share: 2 CFR 200.465 allows a
          less-than-arm's-length rental only up to what ownership would have
          cost, so forgone rent on your own building is not a cost you
          incurred. Space or equipment somebody gives <em>to</em> YBI is a
          different matter, and is recorded as such.
        </p>
      </Card>

      <Segmented value={tab} onChange={setTab} options={[
        ["buildings", "Buildings"], ["space", "Rent roll"],
        ["equipment", "Equipment"], ["inkind", "In kind"]]} />

      {tab === "buildings" && (
        <Card title="Buildings" aside="Square footage has to account for itself">
          {f.length === 0 ? (
            <Empty mark="—" title="No buildings recorded">
              Add the five buildings and their usable area, then the rent roll.
            </Empty>
          ) : (
            <Table columns={[
              { label: "", width: 34, align: "left" },
              { label: "Building", align: "left" }, { label: "Usable" },
              { label: "Units" }, { label: "Charged" }, { label: "At market" },
              { label: "Subsidy" }, { label: "Equipment" },
              { label: "Tenure", align: "left" },
            ]}>
              {f.map((r) => {
                const ctl = (data.control || []).find(
                  (c) => c.facility_id === r.facility_id);
                return (
                  <tr key={r.facility_id}>
                    <td className="l">
                      <Tick state={ctl?.ties ? "done" : ctl?.units ? "failed" : "open"}
                            title={ctl?.ties ? "Units reconcile to the building"
                              : ctl?.units ? `Units are ${ctl.variance} sqft out`
                              : "No units recorded yet"} />
                    </td>
                    <td className="l">
                      <span className="strong">{r.name}</span>
                      <div className="quiet small">{r.code || r.address}</div>
                    </td>
                    <td className="num">{sqft(r.usable_sqft)}</td>
                    <td className="num">{r.units}</td>
                    <td className="num">{money(r.charged)}</td>
                    <td className="num">{money(r.market_value)}</td>
                    <td className="num strong">{money(r.subsidy)}</td>
                    <td className="num quiet">{sqft(r.equipment_sqft)}</td>
                    <td className="l quiet small">
                      {r.owned ? "owned" : `leased · ${r.landlord}`}
                      {r.units_without_market > 0 &&
                        <div className="amt neg">{r.units_without_market} without a market rate</div>}
                    </td>
                  </tr>
                );
              })}
            </Table>
          )}
          {canWrite && <FacilityForm onSaved={load} />}
        </Card>
      )}

      {tab === "space" && (
        <Card title="Rent roll"
              aside={`${(space?.space || []).length} spaces · market beside actual`}>
          {(space?.space || []).length === 0 ? (
            <Empty mark="—" title="No spaces recorded" />
          ) : (
            <Table columns={[
              { label: "Space", align: "left" }, { label: "Use", align: "left" },
              { label: "Occupant", align: "left" }, { label: "Sqft" },
              { label: "Months" }, { label: "Charged" }, { label: "$/sqft" },
              { label: "At market" }, { label: "Subsidy" },
            ]}>
              {space.space.map((u) => (
                <tr key={u.unit_id}>
                  <td className="l">
                    <span className="strong">{u.label}</span>
                    <div className="quiet small">{u.facility_name}</div>
                  </td>
                  <td className="l"><Pill>{u.use}</Pill></td>
                  <td className="l quiet small">
                    {u.occupant || (u.objective_id ? u.objective_id : "—")}
                  </td>
                  <td className="num">{sqft(u.usable_sqft)}</td>
                  <td className="num quiet">{Number(u.months_occupied)}</td>
                  <td className="num">{money(u.actual_annual_charge)}</td>
                  <td className="num quiet">{u.market_rate_psf ? Number(u.market_rate_psf).toFixed(2) : "—"}</td>
                  <td className="num">{money(u.market_value)}</td>
                  <td className={`num strong ${Number(u.subsidy) < 0 ? "amt neg" : ""}`}>
                    {money(u.subsidy)}
                  </td>
                </tr>
              ))}
            </Table>
          )}
          {canWrite && <SpaceForm facilities={f} onSaved={load} />}
        </Card>
      )}

      {tab === "equipment" && (
        <>
          <Card title="Equipment"
                aside="What its use was worth, against what was charged">
            {(kit?.equipment || []).length === 0 ? (
              <Empty mark="—" title="No equipment recorded">
                The asset register lands here. Program equipment needs a
                footprint and, where it is lent, an hourly rate with a basis.
              </Empty>
            ) : (
              <Table columns={[
                { label: "Asset", align: "left" }, { label: "Access", align: "left" },
                { label: "Footprint" }, { label: "Hours" }, { label: "Charged" },
                { label: "At market" }, { label: "Given" },
              ]}>
                {kit.equipment.map((a) => (
                  <tr key={a.asset_id}>
                    <td className="l">
                      <span className="strong">{a.description}</span>
                      <div className="quiet small">
                        {a.asset_id}
                        {a.is_program_equipment && " · programme equipment"}
                      </div>
                    </td>
                    <td className="l">
                      <Pill tone={a.access === "FREE" ? "accent" : ""}>{a.access}</Pill>
                      {a.rate_unknown && <div className="amt neg small">no rate</div>}
                    </td>
                    <td className="num">{sqft(a.footprint_sqft)}</td>
                    <td className="num">{sqft(a.hours_used)}</td>
                    <td className="num">{money(a.charged)}</td>
                    <td className="num">{money(a.market_value)}</td>
                    <td className="num strong">{money(a.subsidy)}</td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          {(kit?.lab_space || []).length > 0 && (
            <Card title="Lab floor consumed by equipment"
                  aside="Square footage alone would spread this across everybody">
              <p className="quiet small">
                A machine dedicated to one programme standing in a shared lab
                takes space the carve-out otherwise treats as serving all of
                them. Where the share is large, hours of use are the better
                driver than floor area.
              </p>
              <Table columns={[
                { label: "Space", align: "left" }, { label: "Use", align: "left" },
                { label: "Usable" }, { label: "Equipment" },
                { label: "Programme kit" }, { label: "Free floor" },
                { label: "Occupied" },
              ]}>
                {kit.lab_space.map((l) => (
                  <tr key={l.unit_id}>
                    <td className="l strong">{l.label}</td>
                    <td className="l"><Pill>{l.use}</Pill></td>
                    <td className="num">{sqft(l.usable_sqft)}</td>
                    <td className="num">{sqft(l.equipment_sqft)}</td>
                    <td className="num">{sqft(l.program_equipment_sqft)}</td>
                    <td className="num">{sqft(l.free_sqft)}</td>
                    <td className={`num strong ${Number(l.occupied_share) > 0.4 ? "amt neg" : ""}`}>
                      {pct(l.occupied_share)}
                    </td>
                  </tr>
                ))}
              </Table>
            </Card>
          )}
        </>
      )}

      {tab === "inkind" && (
        <Card title="In kind"
              aside="What may go on a federal report, and what may only be told">
          {(inKind?.summary || []).length === 0 ? (
            <Empty mark="—" title="Nothing recorded yet" />
          ) : (
            <Table columns={[
              { label: "Kind", align: "left" }, { label: "Standing", align: "left" },
              { label: "Rule", align: "left" }, { label: "Items" },
              { label: "Value" },
            ]}>
              {inKind.summary.map((r, i) => (
                <tr key={i}>
                  <td className="l strong">{r.kind.replace(/_/g, " ").toLowerCase()}</td>
                  <td className="l">
                    <Pill tone={r.standing.startsWith("Third") ? "good"
                              : r.standing.startsWith("Mission") ? "" : "warn"}>
                      {r.standing}
                    </Pill>
                  </td>
                  <td className="l"><span className="mono-ref">{r.citation}</span></td>
                  <td className="num">{r.claims}</td>
                  <td className="num strong">{money(r.value)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function FacilityForm({ onSaved }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ facility_id: "", name: "", code: "", address: "",
                               owned: true, landlord: "", usable_sqft: "",
                               rentable_sqft: "", market_rate_psf: "",
                               market_basis: "", source_document: "" });
  const set = (k, x) => setV((s) => ({ ...s, [k]: x }));

  async function save() {
    try {
      await api.putFacility({
        ...v,
        usable_sqft: Number(v.usable_sqft),
        rentable_sqft: v.rentable_sqft ? Number(v.rentable_sqft) : null,
        market_rate_psf: v.market_rate_psf ? Number(v.market_rate_psf) : null,
      });
      toast(`${v.name} recorded`);
      setOpen(false);
      await onSaved();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { const p = JSON.parse(msg); detail = p.message || p.detail || msg; }
      catch { /* plain */ }
      toast(typeof detail === "string" ? detail : JSON.stringify(detail),
            { tone: "bad", sticky: true });
    }
  }

  if (!open) {
    return (
      <div className="ts-add">
        <button className="linkish" onClick={() => setOpen(true)}>+ Add a building</button>
      </div>
    );
  }
  return (
    <div className="splitter">
      <div className="terms-grid">
        <Field label="Code"><input value={v.code} onChange={(e) => set("code", e.target.value)} /></Field>
        <Field label="Identifier"><input value={v.facility_id} onChange={(e) => set("facility_id", e.target.value)} /></Field>
        <Field label="Name"><input value={v.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Address"><input value={v.address} onChange={(e) => set("address", e.target.value)} /></Field>
        <Field label="Usable square feet"><input className="num" value={v.usable_sqft} onChange={(e) => set("usable_sqft", e.target.value)} /></Field>
        <Field label="Rentable square feet" hint="Includes the common area load">
          <input className="num" value={v.rentable_sqft} onChange={(e) => set("rentable_sqft", e.target.value)} />
        </Field>
        <Field label="Tenure">
          <select value={v.owned ? "owned" : "leased"}
                  onChange={(e) => set("owned", e.target.value === "owned")}>
            <option value="owned">Owned</option>
            <option value="leased">Leased</option>
          </select>
        </Field>
        <Field label="Landlord" hint="Required for a leased building">
          <input value={v.landlord} onChange={(e) => set("landlord", e.target.value)} />
        </Field>
        <Field label="Market rate $/sqft/year">
          <input className="num" value={v.market_rate_psf} onChange={(e) => set("market_rate_psf", e.target.value)} />
        </Field>
        <Field label="What the market rate rests on" hint="A comparable, a survey, an appraisal">
          <input value={v.market_basis} onChange={(e) => set("market_basis", e.target.value)} />
        </Field>
      </div>
      <div className="splitter-foot">
        <button className="primary sm" onClick={save}>Record the building</button>
        <button className="sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

function SpaceForm({ facilities, onSaved }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ unit_id: "", facility_id: "", label: "",
                               usable_sqft: "", use: "TENANT",
                               status: "OCCUPIED", occupant: "",
                               months_occupied: "12", actual_annual_charge: "",
                               market_rate_psf: "", market_basis: "",
                               market_source: "", objective_id: "" });
  const set = (k, x) => setV((s) => ({ ...s, [k]: x }));

  async function save() {
    try {
      await api.putSpaceUnit({
        ...v,
        facility_id: v.facility_id || facilities[0]?.facility_id,
        usable_sqft: Number(v.usable_sqft),
        months_occupied: Number(v.months_occupied),
        actual_annual_charge: v.actual_annual_charge ? Number(v.actual_annual_charge) : null,
        market_rate_psf: v.market_rate_psf ? Number(v.market_rate_psf) : null,
        objective_id: v.objective_id || null,
      });
      toast(`${v.label} recorded`);
      setOpen(false);
      await onSaved();
    } catch (e) {
      const msg = String(e.message || e).replace(/^\d+:\s*/, "");
      let detail = msg;
      try { const p = JSON.parse(msg); detail = p.message || p.detail || msg; }
      catch { /* plain */ }
      toast(typeof detail === "string" ? detail : JSON.stringify(detail),
            { tone: "bad", sticky: true });
    }
  }

  if (!open) {
    return (
      <div className="ts-add">
        <button className="linkish" onClick={() => setOpen(true)}>+ Add a space</button>
      </div>
    );
  }
  return (
    <div className="splitter">
      <div className="terms-grid">
        <Field label="Identifier"><input value={v.unit_id} onChange={(e) => set("unit_id", e.target.value)} /></Field>
        <Field label="Building">
          <select value={v.facility_id} onChange={(e) => set("facility_id", e.target.value)}>
            {facilities.map((f) => (
              <option key={f.facility_id} value={f.facility_id}>{f.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Label" hint="Suite 210, Lab 1"><input value={v.label} onChange={(e) => set("label", e.target.value)} /></Field>
        <Field label="Usable square feet"><input className="num" value={v.usable_sqft} onChange={(e) => set("usable_sqft", e.target.value)} /></Field>
        <Field label="Use">
          <select value={v.use} onChange={(e) => set("use", e.target.value)}>
            {USES.map((u) => <option key={u} value={u}>{u.replace(/_/g, " ")}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select value={v.status} onChange={(e) => set("status", e.target.value)}>
            {STATUSES.map((u) => <option key={u} value={u}>{u.toLowerCase()}</option>)}
          </select>
        </Field>
        <Field label="Occupant"><input value={v.occupant} onChange={(e) => set("occupant", e.target.value)} /></Field>
        <Field label="Months occupied"><input className="num" value={v.months_occupied} onChange={(e) => set("months_occupied", e.target.value)} /></Field>
        <Field label="Charged for the year"><input className="num" value={v.actual_annual_charge} onChange={(e) => set("actual_annual_charge", e.target.value)} /></Field>
        <Field label="Market $/sqft/year"><input className="num" value={v.market_rate_psf} onChange={(e) => set("market_rate_psf", e.target.value)} /></Field>
        <Field label="What that rate rests on">
          <input value={v.market_basis} onChange={(e) => set("market_basis", e.target.value)} />
        </Field>
        <Field label="Objective" hint="Required when the use is a programme">
          <input value={v.objective_id} onChange={(e) => set("objective_id", e.target.value)} />
        </Field>
      </div>
      <div className="splitter-foot">
        <button className="primary sm" onClick={save}>Record the space</button>
        <button className="sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}
