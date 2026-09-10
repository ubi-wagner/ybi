#!/usr/bin/env python3
"""A controller working session, driven through the real API.

Stands in for Tom classifying the 2025 ledger: take the largest groups first,
record a pool, a Form 990 function, a federal treatment and an evidence grade,
with written reasoning and a regulatory citation on every judgment that needs
one. Attach supporting evidence and leave workpaper notes where the reviewer
will look for them.

This is an exercise of the rules, not a fixture. Every decision here has to
satisfy the same schema constraints a human would hit:

  * DIRECT must name a final cost objective; a pooled cost must not.
  * A grade of MANAGEMENT_RECONSTRUCTION or better requires written reasoning.
  * FUNDRAISING and UNALLOWABLE can never be federally allowable.

    python3 scripts/tom_session.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

WHO = "Tom Metzinger"

#: Account fragment -> the judgment to record against it. Matching is on a
#: fragment so the script survives the qualified-path prefixes.
DECISIONS: list[dict] = [
    {
        "match": "5140 Employee Wages",
        "pool": "DIRECT", "function_990": "PROGRAM", "federal": "PENDING",
        "objective_id": "ESP",
        "grade": "MANAGEMENT_RECONSTRUCTION",
        "citation": "2 CFR 200.430(i)",
        "rationale": (
            "Gross payroll posts as two lump journal entries per pay period with "
            "no employee, project or class dimension. Distribution is taken from "
            "the controller's 2025 labour reconstruction pending signed employee "
            "certifications; graded as reconstruction, not verified, until those "
            "are on file."),
        "note": (
            "Wage control is 1,789,993.94 per account 5139. The reconstruction "
            "workbook totals 1,834,993.97, a variance of 45,000.03 that must be "
            "resolved before this distribution supports a federal charge."),
    },
    {
        "match": "5010 Depreciation Expense",
        "pool": "OVERHEAD", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "PENDING",
        "grade": "TEST_ASSUMPTION",
        "citation": "2 CFR 200.436",
        "rationale": (
            "Facilities depreciation. Held at test assumption: depreciation on "
            "the portion of asset cost borne by federal funds is unallowable, and "
            "the asset register with funding source per asset has not been "
            "produced. Tech Block Building 5 alone is 38.5% of the depreciable "
            "basis."),
        "note": (
            "Blocking evidence gap EVG-002. Until the register arrives this "
            "number cannot leave test assumption, and a rate built on it cannot "
            "be sealed."),
    },
    {
        "match": "5085 Advertising",
        "pool": "FUNDRAISING", "function_990": "FUNDRAISING",
        "federal": "UNALLOWABLE",
        "grade": "CORROBORATED",
        "citation": "2 CFR 200.421",
        "rationale": (
            "Advertising and public relations incurred for fundraising. "
            "Unallowable under 200.421 except for the narrow purposes listed "
            "there, none of which apply. Stays in the MTDC base but not in the "
            "pool."),
    },
    {
        "match": "5400 Bad Debt",
        "pool": "UNALLOWABLE", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "UNALLOWABLE",
        "grade": "VERIFIED",
        "citation": "2 CFR 200.426",
        "rationale": "Bad debt is expressly unallowable. Removed from the pool.",
    },
    {
        "match": "5120 Government Relations",
        "pool": "UNALLOWABLE", "function_990": "FUNDRAISING",
        "federal": "UNALLOWABLE",
        "grade": "CORROBORATED",
        "citation": "2 CFR 200.450",
        "rationale": (
            "Government relations retainer. Treated as lobbying and removed from "
            "the pool pending confirmation of the scope of services."),
        "note": "Confirm with the CEO whether any portion is non-lobbying advocacy.",
    },
    {
        "match": "5220 Contributions",
        "pool": "UNALLOWABLE", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "UNALLOWABLE",
        "grade": "VERIFIED",
        "citation": "2 CFR 200.434",
        "rationale": "Contributions made by the organisation are unallowable.",
    },
    {
        "match": "5202 Accounting",
        "pool": "G&A", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "ALLOWABLE",
        "grade": "CORROBORATED",
        "citation": "2 CFR 200.403(d)",
        "rationale": (
            "Accounting, audit and controller services. Held wholly in G&A: the "
            "same function cannot be direct on some awards and indirect on "
            "others in like circumstances, and the 2025 reconstruction charged "
            "part of the controller's fee directly to Hybrid and Rising Tides."),
        "note": (
            "Consistency issue to correct in the reconstruction: 15.4% of the "
            "controller's fee was direct-charged to each of Hybrid and Rising "
            "Tides while 64.5% sat in G&A."),
    },
    {
        "match": "5030 Janitorial",
        "pool": "OVERHEAD", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "PENDING",
        "grade": "CORROBORATED",
        "citation": "2 CFR 200.465",
        "rationale": (
            "Facilities operation and maintenance. Allocable on square footage; "
            "the tenant share is recovered through rent and does not reach the "
            "federal pool."),
    },
    {
        "match": "5200 Real Estate Tax",
        "pool": "OVERHEAD", "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "PENDING",
        "grade": "VERIFIED",
        "citation": "2 CFR 200.470",
        "rationale": "Property taxes on facilities. Allocable with occupancy.",
    },
]

EVIDENCE = [
    {
        "match": "5400 Bad Debt",
        "path": Path("docs/source-documents/accounting-records/"
                     "2025_Profit-and-Loss_QuickBooks.xlsx"),
        "kind": "trial_balance",
        "relevance": "2025 P&L, account 5400 Bad Debt Expense 12,037.85.",
    },
    {
        "match": "5220 Contributions",
        "path": Path("docs/source-documents/accounting-records/"
                     "2025_Profit-and-Loss_QuickBooks.xlsx"),
        "kind": "trial_balance",
        "relevance": "2025 P&L, account 5220 Contributions 1,000.00.",
    },
    {
        "match": "5200 Real Estate Tax",
        "path": Path("docs/source-documents/accounting-records/"
                     "2025_Profit-and-Loss_QuickBooks.xlsx"),
        "kind": "trial_balance",
        "relevance": "2025 P&L, account 5200 Real Estate Tax 26,526.66.",
    },
    {
        "match": "5140 Employee Wages",
        "path": Path("docs/source-documents/accounting-records/"
                     "2025_Grant-Reconciliation-Workbook_controller.xlsx"),
        "kind": "labor_reconstruction",
        "relevance": ("2025 labour distribution by employee and cost objective, "
                      "prepared by the controller September 2026."),
    },
    {
        "match": "5010 Depreciation Expense",
        "path": Path("docs/source-documents/financial-statements/"
                     "2024_YBI_Audited_Financial_Statements_and_Single_Audit.pdf"),
        "kind": "audited_financials",
        "relevance": ("Property note: gross basis 22,393,574 and 2024 depreciation "
                      "704,131. Finding 2024-001 records that capital "
                      "reimbursements were netted against asset cost."),
    },
]


def fetch_queue(c: httpx.Client) -> list[dict]:
    """Pull the whole queue. The endpoint caps a page at 200 groups."""
    out: list[dict] = []
    offset = 0
    while True:
        r = c.get("/api/classify/queue", params={"limit": 200, "offset": offset})
        r.raise_for_status()
        page = r.json()
        if not isinstance(page, list):
            raise RuntimeError(f"unexpected queue response: {page}")
        out.extend(page)
        if len(page) < 200:
            return out
        offset += 200


def find_group(groups: list[dict], fragment: str) -> dict | None:
    for g in groups:
        if fragment.lower() in (g.get("account") or "").lower():
            return g
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    applied = skipped = failed = 0
    with httpx.Client(base_url=args.base, timeout=120) as c:
        c.get("/api/health").raise_for_status()
        groups = fetch_queue(c)
        print(f"{len(groups)} groups in the queue\n")

        print("Evidence")
        # An evidence id has to be cited on the decision itself: the gate reads
        # decision_evidence, not merely whether a document exists somewhere
        # nearby. Attaching and citing are different acts, and only the second
        # one is a claim the reviewer can test.
        cited: dict[str, list[str]] = {}
        for e in EVIDENCE:
            g = find_group(groups, e["match"])
            if not g or not e["path"].exists():
                print(f"  SKIP  {e['match']}")
                continue
            with e["path"].open("rb") as fh:
                r = c.post("/api/evidence/upload",
                           files={"file": (e["path"].name, fh)},
                           data={"kind": e["kind"], "period": "2025",
                                 "uploaded_by": WHO,
                                 "target_type": "LEDGER_GROUP",
                                 "target_id": g["group_key"],
                                 "relevance": e["relevance"]})
            if r.status_code < 400:
                cited.setdefault(e["match"], []).append(r.json()["evidence_id"])
            print(f"  {'OK  ' if r.status_code < 400 else 'FAIL'}  "
                  f"{e['match'][:30]:32s} {e['path'].name[:46]:48s} {r.status_code}")

        print("\nClassification")
        for d in DECISIONS:
            g = find_group(groups, d["match"])
            if not g:
                print(f"  SKIP  {d['match']:38s} not in queue")
                skipped += 1
                continue

            body = {
                "group_keys": [g["group_key"]],
                "pool": d["pool"],
                "function_990": d["function_990"],
                "federal": d["federal"],
                "objective_id": d.get("objective_id"),
                "grade": d["grade"],
                "rationale": d["rationale"],
                "citation": d.get("citation"),
                "evidence_ids": cited.get(d["match"], []),
                "decided_by": WHO,
            }
            r = c.post("/api/classify/decide", json=body)
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail", r.text)
                except ValueError:
                    detail = r.text[:150]
                print(f"  FAIL  {d['match']:38s} {r.status_code} {str(detail)[:160]}")
                failed += 1
                continue
            applied += 1
            print(f"  OK    {d['match']:38s} -> {d['pool']:12s} "
                  f"{d['grade']:26s} {float(g['amount']):>13,.0f}")

            if d.get("note"):
                c.post("/api/evidence/note", json={
                    "target_type": "LEDGER_GROUP",
                    "target_id": body["group_keys"][0],
                    "body": d["note"],
                    "author": WHO,
                    "is_workpaper": True,
                })

        cov = c.get("/api/classify/coverage").json()
        print(f"\nCoverage  {float(cov['pct_dollars']):.1f}% of dollars   "
              f"{cov['groups_decided']}/{cov['groups_total']} groups   "
              f"{cov['decided_lines']}/{cov['total_lines']} lines")

    print(f"\napplied {applied}, skipped {skipped}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
