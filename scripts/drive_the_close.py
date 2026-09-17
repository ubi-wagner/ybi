#!/usr/bin/env python3
"""The 2025 year closed end to end, as the people who close it.

    YBI_SEED_PASSWORD=... DATABASE_URL=... python3 scripts/drive_the_close.py \
        [--base http://127.0.0.1:8000] [--period 2025]

Everything above this in `CLAUDE.md` builds one mechanism at a time and proves
it in isolation. This is the whole of it in one sitting, in the order a year is
actually closed, by the people whose job each step is:

    Heidi   the estate — five buildings, the space in them, and which assets
            federal money bought — proposed, never written
    Tom     every proposal reviewed and accepted; the 757 working positions
            adopted as his own; the rate sealed, computed and signed
    NCDMM   the three America Makes awards restated on the signed rate, with
            the amendment memorandum and the acceptance form, and accepted

**Neither measurement exists.** No building carries square footage and no
asset carries a funding source, so both of the two largest adjustments in the
rate model — the 2 CFR 200.465 facilities carve-out and 200.436(b)
depreciation — have been unevaluable for the life of the system. This run
estimates both from documents already on file and says so on every figure:

    $116.27/sqft   JobsOhio Grant Agreement SFPN_2021_493762-VCG, Commitment
                   1 — "$2,092,861 in building fixed asset investment" for
                   "approximately 18,000 square feet", on this estate
    180,538 sqft   the 2024 audited statements' Note 1 land, building and
                   improvements of $21,098,684, less $107,530 of land, at
                   that rate
    $7.00/sqft     the rate at which the 2025 rent roll accounts for 50.5% of
                   that estate — the floor of the same note's "predominately
                   available to businesses in Mahoning Valley as operating
                   leases"
    2023 + 2024    every capital addition of those two years, because the
                   SEFAs show $465,426 and $2,621,962 of federal capital
                   expenditure against $53,007 and $2,676,739 of additions

Every one is graded `TEST_ASSUMPTION` or `MANAGEMENT_RECONSTRUCTION` and
carries its derivation in its own `note`, because **an estimate that does not
say it is one is a measurement**. Heidi's tape measure supersedes all of it.

**It is deliberately not in `prove.sh`.** Every other drive leaves the record
as it found it and is checked against a census for doing so; this one closes a
year — it accepts recommendations, adopts 757 positions, certifies a rate and
records a sponsor's acceptance — and a cleanup that walked those back would be
withdrawing a signature and a position taken, which this system expresses by
superseding and never by deleting. Run it against a clone.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query                          # noqa: E402
from app.foundation import EMAIL                                  # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []
D = lambda x: Decimal(str(x))                                     # noqa: E731


def ok(what: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  \033[32mok\033[0m       {what}", flush=True)


def bad(what: str) -> None:
    global CHECKS
    CHECKS += 1
    FINDINGS.append(what)
    print(f"  \033[31mFINDING\033[0m  {what}", flush=True)


def note(what: str) -> None:
    print(f"  \033[33m·\033[0m        {what}", flush=True)


def head(what: str) -> None:
    print(f"\n\033[1m{what}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    """Sign in, choosing an own password where the account is still on the
    organisation's — `refuse_issued_password` stops an issued credential
    writing anything."""
    c = httpx.Client(base_url=base, timeout=600)
    own = password.rstrip("!") + "-own!"
    for candidate in (own, password):
        r = c.post("/api/auth/login", json={"email": email,
                                            "password": candidate})
        if r.status_code == 200:
            break
    else:
        print(f"could not sign in as {email}: {r.status_code} {r.text[:200]}",
              file=sys.stderr)
        raise SystemExit(2)
    if r.json().get("must_set_password"):
        ch = c.post("/api/auth/password",
                    json={"current_password": candidate, "new_password": own})
        if ch.status_code != 200:
            print(f"{email} could not set an own password: {ch.status_code} "
                  f"{ch.text[:200]}", file=sys.stderr)
            raise SystemExit(2)
        c.post("/api/auth/login", json={"email": email, "password": own})
    return c


def walk(period: str, key: str) -> dict:
    r = one("""SELECT state, detail FROM v_audit_walk
                WHERE period = %s AND key = %s""", (period, key))
    return r or {"state": "—", "detail": ""}


# ═════════════════════════════════════════════════════════════════════
#  The estate, derived from the documents rather than measured
# ═════════════════════════════════════════════════════════════════════

# JobsOhio Grant Agreement SFPN_2021_493762-VCG, Commitment 1.
PSF_BUILD = Decimal("116.27")
# 2024 audited financial statements, Note 1 (Property and Equipment).
AUDITED_ESTATE = Decimal("21098684")
# Fixed-asset register, GL 1500.
LAND = Decimal("107530.00")
# Derived below and asserted: the rate at which the 2025 rent roll accounts
# for the floor of the audited statements' "predominately".
PSF_RENT = Decimal("7.00")

BUILDINGS = {
    "TBB5":    dict(pat=r"tbb5|tb5|bldg 5|block building 5|juggerbot|jbot"
                        r"|fitz|basement buildout|leapfast|hydroponic",
                    name="Tech Block Building 5",
                    address="252 West Boardman Street, Youngstown OH 44503",
                    rent_leaf="4033 Tech Bldg 5 Rent"),
    "SEMPLE":  dict(pat=r"semple", name="Semple Building",
                    address="Youngstown OH 44503 — street number to confirm",
                    rent_leaf="4022 Semple Rent"),
    "TAFT":    dict(pat=r"\bttc\b|taft", name="Taft Technology Center",
                    address="255 West Federal Street, Youngstown OH 44503",
                    rent_leaf="4021 TTC Rent"),
    "AM":      dict(pat=r"america makes|namii|boardman",
                    name="America Makes Building",
                    address="Boardman Street, Youngstown OH 44503 "
                            "— street number to confirm",
                    rent_leaf="4026 NAMII Rent Boardman St."),
    "YBIMAIN": dict(pat=None, name="YBI Main (Vindicator Building)",
                    address="241 West Federal Street, Youngstown OH 44503",
                    rent_leaf="4020 Rent - YBI Main"),
}
EXTRA_RENT = {"4038 Brite Rent": "YBIMAIN"}


def building_of(description: str) -> str:
    """Which building a capitalised asset belongs to, read off the
    controller's own description. Nothing else on the register says."""
    d = description.lower()
    for code, b in BUILDINGS.items():
        if b["pat"] and re.search(b["pat"], d):
            return code
    return "YBIMAIN"


def estate(period: str) -> dict:
    """The five buildings, their square footage and how much of each is let.

    Square footage is derived twice over and neither derivation is a
    measurement, which is why every row it produces is graded
    `TEST_ASSUMPTION` and carries its arithmetic in its note. The *shares*
    are what the carve-out uses and they are what the documents actually
    support; the absolute areas are a consistent scale for them.
    """
    cap: dict[str, Decimal] = {}
    dep: dict[str, Decimal] = {}
    for r in query("""SELECT gl_account, description, gross_cost, depreciation
                        FROM asset WHERE period = %s""", (period,)):
        if r["gl_account"] not in ("1501", "1511", "1521"):
            continue                       # land, kit and furniture are not area
        b = building_of(r["description"])
        cap[b] = cap.get(b, Decimal(0)) + D(r["gross_cost"])
        dep[b] = dep.get(b, Decimal(0)) + D(r["depreciation"])

    rent: dict[str, Decimal] = {}
    leaf_of = {b["rent_leaf"]: c for c, b in BUILDINGS.items()}
    leaf_of.update(EXTRA_RENT)
    for r in query("""SELECT account, sum(amount) AS credit
                        FROM ledger_line
                       WHERE period = %s AND section = 'Income'
                       GROUP BY 1""", (period,)):
        leaf = r["account"].rsplit(":", 1)[-1]
        if leaf in leaf_of and D(r["credit"]) > 0:
            rent[leaf_of[leaf]] = rent.get(leaf_of[leaf], Decimal(0)) \
                + D(r["credit"])

    total_sqft = ((AUDITED_ESTATE - LAND) / PSF_BUILD).quantize(Decimal("1"))
    tenant = {b: (rent.get(b, Decimal(0)) / PSF_RENT).quantize(Decimal("1"))
              for b in cap}
    let = sum(tenant.values())
    residual = total_sqft - let
    total_cap = sum(cap.values())

    order = sorted(cap, key=lambda b: -cap[b])
    used, own = Decimal(0), {}
    for i, b in enumerate(order):
        if i == len(order) - 1:
            own[b] = residual - used          # residual, so the estate adds up
        else:
            own[b] = (residual * cap[b] / total_cap).quantize(Decimal("1"))
            used += own[b]
    return {"order": order, "cap": cap, "dep": dep, "rent": rent,
            "tenant": tenant, "own": own, "total_sqft": total_sqft,
            "let": let, "rent_total": sum(rent.values())}


WHY_SQFT = (
    "Estimated, not measured. The estate is the 2024 audited statements' "
    "$21,098,684 of land, building and improvements less $107,530 of land, at "
    "$116.27 a square foot — the rate the JobsOhio Grant Agreement "
    "SFPN_2021_493762-VCG states for this estate ($2,092,861 of building fixed "
    "asset investment for approximately 18,000 square feet). Let space is the "
    "2025 rent roll at $7.00 a square foot, which is the rate at which the "
    "rent roll accounts for the floor of the same note's \"predominately "
    "available to businesses in Mahoning Valley as operating leases\". The "
    "balance is allocated between buildings by capitalised cost. Replace this "
    "with a measurement; it is a scale for the shares, not a survey.")


# ═════════════════════════════════════════════════════════════════════
#  Which assets federal money bought
# ═════════════════════════════════════════════════════════════════════

NAMED_FEDERAL = {
    "YBI Portion TBB5 Phase-2":
        ("EDA 06-79-06300",
         "U.S. Department of Commerce, Economic Development Administration",
         "The EDA closeout letter of 17 November 2025 puts the final accepted "
         "total project cost at $2,376,344 and EDA's share at $1,903,179 "
         "(80.09%). The 2024 SEFA carries $1,872,050 of expenditure on "
         "11.307 against this award. Recorded at 100% federal as the "
         "conservative reading; if only EDA's own 80.09% is federal, "
         "19.91% of this asset's depreciation is allowable."),
    "TBB5 Phase 2 Elevator Changeorder":
        ("EDA 06-79-06300",
         "U.S. Department of Commerce, Economic Development Administration",
         "The same project. The JobsOhio agreement names \"installation of a "
         "new freight elevator\" inside the scope EDA closed out, and the "
         "closeout letter of 17 November 2025 still had $188,214.54 to "
         "disburse."),
    "Xjet ARC Equipment":
        ("ARC PW-20599",
         "Appalachian Regional Commission, Appalachian Area Development",
         "The register's own description names ARC. The 2024 SEFA carries "
         "$749,912 of expenditure on 23.002 across PW-20599-IM-22 and "
         "-IM-24."),
}

COVERED = (
    "No document names a funder for this asset. It is recorded federal on the "
    "year it was placed in service: the 2023 and 2024 Schedules of "
    "Expenditures of Federal Awards carry $465,426 and $2,621,962 of federal "
    "expenditure on capital-eligible programmes (EDA 11.307, ARC 23.002) "
    "against $53,007 and $2,676,739 of capital additions in those same years, "
    "so on the face of the audited statements the additions of both years are "
    "covered by federal money in full. This is the conservative reading and "
    "it is an aggregate argument, not an invoice: if only the three assets a "
    "document actually names are federal, $19,477.19 more depreciation is "
    "allowable.")

UNRESTRICTED = (
    "No federal award reaches this asset. The earliest Schedule of "
    "Expenditures of Federal Awards on file is 2023 and it carries no "
    "capital programme before ARC; the 2024 statements' Note 7 names the two "
    "large building grants — $1,500,000 through Youngstown State University "
    "and $3,000,000 to renovate the Vindicator Building — as State of Ohio "
    "money. EDA 06-79-06300 closed out on 17 November 2025.")


def funding_plan(period: str) -> list[dict]:
    """One answer per asset, and the rule each one follows in its own note."""
    out = []
    for a in query("""SELECT asset_id, description, gross_cost, in_service_on,
                             depreciation
                        FROM asset WHERE period = %s
                       ORDER BY gross_cost DESC""", (period,)):
        named = NAMED_FEDERAL.get(a["description"])
        y = a["in_service_on"].year if a["in_service_on"] else 0
        if named:
            ref, funder, why = named
            out.append(dict(asset_id=a["asset_id"], kind="FEDERAL",
                            amount=float(a["gross_cost"]), award_reference=ref,
                            funder=funder, note=why, grade="CORROBORATED",
                            dep=D(a["depreciation"])))
        elif y in (2023, 2024):
            out.append(dict(asset_id=a["asset_id"], kind="FEDERAL",
                            amount=float(a["gross_cost"]),
                            award_reference="EDA 06-79-06300 / ARC PW-20599",
                            funder="Federal — by the year's SEFA, not by "
                                   "invoice",
                            note=COVERED, grade="MANAGEMENT_RECONSTRUCTION",
                            dep=D(a["depreciation"])))
        else:
            out.append(dict(asset_id=a["asset_id"], kind="UNRESTRICTED",
                            amount=float(a["gross_cost"]),
                            award_reference="", funder="YBI unrestricted funds",
                            note=UNRESTRICTED, grade="CORROBORATED",
                            dep=Decimal(0)))
    return out


# ═════════════════════════════════════════════════════════════════════
#  Heidi
# ═════════════════════════════════════════════════════════════════════

def heidi_proposes(h: httpx.Client, period: str, est: dict) -> list[str]:
    """Five buildings and the space in them, proposed and not written.

    The schema lets a space name a building that is only *proposed*, because a
    building and the rooms in it are one afternoon's work and making her wait
    for Tom between the two would be friction with nothing behind it.
    """
    head("Heidi proposes the estate")
    recs: list[str] = []
    for code in est["order"]:
        b = BUILDINGS[code]
        total = est["tenant"][code] + est["own"][code]
        r = h.post(f"/api/positions/recommend?period={period}", json={
            "subject": "FACILITY", "subject_id": code,
            "proposal": {"facility_id": code, "name": b["name"],
                         "code": code, "address": b["address"], "owned": True,
                         "usable_sqft": float(total),
                         "source_document": "2026_YBI_Fixed-Asset-Schedule.xls "
                                            "· 2025_YBI_Lease-Schedule.xlsx · "
                                            "2024 audited statements Note 1",
                         "note": WHY_SQFT},
            "note": (f"{b['name']}: {total:,} usable square feet, estimated "
                     f"from the documents rather than measured. "
                     f"{est['tenant'][code]:,} of it is let on the 2025 rent "
                     f"roll at $7.00/sqft.")})
        if r.status_code != 200:
            bad(f"{code}: the building was refused — {r.status_code} "
                f"{r.text[:200]}")
            continue
        recs.append(r.json()["rec_id"])
        if r.json().get("is_new") is not True:
            bad(f"{code}: reported as an amendment to a building that is not "
                f"on the record")
    ok(f"{len(recs)} building(s) proposed, each one new to the record")

    units = 0
    for code in est["order"]:
        b = BUILDINGS[code]
        for unit_id, label, sqft, use, status, occupant in (
                (f"{code}-T", "Let and committed space", est["tenant"][code],
                 "TENANT", "OCCUPIED",
                 "Tenants of record — 2025_YBI_Lease-Schedule.xlsx"),
                (f"{code}-A", "YBI's own space", est["own"][code],
                 "ADMINISTRATIVE", "INTERNAL", "")):
            if sqft <= 0:
                continue
            payload = {"unit_id": unit_id, "facility_id": code, "label": label,
                       "usable_sqft": float(sqft), "use": use,
                       "status": status, "occupant": occupant,
                       "months_occupied": 12,
                       "note": (
                           "Let space is the building's own 2025 rental "
                           "revenue at $7.00 a square foot, so it is already "
                           "the year's average occupancy and months_occupied "
                           "is 12. YBI's own space is the estate's balance "
                           "allocated by capitalised cost. The split of YBI's "
                           "own space between programme, administrative and "
                           "laboratory use is Heidi's to make and does not "
                           "move the 200.465 carve-out."
                           if use == "TENANT" else
                           "The balance of the building. Recorded "
                           "administrative rather than programme because "
                           "nothing on the record attributes a square foot to "
                           "a cost objective, and programme space names the "
                           "objective it serves. Splitting it changes the "
                           "disclosure and not the carve-out.")}
            if use == "TENANT":
                payload["actual_annual_charge"] = float(
                    est["rent"].get(code, Decimal(0)))
                payload["market_rate_psf"] = float(PSF_RENT)
                payload["market_basis"] = (
                    "The rate at which the 2025 rent roll accounts for 50.5% "
                    "of the estate — the floor of the 2024 audited "
                    "statements' \"predominately available to businesses in "
                    "Mahoning Valley as operating leases\".")
                payload["market_source"] = "2025_YBI_Lease-Schedule.xlsx"
            r = h.post(f"/api/positions/recommend?period={period}",
                       json={"subject": "SPACE_UNIT", "subject_id": unit_id,
                             "proposal": payload,
                             "note": (f"{label} at {b['name']}: "
                                      f"{sqft:,} square feet.")})
            if r.status_code != 200:
                bad(f"{unit_id}: refused — {r.status_code} {r.text[:200]}")
                continue
            recs.append(r.json()["rec_id"])
            units += 1
    ok(f"{units} space unit(s) proposed across {len(est['order'])} buildings")
    return recs


def heidi_answers_the_register(h: httpx.Client, period: str,
                               plan: list[dict]) -> list[str]:
    """The funding source on all 263 assets.

    Two doors, deliberately. The three assets a document actually names go to
    Tom as recommendations, because which award bought a $2.4m building is a
    judgment the controller signs the rate over. The other 260 are a
    transcription of a rule Heidi can state in one sentence, on her own
    register, through her own portfolio — and `PUT /api/facilities/
    asset-funding` is the door `084` built for exactly that.
    """
    head("Heidi answers the asset register")
    recs, written, refused = [], 0, 0
    for a in plan:
        if a["grade"] == "CORROBORATED" and a["kind"] == "FEDERAL":
            r = h.post(f"/api/positions/recommend?period={period}", json={
                "subject": "ASSET_FUNDING", "subject_id": a["asset_id"],
                "proposal": {"asset_id": a["asset_id"], "kind": a["kind"],
                             "amount": a["amount"],
                             "award_reference": a["award_reference"],
                             "funder": a["funder"], "note": a["note"]},
                "note": (f"A document names federal money against this asset: "
                         f"{a['award_reference']}. 200.436(b) makes the "
                         f"depreciation on it unallowable.")})
            if r.status_code != 200:
                bad(f"{a['asset_id']}: funding refused — {r.status_code} "
                    f"{r.text[:200]}")
                refused += 1
            else:
                recs.append(r.json()["rec_id"])
            continue
        r = h.put(f"/api/facilities/asset-funding?period={period}", json={
            "asset_id": a["asset_id"], "kind": a["kind"],
            "amount": a["amount"], "award_reference": a["award_reference"],
            "funder": a["funder"], "note": a["note"]})
        if r.status_code not in (200, 201):
            refused += 1
            if refused <= 3:
                bad(f"{a['asset_id']}: {r.status_code} {r.text[:160]}")
        else:
            written += 1
    ok(f"{written} asset(s) answered on Heidi's own register, "
       f"{len(recs)} put to Tom as a judgment")
    if refused:
        bad(f"{refused} asset(s) could not be answered")
    return recs


# ═════════════════════════════════════════════════════════════════════
#  Tom
# ═════════════════════════════════════════════════════════════════════

def tom_accepts(t: httpx.Client, period: str, recs: list[str]) -> None:
    """Every open recommendation, in the order the register needs them.

    `/positions/review` sorts a building above the rooms inside it, because
    `put_unit` answers 404 on a facility that is not there. The drive follows
    the screen rather than its own list, so it cannot disagree with what Tom
    is shown.
    """
    head("Tom reviews and accepts")
    for subject in ("FACILITY", "SPACE_UNIT", "ASSET_FUNDING"):
        r = t.get(f"/api/positions/review?period={period}&subject={subject}")
        if r.status_code != 200:
            bad(f"{subject}: the review list refused — {r.status_code}")
            continue
        rows = r.json().get("recommendations", [])
        took = 0
        for row in rows:
            a = t.post(
                f"/api/positions/recommendations/{row['item_id']}/accept"
                f"?period={period}",
                json={"reason": "Reviewed against the source documents the "
                                "recommendation cites, and adopted as the "
                                "provisional basis for the 2025 rate.",
                      "rationale": "Adopted from Heidi Ruby's recommendation, "
                                   "which carries its derivation and the "
                                   "documents behind it.",
                      "grade": "MANAGEMENT_RECONSTRUCTION"})
            if a.status_code != 200:
                bad(f"{row['subject_id']} ({subject}): accept refused — "
                    f"{a.status_code} {a.text[:200]}")
            else:
                took += 1
        ok(f"{subject}: {took} of {len(rows)} accepted")
    still = one("""SELECT count(*) AS n FROM recommendation
                    WHERE period = %s AND disposition = 'OPEN'""", (period,))
    if still["n"]:
        bad(f"{still['n']} recommendation(s) still open after the review")
    else:
        ok("no recommendation is left open")


def tom_adopts_the_positions(t: httpx.Client, period: str) -> None:
    """The 757 working positions, adopted as the controller's own judgment.

    Nothing about the cost moves — `position_confirmation` is a different
    table and the seal is untouched — which is the property that makes it
    safe to do in one sitting.
    """
    head("Tom adopts the working positions")
    before = one("""SELECT sum(rate) AS s FROM rate
                     WHERE period = %s AND status <> 'SUPERSEDED'""",
                 (period,))["s"]
    taken = 0
    while True:
        r = t.get(f"/api/positions?period={period}"
                  f"&state=unadopted&limit=200")
        if r.status_code != 200:
            bad(f"the position list refused — {r.status_code} {r.text[:200]}")
            return
        rows = r.json().get("positions", [])
        if not rows:
            break
        ids = [p["decision_id"] for p in rows]
        c = t.post(f"/api/positions/confirm?period={period}",
                   json={"decision_ids": ids,
                         "note": "Reviewed against the account, the payee and "
                                 "the rationale the log recorded, and adopted "
                                 "as my own judgment."})
        if c.status_code != 200:
            bad(f"confirm refused — {c.status_code} {c.text[:200]}")
            return
        got = c.json().get("confirmed", 0)
        taken += got
        if got == 0:
            break
    ok(f"{taken} working position(s) adopted")
    after = one("""SELECT sum(rate) AS s FROM rate
                    WHERE period = %s AND status <> 'SUPERSEDED'""",
                (period,))["s"]
    if before == after:
        ok("no rate moved — adopting a position is not a change to the cost")
    else:
        bad(f"a rate moved on adoption: {before} -> {after}")


def tom_computes(t: httpx.Client, period: str, basis: str) -> dict:
    """Recompute over the sealed set, now that both partitions are answered.

    Computing is arithmetic and sealing is a judgment: this recomputes over
    judgments it did not make and cannot reach. The basis is read from the
    rate on file rather than chosen here — a drive has no business holding an
    opinion about a policy worth nine points of combined rate.
    """
    head("Tom recomputes the rate")
    r = t.post(f"/api/rates/compute?period={period}",
               json={"admin_labour": basis})
    if r.status_code != 200:
        bad(f"compute refused — {r.status_code} {r.text[:300]}")
        return {}
    body = r.json()
    stored = one("""SELECT admin_labour_basis FROM rate
                     WHERE period = %s AND status <> 'SUPERSEDED'
                     ORDER BY computed_at DESC LIMIT 1""", (period,))
    if stored and stored["admin_labour_basis"] != basis:
        bad(f"asked for {basis} and the rate records "
            f"{stored['admin_labour_basis']}")
    else:
        ok(f"computed on the {basis} basis, as asked")
    for c in body.get("carve_outs", []):
        note(f"{c['citation']}  {c['name']}  ${D(c['amount']):,.2f}")
    return body


def tom_certifies(t: httpx.Client, period: str) -> None:
    head("Tom certifies the rate")
    # The signature says what made it. Typing a controller's name here is
    # what put *"certified by Tom Metzinger"* on a memorandum to NCDMM.
    r = t.post(f"/api/rates/certify?period={period}",
               json={"origin": "REHEARSAL",
                     "signature": "Tom Metzinger",
                     "note": "The build-up is mine. The square footage and "
                             "the asset funding are estimates taken off the "
                             "documents on file and are recorded as such; "
                             "they are the two figures I expect to move."})
    if r.status_code != 200:
        bad(f"certify refused — {r.status_code} {r.text[:300]}")
        return
    cert = one("""SELECT certified, signature, certified_by, certified_at,
                         jsonb_array_length(coalesce(outstanding,'[]'::jsonb))
                           AS open_steps
                    FROM v_rate_certified WHERE period = %s""", (period,))
    if cert and cert["certified"]:
        ok(f"certified by {cert['certified_by']} as {cert['signature']!r}, "
           f"carrying {cert['open_steps']} unfinished step(s)")
    else:
        bad("the certificate does not read back as live")


# ═════════════════════════════════════════════════════════════════════
#  The restatement, and the two papers it cannot travel without
# ═════════════════════════════════════════════════════════════════════

AM_BASIS = ("Restated on the 2025 provisional indirect rate, computed over the "
            "sealed classification and certified by the controller. The "
            "invoices as issued recovered indirect inside a loaded labour "
            "rate, which 200.414(f) does not contemplate; this states the "
            "position on a disclosed rate over MTDC.")


def restate(t: httpx.Client, period: str) -> list[dict]:
    head("The America Makes awards, restated on the signed rate")
    r = t.get(f"/api/restate/candidates?period={period}")
    if r.status_code != 200:
        bad(f"the candidate list refused — {r.status_code} {r.text[:200]}")
        return []
    body = r.json()
    for why in body.get("blocked_because", []):
        bad(f"nothing can be restated: {why}")
    out = []
    # Only what an award stands behind. An objective with invoices and no
    # award has nothing to restate *against*: the rate method, the ceiling
    # and the change-of-basis clause are all the agreement's.
    with_award = {a["objective_id"] for a in
                  query("SELECT objective_id FROM award WHERE objective_id "
                        "IS NOT NULL")}
    for c in body.get("objectives", []):
        if c["objective_id"] not in with_award:
            note(f"{c['objective_id']}: {c['invoices']} invoice(s) and no "
                 f"award on the record — nothing to restate against")
            continue
        p = t.post(f"/api/restate?period={period}",
                   json={"objective_id": c["objective_id"],
                         "rate_kind": "INDIRECT_COMBINED", "basis": AM_BASIS})
        if p.status_code != 200:
            bad(f"{c['objective_id']}: restate refused — {p.status_code} "
                f"{p.text[:220]}")
            continue
        out.append(p.json())
        j = p.json()
        note(f"{c['objective_id']}: {j.get('invoices')} invoice(s), "
             f"under-recovered ${D(j.get('under_recovered', 0)):,.2f}, "
             f"over-collected ${D(j.get('over_collected', 0)):,.2f}")
    ok(f"{len(out)} restatement(s) computed")
    return out


def papers(t: httpx.Client, period: str, out_dir: Path) -> list[Path]:
    """The memorandum and the acceptance form, per award, through the routes
    the screen calls."""
    head("The amendment papers")
    wrote = []
    awards = query("""SELECT DISTINCT a.award_id, a.agreement_name
                        FROM restatement r
                        JOIN award a ON a.objective_id = r.objective_id
                       WHERE r.period = %s AND r.status <> 'SUPERSEDED'
                       ORDER BY a.award_id""", (period,))
    for a in awards:
        for what, slug in (("memo", "amendment-memorandum"),
                           ("acceptance", "acceptance-form")):
            r = t.get(f"/api/restate/award/{a['award_id']}/{what}"
                      f"?period={period}")
            if r.status_code != 200:
                bad(f"{a['award_id']} {what}: {r.status_code} {r.text[:200]}")
                continue
            p = out_dir / f"{a['award_id']}_{slug}.pdf"
            p.write_bytes(r.content)
            wrote.append(p)
            ok(f"{p.name}  {len(r.content):,} bytes")
    return wrote


def accept_them(t: httpx.Client, period: str) -> None:
    """NCDMM accepts. Each acceptance names the modification that authorised
    the change of basis, which the schema refuses to do without."""
    head("Every restatement accepted")
    rows = query("""SELECT restatement_id, objective_id, status::text AS status
                      FROM restatement
                     WHERE period = %s AND status NOT IN ('SUPERSEDED',
                                                          'ACCEPTED')
                     ORDER BY objective_id""", (period,))
    for row in rows:
        s = t.post(f"/api/restate/{row['restatement_id']}/status",
                   json={"status": "SUBMITTED",
                         "note": "Issued to NCDMM with the amendment "
                                 "memorandum and the acceptance form."})
        if s.status_code != 200:
            bad(f"{row['objective_id']}: submit refused — {s.status_code} "
                f"{s.text[:200]}")
            continue
        a = t.post(f"/api/restate/{row['restatement_id']}/status",
                   json={"status": "ACCEPTED",
                         "modification_ref": MODIFICATION.get(
                             row["objective_id"], "Modification to be issued"),
                         "note": "Accepted by NCDMM on the acceptance form "
                                 "returned with the amendment memorandum."})
        if a.status_code != 200:
            bad(f"{row['objective_id']}: accept refused — {a.status_code} "
                f"{a.text[:260]}")
        else:
            ok(f"{row['objective_id']} accepted, naming "
               f"{MODIFICATION.get(row['objective_id'], 'a modification')}")
    # An acceptance that named nothing would be the finding this exists for.
    blank = one("""SELECT count(*) AS n FROM restatement
                    WHERE period = %s AND status = 'ACCEPTED'
                      AND coalesce(btrim(modification_ref), '') = ''""",
                (period,))
    if blank["n"]:
        bad(f"{blank['n']} acceptance(s) name no modification")
    else:
        ok("every acceptance names its modification")


#: The instrument each award's change of basis is made under. Hybrid's is on
#: file; the other two have none yet, and the memorandum says so rather than
#: inventing a clause — `056` found three provisions on two awards cited to
#: clauses those agreements do not contain.
MODIFICATION = {
    "HYBRID-II": "NCDMM 20240061 Modification 001, 22 January 2026",
    "DRIVE-AM": "Modification to be issued — no change-of-basis clause is on "
                "the record for this agreement",
    "LTM": "Modification to be issued — Project 88 §4.4",
    "DIG-ENG": "Modification to be issued — SRA-0350 §9",
}


# ═════════════════════════════════════════════════════════════════════
#  What it all moved
# ═════════════════════════════════════════════════════════════════════

def before_and_after(period: str) -> dict:
    r = {x["kind"]: D(x["rate"]) for x in
         query("""SELECT kind, rate FROM rate
                   WHERE period = %s AND status <> 'SUPERSEDED'""", (period,))}
    c = query("""SELECT name, citation, amount FROM carve_out
                  WHERE period = %s ORDER BY amount DESC""", (period,))
    return {"rates": r, "carve_outs": c}


def report(period: str, opening: dict, closing: dict, est: dict) -> None:
    head("What the two measurements moved")
    print(f"  {'':34} {'before':>10} {'after':>10}")
    for kind in ("FRINGE", "OVERHEAD", "G&A", "INDIRECT_COMBINED"):
        a = opening["rates"].get(kind)
        b = closing["rates"].get(kind)
        print(f"  {kind:34} {(f'{a:.2%}' if a is not None else '—'):>10} "
              f"{(f'{b:.2%}' if b is not None else '—'):>10}")
    print()
    for c in closing["carve_outs"]:
        print(f"  {c['citation']:20} {c['name'][:44]:44} "
              f"${D(c['amount']):>12,.2f}")
    total = sum(D(c["amount"]) for c in closing["carve_outs"])
    print(f"  {'':20} {'carved from the overhead pool':44} "
          f"${total:>12,.2f}")
    print()
    print(f"  estate     {est['total_sqft']:,} usable square feet across "
          f"{len(est['order'])} buildings")
    print(f"  let        {est['let']:,} square feet "
          f"({est['let'] / est['total_sqft']:.1%}), against a 2025 rent roll "
          f"of ${est['rent_total']:,.2f}")

    head("Where the walk stands")
    for k in ("LEDGER", "RECONCILE", "CLASSIFY", "SPACE", "ASSETS",
              "EVIDENCE", "SEAL", "RATE", "CERTIFY", "RESTATE", "REPORT"):
        w = walk(period, k)
        colour = {"DONE": "\033[32m", "OPEN": "\033[33m",
                  "NO DATA": "\033[31m"}.get(w["state"], "")
        print(f"  {k:12} {colour}{w['state']:8}\033[0m {w['detail'][:88]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("BASE",
                                                "http://127.0.0.1:8000"))
    ap.add_argument("--period", default="2025")
    ap.add_argument("--out", default="docs/publications/close-2025")
    #: This drive closes a year: it seals, certifies, and records a sponsor's
    #: acceptance. Its docstring has always said **run it against a clone**,
    #: and nothing enforced that — so it was run against the reference record
    #: and the committed publication set came out saying *"certified by Tom
    #: Metzinger, Controller"* over a rate nobody has signed.
    #:
    #: `password_round.py`'s rule, which is the only other act here that takes
    #: something away from the person who should have made it: **never
    #: automatic, and behind an explicit flag.**
    ap.add_argument("--rehearsal", action="store_true",
                    help="required: this database is a clone and everything "
                         "signed here is labelled REHEARSAL")
    args = ap.parse_args()
    period = args.period
    if not args.rehearsal:
        print("This drive seals, certifies and records a sponsor's "
              "acceptance.\nRun it against a clone and pass --rehearsal, so "
              "every signature it makes\nsays a drive made it.", file=sys.stderr)
        return 2
    pw = os.getenv("YBI_SEED_PASSWORD") or os.getenv("YBI_INITIAL_PASSWORD")
    if not pw:
        print("set YBI_SEED_PASSWORD", file=sys.stderr)
        return 2
    open_pool()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    est = estate(period)
    head("The estate, derived from the documents")
    print(f"  {'building':10} {'cap cost':>14} {'2025 rent':>12} "
          f"{'let sqft':>9} {'YBI sqft':>9} {'total':>9} {'let':>7}")
    for b in est["order"]:
        t = est["tenant"][b] + est["own"][b]
        print(f"  {b:10} {est['cap'][b]:>14,.2f} "
              f"{est['rent'].get(b, Decimal(0)):>12,.2f} "
              f"{est['tenant'][b]:>9,} {est['own'][b]:>9,} {t:>9,} "
              f"{est['tenant'][b] / t:>7.1%}")
    print(f"  {'':10} {sum(est['cap'].values()):>14,.2f} "
          f"{est['rent_total']:>12,.2f} {est['let']:>9,} "
          f"{sum(est['own'].values()):>9,} {est['total_sqft']:>9,} "
          f"{est['let'] / est['total_sqft']:>7.1%}")
    if not (Decimal("0.50") <= est["let"] / est["total_sqft"] < Decimal("0.55")):
        bad("the let share is not at the floor of the audited statements' "
            "\"predominately\" — the $7.00 rate no longer derives itself")
    else:
        ok("the let share sits at the floor of the audited statements' "
           "\"predominately available ... as operating leases\"")

    opening = before_and_after(period)
    basis = (one("""SELECT admin_labour_basis FROM rate
                     WHERE period = %s AND status <> 'SUPERSEDED'
                     ORDER BY computed_at DESC LIMIT 1""", (period,))
             or {"admin_labour_basis": "OBJECTIVE"})["admin_labour_basis"]

    heidi = sign_in(args.base, EMAIL["heidi"], pw)
    tom = sign_in(args.base, EMAIL["tom"], pw)

    recs = heidi_proposes(heidi, period, est)
    recs += heidi_answers_the_register(heidi, period, funding_plan(period))
    tom_accepts(tom, period, recs)
    tom_adopts_the_positions(tom, period)
    tom_computes(tom, period, basis)
    tom_certifies(tom, period)
    restate(tom, period)
    papers(tom, period, out_dir)
    accept_them(tom, period)

    closing = before_and_after(period)
    report(period, opening, closing, est)

    head(f"{CHECKS} checks, {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"  \033[31m·\033[0m {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
