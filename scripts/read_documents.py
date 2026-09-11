#!/usr/bin/env python3
"""Read the text of the documents that were filed before anything read them.

    PYTHONPATH=. python3 scripts/read_documents.py            # what it would do
    PYTHONPATH=. python3 scripts/read_documents.py --write

Forty-three documents were on file and `evidence.extracted_text` and
`evidence.page_count` were NULL on every one — columns four things could have
used and nothing had ever written. Uploads read the text now
(`storage.read_text`); this is for the ones that arrived before that, the way
`retype_documents.py` repaired the rows written before the content type was
sniffed.

Like that script, it is one of the few things permitted to read a stored path
backwards, and for the same reason: the bytes are on the volume and the row
is the only thing that knows where.

**Three answers, kept apart.** NULL means nobody has read it. An empty string
means read, and there is nothing extractable — a scanned agreement is thirty
six pages of image, and that is a fact about the document rather than a
failure to look. Text means read. Collapsing the first two would turn "this
cannot be checked" into "this checks out", which is the whole reason the
register could carry a citation to a clause that does not exist.

Reads nothing it has already read: a row with a non-NULL `extracted_text` is
left alone unless `--again` is given.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage                                      # noqa: E402
from app.db import execute, query                            # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="record what was read; without it, say only")
    ap.add_argument("--again", action="store_true",
                    help="re-read rows that already carry text")
    args = ap.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    rows = query("""SELECT evidence_id, uri, filename, mime_type, byte_size,
                           extracted_text IS NULL AS unread
                      FROM evidence ORDER BY received_at, evidence_id""")
    read = blank = already = gone = skipped = 0
    for r in rows:
        if not r["unread"] and not args.again:
            already += 1
            continue
        path = Path(r["uri"])
        if not path.exists():
            print(f"  NO FILE   {r['evidence_id']}  {r['filename'][:48]}",
                  file=sys.stderr)
            gone += 1
            continue
        raw = path.read_bytes()
        text, pages = storage.read_text(raw, r["mime_type"] or "")
        if text is None:
            skipped += 1
            continue
        # Said, because it is the interesting answer. A PDF with pages and
        # no text in them is the one that explains an uncited agreement.
        note = ""
        if len(text.strip()) < 200:
            note = f"  ← {pages or 0} page(s), no text layer"
            blank += 1
        print(f"  {r['evidence_id']}  {(r['filename'] or '')[:44]:44} "
              f"{len(text):>7} chars{note}")
        read += 1
        if args.write:
            execute("""UPDATE evidence SET extracted_text = %s, page_count = %s
                        WHERE evidence_id = %s""",
                    (text, pages, r["evidence_id"]))

    print(f"\n  {read} read"
          + (f", {blank} of them with no text layer" if blank else "")
          + (f", {already} already read" if already else "")
          + (f", {skipped} in a format with no text to read" if skipped else "")
          + (f", {gone} whose bytes are not on this volume" if gone else ""))
    if not args.write:
        print("  nothing written — pass --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
