#!/usr/bin/env python3
"""The 2025 America Makes invoices, rebuilt on the negotiated rate.

Thirty-six of them — three contracts, twelve months — rendered onto the face
NCDMM's payables already recognises, so that what comes out of QuickBooks can
be laid beside what the cost record says the month was worth.

**This is a bookmark, not a filing.** Nothing here is written to `invoice`,
which is append-only and which no route in this system creates a row in. The
output is a set of PDFs, a workbook and a table, all of them reproducible from
the record by running this again — which is the point: a fixed artefact to diff
against, whose provenance is a command rather than a memory.

What is restated, and what is not
─────────────────────────────────

Restating is a **rebuild**, not an addition. YBI billed labour at a loaded
rate — $566,821.99 against $320,488.02 of wages and fringe, 1.77x, where the
full burden the sealed classification computes is 1.44x — so the indirect
recovery is already inside the labour line. A restated invoice therefore takes
labour **down** to wages plus fringe before the indirect line goes on. Adding
an indirect line to the labour as billed would claim indirect twice.

Four figures per month, and every one of them is read:

    LABOR      the month's wages for that objective, from `labor_month` over
               `v_labor_effective`. All fourteen person-objective pairs on
               these three contracts have a full twelve-month hours log, so
               this is the log rather than a smear across the calendar.
    FRINGE     at the rate on the record, spread across the months by largest
               remainder against the annual figure.
    DIRECT     the direct non-labour classified to that objective, by
               transaction date.
    INDIRECT   the engine's own recorded `allocation.allocated` for that
               objective, spread across the months by MTDC.

**Nothing here is computed twice.** The indirect is the allocation the rate
computation persisted, distributed — not a rate re-applied to a base rebuilt
in this script, which would be a second derivation free to disagree with the
first. The twelve months add back to the recorded figure to the cent, and the
script refuses to write anything if they do not.

Largest remainder, not per-month rounding, for the same reason migration 069
exists: rounding each month independently drifted one and two cents against
the engine on all three contracts the first time this ran.

The one thing this cannot do
────────────────────────────

**The category split of the non-labour is not on the cost record.** The ledger
carries an account and a payee — `Grant Expenses:LTM Grant`, `Humtown Products`
— and not an invoice category, so nothing here can say whether $5,500 to a
foundry was MATERIALS or CONSULTANT. Guessing it from a payee name would be
inventing a judgment, which is what every other proposal in this system refuses
to do.

So the restated invoice carries the non-labour in **one line**, and says so on
its face. This is exactly the column Monday's QuickBooks export supplies, and
naming it precisely is more use than a plausible guess: the split plugs in, the
totals do not move.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import os
import sys
from collections import defaultdict
from decimal import Decimal as D, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.db import open_pool, query
from app.domain.invoice_document import (DocumentLine, InvoiceDocument, Party,
                                         render)

PERIOD = "2025"
#: Every month of the year. A contract's own span is read from the record in
#: `months_of()` — this is only the outer bound.
ALL_MONTHS = [f"{PERIOD}-{i:02d}" for i in range(1, 13)]

#: The four awards NCDMM administers, in the order the workpapers read them.
#: `face` is the category structure the contract's own invoices carry, read
#: off `invoice_line` for the ones on file — a restated invoice that dropped
#: a category the sponsor's payables expects would not match their file.
#:
#: **Digital Engineering is here and is not an America Makes award.** NCDMM
#: administers it, but the prime flowing down is N00174-20-1-0031 through
#: Energetics Technology Center and NSWC Indian Head, not the AFRL America
#: Makes cooperative agreement FA8650-20-2-5700 the other three sit under.
#: It is restated on the same rate because the rate is YBI's, not the
#: award's; whose money the offset settles against is a separate question
#: and the workpaper keeps it separate.
CONTRACTS = [
    ("DRIVE-AM",  "AM-DRIVE-AM",  "Drive AM",
     "DRIVE AM Project", "Engel, Gaffney, Kale, Negro, Jaric", "20240119"),
    ("LTM",       "AM-LTM",       "Last Tactical Mile",
     "Impact 2.0 The Last Tactical Mile Project", "Engel, Gaffney", "20250018"),
    ("HYBRID-II", "AM-HYBRID-P2", "Hybrid Phase 2",
     "Hybrid Phase II", "Gaffney, Negro, Longo, Jaric, Metzinger", ""),
    ("DIG-ENG",   "AM-ICAM-DIGENG", "Digital Engineering",
     "Digital Engineering (SRA-0350)", "Gaffney, Longo", "20240105"),
]

#: Where each objective's billing sits in the Income section. The ledger is
#: the billing register and its account names are its own.
INCOME_ACCOUNT = {
    "DRIVE-AM":  "3900 Grant Income:Drive AM",
    "LTM":       "3900 Grant Income:Last Tactical Mile",
    "HYBRID-II": "3900 Grant Income:Hybrid Energy",
    "DIG-ENG":   "3900 Grant Income:Digital Engineering",
}

#: Where a 2025 income posting's description says which invoice category it
#: was billed under. The ledger is the billing register — thirty-six monthly
#: postings, each carrying its category in the description — which is the one
#: place YBI's actual 2025 invoicing was recorded. A description matching
#: nothing here is **reported**, not bucketed: a category nobody thought about
#: should be visible.
BILLED_CATEGORY = [
    ("indirect",  "INDIRECT"),
    ("consultant", "CONSULTANT"),
    ("materials", "MATERIALS"),
    ("travel",    "TRAVEL"),
    ("odc",       "ODC"),
    ("labor",     "LABOR"),
]

REMIT_TO = Party(
    name="Youngstown Business Incubator",
    address="241 West Federal Street\nYoungstown, OH 44503",
    detail="UEI E38PN6F4AVU3 · CAGE 5EAR9")

#: Every one of the three invoices on file bills NCDMM. The register holds
#: `236 W Boardman Street` in Hybrid's `bill_to_name` — an address in the name
#: field, which is a transcription artefact and is reported rather than
#: reproduced onto a document YBI would issue.
BILL_TO = Party(name="NCDMM - America Makes",
                address="2000 Technology Drive, Suite 100\nPittsburgh, PA 15219")


def money(x) -> D:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def spread(total: D, weights: dict[str, D]) -> dict[str, D]:
    """Distribute `total` across `weights`, adding back to `total` exactly.

    Floor every share and hand the spare cents to the largest remainders,
    ties broken by key so the answer is deterministic. **`floor` rather than
    `round` is the load-bearing part**: a floor can only be short, so the
    spare is always a non-negative number of cents to hand out, where
    rounding to nearest makes it signed and a negative spare is the shape
    that silently drops a line.
    """
    live = {k: v for k, v in weights.items() if v > 0}
    if not live or total == 0:
        return {k: D("0.00") for k in weights}
    tw = sum(live.values())
    raw = {k: total * v / tw for k, v in live.items()}
    out = {k: v.quantize(D("0.01"), rounding=ROUND_FLOOR) for k, v in raw.items()}
    spare = int(((total - sum(out.values())) / D("0.01")).to_integral_value())
    order = sorted(raw, key=lambda k: (-(raw[k] - out[k]), k))
    for i in range(spare):
        out[order[i % len(order)]] += D("0.01")
    return {k: out.get(k, D("0.00")) for k in weights}


# ── reading the record ────────────────────────────────────────────────

#: Reading goes through `app.db.query` rather than a cursor of this script's
#: own. Not a style preference: `tests/test_sql_is_real.py` hands every
#: literal statement in `app/`, `scripts/` and `tests/` to `PREPARE`, and it
#: finds them by the name of the function they are passed to. A local helper
#: called `q` is invisible to it, so the first draft of this file had six
#: statements the schema had never checked — the one-door rule that
#: `test_no_screen_reaches_past_the_request_layer` holds for the SPA, in a
#: script.
def rates() -> list[dict]:
    rows = query("SELECT kind, rate, admin_labour_basis, seal_hash "
                  "FROM rate WHERE status = 'PROPOSED'")
    if not rows:
        raise SystemExit("No rate stands on the record. Compute one first.")
    return rows


def allocation(objectives) -> dict[str, tuple[D, D]]:
    rows = query(
        "SELECT a.objective_id, a.base_amount, a.allocated "
        "FROM allocation a JOIN rate r USING (rate_id) "
        "WHERE r.kind = 'INDIRECT_COMBINED' AND r.status = 'PROPOSED' "
        "  AND a.objective_id = ANY(%s)", (objectives,))
    return {r["objective_id"]: (money(r["base_amount"]), money(r["allocated"]))
            for r in rows}


def monthly_labour(objectives) -> tuple[dict[str, dict[str, D]], list]:
    """Each person's wages on each objective, placed in the months their
    hours log puts them in. Largest remainder, so a person's twelve
    months add back to what the distribution says they were paid."""
    hrs = defaultdict(dict)
    for r in query(
            "SELECT employee_key, objective_id, "
            "       to_char(month_start,'YYYY-MM') AS mm, adjusted_hours "
            "FROM labor_month WHERE period = %s AND objective_id = ANY(%s)",
            (PERIOD, objectives)):
        hrs[(r["employee_key"], r["objective_id"])][r["mm"]] = D(str(r["adjusted_hours"]))

    out = defaultdict(lambda: defaultdict(lambda: D("0.00")))
    unlogged = []
    for e in query("SELECT employee_key, objective_id, distributed_wages "
                    "FROM v_labor_effective "
                    "WHERE period = %s AND objective_id = ANY(%s)",
                    (PERIOD, objectives)):
        key = (e["employee_key"], e["objective_id"])
        wages = money(e["distributed_wages"])
        if not hrs.get(key):
            unlogged.append((*key, wages))
            continue
        for mm, amt in spread(wages, hrs[key]).items():
            out[e["objective_id"]][mm] += amt
    return out, unlogged


def monthly_nonlabour(objectives) -> dict[str, dict[str, D]]:
    """Direct non-labour cost by objective and month, by transaction date.

    `AND dl.live` is not optional here even though the join to a live
    decision makes it look redundant: a superseded line is still in
    `decision_line`, and a line that joins once per judgment it has ever
    carried multiplies the sum.
    """
    out = defaultdict(lambda: defaultdict(lambda: D("0.00")))
    for r in query(
            "SELECT d.objective_id, to_char(l.txn_date,'YYYY-MM') AS mm, "
            "       sum(l.amount) AS amount "
            "FROM decision d JOIN decision_line dl USING (decision_id) "
            "     JOIN ledger_line l ON l.line_id = dl.line_id "
            "WHERE d.reversed_at IS NULL AND dl.live AND d.pool = 'DIRECT' "
            "  AND d.objective_id = ANY(%s) AND l.period = %s "
            "GROUP BY 1, 2", (objectives, PERIOD)):
        out[r["objective_id"]][r["mm"]] = money(r["amount"])
    return out


def monthly_billed(account_like) -> tuple[dict, list]:
    """What YBI actually billed that month, from the income side.

    `064` took the Income section out of the classification scope, quite
    correctly — grant income is not cost to classify — and taking it out
    of scope became taking it out of mind. It is the only register of the
    2025 invoicing there is.
    """
    out = defaultdict(lambda: defaultdict(lambda: D("0.00")))
    unmatched = []
    for r in query(
            "SELECT to_char(txn_date,'YYYY-MM') AS mm, description, amount "
            "FROM ledger_line WHERE section = 'Income' AND period = %s "
            "  AND account ILIKE %s", (PERIOD, account_like)):
        text = " ".join(str(r["description"]).split()).lower()
        cat = next((c for k, c in BILLED_CATEGORY if k in text), None)
        if cat is None:
            cat = "OTHER"
            if money(r["amount"]) != 0:
                unmatched.append((r["mm"], r["description"], money(r["amount"])))
        out[r["mm"]][cat] += money(r["amount"])
    return out, unmatched


# ── building the thirty-six ───────────────────────────────────────────

def months_of(objectives) -> dict[str, list[str]]:
    """The months each objective was actually worked or billed in.

    Read from the record rather than assumed to be twelve. Digital
    Engineering ran to 9 July 2025 and has seven; the other three have
    twelve. A constant twelve would have rendered five empty invoices for a
    closed award, which says the months were worked and nothing was billed —
    a different statement from the award having ended.
    """
    out = defaultdict(set)
    for r in query("SELECT objective_id, to_char(month_start,'YYYY-MM') AS mm "
                   "FROM labor_month WHERE period = %s AND objective_id = ANY(%s)",
                   (PERIOD, objectives)):
        out[r["objective_id"]].add(r["mm"])
    for r in query(
            "SELECT d.objective_id, to_char(l.txn_date,'YYYY-MM') AS mm "
            "FROM decision d JOIN decision_line dl USING (decision_id) "
            "     JOIN ledger_line l ON l.line_id = dl.line_id "
            "WHERE d.reversed_at IS NULL AND dl.live AND d.pool = 'DIRECT' "
            "  AND d.objective_id = ANY(%s) AND l.period = %s",
            (objectives, PERIOD)):
        out[r["objective_id"]].add(r["mm"])
    for obj, account in INCOME_ACCOUNT.items():
        if obj not in objectives:
            continue
        for r in query("SELECT to_char(txn_date,'YYYY-MM') AS mm FROM ledger_line "
                       "WHERE section = 'Income' AND period = %s AND account = %s",
                       (PERIOD, account)):
            out[obj].add(r["mm"])
    return {o: sorted(out[o]) for o in objectives}


def recorded_position(objectives) -> dict[str, dict]:
    """What the engine recorded, to check this script against.

    `POST /api/restate` measures the **invoice register**; this script
    measures the **Income section of the ledger**, which is the other
    register of the same billing. Both are right and they are not the same
    population, so the two figures can legitimately differ — and a script
    that quietly disagreed with the engine would be the worse of the two
    ways to find that out.
    """
    return {r["objective_id"]: r for r in query(
        "SELECT objective_id, invoices, billed_total, under_recovered, "
        "       over_collected, register_invoices, register_billed "
        "FROM v_restatement WHERE period = %s AND status <> 'SUPERSEDED' "
        "  AND objective_id = ANY(%s)", (PERIOD, objectives))}


def month_span(mm: str) -> tuple[dt.date, dt.date]:
    y, m = (int(x) for x in mm.split("-"))
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def build():
    objectives = [o for o, *_ in CONTRACTS]
    rate_rows = rates()
    rate_of = {r["kind"]: D(str(r["rate"])) for r in rate_rows}
    meta = {r["kind"]: r for r in rate_rows}
    fringe_rate = rate_of["FRINGE"]
    indirect_rate = rate_of["INDIRECT_COMBINED"]
    basis = meta["INDIRECT_COMBINED"]["admin_labour_basis"]

    alloc = allocation(objectives)
    labour, unlogged = monthly_labour(objectives)
    nonlab = monthly_nonlabour(objectives)
    spans = months_of(objectives)

    built = []
    for obj, award, title, project, personnel, po in CONTRACTS:
        MONTHS = spans[obj]
        lab = {mm: labour[obj].get(mm, D("0.00")) for mm in MONTHS}
        nl = {mm: nonlab[obj].get(mm, D("0.00")) for mm in MONTHS}

        annual_fringe = money(sum(lab.values()) * fringe_rate)
        fr = spread(annual_fringe, lab)
        mtdc = {mm: lab[mm] + fr[mm] + nl[mm] for mm in MONTHS}

        base_recorded, allocated = alloc[obj]
        if sum(mtdc.values()) != base_recorded:
            raise SystemExit(
                f"{obj}: the months come to {sum(mtdc.values())} of MTDC and the "
                f"rate was computed over {base_recorded}. The invoices would not "
                f"tie to the rate they carry. Nothing written.")
        ind = spread(allocated, mtdc)

        billed, unmatched = monthly_billed(INCOME_ACCOUNT[obj])

        for mm in MONTHS:
            built.append(dict(
                objective=obj, award=award, title=title, project=project,
                personnel=personnel, po=po, month=mm,
                labour=lab[mm], fringe=fr[mm], nonlabour=nl[mm],
                mtdc=mtdc[mm], indirect=ind[mm],
                total=mtdc[mm] + ind[mm],
                billed=dict(billed.get(mm, {})),
                billed_total=sum(billed.get(mm, {}).values(), D("0.00")),
                unmatched=unmatched))
    return built, dict(fringe=fringe_rate, indirect=indirect_rate, basis=basis,
                       unlogged=unlogged, alloc=alloc)


def document(row, rates) -> InvoiceDocument:
    """One month, on the face NCDMM's payables already recognises.

    The rate lives in the description and **not** in the RATE column. The
    column formats as money to the cent, so 21.90% prints as `0.22` and
    43.99% as `0.44` — a figure that reads as twenty-two cents on a document
    a payables clerk is meant to check. The originals put quantity 1 at a
    rate equal to the whole amount on every line, which is the shape that
    hides a burdened labour rate; matching it and saying the percentage in
    words is both truer to the face and legible.
    """
    start, end = month_span(row["month"])
    issued = end + dt.timedelta(days=1)
    lines = [
        DocumentLine(category="LABOR", amount=row["labour"],
                     description=f"{row['project']} - {start:%B %Y} · direct labour at cost",
                     personnel=row["personnel"]),
        DocumentLine(category="FRINGE", amount=row["fringe"],
                     description=f"Fringe @ {rates['fringe'] * 100:.2f}% of direct "
                                 f"labour ({row['labour']:,.2f})"),
        DocumentLine(category="ODC", amount=row["nonlabour"],
                     description="Direct non-labour cost classified to this "
                                 "objective (category split not on the cost record)"),
        DocumentLine(category="INDIRECT", amount=row["indirect"],
                     description=f"Indirect @ {rates['indirect'] * 100:.2f}% of MTDC "
                                 f"({row['mtdc']:,.2f})"),
    ]
    caveats = [
        "PROPOSED RESTATEMENT — not an invoice YBI has issued. It rebuilds the "
        f"month on the negotiated rate and supersedes what was billed "
        f"({row['billed_total']:,.2f}).",
        "Labour is at cost. The original billed labour at a loaded rate, so the "
        "indirect recovery was already inside it; adding an indirect line to the "
        "labour as billed would claim indirect twice.",
        "The category split of the non-labour is not on the cost record — the "
        "ledger carries an account and a payee, not an invoice category — so it "
        "is one line rather than a guess.",
        "Requires a §4.4 modification changing the basis from the 10% de minimis "
        "to the negotiated rate. Classification is complete and sealed, the rate "
        "is certified, and the 200.465 facilities carve-out has been evaluated "
        "against the estate on the record.",
    ]
    return InvoiceDocument(
        number=f"R-{row['objective']}-{row['month'].replace('-', '')}",
        invoice_date=issued, remit_to=REMIT_TO, bill_to=BILL_TO,
        lines=tuple(lines), total=row["total"], terms="Net 30",
        po_number=row["po"], service_from=start, service_to=end,
        objective=row["objective"], award=row["award"],
        is_original=True, status="RESTATED",
        source_document="Rebuilt from the sealed 2025 classification. "
                        "scripts/restate_2025_invoices.py",
        caveats=tuple(caveats))


# ── the artefact Monday's export gets laid beside ─────────────────────

HEAD = Font(bold=True, color="FFFFFF")
BAND = PatternFill("solid", fgColor="1F3B4D")
BOLD = Font(bold=True)
MONEY = "#,##0.00;[Red](#,##0.00)"

#: The columns QuickBooks cannot fill in from this side, left empty on
#: purpose. **A blank is unanswered, and unanswered is a value** — writing
#: 0.00 into a column nobody has read off the export would make *there was no
#: such line* and *nobody has looked* the same fact.
FROM_QB = ["QB invoice no", "QB invoice date", "QB labor", "QB fringe",
           "QB materials", "QB travel", "QB consultant", "QB ODC",
           "QB indirect", "QB other", "QB total"]


def workbook_of(built, rates, out: Path) -> None:
    """Three sheets: what to read first, the months, and the categories.

    The caveats go on the first sheet above the figures, because a workbook
    travels and the caveat has to travel with it.
    """
    wb = Workbook()

    ws = wb.active
    ws.title = "Read first"
    notes = [
        ("The 2025 America Makes invoices, rebuilt on the negotiated rate", True),
        ("", False),
        (f"Fringe {rates['fringe'] * 100:.2f}% · indirect combined "
         f"{rates['indirect'] * 100:.2f}% on MTDC · administrative labour "
         f"{rates['basis']}. Read from the rate on the record, not recomputed here.",
         False),
        ("", False),
        ("NOTHING HERE HAS BEEN ISSUED. These are proposed restatements. Every "
         "one requires a §4.4 modification changing the basis from the 10% de "
         "minimis to the negotiated rate before it could be sent.", True),
        ("", False),
        ("Restating is a rebuild, not an addition. YBI billed labour at a loaded "
         "rate — $566,821.99 against $320,488.02 of wages and fringe, 1.77x — so "
         "the indirect recovery is already inside the labour line. The restated "
         "labour is at cost. Adding an indirect line to the labour as billed "
         "would claim indirect twice.", False),
        ("", False),
        ("The category split of the restated non-labour is NOT on the cost "
         "record. The ledger carries an account and a payee, not an invoice "
         "category. The QB columns are the ones the export fills in; the totals "
         "do not move when it does.", False),
        ("", False),
        ("The 200.465 facilities carve-out IS in this rate — carve-outs are "
         "recorded against the estate on the record. That estate is derived "
         "from documents rather than measured from floor plans, and the "
         "derivation takes the low side at every choice, so the carve-out is "
         "if anything too small and the rate too high. A measured floor plan "
         "arrived on 15 September 2026 and has not been accepted into the "
         "record; accepting it will move this rate, and the direction the "
         "measurement points is DOWN.", True),
        ("", False),
        ("No one of the 43 people has certified their 2025 effort under 2 CFR "
         "200.430(i). Every restated labour line is the management "
         "reconstruction at 100%.", False),
        ("", False),
        ("Monthly movements are far larger than the annual ones, in both "
         "directions, because billing and cost do not fall in the same month. "
         "Read the year before reading a month.", False),
    ]
    for i, (text, bold) in enumerate(notes, start=1):
        c = ws.cell(row=i, column=1, value=text)
        c.font = BOLD if bold else Font()
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 110

    cols = ["contract", "objective", "award", "month", "invoice",
            "restated labor", "restated fringe", "restated non-labour",
            "restated MTDC", "restated indirect", "restated total",
            "as billed total", "movement"] + FROM_QB
    ws = wb.create_sheet("By month")
    ws.append(cols)
    for i in range(1, len(cols) + 1):
        ws.cell(row=1, column=i).font = HEAD
        ws.cell(row=1, column=i).fill = BAND
    for r in built:
        ws.append([r["title"], r["objective"], r["award"], r["month"],
                   f"R-{r['objective']}-{r['month'].replace('-', '')}",
                   float(r["labour"]), float(r["fringe"]), float(r["nonlabour"]),
                   float(r["mtdc"]), float(r["indirect"]), float(r["total"]),
                   float(r["billed_total"]),
                   float(r["total"] - r["billed_total"])])
    for i in range(6, 14):
        for c in ws[get_column_letter(i)][1:]:
            c.number_format = MONEY
    for i, w in enumerate([20, 11, 14, 9, 20] + [15] * 8 + [15] * len(FROM_QB), start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "E2"

    ws = wb.create_sheet("As billed by category")
    cats = ["LABOR", "FRINGE", "MATERIALS", "TRAVEL", "CONSULTANT", "ODC",
            "INDIRECT", "OTHER"]
    ws.append(["contract", "month"] + cats + ["billed total"])
    for i in range(1, len(cats) + 4):
        ws.cell(row=1, column=i).font = HEAD
        ws.cell(row=1, column=i).fill = BAND
    for r in built:
        ws.append([r["title"], r["month"]]
                  + [float(r["billed"].get(c, D("0.00"))) for c in cats]
                  + [float(r["billed_total"])])
    for i in range(3, len(cats) + 4):
        for c in ws[get_column_letter(i)][1:]:
            c.number_format = MONEY
    ws.column_dimensions["A"].width = 20
    ws.freeze_panes = "C2"

    wb.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/restated-2025",
                    help="where the rendered invoices go")
    ap.add_argument("--no-render", action="store_true",
                    help="figures and manifest only, no PDFs")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()
    built, rates = build()

    if rates["unlogged"]:
        print("Labour with no monthly hours log — spread would be a smear:")
        for k, o, w in rates["unlogged"]:
            print(f"  {k} on {o}: {w}")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for row in built:
        doc = document(row, rates)
        name = f"{doc.number}.pdf"
        if not args.no_render:
            pdf = render(doc)
            (out / name).write_bytes(pdf)
            digest = hashlib.sha256(pdf).hexdigest()
        else:
            digest = ""
        manifest.append((name, row, digest))

    print(f"{len(manifest)} restated invoices"
          f"{'' if args.no_render else f' rendered to {out}'}")
    print(f"rate on the record: fringe {rates['fringe'] * 100:.2f}%  "
          f"indirect {rates['indirect'] * 100:.2f}%  "
          f"admin labour {rates['basis']}\n")

    hdr = (f"{'contract':20}{'month':9}{'labour':>11}{'fringe':>10}"
           f"{'non-lab':>12}{'indirect':>11}{'restated':>12}{'as billed':>12}{'movement':>12}")
    print(hdr)
    grand = [D("0.00")] * 3
    for obj, award, title, *_ in CONTRACTS:
        rows = [r for r in built if r["objective"] == obj]
        t = [D("0.00")] * 6
        for r in rows:
            mv = r["total"] - r["billed_total"]
            print(f"{title:20}{r['month']:9}{r['labour']:>11}{r['fringe']:>10}"
                  f"{r['nonlabour']:>12}{r['indirect']:>11}{r['total']:>12}"
                  f"{r['billed_total']:>12}{mv:>12}")
            for i, v in enumerate([r["labour"], r["fringe"], r["nonlabour"],
                                   r["indirect"], r["total"], r["billed_total"]]):
                t[i] += v
        print(f"{title + ' TOTAL':20}{'':9}{t[0]:>11}{t[1]:>10}{t[2]:>12}"
              f"{t[3]:>11}{t[4]:>12}{t[5]:>12}{t[4] - t[5]:>12}\n")
        grand = [grand[0] + t[4], grand[1] + t[5], grand[2] + t[4] - t[5]]
    print(f"{'ALL FOUR':20}{'':9}{'':11}{'':10}{'':12}{'':11}"
          f"{grand[0]:>12}{grand[1]:>12}{grand[2]:>12}")

    # Against the engine's own recorded position. The two read different
    # registers, so this is a comparison and not an assertion.
    recorded = recorded_position([o for o, *_ in CONTRACTS])
    print(f"\n{'':20}{'this script':>16}{'the restatement':>18}{'difference':>14}")
    for obj, award, title, *_ in CONTRACTS:
        mine = sum((r["total"] - r["billed_total"]
                    for r in built if r["objective"] == obj), D("0.00"))
        rec = recorded.get(obj)
        if rec is None:
            print(f"{title:20}{mine:>16}{'not restated':>18}{'':>14}")
            continue
        theirs = money(rec["under_recovered"]) - money(rec["over_collected"])
        d = mine - theirs
        print(f"{title:20}{mine:>16}{theirs:>18}{d:>14}"
              f"{'' if d == 0 else '   <- the two registers differ'}")
    off = [(t, o) for o, a, t, *_ in CONTRACTS
           if o in recorded
           and sum((r["total"] - r["billed_total"]
                    for r in built if r["objective"] == o), D("0.00"))
           != money(recorded[o]["under_recovered"]) - money(recorded[o]["over_collected"])]
    if off:
        print("\nWhere they differ, the ledger's Income section carries billing "
              "the invoice register does not.\nThat difference is "
              "`v_invoice_income_tie`, which reports it by name rather than "
              "netting it.")
        for title, obj in off:
            r = recorded[obj]
            print(f"  {title}: the ledger has {sum((x['billed_total'] for x in built if x['objective']==obj), D('0.00')):,.2f} "
                  f"and the invoice register {money(r['billed_total']):,.2f} "
                  f"over {r['register_invoices']} invoices")

    unmatched = [u for r in built for u in r["unmatched"]]
    if unmatched:
        print("\nIncome postings whose description names no invoice category:")
        for mm, desc, amt in sorted(set(unmatched)):
            print(f"  {mm}  {amt:>12}  {' '.join(str(desc).split())[:70]}")

    book = out / "YBI-2025-AM-restated-invoices.xlsx"
    workbook_of(built, rates, book)
    print(f"\nworkbook: {book}")

    if not args.no_render:
        lines = ["# Restated 2025 invoices — manifest",
                 "",
                 "Rendering is deterministic (`invariant=1`), so these digests",
                 "reproduce from the same record. A digest that moves means a",
                 "figure moved.",
                 "",
                 "| invoice | month | total | sha256 |",
                 "| --- | --- | ---: | --- |"]
        for name, row, digest in manifest:
            lines.append(f"| {name} | {row['month']} | {row['total']:,.2f} "
                         f"| `{digest[:16]}` |")
        (out / "MANIFEST.md").write_text("\n".join(lines) + "\n")
        print(f"\nmanifest: {out / 'MANIFEST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
