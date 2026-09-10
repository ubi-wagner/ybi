#!/usr/bin/env python3
"""Load the 2025 QuickBooks exports through the real API, end to end.

Repeatable acceptance run for Phase 1. Every step asserts a control total, so
a regression in the parser or the accept gate fails here rather than in front
of the controller.

    python3 scripts/load_2025.py [--base http://127.0.0.1:8000]

Controls asserted (PLAN.md Phase 1):
    P&L income      6,662,593.00
    P&L COGS           37,261.00
    P&L expenses    6,737,951.18
    P&L net income      4,329.28
    GL dated rows          15,500
    GL subtotal variance     0.00
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

import httpx

SOURCE = Path("docs/source-documents/accounting-records")
PL_FILE = SOURCE / "2025_Profit-and-Loss_QuickBooks.xlsx"
GL_FILE = SOURCE / "2025_General-Ledger_QuickBooks.xlsx"

EXPECTED_PL = {
    "Income": Decimal("6662593.00"),
    "COGS": Decimal("37261.00"),
    "Expense": Decimal("6737951.18"),
    "Other Income": Decimal("116948.46"),
}
EXPECTED_NET = Decimal("4329.28")
EXPECTED_GL_ROWS = 15_500

failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label:38s} {got!s:>16}  expected {want!s:>16}")
    if not ok:
        failures.append(f"{label}: got {got}, expected {want}")


def upload(c: httpx.Client, path: Path, report: str, who: str) -> str:
    # report / period / uploaded_by are query parameters on this endpoint;
    # only the file itself is multipart. Sending them as form fields silently
    # falls back to the GENERAL_LEDGER default.
    with path.open("rb") as fh:
        r = c.post("/api/imports/upload", files={"file": (path.name, fh)},
                   params={"report": report, "period": "2025", "uploaded_by": who})
    r.raise_for_status()
    return r.json()["batch_id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--who", default="Tom Metzinger")
    args = ap.parse_args()

    with httpx.Client(base_url=args.base, timeout=300) as c:
        c.get("/api/health").raise_for_status()

        print("\nProfit and loss")
        pl_batch = upload(c, PL_FILE, "PROFIT_LOSS", args.who)
        pl = c.post(f"/api/imports/{pl_batch}/parse").json()
        for section, want in EXPECTED_PL.items():
            check(section, Decimal(pl["sections"][section]), want)
        check("net income", Decimal(pl["net_income"]), EXPECTED_NET)
        check("section variance", Decimal(pl["variance"]), Decimal("0.00"))
        print(f"        {pl['accounts']} P&L accounts define cost scope")

        print("\nGeneral ledger")
        gl_batch = upload(c, GL_FILE, "GENERAL_LEDGER", args.who)
        gl = c.post(f"/api/imports/{gl_batch}/parse").json()
        check("dated rows", gl["lines"], EXPECTED_GL_ROWS)

        prev = c.get(f"/api/imports/{gl_batch}/preview").json()
        check("subtotal variance", Decimal(prev["reconciliation"]["variance"]),
              Decimal("0.00"))
        check("subtotal mismatches", len(prev["mismatches"]), 0)

        acc = c.post(f"/api/imports/{gl_batch}/accept",
                     params={"accepted_by": args.who})
        acc.raise_for_status()
        print(f"        {acc.json()['lines_promoted']} lines promoted to the ledger")

        print("\nClassification scope")
        cov = c.get("/api/classify/coverage").json()
        print(f"        {cov['groups_remaining']} groups, "
              f"${Decimal(cov['dollars_remaining']):,.2f} to classify")

    print()
    if failures:
        print(f"{len(failures)} control(s) failed:")
        for f in failures:
            print("   -", f)
        return 1
    print("All controls tie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
