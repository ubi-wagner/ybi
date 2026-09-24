#!/usr/bin/env python3
"""Read the form of documents filed before the door started reading it.

`app/shapes.py` records a document's form as it arrives. This goes back for
the rows written before it existed, which is the same job
`retype_documents.py` did when the content type started being read from the
bytes and `read_documents.py` did when the text started being extracted.

    PYTHONPATH=. python3 scripts/read_shapes.py            # say what it would do
    PYTHONPATH=. python3 scripts/read_shapes.py --write

It reads the bytes off the volume at the path the row records, which is the
one direction `storage.py` allows: the database is the index and the tree is
for people, so a path is derived from a row and never parsed back into one.
A row whose bytes are gone is reported rather than skipped — a library entry
that opens on nothing is a finding.

**It re-reads on a new reader by default.** A shape taken by an older
version of the module is not wrong, it is older, and a register holding a
mixed population would be averaging two different readings together.
`--only-missing` keeps the old ones where that is what is wanted.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import shapes  # noqa: E402
from app.db import open_pool, query  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="record the shapes; without it nothing is written")
    ap.add_argument("--only-missing", action="store_true",
                    help="leave shapes an older reader took")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()

    rows = query("""SELECT e.evidence_id, e.filename, e.uri, e.mime_type,
                           e.kind, s.reader
                      FROM evidence e
                      LEFT JOIN document_shape s USING (evidence_id)
                     ORDER BY e.kind, e.filename""")
    todo = [r for r in rows
            if r["reader"] is None
            or (not args.only_missing and r["reader"] != shapes.READER)]
    if not todo:
        print(f"All {len(rows)} document(s) carry a shape from "
              f"{shapes.READER}. Nothing to do.")
        return 0

    print(f"{len(todo)} of {len(rows)} document(s) to read"
          f"{'' if args.write else ' (dry run — pass --write)'}:\n")
    read = gone = 0
    for r in todo:
        path = Path(r["uri"])
        if not path.exists():
            print(f"  {r['evidence_id']}  {r['filename']}: the bytes are not "
                  f"on the volume at {path} — left alone, and it is a "
                  f"finding rather than a skip")
            gone += 1
            continue
        if args.write:
            raw = path.read_bytes()
            shapes.record_shape(r["evidence_id"], raw, r["mime_type"] or "")
        print(f"  {r['evidence_id']}  {r['kind']:28} {r['filename']}")
        read += 1

    print(f"\n{read} read{'' if args.write else ' (nothing written)'}"
          f"{f', {gone} whose bytes are missing' if gone else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
