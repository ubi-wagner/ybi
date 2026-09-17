#!/usr/bin/env python3
"""Load the fixed-asset register, and deliberately not the funding behind it.

    python3 scripts/load_assets.py [path-to-schedule]

`2026_YBI_Fixed-Asset-Schedule.xls` has been on file since the foundation was
loaded, `app/domain/asset_schedule.py` has parsed it since the request
workbooks were built, and **nothing has ever written the 263 assets into the
register**. So `asset` is empty, `v_partition_coverage` reports ASSETS as
NO DATA, and the walk's step 5 has read *needs the asset register* for the
life of the system — over a spreadsheet YBI has had the whole time.

That mattered more once `084` let Heidi answer 200.313(d)(1) one asset at a
time: a funding source names an asset, the schema refuses one for an asset
that is not on the register, and the register was empty. The mechanism was
complete and had nothing to point at — the capability-with-no-door shape one
level up, where the door exists and the room behind it was never furnished.

**The funding column is not loaded, because the schedule does not have one.**
That absence is 2 CFR 200.313(d)(1) unanswered and is a finding in its own
right; it is also exactly the column Heidi fills in. So every asset lands with
no `asset_funding` row at all — *a blank is unanswered, and unanswered is a
value* — and the inventory screen opens on 263 assets that all say **nobody
has looked**, which is the work rather than a gap in it.

Loading is transcription and not judgment: this is YBI's own depreciation
schedule, read as printed, which is why it is a loader beside the ledger's
and not something a person does in the application. Two figures the schedule
prints for itself are checked against what sits under them, the QuickBooks
rule applied to a fixed-asset schedule.

Re-runnable: keyed on the system number the depreciation software already
uses, so a register reloaded next year lands on the same rows rather than
doubling.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, one, open_pool, query              # noqa: E402
from app.domain.asset_schedule import parse_asset_schedule     # noqa: E402

DEFAULT = ("docs/source-documents/asset-register/"
           "2026_YBI_Fixed-Asset-Schedule.xls")


def main() -> int:
    ap = argparse.ArgumentParser(description="Load the fixed-asset register.")
    ap.add_argument("path", nargs="?", default=DEFAULT)
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"no schedule at {path}", file=sys.stderr)
        return 2

    schedule = parse_asset_schedule(path)
    assets = list(schedule.assets)
    if not assets:
        print("the schedule parsed to no assets at all", file=sys.stderr)
        return 2

    open_pool()
    before = one("SELECT count(*) AS n FROM asset WHERE period = %s",
                 (args.period,))["n"]

    written = 0
    for a in assets:
        execute("""
            INSERT INTO asset (asset_id, period, description, gl_account,
                               in_service_on, gross_cost, salvage_value,
                               useful_life_years, method, accum_depr_open,
                               accum_depr_close, depreciation,
                               source_document, evidence_grade, loaded_by,
                               note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    'CORROBORATED','load_assets.py',%s)
            ON CONFLICT (asset_id) DO UPDATE SET
              description = EXCLUDED.description,
              gl_account = EXCLUDED.gl_account,
              in_service_on = EXCLUDED.in_service_on,
              gross_cost = EXCLUDED.gross_cost,
              salvage_value = EXCLUDED.salvage_value,
              useful_life_years = EXCLUDED.useful_life_years,
              method = EXCLUDED.method,
              accum_depr_open = EXCLUDED.accum_depr_open,
              accum_depr_close = EXCLUDED.accum_depr_close,
              depreciation = EXCLUDED.depreciation,
              source_document = EXCLUDED.source_document""",
            (a.asset_id, args.period, a.description, a.gl_account,
             a.in_service_on, a.gross_cost, a.salvage_value,
             a.useful_life_years, a.method or "STRAIGHT_LINE",
             a.accum_depr_open, a.accum_depr_close, a.depreciation,
             "2026_YBI_Fixed-Asset-Schedule.xls",
             f"Asset class {a.asset_class}" if a.asset_class else ""))
        written += 1

    after = one("""SELECT count(*) AS n,
                          COALESCE(sum(gross_cost), 0) AS cost,
                          COALESCE(sum(depreciation), 0) AS depr
                     FROM asset WHERE period = %s""", (args.period,))
    funded = one("""SELECT count(DISTINCT asset_id) AS n FROM asset_funding""")

    print(f"{written} assets written — {after['n']} on the register "
          f"({after['n'] - before} new)")

    # What went in, against what was read. The printed subtotals below tie at
    # *parse* time, so they cannot see a key collision — the parser holds both
    # rows and only the database collapses them. This is the control that can:
    # it caught system number 165 being two assets in two accounts, loading
    # 262 rows from 263 and losing $35,414.95 of cost without a murmur.
    parsed_cost = sum((x.gross_cost for x in assets), Decimal(0))
    if after["n"] != len(assets) or after["cost"] != parsed_cost:
        print(f"\n  the register holds {after['n']} of {len(assets)} parsed "
              f"assets and {after['cost']:,.2f} of {parsed_cost:,.2f} — "
              f"something collided on its key", file=sys.stderr)
        return 1
    print(f"  every one of the {len(assets)} parsed assets is on the register, "
          f"to the cent")
    print(f"  gross cost   {after['cost']:>16,.2f}")
    print(f"  depreciation {after['depr']:>16,.2f}")

    # Every printed subtotal must equal what sits under it, applied to a
    # fixed-asset schedule. The parser computes these; re-deriving them here
    # would be one figure computed twice, which is the thing that can disagree
    # with itself. A loader that says only "263 written" has not said whether
    # they are the right 263.
    print()
    for c in schedule.controls:
        tick = "ties" if c.printed == c.parsed else "OPEN"
        print(f"  {c.gl_account:<8} {c.printed:>14,.2f} printed, "
              f"{c.parsed:>14,.2f} under it  {tick}")
    if not schedule.ties:
        print("\n  the schedule does not foot; nothing above is trustworthy",
              file=sys.stderr)
        return 1
    if schedule.skipped:
        print(f"  sheets that did not look like an asset sheet: "
              f"{', '.join(schedule.skipped)}")

    print(f"\n  {after['n'] - funded['n']} of {after['n']} carry no funding "
          f"source, which is 200.313(d)(1) unanswered and is the column the "
          f"schedule does not have.")
    print("  Heidi answers it one asset at a time on Classify › Equipment, "
          "or in bulk through the Requests workbook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
