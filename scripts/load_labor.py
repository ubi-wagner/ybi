#!/usr/bin/env python3
"""Load the controller's 2025 effort distribution.

Source: the Grant Reconciliation Workbook, sheet "Time Breakdown", rows 98-142.
Each row is one employee; the columns are cost objectives and the values are
the wage dollars the controller distributed to each.

The workbook distributes dollars rather than hours, so dollars are carried as
the effort unit. Shares and distributed wages then come out identical to the
workbook, which is the point — this loads what the controller actually
concluded rather than a re-derivation of it.

Everything lands as a reconstruction at MANAGEMENT RECONSTRUCTION grade,
because that is what it is: prepared in September 2026 for calendar 2025, from
records that were not contemporaneous. The certification workflow is what turns
it into support for a charge.

    PYTHONPATH=. python3 scripts/load_labor.py                 # repo copy
    python3 scripts/load_labor.py path/to/workbook.xlsx        # explicit file
    python3 scripts/load_labor.py --evidence EV-8be4dad4402d   # from the store

The third form is the deployed one. The source workbooks are not baked into
the image — they are the client's financial records, and an image is copied
around — so in production the controller uploads the workbook through the
Evidence screen, where it is hashed and stored, and this loads from that
stored copy. The document the load used is then the document on file, which
is the whole point of a content-addressed store.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from app.db import execute, one, open_pool

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

SOURCE = Path("docs/source-documents/accounting-records/"
              "2025_Grant-Reconciliation-Workbook_controller.xlsx")
SHEET = "Time Breakdown"
HEADER_ROW = 97          # "2025 Wages", then Adj-<objective> across
FIRST, LAST = 98, 142    # employee rows

RATIONALE = (
    "Distributed from the controller's 2025 labour reconstruction. Gross "
    "payroll posts to the ledger as two lump journal entries per pay period "
    "with no employee, project or class dimension, so the distribution was "
    "rebuilt from hours logs and normalised to total compensation."
)


def cells(path: Path, sheet_name: str):
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    path_for = {s.get("name"): "xl/" + target[s.get(NSR + "id")].lstrip("/")
                for s in wb.iter(NS + "sheet")}
    if sheet_name not in path_for:
        raise LookupError(
            f"{path.name} has no {sheet_name!r} sheet. Its sheets are: "
            + ", ".join(sorted(path_for)))
    root = ET.fromstring(z.read(path_for[sheet_name]))
    for row in root.iter(NS + "row"):
        out: dict[str, str] = {}
        for c in row.findall(NS + "c"):
            v = c.find(NS + "v")
            if v is None or v.text is None:
                continue
            text = shared[int(v.text)] if c.get("t") == "s" else v.text
            out[re.match(r"([A-Z]+)", c.get("r")).group(1)] = text
        yield int(row.get("r")), out


def resolve_source(args) -> Path | None:
    """Where the workbook is: named on the command line, on file as evidence,
    or the repo copy for a development run."""
    if args.evidence:
        open_pool()
        row = one("SELECT uri, sha256 FROM evidence WHERE evidence_id = %s",
                  (args.evidence,))
        if not row:
            print(f"no evidence {args.evidence} on file", file=sys.stderr)
            return None
        path = Path(row["uri"])
        if not path.exists():
            print(f"{args.evidence} is on file but {path} is missing — the "
                  f"storage volume may not be mounted", file=sys.stderr)
            return None
        print(f"  from evidence {args.evidence} (sha256 {row['sha256'][:12]}…)")
        return path
    return Path(args.path) if args.path else SOURCE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", help="path to the workbook")
    ap.add_argument("--evidence", help="evidence id of an uploaded workbook")
    args = ap.parse_args()

    source = resolve_source(args)
    if source is None:
        return 2
    if not source.exists():
        print(f"{source} not found", file=sys.stderr)
        return 2

    try:
        rows = dict(cells(source, SHEET))
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    header = rows.get(HEADER_ROW, {})
    objectives = {col: label[4:].strip()
                  for col, label in header.items()
                  if label.startswith("Adj-")}
    if not objectives:
        print("no Adj-<objective> columns found", file=sys.stderr)
        return 2

    open_pool()
    execute("DELETE FROM labor_allocation WHERE period='2025'")

    employees = allocations = 0
    total = Decimal(0)
    for r in range(FIRST, LAST + 1):
        row = rows.get(r, {})
        name = (row.get("A") or "").strip()
        if not name:
            continue
        wages = Decimal(row.get("B") or 0).quantize(Decimal("0.01"))
        if wages <= 0:
            continue
        employees += 1
        total += wages
        for col, objective in sorted(objectives.items()):
            amount = Decimal(row.get(col) or 0).quantize(Decimal("0.01"))
            if amount == 0:
                continue
            execute("""
                INSERT INTO labor_allocation
                  (period, employee_key, employee_name, objective_id,
                   payroll_wages, original_units, reconstructed_units,
                   evidence_quality, rationale, source_document, loaded_by)
                VALUES ('2025',%s,%s,%s,%s,0,%s,'MANAGEMENT_RECONSTRUCTION',
                        %s,%s,'load_labor.py')
                ON CONFLICT (period, employee_key, objective_id)
                  DO UPDATE SET reconstructed_units = EXCLUDED.reconstructed_units,
                                payroll_wages = EXCLUDED.payroll_wages""",
                (name.upper(), name, objective, wages, amount,
                 RATIONALE, source.name))
            allocations += 1

    print(f"  {employees} employees, {allocations} allocations")
    print(f"  distributed wages {total:,}")
    check = one("""SELECT count(*) AS unsigned FROM v_certification_status
                    WHERE period='2025' AND NOT certified""")
    print(f"  awaiting certification: {check['unsigned']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
