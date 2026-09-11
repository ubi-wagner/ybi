#!/usr/bin/env python3
"""Put the foundational documents into the record, through the real door.

    PYTHONPATH=. python3 scripts/seed_documents.py \
        --base https://ybi.up.railway.app --as tom@ybi.org

Everything in `docs/source-documents/` is a document the engagement rests on:
the two NCDMM subrecipient agreements, the audited financial statements and
Single Audit for 2023 and 2024, the Forms 990, and the QuickBooks exports as
they were received. They are the documents a reviewer asks for first, and
until they are in the register they exist only in somebody's Downloads
folder.

They go in through `POST /api/evidence/upload` signed in as a real person,
not written to the table directly. That is the same rule provision.py
follows and for the same reason: an audit trail that shows documents
appearing from nowhere is worth less than one that shows who filed them. The
upload route is content-addressed, so running this twice files nothing twice.

Each document is declared with the kind it actually is. `app/storage.py` maps
a foundational kind to its folder, so nothing here chooses a path — say what
a document is and it lands where it belongs.

    --dry-run     print what would be filed and file nothing
    --base        the running service; defaults to 127.0.0.1:8000
    --as          who files them; needs CONTROLLER or OFFICE
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source-documents"

#: filename -> (kind, period, what it is for)
#:
#: Spelled out rather than inferred from the directory name. A directory is a
#: convenience; the kind is a claim about what a document is, and every one of
#: these was read before it was written down. The period is the year the
#: document is *of*, which for an agreement is the year it was signed — not
#: the year whose cost it governs, because that is every year until it ends.
DOCUMENTS: dict[str, tuple[str, str, str]] = {
    "2023-09-08_NCDMM_SubRecipient_Agreement_Hybrid-Phase-2.pdf": (
        "subrecipient-agreement", "2023",
        "Hybrid Phase 2. The cost-share obligation of $104,000 is in here, "
        "and it has never been tracked."),
    "2024-09-24_NCDMM_SubRecipient_Agreement_Proj88_Last-Tactical-Mile.pdf": (
        "subrecipient-agreement", "2024",
        "Project 88, Last Tactical Mile. The 10% de minimis basis being "
        "restated is the one this agreement set."),
    "2023_YBI_Audited_Financial_Statements_and_Single_Audit.pdf": (
        "audited-financial-statements", "2023",
        "Prior-prior year. Where a reviewer checks whether this year's "
        "treatment is a change in accounting."),
    "2024_YBI_Audited_Financial_Statements_and_Single_Audit.pdf": (
        "audited-financial-statements", "2024",
        "Prior year, and the comparative figures in the 2025 statements."),
    "2023_Form-990_ProPublica_full-filing.pdf": (
        "form-990", "2023",
        "As filed. Functional expense allocation to compare against."),
    "2024_Form-990_ProPublica_full-filing.pdf": (
        "form-990", "2024",
        "As filed. The 2025 return has to be consistent with this or explain "
        "why it is not."),
    "2025_General-Ledger_QuickBooks.xlsx": (
        "general-ledger", "2025",
        "The ledger under review, as exported. Schedule A."),
    "2025_Profit-and-Loss_QuickBooks.xlsx": (
        "profit-and-loss", "2025",
        "One of the three statements the eleven cross-reference points tie."),
    "2025_Balance-Sheet_QuickBooks.xlsx": (
        "balance-sheet", "2025",
        "Carries the opening balances the ledger is proved against."),
    "2025_Grant-Reconciliation-Workbook_controller.xlsx": (
        "grant-reconciliation-workbook", "2025",
        "The controller's own workbook. The source of the 22.45% fringe "
        "rate that the payroll register shows to be 21.90%."),
    "2024-02-05_NCDMM_SubRecipient_Agreement_SRA-0350_ICAM-Digital-Engineering.pdf": (
        "subrecipient-agreement", "2024",
        "ICAM Digital Engineering Workforce, $1,000,690, cost reimbursement "
        "no fee, under Grant N00174-20-1-0031 (CFDA 12.300). Attachment 3 "
        "budgets indirect at 10% of ODCs only — $27,500 on $275,000 — with "
        "no indirect at all on $655,190 of labor."),
    "2026-01-22_NCDMM_Hybrid_20240061_Modification-001.pdf": (
        "award-modification", "2026",
        "Extends Hybrid to 30 June 2026 and raises the obligation by "
        "$12,366 to $512,409. The $104,000 cost share is carried forward "
        "unchanged, so the obligation that was never tracked is now live "
        "in a second year."),
    "2021-07-13_EDA_CD-450_Award_06-79-06300.pdf": (
        "grant-agreement", "2021",
        "The EDA award behind the building assets. A scan with no text "
        "layer — it needs OCR before anything can be read out of it."),
    "2025-11-17_EDA_Closeout-Letter_06-79-06300.pdf": (
        "closeout-letter", "2025",
        "Closes EDA 06-79-06300. Final project cost $2,376,344, EDA share "
        "$1,903,179, disbursed $1,712,861, leaving $188,214.54 still to be "
        "drawn. Records retained three years from this date."),
    "2022-02-02_JobsOhio_Grant-Agreement_SFPN-2021-493762-VCG.pdf": (
        "grant-agreement", "2022",
        "JobsOhio, $475,000 toward $2,428,974 of project investment "
        "including $2,092,861 of building fixed assets. Not federal, which "
        "is what makes it the other half of the funding-source question."),
    "2026_YBI_Fixed-Asset-Schedule.xls": (
        "asset-register", "2026",
        "The asset register. $23,419,573.64 of cost against $10,452,995.43 "
        "of accumulated depreciation. Carries life, method and in-service "
        "date per asset — and no funding source column, which is the one "
        "field 200.436(b) turns on."),
    "2025_YBI_Lease-Schedule.xlsx": (
        "lease-schedule", "2025",
        "Twenty-six tenant leases by building with monthly and annual rent. "
        "The tenant side of the facilities carve-out; square footage is "
        "still missing."),
}


def find(name: str) -> Path | None:
    hits = list(SOURCE.rglob(name))
    return hits[0] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("YBI_BASE",
                                                "http://127.0.0.1:8000"))
    ap.add_argument("--as", dest="who", default="tom@ybi.org")
    ap.add_argument("--password", default=os.getenv("YBI_PASSWORD", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan, missing = [], []
    for name, (kind, period, why) in DOCUMENTS.items():
        path = find(name)
        (plan if path else missing).append((path or name, name, kind,
                                            period, why))

    width = max(len(k) for _, _, k, _, _ in plan + missing) if DOCUMENTS else 0
    for path, name, kind, period, why in plan:
        print(f"  {kind:<{width}}  {period}  {name}")
    for _, name, kind, period, _ in missing:
        print(f"  {kind:<{width}}  {period}  {name}   ** NOT ON DISK **",
              file=sys.stderr)

    if missing:
        print(f"\n{len(missing)} document(s) named here are not in "
              f"{SOURCE.relative_to(ROOT)}. Filing the rest would leave the "
              f"register looking complete when it is not.", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"\n{len(plan)} document(s) would be filed. Nothing written.")
        return 0

    password = args.password or getpass.getpass(f"password for {args.who}: ")

    filed = deduplicated = 0
    with httpx.Client(base_url=args.base, timeout=300) as c:
        r = c.post("/api/auth/login",
                   json={"email": args.who, "password": password})
        if r.status_code != 200:
            print(f"could not sign in as {args.who} ({r.status_code}): "
                  f"{r.text[:200]}", file=sys.stderr)
            return 1
        if r.json().get("must_set_password"):
            print(f"{args.who} is still on an issued password. Nothing can "
                  f"be recorded under it — sign in and change it first.",
                  file=sys.stderr)
            return 1

        for path, name, kind, period, why in plan:
            with path.open("rb") as fh:
                r = c.post("/api/evidence/upload",
                           files={"file": (name, fh,
                                           "application/octet-stream")},
                           data={"kind": kind, "period": period,
                                 "relevance": why})
            if r.status_code != 200:
                print(f"{name}: {r.status_code} {r.text[:200]}",
                      file=sys.stderr)
                return 1
            body = r.json()
            dup = body.get("deduplicated")
            deduplicated += bool(dup)
            filed += not dup
            print(f"  {'already on file' if dup else 'filed':<15} "
                  f"{body.get('evidence_id')}  {name}")

    print(f"\n{filed} filed, {deduplicated} already on file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
