#!/usr/bin/env python3
"""Read every stored document and record what it actually is.

Both upload routes used to keep the content type the client sent, and the
seeding script sends `application/octet-stream` for everything. So a database
filled before that changed holds fourteen PDFs the library will not show,
because the column it reads says they are anonymous bytes.

This re-reads each file and writes back the type its bytes say it is, and the
name it arrived under where that was never recorded. It changes nothing else:
not the path, not the hash, not the identifier. Re-runnable, and quiet about
rows that are already right.

    PYTHONPATH=. python3 scripts/retype_documents.py [--dry-run]

It is a repair, not part of the loading path. A document filed after the
upload routes learned to read their own bytes arrives correct.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app import storage
from app.db import execute, open_pool, query


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would change, change nothing")
    args = ap.parse_args()

    open_pool()
    rows = query("""SELECT evidence_id, uri, coalesce(mime_type,'') AS mime,
                           coalesce(filename,'') AS filename
                      FROM evidence ORDER BY evidence_id""")

    changed = missing = 0
    for row in rows:
        path = Path(row["uri"])
        if not path.exists():
            # Said, not skipped silently. A row whose file is gone is a
            # finding — the index and the volume have parted company.
            print(f"  MISSING  {row['evidence_id']}  {path}", file=sys.stderr)
            missing += 1
            continue

        # The signatures this reads all sit in the first few bytes, and the
        # text check only looks at the first 4 KB. Reading a 9 MB scan in
        # full to answer that would be work for nothing.
        with path.open("rb") as fh:
            head = fh.read(8192)

        name = row["filename"] or storage.original_name(path.name)
        mime = storage.sniff_type(head, name)

        if mime == row["mime"] and name == row["filename"]:
            continue

        what = []
        if mime != row["mime"]:
            what.append(f"{row['mime'] or 'nothing'} -> {mime}")
        if name != row["filename"]:
            what.append(f"named {name}")
        print(f"  {row['evidence_id']}  {'; '.join(what)}")
        changed += 1
        if not args.dry_run:
            execute("UPDATE evidence SET mime_type=%s, filename=%s "
                    "WHERE evidence_id=%s", (mime, name, row["evidence_id"]))

    verb = "would change" if args.dry_run else "changed"
    print(f"\n{len(rows)} document(s), {verb} {changed}"
          + (f", {missing} missing from the volume" if missing else ""))
    # A missing file is a real problem and the exit code should say so even
    # when every type was already right.
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
