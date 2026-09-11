#!/usr/bin/env python3
"""The budget schedules, as read off the signed agreements.

Only what has actually been read. Drive AM's Schedule B is transcribed in
full below because the executed agreement is on file and the page was read
line by line. The other three awards have their totals and their indirect
provision recorded as terms, but nobody has transcribed their category
breakdown — so nothing is recorded for them, and
`v_invoice_budget_check.evaluable` reports NO DATA rather than passing.

That distinction is the point of the table. A category present at zero was
named in the schedule with nothing against it; a category absent was not in
the schedule at all; and an award with no rows has simply not been read. An
invoice format that mirrors the budget cannot be checked against a budget
somebody assumed.

    PYTHONPATH=. python3 scripts/load_award_budgets.py
"""

from __future__ import annotations

import sys
from decimal import Decimal

from app.db import execute, one, open_pool, query

#: Schedule B, Drive AM. "DriveAM with UTEP and Tailored Alloys 24 month
#: budget", seven categories, federal funding only.
#:
#: SUBCONTRACT and EQUIPMENT are here at zero on purpose. They were named in
#: the schedule with nothing against them, which is why they do not appear on
#: invoice 10018 — and recording them is what lets the system tell "budgeted
#: at nothing" apart from "not in the budget".
#:
#: There is no INDIRECT row because Schedule B has no indirect line. That
#: absence is the finding: $583,594 of labour with no provision for indirect
#: of any kind, not a reduced rate and not a de minimis election.
DRIVE_AM = [
    ("LABOR",      "583594", ""),
    ("TRAVEL",      "40000", ""),
    # Schedule B calls this SUBCONTRACT; the register's enum calls it
    # SUBAWARD, and the invoice prints "Subcontract" for it. The schedule's
    # word is what a reader of the agreement sees, so it is kept in the note
    # rather than lost in a translation nobody recorded.
    ("SUBAWARD",        "0", "Schedule B names this SUBCONTRACT, at zero."),
    ("MATERIALS",    "5000", ""),
    ("EQUIPMENT",       "0", "Named in the schedule with nothing against it."),
    ("CONSULTANT",  "60000", ""),
    ("ODC",        "415000", ""),
]

#: (award, citation, note, lines)
BUDGETS = [
    ("AM-DRIVE-AM",
     "Schedule B, Budget — Sub-Recipient Agreement made as of 30 January 2024",
     "Federal funding only. TOTAL PROPOSED COST SHARE is zero on the same "
     "page, which is the reading Schedule A contradicts.",
     DRIVE_AM),
]


def main() -> int:
    open_pool()
    total_written = 0

    for award_id, citation, note, lines in BUDGETS:
        if not one("SELECT 1 FROM award WHERE award_id = %s", (award_id,)):
            print(f"  NO AWARD {award_id} — budget not recorded",
                  file=sys.stderr)
            continue

        proposed = sum(Decimal(a) for _, a, _ in lines)
        for category, amount, line_note in lines:
            execute("""INSERT INTO award_budget
                         (award_id, category, federal, cost_share, citation,
                          note, recorded_by)
                       VALUES (%s,%s,%s,0,%s,%s,'Schedule transcription')
                       ON CONFLICT (award_id, category) DO UPDATE
                         SET federal = EXCLUDED.federal,
                             citation = EXCLUDED.citation,
                             note = EXCLUDED.note""",
                    (award_id, category, Decimal(amount), citation, line_note))
            total_written += 1

        # The schedule has to add to the ceiling the agreement names, or one
        # of the two was transcribed wrong. Said here rather than discovered
        # later against a restatement.
        ceiling = one("SELECT ceiling_federal AS c FROM award WHERE award_id=%s",
                      (award_id,))["c"]
        if ceiling and Decimal(str(ceiling)) != proposed:
            print(f"  MISMATCH {award_id}: schedule totals {proposed:,.2f} "
                  f"against a ceiling of {Decimal(str(ceiling)):,.2f}",
                  file=sys.stderr)
        else:
            print(f"  {award_id:14} {len(lines)} categories, "
                  f"{proposed:,.2f} — ties to the ceiling")

        indirect = [c for c, a, _ in lines if c == "INDIRECT"]
        if not indirect:
            labour = sum(Decimal(a) for c, a, _ in lines
                         if c in ("LABOR", "FRINGE"))
            print(f"  {'':14} no indirect line at all, on {labour:,.2f} "
                  f"of labour")

    # Everything that has not been read, named. An award with no budget is
    # not a passing award; it is one nothing can be checked against.
    unread = query("""SELECT a.award_id FROM award a
                       WHERE NOT EXISTS (SELECT 1 FROM award_budget b
                                          WHERE b.award_id = a.award_id)
                       ORDER BY a.award_id""")
    for row in unread:
        print(f"  NOT READ {row['award_id']} — no budget schedule "
              f"transcribed, so its invoices cannot be checked against one")

    print(f"\n  {total_written} budget line(s) on the record, "
          f"{len(unread)} award(s) with no schedule read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
