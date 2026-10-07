#!/usr/bin/env python3
"""What a liberal-but-defensible reading of the tenancies is worth.

    createdb ybi_lib -T ybi_exam        # a clone, never the record
    python scripts/liberal_rate.py --base http://127.0.0.1:8099

The rate NCDMM and YBI agree under 2 CFR 200.332(a)(4) is *negotiated*, so
the judgments inside it are genuinely YBI's to make. Three of them are not,
whatever the instrument says, and this script holds all three:

  * **200.406.** Floor area whose cost stays in the federal pool and which
    somebody pays YBI rent for carries an applicable credit. So every leg is
    priced twice — with the rent credited and without — and only the first
    is defensible. Printing the uncredited figure alone would put the same
    money into the pool twice.
  * **200.465 / `unit_market_needs_basis`.** Space somebody is charged rent
    for and which is nonetheless called programme space has to name the
    agreement that says so. The scenario supplies a placeholder and says it
    is one; the real move needs the document.
  * **200.403(d).** A reading adopted for one award is adopted for all of
    them. Nothing here is per-award.

Two levers are priced, because they are the only two a negotiated rate
actually hands YBI on 2025: **which floor area is let** (200.465) and
**which parties are subrecipients** (200.331). The tenancy legs move the
pool and nothing else, so each award's position is arithmetic on a
`direct_supported` that cannot move — and the script asserts that it does
not. The 200.331 leg moves each award's *own* direct cost as well, because
the excess over the $25,000 cap leaves that award's base too, so it is
measured through `POST /api/restate` rather than computed here.

**Both run against YBI**, which is the finding and is the reason this script
exists at all. The rent that makes a tenancy programme space becomes an
applicable credit worth more than the carve-out it removes, and a
subrecipient determination shrinks the award's own base faster than it
raises the rate. These three settlements cross zero at a combined rate of
44.80%, above anything this record has ever produced, so no reading here
flips 2025 — and a script that printed only the readings that raise the
number is a rate reverse-engineered, which is the thing the seal exists to
rule out.

Nothing is written to the record of account.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.db import open_pool, query  # noqa: E402
from app.domain.core import money  # noqa: E402
from app.foundation import EMAIL  # noqa: E402

PERIOD = "2025"
AFRL = "FA8650-20-2-5700"
#: The statuses that stand as a position, as `app/routers/restate.py` defines
#: them.
STANDING = ("PROPOSED", "SUBMITTED", "ACCEPTED")

#: Each leg names the lumped tenancy rows it reads as programme space, and
#: why. The register carries one aggregate TENANT row per building, so a leg
#: is a building rather than an occupant — which is a limitation of the
#: derived estate and not of the reading. Heidi's measured plan separates
#: them; it is filed and not accepted.
LEGS = {
    "AM": (["AM-T"], "AM-OTHER",
           "The America Makes building. NCDMM is a federal institute "
           "co-located with YBI under the same programme, not a commercial "
           "tenant, and the rent it pays is NCDMM's own $108,000."),
    "CLIENTS": (["YBIMAIN-T", "TBB5-T"], "HUB",
                "The incubator suites in YBI Main and Tech Block 5. An "
                "incubator housing its client companies is delivering "
                "incubation rather than renting property."),
}
#: Taft is Steelite International across 33,869 sq ft — a manufacturer on a
#: commercial lease, and the one tenancy nobody argues about. It is named
#: here so the list is visibly not "every tenancy that helps".
KEPT_LET = "TAFT-T"

#: The 200.331 leg's basis, and it says it is a scenario. The real
#: determination names which of the regulation's five tests carried it, which
#: is a judgment about the substance of a relationship and not something a
#: script may supply — `a_determination_says_who_and_why` is the schema's
#: floor and the reason for it is that a determination with no reasoning is
#: the next person's puzzle.
PARTY_BASIS = ("SCENARIO priced on a clone, and not a determination. 200.331 "
               "turns on the substance of the relationship and names five "
               "tests; which of them carries each of these six parties is a "
               "judgment with a person's name on it.")


class Clone:
    def __init__(self, base: str, password: str) -> None:
        self.c = httpx.Client(base_url=base, timeout=600)
        r = self.c.post("/api/auth/login",
                        json={"email": EMAIL["tom"], "password": password})
        if r.status_code != 200:
            raise SystemExit(f"could not sign in at {base}: {r.status_code} "
                             f"{r.text[:200]}")
        self.rows = {x["unit_id"]: x for x in query(
            """select unit_id, facility_id, label, use::text u, usable_sqft,
                      occupant, objective_id, actual_annual_charge rent,
                      market_rate_psf psf, market_basis, months_occupied
                 from space_unit where period = %s""", (PERIOD,))}

    def restore(self) -> None:
        for unit_id, row in self.rows.items():
            self._put(row, use=row["u"], objective=row["objective_id"])

    def _put(self, row, *, use: str, objective: str | None,
             basis: str = "") -> None:
        body = {"unit_id": row["unit_id"], "facility_id": row["facility_id"],
                "label": row["label"], "use": use,
                "status": "INTERNAL" if use != "TENANT" else "OCCUPIED",
                "months_occupied": float(row["months_occupied"]),
                "usable_sqft": float(row["usable_sqft"]),
                "occupant": row["occupant"],
                "actual_annual_charge": float(row["rent"] or 0) or None,
                "market_rate_psf": float(row["psf"]) if row["psf"] else None,
                "market_basis": row["market_basis"] or "",
                "objective_id": objective or None,
                "occupancy_basis": basis}
        r = self.c.put("/api/facilities/space", json=body,
                       params={"period": PERIOD})
        if r.status_code != 200:
            raise SystemExit(f"PUT /facilities/space refused for "
                             f"{row['unit_id']}: {r.status_code} "
                             f"{r.text[:400]}")

    def as_programme(self, unit_ids: list[str], objective: str) -> D:
        """Read these tenancies as programme space. Returns the rent moved."""
        moved = D(0)
        for unit_id in unit_ids:
            row = self.rows[unit_id]
            self._put(row, use="PROGRAM", objective=objective,
                      basis="SCENARIO — priced on a clone. The real move "
                            "names the agreement that makes this programme "
                            "space; 200.465 and unit_market_needs_basis "
                            "refuse it without one.")
            moved += D(str(row["rent"] or 0))
        return moved

    def determine(self, value: str) -> list[tuple[str, str, D]]:
        """Record `value` against every open 200.331 party. Returns them."""
        out = []
        for row in query(
                """select objective_id, payee, at_stake
                     from v_subaward_exposure where period = %s
                    order by at_stake desc""", (PERIOD,)):
            r = self.c.put("/api/classify/parties",
                           json={"objective_id": row["objective_id"],
                                 "payee": row["payee"] or "",
                                 "determination": value,
                                 "basis": "" if value == "UNDETERMINED"
                                          else PARTY_BASIS},
                           params={"period": PERIOD})
            if r.status_code != 200:
                raise SystemExit(f"PUT /classify/parties refused for "
                                 f"{row['objective_id']}: {r.status_code} "
                                 f"{r.text[:300]}")
            out.append((row["objective_id"], row["payee"] or "(no payee)",
                        D(str(row["at_stake"]))))
        return out

    def remeasure(self) -> list[tuple[str, D, D, D]]:
        """Withdraw each standing AFRL position and measure it again.

        `133` holds one standing claim per objective, so the withdrawal is
        not a tidy-up — it is the only way to put a second measurement on the
        record, and it is the act a person performs on `/restate`. On a clone
        it is mechanical; on the record it is Tom's.
        """
        rows = query(
            """select r.restatement_id, r.objective_id, a.agreement_name n
                 from v_restatement r join award a on a.award_id = r.award_id
                where r.period = %s and r.status = ANY(%s)
                  and a.prime_agreement like %s
                order by a.agreement_name""",
            (PERIOD, list(STANDING), f"%{AFRL}%"))
        for row in rows:
            w = self.c.post(f"/api/restate/{row['restatement_id']}/status",
                            json={"status": "SUPERSEDED",
                                  "note": "Superseded to measure the same "
                                          "award again under a scenario "
                                          "determination. Clone only."})
            if w.status_code != 200:
                raise SystemExit(f"withdraw refused for {row['n']}: "
                                 f"{w.status_code} {w.text[:300]}")
            m = self.c.post("/api/restate",
                            json={"objective_id": row["objective_id"],
                                  "rate_kind": "INDIRECT_COMBINED",
                                  "basis": "Scenario measurement on a clone, "
                                           "under the 200.331 reading priced "
                                           "by scripts/liberal_rate.py."},
                            params={"period": PERIOD})
            if m.status_code != 200:
                raise SystemExit(f"restate refused for {row['n']}: "
                                 f"{m.status_code} {m.text[:300]}")
        return [(r["n"], money(r["billed_total"]), money(r["supported_total"]),
                 money(r["billed_total"] - r["supported_total"]))
                for r in query(
                    """select a.agreement_name n, r.billed_total,
                              r.supported_total
                         from v_restatement r
                         join award a on a.award_id = r.award_id
                        where r.period = %s and r.status = ANY(%s)
                          and a.prime_agreement like %s
                        order by a.agreement_name""",
                    (PERIOD, list(STANDING), f"%{AFRL}%"))]

    def compute(self) -> dict:
        r = self.c.post("/api/rates/compute", json={"admin_labour": "POOL"},
                        params={"period": PERIOD})
        if r.status_code != 200:
            raise SystemExit(f"compute refused: {r.status_code} {r.text[:300]}")
        return {x["kind"]: x for x in query(
            """select kind, rate, pool_amount, base_amount from rate
                where period = %s and status <> 'SUPERSEDED'""", (PERIOD,))}


def settlements(rate: D) -> tuple[list[tuple[str, D]], D]:
    """Each AFRL award's position at `rate`, and the net.

    `billed - direct x (1 + rate)`, which is the identity the record's own
    restatements satisfy to the cent — checked by the caller before this is
    trusted.
    """
    rows = query(
        """select a.agreement_name n, r.billed_total b, r.direct_supported d
             from v_restatement r join award a on a.award_id = r.award_id
            where r.period = %s and r.status = ANY(%s)
              and a.prime_agreement like %s
            order by a.agreement_name""",
        (PERIOD, list(STANDING), f"%{AFRL}%"))
    out = [(r["n"], money(r["b"] - r["d"] * (1 + rate)), money(r["d"]))
           for r in rows]
    return out, money(sum((p for _, p, _ in out), D(0)))


def crossing() -> D:
    r = query(
        """select sum(r.billed_total) b, sum(r.direct_supported) d
             from v_restatement r join award a on a.award_id = r.award_id
            where r.period = %s and r.status = ANY(%s)
              and a.prime_agreement like %s""",
        (PERIOD, list(STANDING), f"%{AFRL}%"))[0]
    return D(str(r["b"])) / D(str(r["d"])) - 1


def line(label: str, rates: dict, credit: D = D(0)) -> dict:
    """One scenario, with the applicable credit taken off the indirect pool.

    The engine carves on floor area and knows nothing about the rent, so the
    credit is applied here — against the pool, where 200.406 puts it — and
    the uncredited figure is kept beside it only to price what the credit is
    worth.
    """
    combined = rates["INDIRECT_COMBINED"]
    pool, base = D(str(combined["pool_amount"])), D(str(combined["base_amount"]))
    raw = D(str(combined["rate"]))
    credited = (pool - credit) / base if base else D(0)
    return {"label": label, "credit": credit, "raw": raw,
            "credited": credited.quantize(D("0.0001")),
            "fringe": D(str(rates["FRINGE"]["rate"])), "pool": pool,
            "base": base}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8099")
    ap.add_argument("--password", default=os.environ.get("YBI_CLONE_PASSWORD"))
    ap.add_argument("--parties", action="store_true",
                    help="also price the 200.331 leg, which withdraws and "
                         "re-measures the three standing positions")
    args = ap.parse_args()
    if not args.password:
        raise SystemExit("set YBI_CLONE_PASSWORD or pass --password")
    if "ybi_lib" not in (os.environ.get("DATABASE_URL") or ""):
        raise SystemExit("point DATABASE_URL at the clone, never the record.")

    open_pool()
    box = Clone(args.base, args.password)

    runs = [line("as the record stands", box.compute())]
    for name, (units, obj, why) in LEGS.items():
        box.restore()
        credit = box.as_programme(units, obj)
        runs.append(line(name, box.compute(), credit) | {"why": why})
    box.restore()
    credit = sum((box.as_programme(u, o) for u, o, _ in LEGS.values()), D(0))
    runs.append(line("both legs", box.compute(), credit))
    box.restore()

    print("\nEvery figure computed by the engine on a clone. "
          "The record is untouched.")
    print("\nTENANCY — 200.465, and the rent 200.406 makes a credit\n")
    print(f"{'reading':<22}{'rate raw':>10}{'credit':>13}{'rate kept':>11}"
          f"{'  net on the three AFRL awards'}")
    held = None
    for r in runs:
        pos, net = settlements(r["credited"])
        direct = tuple(d for _, _, d in pos)
        # The carve-out moves the pool and no award's own direct cost, so this
        # has to hold across every tenancy leg. If it ever does not, the
        # arithmetic above is measuring two things at once and the leg has to
        # go through the engine the way the 200.331 leg does.
        if held is None:
            held = direct
        elif direct != held:
            raise SystemExit(f"direct_supported moved on a tenancy leg "
                             f"({r['label']}): {held} -> {direct}. Price this "
                             f"through the engine, not here.")
        print(f"  {r['label']:<20}{r['raw']*100:>9.2f}%{r['credit']:>13,.2f}"
              f"{r['credited']*100:>10.2f}%   {net:>12,.2f} "
              f"{'to NCDMM' if net > 0 else 'TO YBI'}")
    print("\n  Each award's direct cost held still across all four, which is "
          "what\n  makes the net arithmetic rather than a second engine run.")
    print(f"  Taft stays let: {KEPT_LET} is Steelite on a commercial lease.")
    for r in runs:
        if r.get("why"):
            print(f"\n  {r['label']}: {r['why']}")

    if args.parties:
        print("\n\nPARTIES — 200.331, read as subrecipients\n")
        parties = box.determine("SUBRECIPIENT")
        rates = box.compute()
        rate = D(str(rates["INDIRECT_COMBINED"]["rate"]))
        base = D(str(rates["INDIRECT_COMBINED"]["base_amount"]))
        print(f"  {len(parties)} parties, "
              f"{sum(p for _, _, p in parties):,.2f} at stake over the "
              f"$25,000 cap")
        for obj, payee, stake in parties:
            print(f"    {obj:<12}{payee:<32}{stake:>13,.2f}")
        print(f"\n  the rate goes to {rate*100:.2f}% over an MTDC of "
              f"{base:,.2f}")
        # And then the awards are measured again, because the excess leaves
        # each award's own direct cost as well as the estate-wide base — which
        # is why this leg cannot be arithmetic on a held `direct_supported`.
        after = box.remeasure()
        total = money(sum((g for _, _, _, g in after), D(0)))
        for name, billed, restated, gap in after:
            print(f"    {name:<22}{billed:>14,.2f}{restated:>14,.2f}"
                  f"{gap:>14,.2f}")
        print(f"    {'NET':<22}{'':>14}{'':>14}{total:>14,.2f} "
              f"{'to NCDMM' if total > 0 else 'TO YBI'}")
        print(f"\n  The rate rose and the net got worse: a subrecipient "
              f"determination\n  shrinks the award's own base faster than it "
              f"raises the rate it is\n  multiplied by. {PARTY_BASIS}")

    cross = crossing()
    print(f"\n\nWhat neither lever reaches: these three cross zero at "
          f"{cross*100:.2f}%\ncombined, above anything this record has "
          f"produced. The rate is not the\nlever on 2025 — the attribution "
          f"of cost to each award is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
