import React, { useCallback, useEffect, useState } from "react";
import { api, count, explain, money } from "../api.js";
import { Card, Drawer, Empty, Field, PageHead, Pill, Segmented, Stat, Table,
         Tick, useToast } from "../components/ui.jsx";
import Propose from "../components/Propose.jsx";
import SubjectNotes from "../components/SubjectNotes.jsx";

/*
  Five buildings, the space in them, and what it is all worth.

  The subsidy column is the one nobody has ever added up: an incubator lets
  space below market and lends equipment for nothing, and that gap is the
  mission. It is deliberately shown next to a standing line about what it is
  not — forgone rent on your own building is not cost share, and the moment a
  big number appears on a screen somebody will want to put it on a federal
  report.
*/

const sqft = (v) => v === null || v === undefined ? "—"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const pct = (v) => v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(0)}%`;

const USES = ["TENANT", "PROGRAM", "ADMINISTRATIVE", "SHARED_LAB", "COMMON",
              "VACANT", "COMMITTED"];
const STATUSES = ["OCCUPIED", "VACANT", "INTERNAL", "COMMITTED", "COMMON"];

const USE_HINT = {
  TENANT: "Let to somebody outside YBI. Comes out of the federal pool.",
  PROGRAM: "Delivering a programme. Names the cost objective it serves.",
  ADMINISTRATIVE: "YBI's own offices.",
  SHARED_LAB: "Shared equipment floor.",
  COMMON: "Corridors, stairs, plant.",
  VACANT: "Nobody in it. Comes out of the federal pool like tenant space.",
  COMMITTED: "Let from a date but not yet occupied.",
};

export default function Facilities({ actor, tab: initialTab }) {
  // The room the controller is correcting. `put_unit` has always been an
  // upsert on `unit_id`, so the register could be corrected from the day
  // it was written — by retyping an identifier exactly, which is not a
  // thing anybody does. The capability was there and the door was not.
  const [editUnit, setEditUnit] = useState(null);
  // And the asset he is answering. `putAssetFunding` has been in `api.js`
  // since the route was written and was called by nothing: the only path
  // on this screen was Propose, which Tom may not then accept — nobody
  // disposes of their own recommendation. The refusal even names the way
  // out, *record the change directly*, and there was no door for it.
  const [fundAsset, setFundAsset] = useState(null);
  /* Portfolio, not rank.
     `actor.role === "CONTROLLER"` was rank, and CONTROLLER is the name of a
     portfolio *and* of a rank — the one place this file's rules say is
     easiest to collapse. Every facilities route is
     require_portfolio(FACILITIES, CONTROLLER) and every equipment route is
     require_portfolio(INVENTORY, CONTROLLER), so reading rank hid the write
     forms from exactly the person who holds the portfolio and nothing else:
     a nav stricter than the API, which is the same defect as one looser. */
  const held = new Set(actor?.portfolios || []);
  const canSpace = held.has("FACILITIES") || held.has("CONTROLLER");
  const canKit = held.has("INVENTORY") || held.has("CONTROLLER");
  const canWrite = canSpace;
  /* The tab was a prop that nothing read, so `/classify/assets` — the
     destination the worklist and the walk both print for the asset register —
     opened on Buildings. */
  const [tab, setTab] = useState(initialTab || "buildings");
  const [data, setData] = useState(null);
  const [space, setSpace] = useState(null);
  const [kit, setKit] = useState(null);
  const [inKind, setInKind] = useState(null);
  const [funding, setFunding] = useState(null);
  const [notesOn, setNotesOn] = useState(null);
  const [answering, setAnswering] = useState(null);
  const [assetsShown, setAssetsShown] = useState(25);
  const [kitShown, setKitShown] = useState(25);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [f, s, e, k, fu] = await Promise.all([
        api.facilities(), api.spaceUnits({}), api.equipment(), api.inKind(),
        api.assetFunding(),
      ]);
      setData(f); setSpace(s); setKit(e); setInKind(k); setFunding(fu);
      setError("");
    } catch (err) { setError(explain(err)); }
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
          <Propose
            subject="FACILITY"
            title="a building"
            subjectLabel="Building reference"
            /* A count belongs on a screen that reads it from the record.
               This asserted one — "no building carries square footage" — and
               went on saying it with a building on the table underneath. The
               rule is what is worth saying anyway, and the rule does not
               expire. */
            hint="Until a building carries its area the 200.465 carve-out
                  cannot be sized, and every dollar of tenant and vacant
                  occupancy cost stays in the federal pool. It is the single
                  largest adjustment in the rate model."
            fields={[
              /* The six buildings YBI's own lease book names, offered rather
                 than typed. The book cannot create a facility — it carries no
                 square footage and `usable_sqft` is NOT NULL above zero, so a
                 row from it would mean inventing the driver of the largest
                 adjustment in the rate model. It can stop somebody typing a
                 building's name from memory, which is the difference between
                 "tell us about your space" and "here are your buildings; how
                 many square feet is each one?" */
              { name: "name", label: "Name", required: true,
                type: (data.known_buildings || []).length ? "suggest" : "text",
                options: (data.known_buildings || []).map((b) => b.name),
                hint: (data.known_buildings || []).length
                  ? `Your lease book names ${(data.known_buildings || []).length} buildings. Pick one or type another.`
                  : undefined },
              { name: "usable_sqft", label: "Usable square feet",
                type: "number", required: true,
                hint: "What the carve-out is sized by." },
              { name: "rentable_sqft", label: "Rentable square feet",
                type: "number", hint: "Optional; never less than usable." },
              { name: "address", label: "Address", type: "text" },
              { name: "owned", label: "Owned by YBI", type: "bool" },
            ]}
            onDone={load} />
          {f.length === 0 ? (
            <Empty mark="—" title="No buildings recorded">
              Nothing is on the record yet. Propose a building above, or record
              one directly if the measurement is settled — both end in the same
              place and only one of them puts it in front of the controller.
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
                    <td className="num">
                      {sqft(r.usable_sqft)}
                      {/* The figure was in the tick's `title` — a tooltip
                          nobody hovers. A building that does not add up is
                          the one thing on this table worth acting on, and
                          the amount is what says how far off it is. */}
                      {ctl && ctl.units > 0 && !ctl.ties && (
                        <div className="amt neg small">
                          {Number(ctl.variance) > 0
                            ? `rooms are ${sqft(ctl.variance)} over`
                            : `${sqft(-ctl.variance)} not attributed`}
                        </div>
                      )}
                    </td>
                    <td className="num">{r.units}</td>
                    <td className="num">{money(r.charged)}</td>
                    <td className="num">{money(r.market_value)}</td>
                    <td className="num strong">{money(r.subsidy)}</td>
                    <td className="num quiet">{sqft(r.equipment_sqft)}</td>
                    <td className="l quiet small">
                      <a href="#" onClick={(e) => {
                           e.preventDefault();
                           setNotesOn({ subject: "FACILITY", id: r.facility_id,
                                        title: r.name });
                         }}>Notes</a>
                      {" · "}
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
          <Propose
            subject="SPACE_UNIT"
            title="a space"
            subjectLabel="Space reference"
            hint="Every square foot of a building has to be accounted for —
                  tenant, programme, administrative, shared lab, common or
                  vacant. A building that does not add up drops out of the
                  carve-out entirely, and all of its occupancy cost reaches the
                  federal pool unchallenged."
            fields={[
              { name: "facility_id", label: "Building", type: "select",
                required: true, options: f.map((x) => x.facility_id),
                hint: "Or a building you have just proposed." },
              { name: "label", label: "What it is called", type: "text",
                required: true },
              { name: "usable_sqft", label: "Usable square feet",
                type: "number", required: true },
              { name: "use", label: "Use", type: "select", required: true,
                options: USES,
                hint: "Tenant and vacant space is what comes out of the pool." },
              { name: "status", label: "Status", type: "select",
                required: true, options: STATUSES },
              { name: "occupant", label: "Occupant", type: "text",
                hint: "Required where the status is OCCUPIED." },
              { name: "objective_id", label: "Cost objective", type: "text",
                hint: "Required where the use is PROGRAM." },
              { name: "floor", label: "Floor", type: "text" },
            ]}
            onDone={load} />

          {(space?.space || []).length === 0 ? (
            <Empty mark="—" title="No spaces recorded" />
          ) : (
            <Table columns={[
              { label: "Space", align: "left" }, { label: "Use", align: "left" },
              { label: "Occupant", align: "left" }, { label: "Sqft" },
              { label: "Months" }, { label: "Charged" }, { label: "$/sqft" },
              { label: "At market" }, { label: "Subsidy" },
              { label: "", align: "left" },
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
                  <td className="l">
                    {canWrite && (
                      <button className="ghost" onClick={() => setEditUnit(u)}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
          {canWrite && <SpaceForm facilities={f} onSaved={load}
                                  editing={editUnit}
                                  onClosed={() => setEditUnit(null)} />}
        </Card>
      )}

      {tab === "equipment" && (
        <>
          <Card title="Who paid for each asset"
                variant="raised"
                aside={funding?.totals
                  ? `${count(funding.totals.unanswered)} of ${count(funding.totals.assets)} unanswered`
                  : "the register is empty"}>
            <p className="muted">
              2 CFR 200.313(d)(1) requires the funding source on the property
              record and the fixed-asset schedule has no such column — which is
              a finding of its own. It decides 200.436(b): depreciation on a
              federally funded asset is unallowable, and{" "}
              <strong>$850,383</strong> of depreciation is waiting on it.{" "}
              <em>A blank is unanswered, and unanswered is a value</em> — there
              is no federal money in this asset and nobody has looked are
              different facts, so the second is never written as 0.00.
            </p>
            <Propose
              key={answering || "new"}
              presetId={answering || ""}
              startOpen={!!answering}
              subject="ASSET_FUNDING"
              title="a funding source"
              subjectLabel="Asset id"
              hint="One source for one asset. An asset may carry several; each
                    is proposed on its own, because a federal share and a
                    private share are two answers and not one."
              fields={[
                { name: "kind", label: "Source", type: "select", required: true,
                  options: ["FEDERAL", "STATE", "LOCAL", "PRIVATE", "DEBT",
                            "UNRESTRICTED"] },
                { name: "amount", label: "Amount", type: "number",
                  required: true,
                  hint: "0.00 is a real answer: this source paid nothing." },
                { name: "award_reference", label: "Award reference",
                  type: "text",
                  hint: "Required for a federal source — 200.313(d)(1)." },
                { name: "funder", label: "Funder", type: "text" },
              ]}
              onDone={() => { setAnswering(null); load(); }} />
            {!funding || (funding.assets || []).length === 0 ? (
              <Empty mark="—" title="The asset register is empty">
                It arrives whole, from the fixed-asset schedule YBI already
                holds — ask for it on the Requests screen. The funding source is
                the one column that schedule does not carry, and it is the
                column that answers 200.436(b).
              </Empty>
            ) : (
              <Table columns={[
                { label: "Asset", align: "left" },
                { label: "Gross cost" }, { label: "Depreciation" },
                { label: "Funding on file", align: "left" },
              ]}>
                {funding.assets.slice(0, assetsShown).map((a) => (
                  <tr key={a.asset_id}>
                    <td className="l">
                      <span className="strong">{a.description}</span>
                      <div className="rowsub">{a.asset_id}</div>
                    </td>
                    <td className="num">{money(a.gross_cost)}</td>
                    <td className="num">{money(a.depreciation)}</td>
                    <td className="l">
                      <a href="#" onClick={(e) => {
                           e.preventDefault();
                           setNotesOn({ subject: "ASSET_FUNDING",
                                        id: a.asset_id,
                                        title: a.description });
                         }}>Notes</a>{" · "}
                      {Number(a.sources) === 0
                        ? <>
                            <Pill tone="warn">nobody has looked</Pill>
                            {canKit && <>
                              {" · "}
                              <a href="#" onClick={(e) => {
                                   e.preventDefault();
                                   setFundAsset({ asset: a });
                                 }}>Answer</a>
                            </>}
                            {" · "}
                            <a href="#" onClick={(e) => {
                                 e.preventDefault();
                                 setAnswering(a.asset_id);
                                 window.scrollTo({ top: 0, behavior: "smooth" });
                               }}>Recommend</a>
                          </>
                        : <>
                            {(a.funding || []).map((x, n) => (
                              <div key={n} className="rowsub">
                                {x.kind} {money(x.amount)}
                                {x.award_reference ? ` · ${x.award_reference}` : ""}
                                {/* An answered asset offered nothing at all, so
                                    a wrong answer was permanent from the screen.
                                    The route upserts on (asset, kind, award). */}
                                {canKit && <>
                                  {" · "}
                                  <a href="#" onClick={(e) => {
                                       e.preventDefault();
                                       setFundAsset({ asset: a, source: x });
                                     }}>Correct</a>
                                </>}
                              </div>))}
                            {canKit && (
                              <a href="#" className="rowsub" onClick={(e) => {
                                   e.preventDefault();
                                   setFundAsset({ asset: a });
                                 }}>+ another source</a>)}
                          </>}
                    </td>
                  </tr>
                ))}
              </Table>
            )}
            {funding && (funding.assets || []).length > assetsShown && (
              <div className="row-actions">
                <button onClick={() => setAssetsShown(assetsShown + 25)}>
                  Show 25 more
                </button>
                <span className="rowsub">
                  {count(assetsShown)} of {count(funding.assets.length)} shown
                  — unanswered first, then by what the asset cost.
                </span>
              </div>
            )}
          </Card>

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
                {kit.equipment.slice(0, kitShown).map((a) => (
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
            {(kit?.equipment || []).length > kitShown && (
              <div className="row-actions">
                <button onClick={() => setKitShown(kitShown + 25)}>
                  Show 25 more
                </button>
                <span className="rowsub">
                  {count(kitShown)} of {count(kit.equipment.length)} shown
                  — programme equipment first, then by name.
                </span>
              </div>
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
      <SubjectNotes subject={notesOn?.subject} subjectId={notesOn?.id}
                    title={notesOn?.title}
                    onClose={() => setNotesOn(null)} />
      <AssetFundingForm target={fundAsset} onSaved={load}
                        onClosed={() => setFundAsset(null)} />
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
      const msg = explain(e);
      toast(msg,
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

/* Answering an asset directly.
 *
 * `PUT /api/facilities/asset-funding` is `require_portfolio(INVENTORY,
 * CONTROLLER)` and upserts on (asset, kind, award reference), so correcting
 * an answer is the same act as giving one. Propose stays beside it and is
 * the right door for somebody who is *not* going to dispose of it — the
 * auditor, or Heidi asking Tom. Both are offered, because they mean
 * different things: one records a judgment, the other asks for one.
 *
 * A blank amount is never written as 0.00. `there is no federal money in
 * this asset` is a row at 0.00 and `nobody has looked` is no row, which is
 * the intake's rule and the reason the register can state the gap. */
function AssetFundingForm({ target, onSaved, onClosed }) {
  const toast = useToast();
  const src = target?.source;
  const [v, setV] = useState({ kind: "FEDERAL", amount: "", award_reference: "",
                               funder: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState("");
  const set = (k, x) => setV((s) => ({ ...s, [k]: x }));

  useEffect(() => {
    if (!target) return;
    setRefusal("");
    setV({ kind: src?.kind || "FEDERAL",
           amount: src?.amount ?? "",
           award_reference: src?.award_reference || "",
           funder: src?.funder || "",
           note: src?.note || "" });
  }, [target]);

  async function save() {
    setBusy(true);
    setRefusal("");
    try {
      await api.putAssetFunding({
        asset_id: target.asset.asset_id,
        kind: v.kind,
        amount: Number(v.amount),
        award_reference: v.award_reference,
        funder: v.funder,
        note: v.note,
      });
      toast(`${target.asset.description} — ${v.kind} recorded`);
      onClosed();
      await onSaved();
    } catch (e) {
      setRefusal(explain(e));
      toast(explain(e), { tone: "fail" });
    } finally { setBusy(false); }
  }

  return (
    <Drawer
      open={!!target}
      title={src ? "Correct a funding source" : "Where the money came from"}
      subtitle={target ? `${target.asset.description} · ${target.asset.asset_id}` : ""}
      onClose={onClosed}
      footer={<>
        <button className="btn" onClick={onClosed}>Cancel</button>
        <button className="btn primary" disabled={busy} onClick={save}>
          {busy ? "Recording…" : src ? "Save the correction" : "Record it"}
        </button>
      </>}>
      <p className="rowsub">
        2 CFR 200.313(d)(1) wants the funding source on the property record, and
        200.436(b) makes depreciation on a federally funded asset unallowable.
        An asset may carry more than one source; each is recorded on its own,
        because a federal share and a private share are two answers.
      </p>
      <Field label="Source" required>
        <select value={v.kind} onChange={(e) => set("kind", e.target.value)}
                disabled={!!src}>
          {["FEDERAL","STATE","LOCAL","PRIVATE","DEBT","UNRESTRICTED"]
            .map((k) => <option key={k} value={k}>{k.toLowerCase()}</option>)}
        </select>
      </Field>
      <Field label="Amount" required
             hint="0.00 is a real answer: this source paid nothing toward it.">
        <input className="num" value={v.amount}
               onChange={(e) => set("amount", e.target.value)} />
      </Field>
      <Field label="Award reference"
             hint="Required for a federal source — 200.313(d)(1) names the award.">
        <input value={v.award_reference} readOnly={!!src}
               onChange={(e) => set("award_reference", e.target.value)} />
      </Field>
      <Field label="Funder"><input value={v.funder}
             onChange={(e) => set("funder", e.target.value)} /></Field>
      <Field label="What this rests on"
             hint="The schedule, the SEFA, the grant agreement — whatever says so.">
        <textarea rows={4} value={v.note}
                  onChange={(e) => set("note", e.target.value)} />
      </Field>
      {refusal && <p className="refusal">{refusal}</p>}
    </Drawer>
  );
}

function SpaceForm({ facilities, onSaved, editing, onClosed }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ unit_id: "", facility_id: "", label: "",
                               usable_sqft: "", use: "TENANT",
                               status: "OCCUPIED", occupant: "",
                               months_occupied: "12", actual_annual_charge: "",
                               market_rate_psf: "", market_basis: "",
                               market_source: "", objective_id: "",
                               occupancy_basis: "", floor: "" });
  const set = (k, x) => setV((s) => ({ ...s, [k]: x }));

  /* Editing a room is the same act as recording one — `put_unit` upserts on
     `unit_id` — so it is the same form, filled in. Every column the form can
     write is read back from the rent roll (migration `127` carries the two
     it did not), because an edit that puts back less than it read clears
     what it did not show. */
  useEffect(() => {
    if (!editing) return;
    setV({
      unit_id: editing.unit_id || "",
      facility_id: editing.facility_id || "",
      label: editing.label || "",
      usable_sqft: editing.usable_sqft ?? "",
      use: editing.use || "TENANT",
      status: editing.status || "OCCUPIED",
      occupant: editing.occupant || "",
      months_occupied: editing.months_occupied ?? "12",
      actual_annual_charge: editing.actual_annual_charge ?? "",
      market_rate_psf: editing.market_rate_psf ?? "",
      market_basis: editing.market_basis || "",
      market_source: editing.market_source || "",
      objective_id: editing.objective_id || "",
      occupancy_basis: editing.occupancy_basis || "",
      floor: editing.floor || "",
    });
    setOpen(true);
  }, [editing]);

  const close = () => { setOpen(false); onClosed && onClosed(); };

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
      toast(`${v.label} ${editing ? "corrected" : "recorded"}`);
      close();
      await onSaved();
    } catch (e) {
      const msg = explain(e);
      toast(msg,
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
        <Field label="Identifier"
               hint={editing ? "What the correction is keyed on — fixed here."
                             : undefined}>
          <input value={v.unit_id} readOnly={!!editing}
                 onChange={(e) => set("unit_id", e.target.value)} />
        </Field>
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
        <Field label="Floor" hint="Ground, 2, mezzanine">
          <input value={v.floor} onChange={(e) => set("floor", e.target.value)} />
        </Field>
        <Field label="Objective" hint="Required when the use is a programme">
          <input value={v.objective_id} onChange={(e) => set("objective_id", e.target.value)} />
        </Field>
        <Field label="The agreement that says which"
               hint={"A commercial lease, or an incubation or residency agreement. " +
                     "Required where the space is charged for and called programme " +
                     "space \u2014 that reading takes its occupancy cost out of the " +
                     "rental side and into the federal pool, so it does not rest on " +
                     "nobody\u2019s document. Blank is fine and means nobody has read one."}>
          <input value={v.occupancy_basis} onChange={(e) => set("occupancy_basis", e.target.value)} />
        </Field>
      </div>
      <div className="splitter-foot">
        <button className="primary sm" onClick={save}>
          {editing ? "Save the correction" : "Record the space"}
        </button>
        <button className="sm" onClick={close}>Cancel</button>
      </div>
    </div>
  );
}
