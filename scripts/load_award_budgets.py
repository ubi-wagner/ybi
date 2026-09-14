#!/usr/bin/env python3
"""The budget schedules, as read off the signed agreements.

Only what has actually been read — which is now all four America Makes
awards, each transcribed line by line off its own page.

Three of them were missing and each was missing for a different reason.
Hybrid Phase 2's Schedule B is an **image** in the PDF, which is why text
extraction found "Budget Summary" and nothing under it; its four categories
had in fact been typed into `award_budget_line` back in migration `004` and
**nothing has ever read that table**, so the check reported Hybrid
unevaluable for the whole engagement with the numbers sitting in the
database. `052` drops it, and the figures below are read off the page again
rather than copied across — a copy of a copy is not a transcription. Last
Tactical Mile's is plain text on page 44 and nobody had been to it. Digital
Engineering had no award row at all.

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

#: Schedule B, Hybrid Phase 2. An image on page 17 of the executed
#: agreement, transcribed from it.
#:
#: SUBCONTRACT, MATERIALS and EQUIPMENT are named in the schedule at zero;
#: ODC carries the whole $104,000 of cost share and nothing else does.
#:
#: **No INDIRECT row.** The second of the four with none at all — $449,043 of
#: labour with no provision for indirect of any kind.
HYBRID_P2 = [
    ("LABOR",      "449043", ""),
    ("TRAVEL",       "4500", ""),
    ("SUBAWARD",        "0", "Schedule B names this SUBCONTRACT, at zero."),
    ("MATERIALS",       "0", "Named in the schedule with nothing against it."),
    ("EQUIPMENT",       "0", "Named in the schedule with nothing against it."),
    ("CONSULTANT",  "40000", ""),
    ("ODC",          "6500", ""),
]

#: The cost-share side of Hybrid's schedule sits entirely on ODC.
HYBRID_P2_SHARE = {"ODC": "104000"}

#: Schedule B, Last Tactical Mile. Page 44, plain text.
#:
#: This one **does not foot to its own printed total**: the federal
#: categories add to $899,500.76 against a printed $899,500, and the cost
#: share to $513,065.12 against $513,065. Transcribed as printed, because a
#: loader that adjusted a category to make the page come out would be
#: inventing a budget. `v_award_budget_check` reports it.
#:
#: It is also the only one of the four with a real indirect provision on the
#: federal side — $81,772.76 — and the only one whose cost share is largely
#: *unrecovered indirect*, $233,543.12, which is the same money seen from the
#: other end and the clearest statement in the file of what the de minimis
#: election costs.
LTM = [
    ("LABOR",      "212326", ""),
    ("TRAVEL",          "0", "Named in the schedule with nothing against it."),
    ("SUBAWARD",        "0", "Schedule B names this SUBCONTRACT, at zero."),
    ("MATERIALS",       "0", "Named in the schedule with nothing against it."),
    ("EQUIPMENT",       "0", "Named in the schedule with nothing against it."),
    ("CONSULTANT", "605402", ""),
    ("ODC",             "0", "Named in the schedule with nothing against it."),
    ("INDIRECT", "81772.76", "Schedule B prints this as INDIRECTS, with no "
                             "base or rate stated."),
]

LTM_SHARE = {"CONSULTANT": "279522", "INDIRECT": "233543.12"}

#: Attachment 3, Digital Engineering. Page 26 of SRA-0350, plain text.
#:
#: The one award that budgets indirect at a stated rate, and it is the
#: narrowest possible one: **10% of ODCs only**, $27,500 against $275,000 —
#: with $655,190 of labour carrying none. That is the recovery the
#: restatement exists to go after, stated on the face of the agreement.
DIG_ENG = [
    ("LABOR",      "655190", ""),
    ("TRAVEL",      "35000", ""),
    ("SUBAWARD",        "0", "Attachment 3 names this SUBCONTRACT, at zero."),
    ("MATERIALS",    "8000", ""),
    ("EQUIPMENT",       "0", "Named in the schedule with nothing against it."),
    ("CONSULTANT",      "0", "Named in the schedule with nothing against it."),
    ("ODC",        "275000", ""),
    ("INDIRECT",    "27500", "Attachment 3 prints this as INDIRECTS on ODC's "
                             "(10%) — on ODCs only, and on nothing else."),
]


#: (award, citation, note, lines, cost_share, printed_federal,
#:  printed_cost_share, why the printed total may differ from the ceiling)
BUDGETS = [
    ("AM-DRIVE-AM",
     "Schedule B, Budget — Sub-Recipient Agreement made as of 30 January 2024",
     "Federal funding only. TOTAL PROPOSED COST SHARE is zero on the same "
     "page, which is the reading Schedule A contradicts.",
     DRIVE_AM, {}, "1103594", "0", ""),
    ("AM-HYBRID-P2",
     "Schedule B, Budget — Sub-Recipient Agreement executed 8 September 2023",
     "An image on page 17 of the executed agreement. No indirect line of any "
     "kind against $449,043 of labour.",
     HYBRID_P2, HYBRID_P2_SHARE, "500043", "104000",
     "Modification 001 of 22 January 2026 raised the obligation to $512,409 "
     "and extended performance to 30 June 2026. The schedule is the one "
     "attached to the agreement executed on 8 September 2023 and was not "
     "reissued; the $12,366 difference is the modification."),
    ("AM-LTM-PROJ88",
     "Schedule B, Budget — Sub-Recipient Agreement executed 24 September 2024",
     "Does not foot to its own printed totals: federal by $0.76 and cost "
     "share by $0.12. Transcribed as printed rather than adjusted.",
     LTM, LTM_SHARE, "899500", "513065", ""),
    ("AM-ICAM-DIGENG",
     "Attachment 3, Basis of Estimate/Budget — Sub-Recipient Agreement "
     "SRA-0350 executed 5 February 2024",
     "The only one of the four that budgets indirect at a stated rate, and "
     "it is 10% of ODCs only — $27,500, against $655,190 of labour carrying "
     "none.",
     DIG_ENG, {}, "1000690", "0", ""),
]


def main() -> int:
    open_pool()
    total_written = 0

    for (award_id, citation, note, lines, share, printed_federal,
         printed_share, ceiling_differs) in BUDGETS:
        if not one("SELECT 1 FROM award WHERE award_id = %s", (award_id,)):
            print(f"  NO AWARD {award_id} — budget not recorded",
                  file=sys.stderr)
            continue

        proposed = sum(Decimal(a) for _, a, _ in lines)
        proposed_share = sum(Decimal(v) for v in share.values())
        for category, amount, line_note in lines:
            execute("""INSERT INTO award_budget
                         (award_id, category, federal, cost_share, citation,
                          note, recorded_by)
                       VALUES (%s,%s,%s,%s,%s,%s,'Schedule transcription')
                       ON CONFLICT (award_id, category) DO UPDATE
                         SET federal = EXCLUDED.federal,
                             cost_share = EXCLUDED.cost_share,
                             citation = EXCLUDED.citation,
                             note = EXCLUDED.note""",
                    (award_id, category, Decimal(amount),
                     Decimal(share.get(category, "0")), citation, line_note))
            total_written += 1

        # The header figures the schedule prints for itself. Kept apart from
        # the award's ceiling, because a modification moves a ceiling and
        # leaves the schedule where it was — Hybrid's schedule is $500,043
        # and its ceiling is $512,409, and both are right.
        execute("""INSERT INTO award_budget_schedule
                     (award_id, citation, printed_federal, printed_cost_share,
                      ceiling_differs_because, note, recorded_by)
                   VALUES (%s,%s,%s,%s,%s,%s,'Schedule transcription')
                   ON CONFLICT (award_id) DO UPDATE
                     SET citation = EXCLUDED.citation,
                         printed_federal = EXCLUDED.printed_federal,
                         printed_cost_share = EXCLUDED.printed_cost_share,
                         ceiling_differs_because = EXCLUDED.ceiling_differs_because,
                         note = EXCLUDED.note""",
                (award_id, citation, Decimal(printed_federal),
                 Decimal(printed_share), ceiling_differs, note))

        # Does the schedule foot to the total printed on it? The QuickBooks
        # rule, applied to an agreement. LTM's does not, by 88 cents across
        # the two sides, and that is a fact about the document.
        foots = proposed - Decimal(printed_federal)
        share_foots = proposed_share - Decimal(printed_share)
        if foots or share_foots:
            print(f"  {award_id:14} {len(lines)} categories, "
                  f"{proposed:,.2f} against a printed {Decimal(printed_federal):,.2f} "
                  f"— DOES NOT FOOT by {foots:+,.2f}"
                  + (f", cost share {share_foots:+,.2f}" if share_foots else ""))
        else:
            print(f"  {award_id:14} {len(lines)} categories, "
                  f"{proposed:,.2f} — foots to the total printed on it")

        # And does the printed total reach the ceiling? Allowed to differ,
        # and then it has to say why.
        ceiling = one("SELECT ceiling_federal AS c FROM award WHERE award_id=%s",
                      (award_id,))["c"]
        gap = Decimal(printed_federal) - Decimal(str(ceiling or 0))
        if gap and not ceiling_differs:
            print(f"  {'':14} MISMATCH against the ceiling by {gap:+,.2f} "
                  f"and nothing on file says why", file=sys.stderr)
        elif gap:
            print(f"  {'':14} {gap:+,.2f} against the ceiling — "
                  f"{ceiling_differs[:72]}…")

        indirect = [a for c, a, _ in lines if c == "INDIRECT"]
        labour = sum(Decimal(a) for c, a, _ in lines if c in ("LABOR", "FRINGE"))
        if not indirect:
            print(f"  {'':14} no indirect line at all, on {labour:,.2f} "
                  f"of labour")
        else:
            print(f"  {'':14} indirect {Decimal(indirect[0]):,.2f}, "
                  f"on {labour:,.2f} of labour")

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
