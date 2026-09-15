#!/usr/bin/env python3
"""Put back an invoice line the parser could not read.

`v_invoice_footing_check` reports an invoice whose lines do not add to the
total on its own face, and `NO DATA` where it carries no line at all. AAMEN
9079 was the second kind: its line prints without the quantity and rate
columns the other eleven carry, `load_invoices_2025.py` matched nothing, and
its own footing check opened `if inv["lines"] and ...` — which excludes
exactly that case.

This is the shape `retype_documents.py` and `read_documents.py` already
answer: the loader is fixed, and the rows written before it was fixed need
somebody to go back for them.

**It is self-limiting and refuses rather than guessing.** It touches only an
invoice carrying *no lines at all*, only where the source document is on file,
only where re-parsing finds lines, and only where those lines add to the
header total to the cent. Anything else is reported and left alone — an
invoice whose lines disagree with its face is a question for a person, not a
row to overwrite.

    python scripts/repair_invoice_lines.py            # say what it would do
    python scripts/repair_invoice_lines.py --write    # do it
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query, transaction  # noqa: E402

INTAKE = Path(__file__).resolve().parent.parent / "intake"


def loader():
    """The 2025 loader's own parser, so there is one reading of a face."""
    path = Path(__file__).resolve().parent / "load_invoices_2025.py"
    spec = importlib.util.spec_from_file_location("_li", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="write the lines; without it nothing is written")
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()
    li = loader()

    empty = query("""SELECT f.objective_id, f.invoice_number, f.header_total,
                            i.invoice_id, i.source_document
                       FROM v_invoice_footing_check f
                       JOIN invoice i ON i.invoice_number = f.invoice_number
                                     AND i.period = f.period
                      WHERE f.period = %s AND f.state = 'NO DATA'
                      ORDER BY f.objective_id, f.invoice_number""",
                  (args.period,))
    if not empty:
        print("Every invoice carries lines that add to its face. Nothing to do.")
        return 0

    print(f"{len(empty)} invoice(s) carry no line at all:\n")
    fixed = refused = 0
    for e in empty:
        src = INTAKE / (e["source_document"] or "")
        head = Decimal(str(e["header_total"] or 0))
        label = f"{e['objective_id']} {e['invoice_number']}"
        if not e["source_document"] or not src.exists():
            print(f"  {label}: {e['source_document'] or 'no source document'} "
                  f"is not on file — left alone")
            refused += 1
            continue
        found = [x for inv in li.parse(src) if inv["number"] == e["invoice_number"]
                 for x in inv["lines"]]
        if not found:
            print(f"  {label}: re-parsing {src.name} still finds no line — "
                  f"left alone, and it is a question for a person")
            refused += 1
            continue
        total = sum(x["amount"] for x in found)
        if abs(total - head) > Decimal("0.01"):
            print(f"  {label}: the face reads {total:,.2f} against a header of "
                  f"{head:,.2f} — left alone rather than made to agree")
            refused += 1
            continue
        print(f"  {label}: {len(found)} line(s), {total:,.2f}, agrees with the "
              f"face{'' if args.write else '  (not written)'}")
        if args.write:
            with transaction() as cur:
                for i, x in enumerate(found, 1):
                    cur.execute("""INSERT INTO invoice_line
                                     (invoice_id, sequence, category,
                                      description, quantity, rate, amount)
                                   VALUES (%s,%s,%s,%s,1,%s,%s)""",
                                (e["invoice_id"], i,
                                 li.categorise(x["label"]), x["label"][:400],
                                 x["rate"], x["amount"]))
                cur.execute("""INSERT INTO audit_log
                                 (action, entity, entity_id, actor, reason)
                               VALUES ('INVOICE_LINE_REPAIR','invoice',%s,
                                       'repair_invoice_lines.py',%s)""",
                            (str(e["invoice_id"]),
                             f"{len(found)} line(s) read off "
                             f"{src.name}; the loader's regex required a "
                             f"quantity and rate this face does not print"))
        fixed += 1

    print(f"\n{fixed} repaired{'' if args.write else ' (dry run — pass --write)'}"
          f", {refused} left alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
