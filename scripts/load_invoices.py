#!/usr/bin/env python3
"""Load the three America Makes invoices, as transcribed from the PDFs.

Source: YBI_Invoices_1.pdf — invoices 10023 (Hybrid Phase II), 10018 (Drive
AM) and 10039 (Last Tactical Mile), April 2026. The same transcription the
domain tests run against, so the register and the regression cannot drift
apart.

These are the invoices the restatement is about. Two of the three carry no
indirect line at all; the third carries a flat $3,000 that is 81,772.76 spread
across twenty-seven months rather than a rate applied to a base. The labour
amounts are already burdened — fringe is inside them — which is why the
restatement claims indirect and not unbilled fringe.

    PYTHONPATH=. python3 scripts/load_invoices.py
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal

from app.db import execute, one, open_pool, query, transaction

SOURCE = "YBI_Invoices_1.pdf"
SERVICE_FROM = dt.date(2026, 4, 1)
SERVICE_TO = dt.date(2026, 4, 30)
INVOICE_DATE = dt.date(2026, 5, 1)

#: (number, objective, award, po, bill-to, [(category, amount, description,
#: personnel)])
INVOICES = [
    ("10023", "HYBRID-II", "AM-HYBRID-P2", "", "236 W Boardman Street", [
        ("LABOR", "1374.00", "April 2026 - Labor",
         "Gaffney, Negro, Longo, Jaric, Metzinger"),
        ("TRAVEL", "0.00", "", ""),
        ("ODC", "0.00", "", ""),
        ("CONSULTANT", "0.00", "Rich Lonardo", ""),
    ]),
    ("10018", "DRIVE-AM", None, "20240119", "NCDMM - America Makes", [
        ("LABOR", "18448.11", "DRIVE AM Project - April 2026",
         "Engel, Gaffney, Kale, Negro, Jaric"),
        ("TRAVEL", "0.00", "", ""),
        ("MATERIALS", "0.00", "", ""),
        ("CONSULTANT", "0.00", "", ""),
        ("ODC", "19145.79", "", ""),
    ]),
    ("10039", "LTM", None, "20250018", "NCDMM - America Makes", [
        ("OTHER", "0.00", "Impact 2.0 The Last Tactical Mile - April 2026", ""),
        ("LABOR", "7493.52", "Labor", "Engel, Gaffney"),
        ("TRAVEL", "0.00", "", ""),
        ("MATERIALS", "0.00", "", ""),
        ("CONSULTANT", "8500.00", "", ""),
        ("INDIRECT", "3000.00", "", ""),
    ]),
]

#: The two awards the register did not have.
#:
#: A ceiling is read off the executed agreement or it is left at zero, which
#: the constraint test reads as "no ceiling on file" rather than as a ceiling
#: of nothing. A ceiling invented for convenience is the number a restatement
#: would later be capped against, so the two states are kept apart.
#:
#: Last Tactical Mile sat at zero for longer than it should have. The
#: executed agreement was on file the whole time and nobody had read §4.3 into
#: the record — which is the shape of mistake this system exists to catch, so
#: it is written down here rather than quietly corrected.
AWARDS = [
    # §4.3: "The total funds authorized by this agreement shall not exceed
    # $1,103,594." The clause names no cost share and Schedule B proposes
    # none — while Schedule A expects a 1:1 ratio. That conflict is recorded
    # as a term rather than resolved here; §11.11 says the Agreement governs
    # over a Schedule, which is an argument and not an answer.
    # Made as of 30 January 2024; §10.1 runs the term to 4 January 2026.
    ("AM-DRIVE-AM", "DRIVE-AM", "NCDMM / America Makes",
     "FA8650-20-2-5700", "COOPERATIVE_SUB", 1103594, 0, dt.date(2024, 1, 30),
     dt.date(2026, 1, 4), "DE_MINIMIS_10",
     "§4.3 Total Obligation, Sub-Recipient Agreement made as of "
     "30 January 2024"),
    # §4.3: "The total funds authorized by this agreement shall not exceed
    # $899,500 in federal funding and $513,065 cost share." 27-month period
    # of performance from 24 September 2024.
    ("AM-LTM-PROJ88", "LTM", "NCDMM / America Makes",
     "FA8650-20-2-5700", "COOPERATIVE_SUB", 899500, 513065,
     dt.date(2024, 9, 24), dt.date(2026, 12, 31), "DE_MINIMIS_10",
     "§4.3 Total Obligation, Sub-Recipient Agreement executed "
     "24 September 2024"),
    # The fourth America Makes award, and the one that had no row at all —
    # SRA-0350 ICAM Digital Engineering, executed 5 February 2024, on file
    # since the first document drop. No award means no ceiling, and a
    # restatement is capped against a ceiling, so nothing could be measured
    # for it.
    #
    # It is worded differently from the other three and the citation has to
    # say so. There is no §4.3 here: §9 CONTRACT VALUE AND CONTRACT FUNDING
    # carries it — "This Agreement value is $1,000,690.00. This Agreement
    # funding is $1,000,690.00 … The total funds authorized by this agreement
    # shall not exceed $1,000,690.00." No cost share is named anywhere, and
    # Attachment 3 proposes none.
    #
    # §7: "Date of Award through July 9, 2025", options none. The agreement
    # is effective on NCDMM's signature, dated 5 February 2024.
    #
    # The prime is not the America Makes cooperative agreement the other
    # three flow down from: this one runs through Energetics Technology
    # Center and NSWC Indian Head under Grant N00174-20-1-0031, CFDA 12.300.
    ("AM-ICAM-DIGENG", "DIG-ENG", "NCDMM / Energetics Technology Center",
     "N00174-20-1-0031", "COOPERATIVE_SUB", 1000690, 0,
     dt.date(2024, 2, 5), dt.date(2025, 7, 9), "DE_MINIMIS_10",
     "§9 Contract Value and Contract Funding, Sub-Recipient Agreement "
     "SRA-0350 executed 5 February 2024"),
]


def main() -> int:
    open_pool()

    for (award_id, objective, sponsor, prime, instrument, ceiling,
         cost_share, start, end, method, citation) in AWARDS:
        existing = one("""SELECT ceiling_federal, cost_share_required
                            FROM award WHERE award_id = %s""", (award_id,))
        if existing:
            # A ceiling that has since been read off the agreement is written
            # in. Leaving it at zero because the row already exists is how a
            # placeholder becomes permanent.
            if ceiling and not existing["ceiling_federal"]:
                execute("""UPDATE award SET ceiling_federal = %s,
                                  cost_share_required = %s, citation = %s
                            WHERE award_id = %s""",
                        (ceiling, cost_share or 0, citation, award_id))
                print(f"  ceiling  {award_id} — {ceiling:,} federal, "
                      f"{(cost_share or 0):,} cost share, from {citation}")
            else:
                print(f"  exists   {award_id}")
            continue
        # ceiling_federal is NOT NULL in the schema; 0 records "not yet
        # known", and the constraint test reads it as no ceiling rather than
        # as a ceiling of nothing.
        execute("""INSERT INTO award (award_id, objective_id, sponsor,
                                      prime_agreement, instrument,
                                      ceiling_federal, cost_share_required,
                                      period_start, period_end, rate_method,
                                      citation)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (award_id, objective, sponsor, prime, instrument,
                 ceiling or 0, cost_share or 0, start, end, method, citation))
        print(f"  created  {award_id}")

    loaded = 0
    for number, objective, award_id, po, bill_to, lines in INVOICES:
        if one("SELECT 1 FROM invoice WHERE invoice_number = %s", (number,)):
            print(f"  exists   invoice {number}")
            continue
        total = sum(Decimal(a) for _, a, _, _ in lines)
        indirect = sum(Decimal(a) for c, a, _, _ in lines if c == "INDIRECT")
        with transaction() as cur:
            cur.execute("""INSERT INTO invoice
                             (period, award_id, objective_id, seq,
                              invoice_number, invoice_date, service_from,
                              service_to, po_number, bill_to_name, terms,
                              direct_claimed, indirect_claimed, total, status)
                           VALUES ('2025',%s,%s,%s,%s,%s,%s,%s,%s,%s,'Net 30',
                                   %s,%s,%s,'ISSUED')
                           RETURNING invoice_id""",
                        (award_id, objective, int(number), number,
                         INVOICE_DATE, SERVICE_FROM, SERVICE_TO, po, bill_to,
                         total - indirect, indirect, total))
            invoice_id = cur.fetchone()["invoice_id"]
            for i, (category, amount, description, personnel) in enumerate(lines, 1):
                cur.execute("""INSERT INTO invoice_line
                                 (invoice_id, sequence, category, description,
                                  quantity, rate, amount, personnel)
                               VALUES (%s,%s,%s,%s,1,%s,%s,%s)""",
                            (invoice_id, i, category, description,
                             Decimal(amount), Decimal(amount), personnel))
        loaded += 1
        print(f"  loaded   invoice {number:6} {objective:10} "
              f"{total:>12,.2f}  indirect {indirect:>10,.2f}")

    # An invoice can arrive before its award is registered — the schema makes
    # award_id nullable on purpose, because holding evidence out of the system
    # until the paperwork catches up is the wrong way round. Two of these did:
    # Drive AM and Last Tactical Mile were loaded before their agreements were
    # read into the record, and stayed unlinked afterwards.
    #
    # An auditor could then walk an invoice to its objective and no further,
    # which is one link short of the agreement that authorised the money. So
    # the link is resolved here, after the awards are in, rather than written
    # into the list above — an award that arrives next year gets picked up on
    # the next run instead of needing this file edited.
    #
    # Only where exactly one award covers the objective. Two is ambiguous and
    # a guess at which one authorised an invoice is exactly the kind of
    # inference this system refuses to make elsewhere.
    linked = query("""UPDATE invoice i SET award_id = a.award_id
                        FROM award a
                       WHERE a.objective_id = i.objective_id
                         AND i.award_id IS NULL
                         AND (SELECT count(*) FROM award x
                               WHERE x.objective_id = i.objective_id) = 1
                   RETURNING i.invoice_number, a.award_id""")
    for row in linked:
        print(f"  linked   invoice {row['invoice_number']} -> "
              f"{row['award_id']}")
    orphan = query("""SELECT invoice_number, objective_id FROM invoice
                       WHERE award_id IS NULL ORDER BY invoice_number""")
    for row in orphan:
        print(f"  UNLINKED invoice {row['invoice_number']} on "
              f"{row['objective_id']} — no single award covers that "
              f"objective, so nothing was assumed")

    print(f"\n  {loaded} invoices loaded from {SOURCE}")
    gap = one("""SELECT count(*) AS n,
                        COALESCE(sum(mtdc_as_billed), 0) AS base
                   FROM v_invoice_category
                  WHERE no_indirect_billed AND mtdc_as_billed > 0""")
    if gap and gap["n"]:
        print(f"  {gap['n']} of them bill no indirect at all, on a base of "
              f"${gap['base']:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
