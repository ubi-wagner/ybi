"""Buildings, the space in them, the equipment standing in it, and what all
of it is worth.

Three readers want different things from the same facts. The rate wants the
square-footage carve-out: whose activity uses which space. The board and the
990 narrative want the subsidy — an incubator lets space below market and
lends equipment for nothing, and nobody has ever counted it. Cost share wants
a subset of that, and a strict one.

The strictness is the part worth stating out loud. Space YBI owns and lets
cheaply is not cost share: 2 CFR 200.465 allows a less-than-arm's-length
rental only up to what ownership would have cost, so forgone rent on your own
building is not a cost you incurred. Third-party donations are claimable;
unrecovered indirect is claimable with prior written approval. The schema
refuses the wrong combination rather than trusting anyone to remember.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.audit import record
from app.auth import (Actor, require_facilities, require_inventory,
                      require_reader)
from app.db import execute, one, query
from app.domain.core import money
from app.settings import settings
from app.vocab import (AccessPolicy, FundingKind, InKindKind,
                       OccupancyStatus, SpaceUse)

router = APIRouter(prefix="/facilities", tags=["facilities"],
                   dependencies=[Depends(require_reader)])


class BlankNotNull(BaseModel):
    """A column that is NULL in the register arrives as a blank, not a 422.

    These bodies are posted back by the screens that *read* the register —
    correcting a building or a room is the same upsert as recording one, so
    the form is pre-filled from the row it is about. A `str = ""` field
    refuses `None`, and `facility.code` is nullable, so the API refused a row
    the API itself had just produced, naming a field nobody had typed in.

    The screens coerce with `|| ""` and were right by luck. This is the rule
    rather than the habit: whatever the register answers with can be handed
    straight back.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _blank_for_null(cls, v, info):
        if v is None:
            f = cls.model_fields.get(info.field_name)
            if f is not None and f.annotation is str:
                return ""
        return v


class FacilityIn(BlankNotNull):
    facility_id: str
    name: str
    code: str = ""
    address: str = ""
    owned: bool = True
    landlord: str = ""
    usable_sqft: float = Field(gt=0)
    rentable_sqft: float | None = None
    year_built: int | None = None
    annual_lease_cost: float | None = None
    market_rate_psf: float | None = None
    market_basis: str = ""
    source_document: str = ""
    note: str = ""


class UnitIn(BlankNotNull):
    unit_id: str
    facility_id: str
    label: str
    floor: str = ""
    usable_sqft: float = Field(gt=0)
    use: SpaceUse
    status: OccupancyStatus
    objective_id: str | None = None
    occupant: str = ""
    months_occupied: float = Field(default=12, gt=0, le=12)
    actual_annual_charge: float | None = None
    market_rate_psf: float | None = None
    market_basis: str = ""
    market_source: str = ""
    #: The agreement that settles what kind of occupancy this is. Blank is
    #: honest and means nobody has read one; it is never a claim that none
    #: exists. `unit_paid_program_names_its_agreement` refuses only the one
    #: case that moves the rate — space charged for and called programme.
    occupancy_basis: str = ""
    note: str = ""


class AssetFundingIn(BaseModel):
    asset_id: str
    kind: FundingKind
    amount: float = Field(ge=0)
    award_reference: str = ""
    funder: str = ""
    counted_as_cost_share: bool = False
    note: str = ""


class EquipmentUseIn(BaseModel):
    asset_id: str
    objective_id: str | None = None
    user_name: str = ""
    hours: float = Field(gt=0)
    charged: float = 0
    source_document: str = ""
    note: str = ""


class InKindIn(BaseModel):
    kind: InKindKind
    description: str
    value: float = Field(ge=0)
    valuation_basis: str
    measured: str = ""
    objective_id: str | None = None
    award_id: str | None = None
    source_document: str = ""
    claimed_as_cost_share: bool = False
    agency_approval: str = ""


def _known_buildings(period: str) -> list[dict]:
    """The buildings YBI's own lease book names, with their tenants.

    `2025_YBI_Lease-Schedule.xlsx` has been on file since the foundation was
    loaded and carries twenty-six tenancies across six buildings — who, which
    building, the term and the rent. What it does not carry is **square
    footage**, which is the one number the 200.465 carve-out is sized by and
    the one thing somebody has to go and measure.

    So it cannot create a `facility`: `usable_sqft` is NOT NULL and CHECKed
    above zero, and inventing an area to get a row in would be inventing the
    driver of the largest adjustment in the rate model. What it can do is stop
    Heidi typing a building's name from memory — the ask collapses from *tell
    us about your space* to *here are your buildings; how many square feet is
    each one?*

    A document that will not parse is a thing to fix and not a reason for the
    screen to fail, so this answers empty and the form takes a free-typed name.
    """
    from app.routers.requests import _lease_book

    seen: dict[str, dict] = {}
    for t in _lease_book(period):
        b = seen.setdefault(t.building, {"name": t.building, "tenancies": 0,
                                         "annual_rent": Decimal(0),
                                         "on_the_record": False})
        b["tenancies"] += 1
        b["annual_rent"] += t.annual_rent or Decimal(0)
    on_record = {r["name"] for r in
                 query("SELECT name FROM facility WHERE period = %s", (period,))}
    for b in seen.values():
        b["on_the_record"] = b["name"] in on_record
        b["annual_rent"] = str(money(b["annual_rent"]))
    return sorted(seen.values(), key=lambda b: b["name"])


@router.get("")
def facilities(period: str = None) -> dict:
    """The buildings, with the subsidy each carries."""
    period = period or settings.period
    rows = query("SELECT * FROM v_facility_summary WHERE period = %s "
                 "ORDER BY name", (period,))
    control = query("SELECT * FROM v_space_unit_control WHERE period = %s "
                    "ORDER BY name", (period,))
    occupancy = query("SELECT * FROM v_facility_occupancy WHERE period = %s",
                      (period,))
    return {"period": period, "facilities": rows, "control": control,
            "occupancy": occupancy,
            "known_buildings": _known_buildings(period)}


@router.put("")
def put_facility(body: FacilityIn, period: str = None,
                 actor: Actor = Depends(require_facilities)) -> dict:
    period = period or settings.period
    execute("""INSERT INTO facility
                 (facility_id, period, name, code, address, owned, landlord,
                  usable_sqft, rentable_sqft, year_built, annual_lease_cost,
                  market_rate_psf, market_basis, source_document, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (facility_id) DO UPDATE SET
                 name = EXCLUDED.name, code = EXCLUDED.code,
                 address = EXCLUDED.address, owned = EXCLUDED.owned,
                 landlord = EXCLUDED.landlord,
                 usable_sqft = EXCLUDED.usable_sqft,
                 rentable_sqft = EXCLUDED.rentable_sqft,
                 year_built = EXCLUDED.year_built,
                 annual_lease_cost = EXCLUDED.annual_lease_cost,
                 market_rate_psf = EXCLUDED.market_rate_psf,
                 market_basis = EXCLUDED.market_basis,
                 source_document = EXCLUDED.source_document,
                 note = EXCLUDED.note""",
            (body.facility_id, period, body.name, body.code, body.address,
             body.owned, body.landlord, body.usable_sqft, body.rentable_sqft,
             body.year_built, body.annual_lease_cost, body.market_rate_psf,
             body.market_basis, body.source_document, body.note))
    record(actor, "FACILITY", "facility", body.facility_id,
           after={"name": body.name, "usable_sqft": body.usable_sqft,
                  "owned": body.owned,
                  "market_rate_psf": body.market_rate_psf},
           reason=body.source_document or "facility recorded")
    return {"facility_id": body.facility_id}


@router.get("/space")
def space(period: str = None, facility_id: str = None) -> dict:
    """The rent roll, with what each space would fetch beside what it was
    charged."""
    period = period or settings.period
    rows = query("""SELECT * FROM v_space_economics
                     WHERE period = %s AND (%s::text IS NULL OR facility_id = %s::text)
                     ORDER BY facility_name, label""",
                 (period, facility_id, facility_id))
    totals = one("""SELECT COALESCE(sum(market_value), 0) AS market_value,
                           COALESCE(sum(actual_annual_charge), 0) AS charged,
                           COALESCE(sum(subsidy), 0) AS subsidy,
                           count(*) FILTER (WHERE market_unknown) AS no_market,
                           count(*) AS units
                      FROM v_space_economics
                     WHERE period = %s AND (%s::text IS NULL OR facility_id = %s::text)""",
                 (period, facility_id, facility_id))
    return {"period": period, "space": rows, "totals": totals,
            "note": "Subsidy on space YBI owns is mission value, not cost "
                    "share — 2 CFR 200.465."}


@router.put("/space")
def put_unit(body: UnitIn, period: str = None,
             actor: Actor = Depends(require_facilities)) -> dict:
    period = period or settings.period
    if not one("SELECT 1 FROM facility WHERE facility_id = %s AND period = %s",
               (body.facility_id, period)):
        raise HTTPException(404, f"No facility {body.facility_id} in {period}.")
    execute("""INSERT INTO space_unit
                 (unit_id, facility_id, period, label, floor, usable_sqft, use,
                  status, objective_id, occupant, months_occupied,
                  actual_annual_charge, market_rate_psf, market_basis,
                  market_source, occupancy_basis, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (unit_id) DO UPDATE SET
                 label = EXCLUDED.label, floor = EXCLUDED.floor,
                 usable_sqft = EXCLUDED.usable_sqft, use = EXCLUDED.use,
                 status = EXCLUDED.status, objective_id = EXCLUDED.objective_id,
                 occupant = EXCLUDED.occupant,
                 months_occupied = EXCLUDED.months_occupied,
                 actual_annual_charge = EXCLUDED.actual_annual_charge,
                 market_rate_psf = EXCLUDED.market_rate_psf,
                 market_basis = EXCLUDED.market_basis,
                 market_source = EXCLUDED.market_source,
                 occupancy_basis = EXCLUDED.occupancy_basis,
                 note = EXCLUDED.note""",
            (body.unit_id, body.facility_id, period, body.label, body.floor,
             body.usable_sqft, body.use.value, body.status.value,
             body.objective_id, body.occupant, body.months_occupied,
             body.actual_annual_charge, body.market_rate_psf, body.market_basis,
             body.market_source, body.occupancy_basis, body.note))
    record(actor, "SPACE_UNIT", "space_unit", body.unit_id,
           after={"facility_id": body.facility_id, "label": body.label,
                  "sqft": body.usable_sqft, "use": body.use.value,
                  "charged": body.actual_annual_charge,
                  "market_rate_psf": body.market_rate_psf,
                  "occupancy_basis": body.occupancy_basis},
           reason=body.market_source or "space recorded")
    return {"unit_id": body.unit_id}


@router.get("/equipment")
def equipment(period: str = None) -> dict:
    """The register, what its use was worth, and the lab floor it stands on."""
    period = period or settings.period
    rows = query("""SELECT * FROM v_equipment_subsidy WHERE period = %s
                     ORDER BY is_program_equipment DESC, description""",
                 (period,))
    lab = query("""SELECT * FROM v_lab_space_consumed WHERE period = %s
                    AND equipment_sqft > 0 ORDER BY occupied_share DESC""",
                (period,))
    totals = one("""SELECT COALESCE(sum(market_value), 0) AS market_value,
                           COALESCE(sum(charged), 0) AS charged,
                           COALESCE(sum(subsidy), 0) AS subsidy,
                           COALESCE(sum(hours_used), 0) AS hours,
                           count(*) FILTER (WHERE rate_unknown) AS no_rate
                      FROM v_equipment_subsidy WHERE period = %s""", (period,))
    return {"period": period, "equipment": rows, "lab_space": lab,
            "totals": totals}


@router.post("/equipment/use")
def put_equipment_use(body: EquipmentUseIn, period: str = None,
                      actor: Actor = Depends(require_inventory)) -> dict:
    """Record that somebody used a machine, and what they were charged.

    The unit of the equipment subsidy, and a better driver for lab cost than
    floor area on its own — square footage says where a machine stands, hours
    say who it served.
    """
    period = period or settings.period
    if not one("SELECT 1 FROM asset WHERE asset_id = %s", (body.asset_id,)):
        raise HTTPException(404, f"No asset {body.asset_id}.")
    r = one("""INSERT INTO equipment_use
                 (asset_id, period, objective_id, user_name, hours, charged,
                  source_document, note, recorded_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING use_id""",
            (body.asset_id, period, body.objective_id, body.user_name,
             body.hours, body.charged, body.source_document, body.note,
             actor.actor_id))
    record(actor, "EQUIPMENT_USE", "asset", body.asset_id,
           after={"hours": body.hours, "charged": body.charged,
                  "objective_id": body.objective_id},
           reason=body.source_document or "equipment use recorded")
    return {"use_id": r["use_id"]}


@router.put("/asset-funding")
def put_asset_funding(body: AssetFundingIn, period: str = None,
                      actor: Actor = Depends(require_inventory)) -> dict:
    """Record where the money for one asset came from.

    The door this register never had. `asset_funding` was written by exactly
    one thing — the workbook that comes back through `/requests` — so the only
    way to answer 200.313(d)(1) for a single asset was a spreadsheet round
    trip. That is the capability-with-no-door shape pointed at the register
    holding up $850,383 of depreciation under 200.436(b).

    A blank stays a blank. *There is no federal money in this asset* and
    *nobody has looked* are different facts all the way down: the first is a
    row at 0.00 and the second is no row, which is the intake's own rule and
    the reason `v_depreciation_basis` can state the gap rather than imply it.
    """
    period = period or settings.period
    if not one("SELECT 1 FROM asset WHERE asset_id = %s AND period = %s",
               (body.asset_id, period)):
        raise HTTPException(404, f"No asset {body.asset_id} in {period}.")
    execute("""INSERT INTO asset_funding
                 (asset_id, kind, amount, award_reference, funder,
                  counted_as_cost_share, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (asset_id, kind, award_reference) DO UPDATE SET
                 amount = EXCLUDED.amount, funder = EXCLUDED.funder,
                 counted_as_cost_share = EXCLUDED.counted_as_cost_share,
                 note = EXCLUDED.note""",
            (body.asset_id, body.kind.value, body.amount,
             body.award_reference, body.funder, body.counted_as_cost_share,
             body.note))
    record(actor, "ASSET_FUNDING", "asset", body.asset_id,
           after={"kind": body.kind.value, "amount": body.amount,
                  "award_reference": body.award_reference,
                  "funder": body.funder},
           reason=body.note or "funding source recorded")
    return {"asset_id": body.asset_id, "kind": body.kind.value}


@router.get("/asset-funding")
def asset_funding(period: str = None) -> dict:
    """Every asset with what is known about who paid for it.

    Ordered by what is *not* answered first, because the register is empty and
    the whole question is which assets nobody has been through.
    """
    period = period or settings.period
    rows = query("""SELECT a.asset_id, a.description, a.serial_number,
                           a.gross_cost, a.depreciation, a.in_service_on,
                           a.gl_account,
                           COALESCE(sum(f.amount), 0) AS funded,
                           count(f.*) AS sources,
                           COALESCE(jsonb_agg(jsonb_build_object(
                               'kind', f.kind, 'amount', f.amount,
                               'award_reference', f.award_reference,
                               'funder', f.funder))
                                    FILTER (WHERE f.asset_id IS NOT NULL),
                                    '[]'::jsonb) AS funding
                      FROM asset a
                      LEFT JOIN asset_funding f ON f.asset_id = a.asset_id
                     WHERE a.period = %s
                     GROUP BY a.asset_id, a.description, a.serial_number,
                              a.gross_cost, a.depreciation, a.in_service_on,
                              a.gl_account
                     ORDER BY count(f.*) = 0 DESC, a.gross_cost DESC""",
                 (period,))
    totals = one("""SELECT count(*) AS assets,
                           COALESCE(sum(a.gross_cost), 0) AS gross_cost,
                           COALESCE(sum(a.depreciation), 0) AS depreciation,
                           count(*) FILTER (WHERE NOT EXISTS (
                               SELECT 1 FROM asset_funding f
                                WHERE f.asset_id = a.asset_id)) AS unanswered
                      FROM asset a WHERE a.period = %s""", (period,))
    return {"period": period, "assets": rows, "totals": totals}


@router.get("/in-kind")
def in_kind(period: str = None) -> dict:
    """What may be offered as cost share, and what may only be told.

    Both are worth having. Only one of them goes on a federal report.
    """
    period = period or settings.period
    return {
        "period": period,
        "summary": query("SELECT * FROM v_in_kind_summary WHERE period = %s "
                         "ORDER BY claimed_as_cost_share DESC, kind", (period,)),
        "claims": query("""SELECT claim_id, kind::text AS kind, description,
                                  measured, value, valuation_basis,
                                  objective_id, award_id, claimed_as_cost_share,
                                  agency_approval, recorded_name, recorded_at
                             FROM in_kind_claim
                            WHERE period = %s AND superseded_at IS NULL
                            ORDER BY value DESC""", (period,)),
    }


@router.post("/in-kind")
def put_in_kind(body: InKindIn, period: str = None,
                actor: Actor = Depends(require_inventory)) -> dict:
    """Record an in-kind item.

    The schema refuses to mark YBI's own subsidy as cost share, and refuses
    unrecovered indirect without an approval reference. Those refusals are the
    point of the table: they are the two mistakes that would otherwise be made
    in good faith by somebody adding up everything valuable the organisation
    gave away.
    """
    period = period or settings.period
    r = one("""INSERT INTO in_kind_claim
                 (period, kind, objective_id, award_id, description, measured,
                  value, valuation_basis, source_document,
                  claimed_as_cost_share, agency_approval, recorded_by,
                  recorded_name)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING claim_id""",
            (period, body.kind.value, body.objective_id, body.award_id,
             body.description, body.measured, body.value,
             body.valuation_basis, body.source_document,
             body.claimed_as_cost_share, body.agency_approval,
             actor.actor_id, actor.display_name))
    record(actor, "IN_KIND", "in_kind_claim", str(r["claim_id"]),
           after={"kind": body.kind.value, "value": body.value,
                  "claimed_as_cost_share": body.claimed_as_cost_share},
           reason=body.valuation_basis[:400])
    return {"claim_id": r["claim_id"]}
