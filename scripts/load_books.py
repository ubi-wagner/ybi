#!/usr/bin/env python3
"""The general ledger, the profit and loss and the balance sheet, at boot.

    PYTHONPATH=. python3 scripts/load_books.py

**The deployment could not bring back its own books.** `app/foundation.py`
files `2025_General-Ledger_QuickBooks.xlsx` into the library and read no row
out of it, because promoting it lived inside an HTTP handler with an `Actor`
in its signature — and a boot has no socket and nobody to be. So a rebuilt
service came back with the paper on the shelf and 15,500 lines missing, and
the only way to fix it was a person at a console.

This is `scripts/load_2025.py` with the transport taken out. It calls the
same `stage_file`, `parse_batch` and `promote_batch` the screen calls, so
there is **one implementation**: the same parsers, the same accept gate, the
same trigger refusing a promote while any printed subtotal is off by more
than half a cent. What differs is only who the row says did it — a
provenance label, `deployment bootstrap`, and an audit row that claims no
account and no session, which is what migration `087` defines for a
mechanism acting in its own name.

Re-runnable. A file already staged under the same SHA-256 is recognised, and
`ledger_import` is UNIQUE on (period, sha256) so re-accepting one is a no-op.

Every control the interactive path checks is checked here and the run fails
if one does not tie — a ledger that is loaded without its controls tying is
worse than no ledger, because nothing downstream knows.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.imports import (parse_batch, preview,  # noqa: E402
                                 promote_batch, stage_file)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source-documents" / "accounting-records"
BY = "deployment bootstrap"
PERIOD = os.environ.get("YBI_PERIOD", "2025")

#: The three exports, and what each one is for. Order matters: the profit and
#: loss defines the cost scope every ledger line is then sectioned against,
#: and the balance sheet's net income is checked against the P&L's.
BOOKS = (
    ("PROFIT_LOSS", "2025_Profit-and-Loss_QuickBooks.xlsx"),
    ("BALANCE_SHEET", "2025_Balance-Sheet_QuickBooks.xlsx"),
    ("GENERAL_LEDGER", "2025_General-Ledger_QuickBooks.xlsx"),
)


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    loaded = 0
    for report, name in BOOKS:
        path = SOURCE / name
        if not path.exists():
            print(f"  not in the image: {name}", file=sys.stderr)
            return 1
        batch = stage_file(path.read_bytes(), name, report, PERIOD, BY)
        out = parse_batch(batch["batch_id"], BY)

        if report == "PROFIT_LOSS":
            v = Decimal(out["variance"])
            if abs(v) > Decimal("0.01"):
                print(f"  the profit and loss does not foot by {v}", file=sys.stderr)
                return 1
            print(f"  profit and loss   {out['accounts']} accounts, "
                  f"net income {Decimal(out['net_income']):,.2f}")
        elif report == "BALANCE_SHEET":
            for k in ("balance_variance", "net_income_variance"):
                if abs(Decimal(out[k])) > Decimal("0.01"):
                    print(f"  balance sheet: {k} is {out[k]}", file=sys.stderr)
                    return 1
            print(f"  balance sheet     {out['accounts']} accounts, "
                  f"assets {Decimal(out['assets']):,.2f}")
        else:
            # The subtotal gate, read before the promote rather than after —
            # the trigger refuses anyway, and a refusal read as a crash is
            # the thing a person at a console would have had to interpret.
            prev = preview(batch["batch_id"])
            if not prev["acceptable"]:
                bad = len(prev["mismatches"])
                print(f"  the general ledger has {bad} printed subtotal(s) "
                      f"that do not equal what sits under them; nothing was "
                      f"promoted", file=sys.stderr)
                return 1
            done = promote_batch(batch["batch_id"], BY)
            print(f"  general ledger    {done['lines_promoted']:,} lines promoted")
        loaded += 1

    print(f"{loaded} of {len(BOOKS)} book(s) in, as {BY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
