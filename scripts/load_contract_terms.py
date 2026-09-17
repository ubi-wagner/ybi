#!/usr/bin/env python3
"""The provisions, read off the executed agreements into the record.

These were read once, by hand, out of four signed PDFs — §4.3 for a ceiling,
§10.1 for a term, Schedule B for what indirect was budgeted, §11.11 for which
document governs when two of them disagree. That work produced twenty-six
terms and lived in one database, because it was recorded through the screen
and never written down anywhere a fresh deployment would find it.

A system review caught it: seeded from nothing, the award register carried
three contracts and no provisions at all, and an auditor walking back from an
invoice reached the agreement and then a 404. Everything above the agreement
was reproducible and the reading of the agreement was not.

So it is here. Recorded through the real endpoint signed in as the
controller, so the trail shows a person recording a reading of a document
rather than a migration asserting one.

    PYTHONPATH=. python3 scripts/load_contract_terms.py \\
        --base http://127.0.0.1:8000 --password ...

Every term names the clause it came from. A provision with no citation is
somebody's recollection of a contract, which is worth nothing in a dispute
and worse than nothing in a file.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import httpx

from app.foundation import EMAIL  # noqa: E402

#: (award, key, value, citation, note)
TERMS = [
    # ── AM-DRIVE-AM ───────────────────────────────────────────
    ("AM-DRIVE-AM", "Allowability",
     "Reimbursement only for costs allowable under 2 CFR 200 Subpart E",
     "§4.2, closing sentence", ""),
    ("AM-DRIVE-AM", "Budget as proposed",
     "Labour 583,594 · travel 40,000 · materials 5,000 · consultants 60,000 · ODCs 415,000 = 1,103,594. There is no indirect line of any kind.",
     "Schedule B, Budget", ""),
    ("AM-DRIVE-AM", "Conflicts",
     "Where the Agreement conflicts with a Schedule, the Agreement governs. That is an argument for the zero reading and not an answer: §4.3 is silent on cost share rather than contradicting Schedule A, and silence may not be a conflict.",
     "§11.11 Conflicts", ""),
    ("AM-DRIVE-AM", "Cost share — UNRESOLVED",
     "Schedule B proposes zero and §4.3 names none, while Schedule A expects the ratio of America Makes funding to cost share to be roughly 1:1 at all times, with monthly cost share reports, a corrective action plan if the ratio is missed, and cancellation as a stated remedy. The Statement of Objectives records cost share as TBD. These cannot all be true.",
     "Schedule A (Project Reporting); Schedule B; Statement of Objectives, 16 August 2023", ""),
    ("AM-DRIVE-AM", "Indirect recovery",
     "None budgeted. Not a reduced rate and not a de minimis line — no indirect line exists, so any indirect recovered has to displace direct cost inside the ceiling.",
     "Schedule B, Budget", ""),
    ("AM-DRIVE-AM", "Reporting",
     "Monthly technical and financial reports, invoices and cost share reports due by the 10th of the following month",
     "Schedule A, Project Reporting", ""),
    ("AM-DRIVE-AM", "Term",
     "From 30 January 2024 until 4 January 2026",
     "§10.1 Term; agreement made as of 30 January 2024", ""),
    ("AM-DRIVE-AM", "Total obligation",
     "$1,103,594. The clause names no cost share.",
     "§4.3 Total Obligation", ""),
    # ── AM-HYBRID-P2 ──────────────────────────────────────────
    ("AM-HYBRID-P2", "Change of basis",
     "No change binding unless incorporated in a written modification signed by both parties",
     "§4.4", ""),
    ("AM-HYBRID-P2", "Cost share ratio",
     "Approximately 1:1 America Makes funds to cost share at all times throughout the project",
     "Statement of Work, financial reporting", ""),
    ("AM-HYBRID-P2", "Indirect provision",
     "10% of ODCs only; no indirect on labor",
     "Attachment 3, Basis of Estimate", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-HYBRID-P2", "Invoicing and reports",
     "Monthly invoices and cost share reports, due by the 10th",
     "§4.4 Invoicing and Progress Reports; Statement of Work", ""),
    ("AM-HYBRID-P2", "Invoicing frequency",
     "Monthly, by the fifth business day",
     "§25 Invoicing", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-HYBRID-P2", "Payment terms",
     "Net 30 from receipt of a correct invoice",
     "§26 Payment", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-HYBRID-P2", "Period of performance",
     "Extended to 30 June 2026",
     "Modification 001, Actions taken", ""),
    ("AM-HYBRID-P2", "Total obligation",
     "$512,409 federal funds and $104,000 cost share",
     "§4.2, as amended by Modification 001 (22 January 2026)", ""),
    # ── AM-LTM-PROJ88 ─────────────────────────────────────────
    ("AM-LTM-PROJ88", "Allowability",
     "Reimbursement only for costs allowable under 2 CFR 200 Subpart E",
     "§4.2, closing sentence", ""),
    ("AM-LTM-PROJ88", "Change of basis",
     "A change in the scope of work that increases cost requires the parties to amend the SOW and budget by written agreement; a disagreement after 30 days goes to binding arbitration",
     "§4.4 Expense Changes; §4.7", ""),
    ("AM-LTM-PROJ88", "Cost share, YBI's own share",
     "$213,037 of the $513,065. The balance is partner cost share pledged by the University of Northern Iowa and the industry partners named in the proposal, which YBI does not incur but is obliged to evidence.",
     "Proposal cover table, Lead Organization and Partners", ""),
    ("AM-LTM-PROJ88", "Indirect basis as billed",
     "10% de minimis under 2 CFR 200.414(f) — the basis being restated",
     "2 CFR 200.414(f)", ""),
    ("AM-LTM-PROJ88", "Indirect provision",
     "10% of ODCs only; no indirect on labor",
     "Attachment 3, Basis of Estimate", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-LTM-PROJ88", "Invoicing frequency",
     "Monthly, by the fifth business day",
     "§25 Invoicing", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-LTM-PROJ88", "Payment terms",
     "Net 30 from receipt of a correct invoice",
     "§26 Payment", 
     "NOT IN THE DOCUMENT. The agreement on file contains no such clause — it is ARTICLE-numbered and has no numbered ALL-CAPS clause anywhere, and the phrases are absent too. This is ICAM's §25/§26, which that agreement does contain. Recorded as it stands with this note rather than removed, because the substance may be right and sourced elsewhere; v_award_citation_check reports it NOT IN DOCUMENT and FOR_TOM_TO_VERIFY carries it."),
    ("AM-LTM-PROJ88", "Period of performance",
     "27 months from 24 September 2024",
     "Proposal cover table, Duration", ""),
    ("AM-LTM-PROJ88", "Prime agreement",
     "AFRL cooperative agreement FA8650-20-2-5700, CFDA 12.800, via NCDMM",
     "Recitals", ""),
    ("AM-LTM-PROJ88", "Total obligation",
     "$899,500 federal funding and $513,065 cost share — $1,412,565 project total",
     "§4.3 Total Obligation", ""),
    # ── AM-ICAM-DIGENG ────────────────────────────────────────
    #
    # The fourth America Makes agreement, and the one the register had no row
    # for at all. It is worded differently from the other three and the
    # citations have to say so: there is no §4.3 here, and the numbering runs
    # to plain sections rather than articles.
    ("AM-ICAM-DIGENG", "Total obligation",
     "$1,000,690. The clause names no cost share, and Attachment 3 proposes "
     "none.",
     "§9 Contract Value and Contract Funding", ""),
    ("AM-ICAM-DIGENG", "Term",
     "Date of award through 9 July 2025. Options: none. The agreement is "
     "effective on NCDMM's signature, dated 5 February 2024; YBI signed on "
     "2 February 2024.",
     "§7 Period of Performance; signature block", ""),
    ("AM-ICAM-DIGENG", "Prime agreement",
     "Grant N00174-20-1-0031, CFDA 12.300 — NCDMM administers for Energetics "
     "Technology Center and the Naval Surface Warfare Center Indian Head "
     "Division. Not the America Makes cooperative agreement the other three "
     "flow down from, which matters for which Single Audit programme the "
     "cost lands in.",
     "Recitals; Attachment 2 Flowdown Clauses", ""),
    ("AM-ICAM-DIGENG", "Budget as proposed",
     "Labour 655,190 · travel 35,000 · materials 8,000 · ODCs 275,000 · "
     "indirects on ODCs at 10% 27,500 = 1,000,690. Subcontract, equipment "
     "and consultant are named at zero. Cost share is zero in every "
     "category.",
     "Attachment 3, Basis of Estimate/Budget", ""),
    ("AM-ICAM-DIGENG", "Indirect provision",
     "10% of ODCs only — $27,500 against $275,000. $655,190 of labour "
     "carries no indirect of any kind. This is the narrowest of the four: "
     "Drive AM and Hybrid budget no indirect line at all, Last Tactical Mile "
     "budgets $81,772.76, and this one budgets a rate that reaches a "
     "quarter of the award's cost base.",
     "Attachment 3, Basis of Estimate/Budget", ""),
    ("AM-ICAM-DIGENG", "Contract type",
     "Cost Reimbursement No Fee.",
     "§6 Contract Type", ""),
    ("AM-ICAM-DIGENG", "Invoicing frequency",
     "Monthly, by the fifth business day of the month following the month "
     "worked. A cost-type invoice must carry prior, current and cumulative "
     "cost and hours by named individual, and ODCs by category, signed by "
     "an authorised official.",
     "§25 Invoicing", ""),
    ("AM-ICAM-DIGENG", "Payment terms",
     "Pay-when-paid: within thirty days of NCDMM receiving payment from the "
     "Government.",
     "§26 Payment", ""),
    ("AM-ICAM-DIGENG", "Allowability",
     "Governed by 2 CFR 200 as modified by 2 CFR 1103, the DoD interim "
     "implementation.",
     "Attachment 2, Flow-Down 1.00 Administrative Requirements", ""),
    ("AM-ICAM-DIGENG", "Conflicts",
     "The Agreement and its attachments govern, then the Statement of Work, "
     "then orders, then Government terms, then representations, then other "
     "exhibits — resolved by the most reasonable interpretation giving full "
     "consideration to the parties' intentions. Unlike Drive AM's §11.11 "
     "this is not a bare precedence rule, so a conflict here is argued "
     "rather than decided by rank.",
     "§3 Order of Precedence", ""),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--who", default=EMAIL["tom"])
    ap.add_argument("--password", default="")
    args = ap.parse_args()

    password = (args.password or os.environ.get("YBI_SEED_PASSWORD")
                or getpass.getpass(f"password for {args.who}: "))

    c = httpx.Client(base_url=args.base, timeout=60)
    r = c.post("/api/auth/login",
               json={"email": args.who, "password": password})
    if r.status_code != 200:
        print(f"could not sign in as {args.who} ({r.status_code})",
              file=sys.stderr)
        return 1
    if r.json().get("must_set_password"):
        print(f"{args.who} is on a password somebody else chose, so nothing "
              f"can be recorded under it — sign in and change it first.",
              file=sys.stderr)
        return 1

    known = {a["award_id"] for a in c.get("/api/contracts").json()["contracts"]}

    written = skipped = 0
    for award, key, value, citation, note in TERMS:
        if award not in known:
            # Said, not skipped quietly. A provision with no award to hang on
            # means the award register and this file have parted company, and
            # the fix is upstream rather than here.
            print(f"  NO AWARD {award} — {key!r} not recorded",
                  file=sys.stderr)
            skipped += 1
            continue
        r = c.put(f"/api/contracts/{award}/terms",
                  json={"term_key": key, "term_value": value,
                        "citation": citation, "note": note})
        if r.status_code >= 400:
            print(f"  FAILED   {award} {key!r} — {r.status_code} "
                  f"{r.text[:120]}", file=sys.stderr)
            skipped += 1
            continue
        written += 1
        print(f"  {award:14} {key[:34]:34} {citation[:36]}")

    print(f"\n  {written} provision(s) on the record"
          + (f", {skipped} not recorded" if skipped else ""))
    c.close()
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
