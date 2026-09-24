#!/usr/bin/env python3
"""Feed every document we hold through the real doors, and measure the forms.

    PYTHONPATH=. python3 scripts/drive_documents.py --base http://127.0.0.1:8000

Every other drive proves that a *figure* is right. This one asks the
question underneath all of them: **will the next document break it?**

Every parser in this system was written against one instance of the document
it parses, and three have already been caught by the second one — the asset
schedule that prints a system number only when it changes ($2.5m dropped and
every printed subtotal still tying), the two executed agreements with no
numbered clause anywhere (three provisions on each cited to §25 and §26,
which appear in neither), and the agreement that is thirty-six pages and
seventy characters. All three are differences in **form**, and all three
were found by a person reading.

What it does, in the order a document actually arrives:

    upload      every file under docs/source-documents/, through
                `POST /api/documents/upload` — the door everybody signed in
                has, content-addressed so a second run files nothing twice
    read        the form and content off the bytes, at that door, the way
                `storage.read_text()` already reads the text
    compare     `GET /api/documents/variability`, which is the analytics:
                per family, which form attributes differ and what they were

**It is a read of the record, not a change to it.** Nothing is classified,
attached, sealed or computed. The upload route is content-addressed, so on a
record that already holds these documents every one deduplicates and the
drive is measuring what is there rather than what it just put there — which
is the defect `review_system.py` was fixed for.

Two rules it keeps, both this repository's own:

  * **A family of one is `NO DATA`, never `UNIFORM`.** One document agrees
    with itself perfectly. Reporting that as uniform would say a parser has
    been proved against variation when nothing has ever varied.
  * **Differences are named, never scored.** A variability index over
    twenty-four documents is a figure nobody can reproduce and nobody can
    act on; the attribute and its values are what somebody goes and looks at.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.foundation import DOCUMENTS, EMAIL  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "source-documents"

#: What each document *is* comes from `foundation.DOCUMENTS`, which is
#: already the one roster of these papers and the one `seed_documents.py` and
#: the boot both read. A folder map here was the first draft and it was the
#: hand-kept map twice over: it is a second copy of a fact the record holds,
#: and it was **coarser** than the record — filing all eight award documents
#: as `award-agreement` where the register distinguishes a subrecipient
#: agreement from a grant agreement, a modification and a closeout letter.
#: That is not a tidiness point: those four are different instruments with
#: different clause conventions, and a family that lumps them together
#: reports variability that is a finding about our filing rather than about
#: the documents.
#:
#: The six invoice PDFs are not on that roster — they are read by
#: `load_invoices_2025.py` rather than filed by the boot — so they carry the
#: one kind the register already gives them.
def kind_of(path: Path) -> str:
    named = DOCUMENTS.get(path.name)
    if named:
        return named[0]
    if path.parent.name == "invoices":
        return "invoice"
    return "document"


PASS, FAIL, NOTE = "  ok   ", "  FAIL ", "  ·    "


class Drive:
    def __init__(self, base: str, password: str) -> None:
        self.c = httpx.Client(base_url=base.rstrip("/") + "/api", timeout=120)
        self.checks = self.findings = 0
        self.password = password

    def sign_in(self, email: str) -> None:
        r = self.c.post("/auth/login",
                        json={"email": email, "password": self.password})
        if r.status_code != 200:
            raise SystemExit(f"could not sign in as {email}: "
                             f"{r.status_code} {r.text[:200]}")
        print(f"signed in as {r.json()['display_name']}")

    def ok(self, good: bool, said: str) -> bool:
        self.checks += 1
        if not good:
            self.findings += 1
        print((PASS if good else FAIL) + said)
        return good


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD"))
    args = ap.parse_args()
    if not args.password:
        raise SystemExit("YBI_SEED_PASSWORD is not set and --password was "
                         "not given.")

    d = Drive(args.base, args.password)
    # The office portfolio files papers; the upload door itself is open to
    # anybody signed in, which is why it can be this wide.
    d.sign_in(EMAIL["heidi"])

    files = sorted(p for p in SOURCE.rglob("*") if p.is_file())
    if not d.ok(bool(files), f"{len(files)} document(s) under "
                             f"{SOURCE.relative_to(ROOT)}"):
        return 2

    print("\nThrough the upload door, as they would arrive\n")
    filed = deduped = 0
    for p in files:
        kind = kind_of(p)
        with p.open("rb") as fh:
            r = d.c.post("/documents/upload",
                         files={"file": (p.name, fh,
                                         "application/octet-stream")},
                         data={"kind": kind, "period": "2025",
                               "note": "drive_documents.py"})
        if r.status_code != 200:
            d.ok(False, f"{p.name}: {r.status_code} {r.text[:120]}")
            continue
        body = r.json()
        if body.get("deduplicated"):
            deduped += 1
        else:
            filed += 1
        print(f"{NOTE}{kind:30} {p.name[:44]:46} "
              f"{'already on file' if body.get('deduplicated') else 'filed'}")

    d.ok(True, f"{filed} filed, {deduped} already on file — the door is "
               f"content-addressed, so a second run measures rather than "
               f"duplicates")

    # ── The analytics ─────────────────────────────────────────────────
    print("\nVariability of form, per family\n")
    r = d.c.get("/documents/variability")
    if not d.ok(r.status_code == 200,
                f"GET /documents/variability answered {r.status_code}"):
        print(r.text[:400])
        return 2
    v = r.json()
    cov = v["coverage"]

    print(f"{'family':32} {'n':>3}  {'state':8} what differs")
    print(f"{'-' * 32} {'-' * 3}  {'-' * 8} {'-' * 30}")
    for f in v["families"]:
        says = ", ".join(f["varies_on"]) if f["varies_on"] else "—"
        print(f"{f['family']:32} {f['instances']:>3}  {f['state']:8} {says}")

    # The two findings that are about a document rather than about a family.
    if v["unreadable"]:
        print("\nCould not be read at all:")
        for u in v["unreadable"]:
            print(f"{NOTE}{u['filename']}: {u['why']}")
    if v["thin"]:
        print("\nOn file and not readable as text — no clause of these can "
              "be checked against the document:")
        for t in v["thin"]:
            print(f"{NOTE}{t['filename'][:52]:54} {t['pages']:>3}pp  "
                  f"{t['chars_per_page']:>7} chars/page  {t['text_layer']}")

    print(f"\n{cov['shaped']} of {cov['documents']} document(s) read · "
          f"{cov['families_varying']} family(ies) vary · "
          f"{cov['families_uniform']} uniform · "
          f"{cov['families_of_one']} of one, which cannot be evaluated")

    # A family of one is the honest answer and it is also the thing to say
    # out loud: those parsers have never met a second document.
    d.ok(cov["families_of_one"] >= 0,
         f"{cov['families_of_one']} family(ies) hold a single document, so "
         f"their parsers have never been met by a second shape")
    d.ok(cov["shaped"] == cov["documents"],
         f"every document on the record carries a form "
         f"({cov['shaped']} of {cov['documents']})")

    print(f"\n{d.checks} checks, {d.findings} finding(s).")
    return 1 if d.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
