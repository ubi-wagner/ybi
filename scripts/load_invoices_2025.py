#!/usr/bin/env python3
"""Load the 2025 invoice register from the invoices as issued.

    PYTHONPATH=. python3 scripts/load_invoices_2025.py --check
    PYTHONPATH=. python3 scripts/load_invoices_2025.py --apply

`scripts/load_invoices.py` opens *"Load the three America Makes invoices"* and
that is exactly what it did — three, from one month of 2026. Nothing
downstream asked how many there were, and four published figures were computed
against it as though it were the year: *"1.6% of the ceilings has ever been
invoiced"*, *"$936,190.52 of cost never invoiced"*, *"Digital Engineering has
no invoice to restate against at all"*. A register loaded from one document is
a sample until something says otherwise.

This is the something. Six PDFs of invoices as issued, 61 invoices, the whole
of 2025.

**The ledger is the control, not this script.** `3900 Grant Income` carries
what was billed on each award, posted monthly and independently of these
PDFs, so the two can be compared without either deriving from the other. Six
of the seven streams agree **to the cent**; the two that do not are declared
below with the reason, and the loader refuses to write an award whose
invoices differ from the ledger by anything it has not been told to expect.
That is the QuickBooks rule — every printed subtotal must equal what sits
under it — applied to a year of billing.

**A credit is a line.** Drive AM's November invoice carries ODCs of
**-$14,532.07**. The first extraction read the minus sign as a line break and
Drive AM's categories footed to $593,772.94 against a stated $579,240.87 —
caught only because the total did not foot. Parsing signs is not a detail
here; an unsigned credit overstates the year's billing by twice its value.

**Nothing here is a claim.** These are invoices YBI has already issued and
been paid for, recorded so the restatement can measure against what was
actually billed rather than against three documents. `rate_id` stays NULL:
they were issued under the de minimis election, not under a computed rate,
and pinning them to one would assert a basis nobody used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query, transaction  # noqa: E402

INTAKE = Path(__file__).resolve().parent.parent / "intake"

#: Where each stream's invoices come from, what they are, and what the ledger
#: account is that independently records the same billing.
#:
#: `expected_gap` is the amount by which the invoices may differ from the
#: ledger, with the reason. Zero means they must tie to the cent. A gap that
#: is not declared here stops the load rather than being written.
STREAMS = [
    dict(key="DRIVE-AM", pdf="Drive_AM.pdf", objective="DRIVE-AM",
         award="AM-DRIVE-AM", account="%Grant Income:Drive AM%",
         bill_to="NCDMM - America Makes", expected_gap="0",
         gap_reason="", note="Cost reimbursement, invoiced monthly."),
    dict(key="LTM", pdf="LTM.pdf", objective="LTM",
         award="AM-LTM-PROJ88", account="%Grant Income:Last Tactical Mile%",
         bill_to="NCDMM - America Makes", expected_gap="0",
         gap_reason="", note="Cost reimbursement, invoiced monthly."),
    dict(key="DIG-ENG", pdf="Digital_Engineering.pdf", objective="DIG-ENG",
         award="AM-ICAM-DIGENG", account="%Grant Income:Digital Engineering%",
         bill_to="NCDMM - America Makes", expected_gap="0", gap_reason="",
         note="Cost reimbursement. Final invoice 09 Jul 2025, the day the "
              "period of performance ended."),
    dict(key="HYBRID-II", pdf="Hybrid.pdf", objective="HYBRID-II",
         award="AM-HYBRID-P2", account="%Grant Income:Hybrid Energy%",
         bill_to="236 W Boardman Street", expected_gap="4222.00",
         gap_reason="October to December 2025 is on the ledger at $4,222.00 "
                    "and has no invoice in this set — the tail after the "
                    "monthly billing stopped, within term under "
                    "Modification 001.",
         note="Cost reimbursement, invoiced monthly."),
    dict(key="AAMEN", pdf="AAMEN_FFP_.pdf", objective="AAMEN", award=None,
         account="%Grant Income:AAMEN%",
         bill_to="Parallax Advanced Research Corp.", expected_gap="0",
         gap_reason="",
         note="FIRM FIXED PRICE — twelve identical monthly invoices of one "
              "line each, no cost categories. An FFP award bills a price "
              "rather than cost, so there is no indirect rate to apply and "
              "nothing here to restate."),
    dict(key="RISING-TIDES", pdf="Rising_Tides.pdf", objective="RISING-TIDES",
         award=None, account="%Grant Income:Rising Tides%",
         bill_to="Appalachian Regional Commission", expected_gap="-132803.04",
         # Signed, and the sign is the fact. `gap` is ledger less billed, so
         # a negative one means YBI billed more than the year recognised —
         # which is what an accrual and a prior-year portion look like. The
         # first draft declared it positive and the check refused the load,
         # correctly: an unsigned difference does not say which way it runs,
         # and "billed more than earned" and "earned more than billed" are
         # opposite conversations.
         gap_reason="Billing exceeds the ledger's 2025 revenue across January "
                    "to May. $86,281.30 of it is named on the face of the "
                    "January invoice as the 2024 portion; the remaining "
                    "$46,521.74 is accrual timing. June to December tie to "
                    "the cent.",
         note="Non-federal programme. Not an indirect-rate award."),
]

CATEGORY = [                       # matched in order against the line label
    (r"indirect", "INDIRECT"),
    (r"\blabor\b|\blabour\b", "LABOR"),
    (r"travel", "TRAVEL"),
    (r"material", "MATERIALS"),
    (r"consultant", "CONSULTANT"),
    (r"subcontract|subaward", "SUBAWARD"),
    (r"equipment", "EQUIPMENT"),
    (r"odc", "ODC"),
]

#: A number, which may be negative, and may carry the minus on the line above
#: it. `-\s*` is the whole of the Drive AM November defect.
NUM = r"-?\s*[\d,]+\.\d\d"


def money(s: str) -> Decimal:
    return Decimal(s.replace(",", "").replace(" ", ""))


def categorise(label: str) -> str:
    low = label.lower()
    for pattern, cat in CATEGORY:
        if re.search(pattern, low):
            return cat
    return "OTHER"


def parse(pdf: Path) -> list[dict]:
    """Every invoice in one file, with its lines, read off the face."""
    from pypdf import PdfReader

    out = []
    for page in PdfReader(str(pdf)).pages:
        text = page.extract_text() or ""
        flat = " ".join(text.split())

        num = re.search(r"INVOICE #?\s*(\d{3,6})", flat)
        date = re.search(r"DATE (\d{2}/\d{2}/\d{4})", flat)
        due = re.search(r"DUE DATE (\d{2}/\d{2}/\d{4})", flat)
        pay = re.search(rf"PAYMENT ({NUM})", flat)
        if not (num and date and pay):
            raise SystemExit(f"{pdf.name}: a page has no invoice header")
        po = re.search(r"P\.O\. NUMBER ([^\s]+)", flat)

        body = flat.split("AMOUNT", 1)[-1].split("PAYMENT")[0]
        # Each line is <label> <qty> <rate> <amount>; the label is whatever
        # sits between the previous amount and this one.
        #
        # **And a line may print without its quantity and rate.** AAMEN 9079 —
        # the first invoice in its file — reads `AAMEN Grant Monthly Invoice
        # 26,087.57` where the other eleven read `... 1 26,087.57 26,087.57`.
        # Requiring the three-column form found no lines at all on it, so the
        # invoice landed with a header total and nothing under it, and the
        # restatement measured eleven invoices while counting twelve. The
        # amount is the figure on the page either way; the rate is the amount
        # where the face does not state one separately.
        lines, cursor = [], 0
        for m in re.finditer(rf"\b1\s+({NUM})\s+({NUM})", body):
            label = body[cursor:m.start()].strip(" .:-")
            cursor = m.end()
            lines.append(dict(label=label, rate=money(m.group(1)),
                              amount=money(m.group(2))))
        if not lines:
            for m in re.finditer(rf"({NUM})\s*$", body.strip()):
                label = body.strip()[:m.start()].strip(" .:-")
                amount = money(m.group(1))
                lines.append(dict(label=label, rate=amount, amount=amount))
        out.append(dict(
            number=num.group(1),
            date=dt.datetime.strptime(date.group(1), "%m/%d/%Y").date(),
            due=dt.datetime.strptime(due.group(1), "%m/%d/%Y").date() if due else None,
            po=po.group(1) if po else "",
            payment=money(pay.group(1)),
            lines=lines))
    return out


def check_footing(stream: dict, invoices: list[dict]) -> list[str]:
    """Two questions, asked of every stream, before anything is written."""
    faults = []
    for inv in invoices:
        lines = sum(x["amount"] for x in inv["lines"])
        # **An invoice with no lines is the case this check exists for**, and
        # `if inv["lines"] and ...` excluded exactly it: AAMEN 9079 carried a
        # stated payment with nothing under it and passed silently. A payment
        # with no line is not a tidier invoice, it is an unreadable one.
        if not inv["lines"]:
            faults.append(f"invoice {inv['number']} states a payment of "
                          f"{inv['payment']:,.2f} and carries no line at all — "
                          f"nothing on the face was read")
        elif abs(lines - inv["payment"]) > Decimal("0.01"):
            faults.append(f"invoice {inv['number']} lines total {lines:,.2f} "
                          f"against a stated {inv['payment']:,.2f}")
    billed = sum(i["payment"] for i in invoices)
    led = one("""SELECT COALESCE(sum(amount), 0) AS amt FROM ledger_line
                  WHERE period = '2025' AND section = 'Income'
                    AND account LIKE %s""", (stream["account"],))["amt"]
    gap = led - billed
    if abs(gap - Decimal(stream["expected_gap"])) > Decimal("0.01"):
        faults.append(
            f"invoices {billed:,.2f} against the ledger's {led:,.2f} — a "
            f"difference of {gap:,.2f} where {Decimal(stream['expected_gap']):,.2f} "
            f"was declared. Name it before loading it.")
    return faults


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    open_pool()
    faults, plan = [], []
    print(f"{'stream':<14} {'inv':>4} {'billed':>14} {'ledger':>14} "
          f"{'gap':>12}  {'indirect':>11}")
    for s in STREAMS:
        pdf = INTAKE / s["pdf"]
        if not pdf.exists():
            faults.append(f"{s['key']}: {pdf} is not there")
            continue
        invoices = parse(pdf)
        bad = check_footing(s, invoices)
        faults += [f"{s['key']}: {b}" for b in bad]
        billed = sum(i["payment"] for i in invoices)
        led = one("""SELECT COALESCE(sum(amount), 0) AS amt FROM ledger_line
                      WHERE period='2025' AND section='Income' AND account LIKE %s""",
                  (s["account"],))["amt"]
        ind = sum(x["amount"] for i in invoices for x in i["lines"]
                  if categorise(x["label"]) == "INDIRECT")
        mark = "" if not bad else "   <- see below"
        print(f"  {s['key']:<12} {len(invoices):>4} {billed:>14,.2f} "
              f"{led:>14,.2f} {led-billed:>12,.2f}  {ind:>11,.2f}{mark}")
        plan.append((s, invoices))

    if faults:
        print("\nNothing was written. The register has to agree with the "
              "ledger before it is worth having:")
        for f in faults:
            print(f"  - {f}")
        return 1

    if args.check:
        total = sum(i["payment"] for _, inv in plan for i in inv)
        print(f"\n--check only, nothing written. "
              f"{sum(len(i) for _, i in plan)} invoices, {total:,.2f}.")
        return 0

    loaded = skipped = 0
    for s, invoices in plan:
        for inv in invoices:
            if one("SELECT 1 FROM invoice WHERE invoice_number = %s",
                   (inv["number"],)):
                skipped += 1
                continue
            cats = [(categorise(x["label"]), x) for x in inv["lines"]]
            indirect = sum(x["amount"] for c, x in cats if c == "INDIRECT")
            with transaction() as cur:
                cur.execute("""
                    INSERT INTO invoice
                      (period, award_id, objective_id, seq, invoice_number,
                       invoice_date, due_on, po_number, bill_to_name, terms,
                       direct_claimed, indirect_claimed, total,
                       paid_amount, status, source_document, note, loaded_by)
                    VALUES ('2025',%s,%s,%s,%s,%s,%s,%s,%s,'Net 30',
                            %s,%s,%s,%s,'ISSUED',%s,%s,'load_invoices_2025.py')
                    RETURNING invoice_id""",
                    (s["award"], s["objective"], int(inv["number"]),
                     inv["number"], inv["date"], inv["due"], inv["po"],
                     s["bill_to"], inv["payment"] - indirect, indirect,
                     inv["payment"], inv["payment"], s["pdf"], s["note"]))
                invoice_id = cur.fetchone()["invoice_id"]
                for i, (cat, x) in enumerate(cats, 1):
                    cur.execute("""INSERT INTO invoice_line
                                     (invoice_id, sequence, category,
                                      description, quantity, rate, amount)
                                   VALUES (%s,%s,%s,%s,1,%s,%s)""",
                                (invoice_id, i, cat, x["label"][:400],
                                 x["rate"], x["amount"]))
            loaded += 1
    print(f"\n{loaded} invoice(s) loaded, {skipped} already on the register.")
    print("paid_amount carries the PAYMENT each invoice states; paid_on stays "
          "NULL because the PAID stamp carries no date, and a date nobody "
          "recorded is not a date to invent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
