#!/usr/bin/env python3
"""Point each award at the executed agreement it was read out of.

    PYTHONPATH=. python3 scripts/link_agreements.py

Run after the documents are filed. `scripts/seed.sh` loads the contract
provisions at step five and the documents at step six — the provisions hang
off the awards, and the awards come from the invoice load — so the terms
genuinely are recorded before the paper arrives, and something has to close
the loop afterwards.

Which filename fragment identifies an award's agreement is a fact nobody can
derive, and it lives on `award.agreement_name` (migration `058`) rather than
here. This does the matching and nothing else: a second copy of that mapping
in a script is the shape that produced two coverage figures six-fold apart.

Also reads the text of anything filed before uploads did
(`scripts/read_documents.py` is the same job standing alone), because a
citation cannot be checked against a document nothing has read.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, query                            # noqa: E402


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    unnamed = query("""SELECT award_id FROM award
                        WHERE agreement_name IS NULL ORDER BY award_id""")
    for row in unnamed:
        # Said, not skipped quietly. An award whose agreement nobody has
        # named cannot have a citation checked against anything, and
        # v_award_citations reports it unevaluable rather than clean.
        print(f"  NO AGREEMENT NAMED  {row['award_id']}", file=sys.stderr)

    execute("""UPDATE award a SET agreement_evidence_id = e.evidence_id
                 FROM evidence e
                WHERE a.agreement_evidence_id IS NULL
                  AND a.agreement_name IS NOT NULL
                  AND e.kind = 'subrecipient-agreement'
                  AND e.filename LIKE '%' || a.agreement_name || '%'""")
    execute("""UPDATE award_term t SET evidence_id = a.agreement_evidence_id
                 FROM award a
                WHERE a.award_id = t.award_id
                  AND t.evidence_id IS NULL
                  AND a.agreement_evidence_id IS NOT NULL""")

    rows = query("""SELECT award_id, agreement, page_count,
                           agreement_is_an_image, terms, found,
                           not_in_document, untestable, unevaluable
                      FROM v_award_citations ORDER BY award_id""")
    for r in rows:
        doc = (r["agreement"] or "").split("_")[-1] or "— none on file"
        note = ""
        if r["agreement_is_an_image"]:
            note = f"  ← {r['page_count']} pages, no text layer"
        elif r["not_in_document"]:
            note = f"  ← {r['not_in_document']} cite a clause it does not contain"
        print(f"  {r['award_id']:16} {doc[:42]:42} "
              f"{r['found']}/{r['terms']} found{note}")

    bad = sum(r["not_in_document"] for r in rows)
    blind = sum(r["unevaluable"] for r in rows)
    print(f"\n  {len(rows)} award(s)"
          + (f", {bad} provision(s) citing a clause the agreement does not "
             f"contain" if bad else "")
          + (f", {blind} that cannot be checked at all" if blind else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
