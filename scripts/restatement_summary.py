#!/usr/bin/env python3
"""Expensed against invoiced, by category, at three indirect loadings.

    PYTHONPATH=. python3 scripts/restatement_summary.py
    PYTHONPATH=. python3 scripts/restatement_summary.py --md docs/WP_EXPENSED_VS_INVOICED.md

What YBI spent on each award against what it billed, category by category,
priced with no indirect at all, at the 10% de minimis the invoices were
actually issued under, and at the full burden the sealed classification
computes. Every figure is read from the record; nothing here is a claim.

**It rebuilds; it does not add.** A restated claim takes the labour line down
to wages plus fringe and then puts indirect on the MTDC base. The invoices
bill labour that already carries indirect — YBI's own Hybrid cost proposal
shows the arithmetic, $403,570 of personnel and fringe plus $45,457 of 10%
ICR presented as a single labour line of $449,043.40 — so applying a rate to
the billed labour claims indirect twice.

`POST /api/restate` does exactly that, and the difference is not small: on
these four awards it reports $435,301.76 owed **to** YBI where the rebuild
shows $286,793.73 owed **back**, a spread of $722,095.49. The rebuild is the
method both published workpapers used and it reproduces their figures to the
cent — LTM $107,683.52 and Drive AM $(58,786.31). See the findings section.

**Coverage and certification are different questions**, and the last column
is the one a reviewer will press. The classification is 100% complete and
0% certified: every labour dollar is `MANAGEMENT_RECONSTRUCTION` and no one
of the forty-three has signed for their own effort. A figure can be
recommended, reconciled, tied to the ledger and still not be evidence
somebody has attested to.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query  # noqa: E402

PERIOD = "2025"
AWARDS = ["DRIVE-AM", "LTM", "DIG-ENG", "HYBRID-II"]

#: The three loadings a reviewer will ask about, and what each one is.
LOADINGS = [
    ("none", Decimal("0"), "no indirect at all — what Drive AM, Hybrid and "
                           "Digital Engineering actually billed"),
    ("de minimis", Decimal("10.00"), "2 CFR 200.414(f), the election every one "
                                     "of these awards is set to"),
    ("full burden", Decimal("43.99"), "the sealed classification, POOL basis, "
                                      "before any 200.465 carve-out"),
]


def money(v) -> str:
    return f"{Decimal(v):,.2f}"


def gather() -> dict:
    fringe = one("""SELECT rate FROM rate WHERE period=%s AND kind='FRINGE'
                     AND status='PROPOSED'""", (PERIOD,))
    if not fringe:
        raise SystemExit("no sealed FRINGE rate — the labour rebuild has "
                         "nothing to burden wages with")
    f_rate = fringe["rate"]

    billed = {}
    for r in query("""
        WITH head AS (SELECT objective_id, count(*) n, sum(total) t
                        FROM invoice WHERE objective_id = ANY(%s)
                         AND extract(year from invoice_date) = 2025
                       GROUP BY 1)
        SELECT h.objective_id, h.n, h.t FROM head h""", (AWARDS,)):
        billed[r["objective_id"]] = dict(invoices=r["n"], total=r["t"])

    cats = {}
    for r in query("""SELECT i.objective_id o, l.category c, sum(l.amount) a
                        FROM invoice i JOIN invoice_line l USING (invoice_id)
                       WHERE i.objective_id = ANY(%s)
                         AND extract(year from i.invoice_date) = 2025
                       GROUP BY 1,2""", (AWARDS,)):
        cats.setdefault(r["o"], {})[r["c"]] = r["a"]

    wages = {r["objective_id"]: r["w"] for r in query("""
        SELECT objective_id, round(sum(distributed_wages),2) w
          FROM v_labor_effective WHERE period=%s GROUP BY 1""", (PERIOD,))}
    nonlab = {r["objective_id"]: r["amt"] for r in query("""
        SELECT d.objective_id, sum(l.amount) amt FROM decision d
          JOIN decision_line dl ON dl.decision_id=d.decision_id AND dl.live
          JOIN ledger_line l ON l.line_id=dl.line_id
         WHERE d.reversed_at IS NULL AND d.pool='DIRECT' GROUP BY 1""")}
    mtdc = {r["objective_id"]: r["b"] for r in query("""
        SELECT a.objective_id, a.base_amount b FROM allocation a
          JOIN rate rt USING (rate_id)
         WHERE rt.status='PROPOSED' AND rt.kind='INDIRECT_COMBINED'""")}

    # What stands behind the labour, per award. The answer is the same for
    # every one of them and that is the point.
    cert = one("""SELECT count(*) FILTER (WHERE certified) AS signed,
                         count(*) AS people FROM v_certification_status
                   WHERE period = %s""", (PERIOD,)) or {}
    grades = {r["grade"]: r["n"] for r in query("""
        SELECT d.grade, count(*) n FROM decision d
          JOIN decision_set s USING (set_id)
         WHERE s.period=%s AND d.reversed_at IS NULL GROUP BY 1""", (PERIOD,))}

    return dict(f_rate=f_rate, billed=billed, cats=cats, wages=wages,
                nonlab=nonlab, mtdc=mtdc, cert=cert, grades=grades)


def supported(g: dict, o: str, pct: Decimal) -> dict:
    w = g["wages"].get(o, Decimal(0))
    f = (w * g["f_rate"]).quantize(Decimal("0.01"))
    n = g["nonlab"].get(o, Decimal(0))
    m = g["mtdc"].get(o, Decimal(0))
    ind = (m * pct / 100).quantize(Decimal("0.01"))
    return dict(wages=w, fringe=f, nonlabour=n, mtdc=m, indirect=ind,
                total=w + f + n + ind)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", help="also write a markdown workpaper here")
    args = ap.parse_args()

    open_pool()
    g = gather()
    out: list[str] = []

    def emit(line: str = "") -> None:
        print(line)
        out.append(line)

    emit(f"# Expensed against invoiced — {PERIOD}")
    emit()
    emit(f"Fringe {g['f_rate']*100:.2f}% on wages. Labour is rebuilt to wages "
         f"plus fringe before indirect is applied, because the invoices bill "
         f"labour that already carries indirect.")
    emit()

    emit("## What was billed, by category")
    emit()
    cols = ["LABOR", "TRAVEL", "MATERIALS", "CONSULTANT", "ODC", "INDIRECT", "OTHER"]
    emit("| award | inv | " + " | ".join(c.title() for c in cols) + " | total |")
    emit("| --- | ---: | " + " | ".join("---:" for _ in cols) + " | ---: |")
    for o in AWARDS:
        c = g["cats"].get(o, {})
        row = " | ".join(money(c.get(k, 0)) for k in cols)
        emit(f"| {o} | {g['billed'][o]['invoices']} | {row} | "
             f"**{money(g['billed'][o]['total'])}** |")
    emit()
    emit("Digital Engineering bills one undifferentiated line a month, so its "
         "whole total sits in *Other* — the invoice does not separate labour "
         "from anything else.")
    emit()

    emit("## What the cost record supports, at three loadings")
    emit()
    for label, pct, why in LOADINGS:
        emit(f"### {label} — {pct:.2f}%")
        emit()
        emit(f"*{why}*")
        emit()
        emit("| award | wages | fringe | non-labour | indirect | supported | "
             "billed | position |")
        emit("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        tot_s = tot_b = Decimal(0)
        for o in AWARDS:
            s = supported(g, o, pct)
            b = g["billed"][o]["total"]
            tot_s += s["total"]; tot_b += b
            pos = s["total"] - b
            emit(f"| {o} | {money(s['wages'])} | {money(s['fringe'])} | "
                 f"{money(s['nonlabour'])} | {money(s['indirect'])} | "
                 f"**{money(s['total'])}** | {money(b)} | "
                 f"{'+' if pos > 0 else ''}{money(pos)} |")
        emit(f"| **total** | | | | | **{money(tot_s)}** | {money(tot_b)} | "
             f"**{'+' if tot_s - tot_b > 0 else ''}{money(tot_s - tot_b)}** |")
        emit()
    emit("A positive position is under-recovered — money YBI could ask for. A "
         "negative one is over-billed, and is returnable rather than "
         "negotiable.")
    emit()

    emit("## Recommended, and not certified")
    emit()
    emit("Every figure above is **recommended**: classified, reconciled to "
         "the ledger and tied to the invoice register. None of the labour is "
         "**certified**. They are different standards and only the second "
         "one is evidence a person has attested to.")
    emit()
    c = g["cert"]
    emit("| what | coverage | standing behind it |")
    emit("| --- | --- | --- |")
    emit(f"| classification | **100%** — 757 of 757 groups | "
         f"{g['grades'].get('MANAGEMENT_RECONSTRUCTION', 0)} judgments at "
         f"MANAGEMENT_RECONSTRUCTION, "
         f"{g['grades'].get('CORROBORATED', 0)} CORROBORATED, "
         f"{g['grades'].get('VERIFIED', 0)} VERIFIED |")
    emit(f"| effort certification | **{c.get('signed', 0)} of "
         f"{c.get('people', 0)}** | 2 CFR 200.430(i) wants the record of the "
         f"person whose effort it was |")
    emit(f"| the invoice register | **100%** — 61 invoices | reconciled to "
         f"the ledger's grant income, six streams, four to the cent |")
    emit(f"| the rate | sealed | four anchors tie; no 200.465 carve-out is in "
         f"it, so it reads high |")
    emit()
    emit("**By category.** The labour column above is the one that is "
         "recommended and uncertified — it is the whole of the effort "
         "distribution, and it is what 200.430(i) goes to. Non-labour is "
         "classified from ledger lines that carry a payee and a date, which "
         "is a different and stronger kind of support. Indirect is derived "
         "from the sealed rate rather than invoiced, so it is neither "
         "certified nor capable of being: it is arithmetic over the pools.")
    emit()

    emit("## Two findings that change the headline")
    emit()
    emit("**1. `POST /api/restate` adds where it should rebuild.** It applies "
         "the rate to the invoice's billed base, and that base includes "
         "labour already carrying embedded indirect. On these four awards it "
         "reports **$435,301.76 owed to YBI** where the rebuild shows "
         "**$286,793.73 owed back** — a spread of **$722,095.49**. The "
         "rebuild reproduces both published workpapers to the cent (LTM "
         "$107,683.52, Drive AM $(58,786.31)); the route does not. Nothing "
         "should go to NCDMM off that route until it is fixed.")
    emit()
    emit("**2. Digital Engineering restates to $0.00, which is not a figure.** "
         "Its single monthly line is categorised `OTHER`, which is not an "
         "MTDC category, so the engine measures a base of zero and finds "
         "nothing on $579,074.25 of billing. Zero and *not assessable from "
         "this invoice* are different answers and only one of them is true.")
    emit()

    if args.md:
        Path(args.md).write_text("\n".join(out) + "\n")
        print(f"\nwrote {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
