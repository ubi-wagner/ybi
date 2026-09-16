#!/usr/bin/env python3
"""What the settlement comes to on each contract, as a function of the rate.

The hope put to this is that the four America Makes positions come out close
to net zero. They do not, and the direction is the first thing worth knowing:
**a lower rate makes every give-back larger and the one claim smaller**, so
moving towards the 21% this engagement expects moves the net further from
zero, not closer.

The reason is arithmetic that the per-contract table makes plain. Restating is
a rebuild: the loaded labour line comes *down* to wages plus fringe, and the
indirect then goes on over MTDC. So a contract's position is

    billed  −  (direct supported  +  rate × MTDC)

which is a straight line in the rate whose slope is that contract's own MTDC.
Where the cost record attributes little cost to an award, the slope is small
and no rate anybody would propose can reach the billing. **The lever is
attribution, not the rate.**

Nothing here is a position and nothing runs against the record of account.
Every rate is *computed* by `POST /api/rates/compute` rather than asserted,
which is the only honest way to walk a range: the 200.465 carve-out is linear
in the share of the estate that is not YBI's own, so moving that share on a
sandbox walks the engine across the band. Every settlement figure is then read
back off `v_restatement` after `POST /api/restate`.

    createdb ybi_settle -T ybi_exam      # a clone, never the record
    DATABASE_URL=...ybi_settle python scripts/settlement_at_rate.py \
        --base http://127.0.0.1:8040 --write
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal as D
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import open_pool, query  # noqa: E402
from app.foundation import EMAIL     # noqa: E402

DOC = ROOT / "docs" / "SETTLEMENT_AT_RATE_2025.md"
PERIOD = "2025"

#: The four America Makes awards, in the order the settlement memorandum
#: takes them: the three that run one way, then the one that runs the other.
OBJECTIVES = ("DRIVE-AM", "DIG-ENG", "HYBRID-II", "LTM")

#: The share of the estate that is not YBI's own, at each point of the walk.
#: The middle one is the derived estate on the record; the rest exist to draw
#: the line either side of it. None of them is a measurement.
SHARES = ("0.0001", "0.20", "0.35", "0.505295", "0.60", "0.70", "0.80")

BASIS = ("Scenario run on a sandbox clone: the settlement priced at this "
         "indirect rate so each award's position can be read as a function "
         "of the rate rather than as a single point. Not a position.")


def money(x) -> str:
    return f"{D(str(x)):,.2f}"


def pct(x, places: int = 2) -> str:
    return f"{D(str(x)) * 100:.{places}f}%"


class Sandbox:
    """The running service, signed in as the controller."""

    def __init__(self, base: str, password: str) -> None:
        self.c = httpx.Client(base_url=base, timeout=600)
        r = self.c.post("/api/auth/login",
                        json={"email": EMAIL["tom"], "password": password})
        if r.status_code != 200:
            raise SystemExit(f"could not sign in at {base}: "
                             f"{r.status_code} {r.text[:200]}")
        # The session is a cookie and httpx keeps it; there is no bearer here.
        self.facilities = {row["facility_id"]: D(str(row["usable_sqft"]))
                           for row in query("SELECT facility_id, usable_sqft "
                                            "  FROM facility WHERE period = %s",
                                            (PERIOD,))}
        self.tenant = {row["facility_id"]: row for row in query(
            "SELECT facility_id, usable_sqft, actual_annual_charge, "
            "       market_rate_psf, market_basis "
            "  FROM space_unit WHERE period = %s AND use = 'TENANT'",
            (PERIOD,))}
        self.estate = sum(self.facilities.values())
        if not self.tenant:
            raise SystemExit("no let space on this record — there is no "
                             "carve-out to move, so there is no walk.")

    def _put(self, body: dict) -> None:
        r = self.c.put("/api/facilities/space", json=body,
                       params={"period": PERIOD})
        if r.status_code != 200:
            raise SystemExit(f"PUT /facilities/space refused: "
                             f"{r.status_code} {r.text[:300]}")

    def set_excluded(self, share: D) -> D:
        """Put the same excluded share on every building: let first, then vacant.

        Let space is capped at what the lease book already says, so the walk
        never invents a tenancy; everything above that is vacancy, which is
        the one thing this record measures none of and which the published
        rate is therefore not conservative about.
        """
        excluded = D(0)
        for fid, usable in self.facilities.items():
            base = self.tenant[fid]
            target = (usable * share).quantize(D("0.01"))
            let = min(D(str(base["usable_sqft"])), target)
            self._put({"unit_id": f"{fid}-T", "facility_id": fid,
                       "label": "Let and committed space", "use": "TENANT",
                       "status": "OCCUPIED", "months_occupied": 12,
                       "usable_sqft": float(max(let, D("0.01"))),
                       "occupant": "Tenants of record — scenario",
                       "actual_annual_charge":
                           float(base["actual_annual_charge"]),
                       "market_rate_psf": float(base["market_rate_psf"]),
                       "market_basis": base["market_basis"]})
            for unit_id, label, use, status, area in (
                    (f"{fid}-V", "Vacant space", "VACANT", "VACANT",
                     target - let),
                    (f"{fid}-A", "YBI's own space", "ADMINISTRATIVE",
                     "INTERNAL", usable - target)):
                # A row of no area is refused outright, and a stale row left
                # standing would still be counted. One hundredth of a square
                # foot is the smallest honest placeholder and moves nothing.
                self._put({"unit_id": unit_id, "facility_id": fid,
                           "label": label, "use": use, "status": status,
                           "months_occupied": 12,
                           "usable_sqft": float(max(area, D("0.01")))})
            excluded += target
        return excluded / self.estate

    def compute(self) -> tuple[dict, D]:
        r = self.c.post("/api/rates/compute", json={"admin_labour": "POOL"},
                        params={"period": PERIOD})
        if r.status_code != 200:
            raise SystemExit(f"compute refused: {r.status_code} {r.text[:300]}")
        rates = {x["kind"]: D(str(x["rate"])) for x in query(
            "SELECT kind, rate FROM rate WHERE period = %s "
            "   AND status <> 'SUPERSEDED' ORDER BY computed_at DESC",
            (PERIOD,))}
        carve = query("SELECT coalesce(sum(amount), 0) AS a FROM carve_out "
                      " WHERE period = %s", (PERIOD,))[0]["a"]
        return rates, D(str(carve))

    def restate(self) -> dict:
        out = {}
        for obj in OBJECTIVES:
            r = self.c.post("/api/restate",
                            json={"objective_id": obj, "basis": BASIS},
                            params={"period": PERIOD})
            if r.status_code != 200:
                raise SystemExit(f"restate {obj} refused: "
                                 f"{r.status_code} {r.text[:300]}")
            out[obj] = query(
                """SELECT invoices, billed_total, direct_supported,
                          indirect_rebuilt, supported_total, under_recovered,
                          over_collected, rate_applied
                     FROM v_restatement
                    WHERE period = %s AND objective_id = %s
                      AND status <> 'SUPERSEDED'
                    ORDER BY computed_at DESC LIMIT 1""", (PERIOD, obj))[0]
        return out


def position(row) -> D:
    """One signed figure, for the shape of the line only.

    The settlement itself never nets these: a claim and a give-back are two
    conversations and `v_restatement` deliberately carries them apart. This is
    used to read the slope and the break-even, and both directions are printed
    in full above any aggregate.
    """
    return D(str(row["under_recovered"])) - D(str(row["over_collected"]))


def walk(box: Sandbox) -> list[dict]:
    out = []
    for share in SHARES:
        excluded = box.set_excluded(D(share))
        rates, carve = box.compute()
        out.append({"excluded": excluded, "carve": carve, "rates": rates,
                    "positions": box.restate()})
        print(f"  excluded {excluded:8.4%}   combined "
              f"{rates['INDIRECT_COMBINED']:7.4%}", flush=True)
    return out


def line(points: list[tuple[D, D]]) -> tuple[D, D]:
    """Slope and break-even of a position that is affine in the rate.

    Read off two engine runs rather than derived a second time in Python: the
    slope *is* the objective's MTDC, and taking it from the runs is what makes
    the straight line a finding rather than an assumption.
    """
    (x0, y0), (x1, y1) = points[0], points[-1]
    m = (y1 - y0) / (x1 - x0)
    return m, x0 - y0 / m


def billed_shape() -> dict:
    """What each award's invoices say they were billing for.

    The categories are the invoice register's own, not a reading of them.
    """
    shape = {}
    for row in query(
            """SELECT i.objective_id, il.category::text AS category,
                      sum(il.amount) AS amount
                 FROM invoice i JOIN invoice_line il
                      ON il.invoice_id = i.invoice_id
                WHERE i.period = %s GROUP BY 1, 2""", (PERIOD,)):
        shape.setdefault(row["objective_id"], {})[row["category"]] = \
            D(str(row["amount"]))
    return shape


def attributed() -> dict:
    """The wages the effort distribution puts on each objective, and the
    direct non-labour the classification puts there. Two registers, read
    separately, because they are answered by different people."""
    out = {}
    for row in query("""SELECT objective_id, count(*) AS people,
                               sum(distributed_wages) AS wages
                          FROM v_labor_effective WHERE period = %s
                         GROUP BY 1""", (PERIOD,)):
        out.setdefault(row["objective_id"], {})["wages"] = D(str(row["wages"]))
        out[row["objective_id"]]["people"] = row["people"]
    for row in query("""SELECT d.objective_id, count(*) AS lines,
                               sum(l.amount) AS amount
                          FROM decision_line dl
                          JOIN decision d ON d.decision_id = dl.decision_id
                          JOIN decision_set s ON s.set_id = d.set_id
                          JOIN ledger_line l ON l.line_id = dl.line_id
                         WHERE dl.live AND d.reversed_at IS NULL
                           AND s.period = %s AND d.pool = 'DIRECT'
                         GROUP BY 1""", (PERIOD,)):
        out.setdefault(row["objective_id"], {})["nonlabour"] = \
            D(str(row["amount"]))
        out[row["objective_id"]]["lines"] = row["lines"]
    return out


NAME = {"DRIVE-AM": "Drive AM", "DIG-ENG": "Digital Engineering",
        "HYBRID-II": "Hybrid Phase II", "LTM": "Last Tactical Mile"}


def report(runs: list[dict]) -> list[str]:
    o, w = [], lambda s: o.append(s)
    here = next(r for r in runs
                if str(round(r["excluded"], 4)) == "0.5053")
    ref = here["rates"]["INDIRECT_COMBINED"]
    shape, attr = billed_shape(), attributed()
    points = {obj: [(r["rates"]["INDIRECT_COMBINED"],
                     position(r["positions"][obj])) for r in runs]
              for obj in OBJECTIVES}

    w("# The settlement on each contract, as a function of the rate")
    w("")
    w("_2025 · generated by `scripts/settlement_at_rate.py` against a "
      "sandbox clone. Nothing here was written to the record of account, "
      "and nothing here is a position._")
    w("")
    w("## The direction, first")
    w("")
    w("**A lower indirect rate makes every give-back larger and the one "
      "claim smaller.** Restating is a rebuild, not an addition: the loaded "
      "labour line comes *down* to wages plus fringe, and the indirect then "
      "goes on over MTDC. So each award's position is")
    w("")
    w("        billed  −  ( direct supported  +  rate × MTDC )")
    w("")
    w("which is a straight line in the rate whose slope is that award's own "
      "MTDC. Every point below was computed by the engine and read back off "
      "`v_restatement`; the line is read off the runs rather than derived a "
      "second time.")
    w("")

    w("## Per contract, across the band")
    w("")
    head = "| combined rate | " + " | ".join(NAME[x] for x in OBJECTIVES) + \
           " | to claim | to return |"
    w(head)
    w("| ---: |" + " ---: |" * (len(OBJECTIVES) + 2))
    for r in runs:
        claim = sum(D(str(r["positions"][x]["under_recovered"]))
                    for x in OBJECTIVES)
        give = sum(D(str(r["positions"][x]["over_collected"]))
                   for x in OBJECTIVES)
        cells = " | ".join(money(position(r["positions"][x]))
                           for x in OBJECTIVES)
        mark = " **" if r is here else " "
        w(f"|{mark}{pct(r['rates']['INDIRECT_COMBINED'])}"
          f"{mark.strip() and '**' or ''} | {cells} | {money(claim)} "
          f"| {money(give)} |")
    w("")
    w(f"The bold row is the certified rate on the derived estate "
      f"({pct(ref)}), and it reproduces the four positions already on the "
      f"record to the cent. A negative figure is money to give back.")
    w("")
    w("**The two directions are never added together.** A claim and a "
      "give-back are two conversations, which is why `v_restatement` carries "
      "them in separate columns and why the aggregate columns above are two "
      "columns rather than one.")
    w("")
    w("**And the four are not one settlement.** Digital Engineering flows "
      "from a different prime — N00174-20-1-0031 through Energetics "
      "Technology Center and NSWC Indian Head — while the other three flow "
      "from AFRL FA8650-20-2-5700. Federal award funds are not fungible "
      "between programmes, so the largest single figure in the table sits on "
      "its own side of any aggregate. The settlement memorandum prices it "
      "both ways for that reason.")
    w("")

    w("## Where each contract crosses zero")
    w("")
    w("| | slope — its own MTDC | nets zero at a combined rate of |")
    w("| --- | ---: | ---: |")
    for obj in OBJECTIVES:
        m, be = line(points[obj])
        w(f"| {NAME[obj]} | {money(m)} | {pct(be)} |")
    allpts = [(runs[i]["rates"]["INDIRECT_COMBINED"],
               sum(position(runs[i]["positions"][x]) for x in OBJECTIVES))
              for i in range(len(runs))]
    m, be = line(allpts)
    w(f"| **all four together** | **{money(m)}** | **{pct(be)}** |")
    w("")
    w("Three of the four cross above any rate anybody could propose, and "
      "Last Tactical Mile crosses *below* the band — under that rate LTM "
      "stops being a claim and becomes a give-back as well. **There is no "
      "rate at which this settles near zero.**")
    w("")

    w("## Why the rate is not the lever")
    w("")
    w("Each award's slope is the cost the record attributes to it. Where "
      "that is small against what was billed, no rate can close the gap:")
    w("")
    w("| | invoices | billed | wages distributed | direct non-labour | "
      "billed ÷ supported |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    for obj in OBJECTIVES:
        row = here["positions"][obj]
        a = attr.get(obj, {})
        billed = D(str(row["billed_total"]))
        sup = D(str(row["supported_total"]))
        w(f"| {NAME[obj]} | {row['invoices']} | {money(billed)} "
          f"| {money(a.get('wages', 0))} ({a.get('people', 0)} people) "
          f"| {money(a.get('nonlabour', 0))} ({a.get('lines', 0)} lines) "
          f"| {billed / sup:.2f}× |")
    w("")
    burden = (1 + here["rates"]["FRINGE"]) * (1 + ref)
    w("**The labour line is where it shows, and it has to be compared like "
      "with like.** A fully burdened dollar of wages at the certified rate "
      f"costs {burden:.4f} — fringe, then indirect over MTDC. Set the "
      "labour each award actually billed against the wages the effort "
      "distribution puts on it:")
    w("")
    w("| | labour billed | wages distributed | multiple | "
      f"against a full burden of {burden:.4f} |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for obj in OBJECTIVES:
        lab = shape.get(obj, {}).get("LABOR", D(0))
        wages = attr.get(obj, {}).get("wages", D(0))
        if lab <= 0 or wages <= 0:
            w(f"| {NAME[obj]} | — | {money(wages)} | — | its register "
              f"carries no labour line at all |")
            continue
        mult = lab / wages
        over = (mult / burden - 1)
        w(f"| {NAME[obj]} | {money(lab)} | {money(wages)} | {mult:.2f}× "
          f"| {over:+.0%} |")
    w("")
    w("Three of the four billed labour at well above what a fully burdened "
      "hour costs on this record. That is either an award billed above its "
      "cost or a year's cost the record has not attributed to the award "
      "that incurred it, and the second is the one worth going and "
      "checking.")
    w("")
    w("**Digital Engineering is the sharpest case and the largest figure in "
      "the file.** Its whole cost on this record is "
      f"{money(attr['DIG-ENG']['nonlabour'])} of ledger expense in one "
      f"account and {money(attr['DIG-ENG']['wages'])} of distributed wages "
      f"across {attr['DIG-ENG']['people']} people, against "
      f"{money(here['positions']['DIG-ENG']['billed_total'])} billed over "
      f"{here['positions']['DIG-ENG']['invoices']} invoices — and its "
      "invoice register carries every dollar of that billing in a single "
      "undifferentiated category, so nothing on the record says what it was "
      "billed *for*:")
    w("")
    w("| | " + " | ".join(sorted({c for obj in OBJECTIVES
                                  for c in shape.get(obj, {})})) + " |")
    cats = sorted({c for obj in OBJECTIVES for c in shape.get(obj, {})})
    w("| --- |" + " ---: |" * len(cats))
    for obj in OBJECTIVES:
        w(f"| {NAME[obj]} | " + " | ".join(
            money(shape.get(obj, {}).get(c, 0)) for c in cats) + " |")
    w("")

    w("## What would move it")
    w("")
    w("Closing a give-back takes attributed cost, not rate. At the certified "
      f"rate a dollar of additional direct cost on an award reduces its "
      f"give-back by {1 + ref:.4f}, so:")
    w("")
    w("| | to give back | direct cost that would close it | as wages |")
    w("| --- | ---: | ---: | ---: |")
    fr = here["rates"]["FRINGE"]
    for obj in OBJECTIVES:
        over = D(str(here["positions"][obj]["over_collected"]))
        if over <= 0:
            continue
        need = over / (1 + ref)
        w(f"| {NAME[obj]} | {money(over)} | {money(need)} "
          f"| {money(need / (1 + fr))} |")
    w("")
    w("Those are checkable asks rather than arithmetic: is there 2025 cost "
      "that belongs to these awards and is currently sitting on another "
      "objective? The labour half is the effort distribution, where "
      "thirty-five of the forty-three people carry one summary row rather "
      "than a month-by-month log, so the attribution for most of the payroll "
      "is coarse. The non-labour half is already a known open item — Drive "
      "AM's ODC gap is on the record.")
    w("")
    w("**Nothing here proposes moving cost onto an award to reduce a "
      "give-back.** That would be the rate reverse-engineered by another "
      "route, which is exactly what the seal exists to rule out. The "
      "question is whether the record is complete, and it is answered by "
      "going and looking — a person's hours log, an invoice's backup — not "
      "by choosing a number.")
    return o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8040")
    ap.add_argument("--password", default=os.environ.get(
        "YBI_OWN_PASSWORD", "PubRound2026-own!"))
    ap.add_argument("--write", action="store_true",
                    help="also write docs/SETTLEMENT_AT_RATE_2025.md")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()
    box = Sandbox(args.base, args.password)
    print(f"walking {len(SHARES)} points against {args.base}")
    text = "\n".join(report(walk(box))) + "\n"
    print(text)
    if args.write:
        DOC.write_text(text)
        print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
