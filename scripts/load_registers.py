#!/usr/bin/env python3
"""Transcribe every register that is not already in.

    PYTHONPATH=. python3 scripts/load_registers.py

One line in `scripts/seed.sh` for what used to be seven, and the point is
not the line count. The seven were a list of loaders in a shell script and
`app/foundation.py` needed the same list to bring a rebuilt deployment
back — and two lists of one thing is the defect that module is named after,
one level up. So the list is `foundation.REGISTERS` and this walks it; the
boot walks the same one.

Nothing here is a judgment. Every step reads a document already in the image
and writes what it says. The ledger, the contract provisions, the projects
and the eleven control points are not on the list, because each writes
through the API as a person and `refuse_issued_password` means a boot has
nobody to be — they stay where a person runs them.

Safe to run twice, which is why `seed.sh` does: a register already in is
skipped by name, and the two steps that need the documents filed find them
on the second pass.

    --list      print the list and what each one is for, and write nothing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import foundation                                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Load the transcribed registers.")
    ap.add_argument("--list", action="store_true",
                    help="print the list and write nothing")
    args = ap.parse_args()

    if args.list:
        for r in foundation.REGISTERS:
            print(f"\n{r.name}\n  scripts/{r.script} "
                  f"{' '.join(r.args)}".rstrip())
            print(f"  counted by       {r.loaded}")
            print("  run              " + ("every time; the loader is its "
                                           "own guard" if r.always else
                                           "only when that count is nought"))
            print(textwrap.fill(r.why, 72, initial_indent="  ",
                                subsequent_indent="  "))
        return 0

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    # The walk says what it did through the log, the same way it does at
    # boot, so a person reading a seed and a person reading a deploy are
    # reading the same sentences.
    logging.basicConfig(level=logging.INFO, format="  %(message)s",
                        stream=sys.stdout)
    logging.getLogger("ybi.db").setLevel(logging.WARNING)

    done = foundation.ensure_registers()
    print(f"{len(done)} of {len(foundation.REGISTERS)} register(s) "
          f"transcribed this run" + (f": {', '.join(done)}" if done else
                                     " — everything else was already in"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
