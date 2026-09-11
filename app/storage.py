"""Where a file goes on the volume, decided in one place.

Three routes write documents — the QuickBooks importer, the evidence route
and the document inbox everybody in the organisation has — and until now all
three built their own path inline, so every file in the engagement landed in
one of two flat directories named by hash. That works for a machine and is
useless to a person: an auditor handed the volume sees four thousand files
called `9b9bee496040ace6_…` and no way to tell a lease from a timesheet
without joining to the database first.

**The database is the index; this tree is for people.** A path is derived
from what the row already says — period, kind, category — and is never parsed
back to recover it. Nothing reads a directory to decide what a document is.
That rule is what keeps the tree a convenience rather than a second source of
truth that can disagree with the first, and it is why moving a file by hand
breaks nothing except the ability to find it.

The layout:

    <YBI_STORAGE_DIR>/              the mounted volume; on Railway /srv/storage
      README.txt                    written at boot, says what this is
      source/<period>/<report>/     the QuickBooks and payroll exports
      foundation/<category>/        what governs the engagement, not one period
      evidence/<period>/<kind>/     everything attached to the cost record

`foundation/` is deliberately not period-nested. A subrecipient agreement
signed in 2023 governs cost incurred in 2025 and will govern 2026; filing it
under a year is filing it under the wrong question. The year it belongs to is
in the filename and in `evidence.period`, where something can be queried on
it.

There is no inbox directory. An unattached document is a queue — it is what
`v_evidence_inbox` selects — and giving that queue a folder would mean a file
had to be moved when somebody made a judgment about it, which is a second
index and a way for the two to drift.

Filenames keep the `<sha16>_<original name>` shape they have always had. The
hash prefix is what makes two people sending the same scan one document, and
the original name after it is what makes the directory readable.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.settings import settings

#: Every path in the system hangs off this. On Railway it must equal the
#: volume mount path — anything written outside it is on the container
#: filesystem, which is discarded on the next deploy.
ROOT = Path(settings.storage_dir)

SOURCE = ROOT / "source"
FOUNDATION = ROOT / "foundation"
EVIDENCE = ROOT / "evidence"

#: Kinds that describe a document governing the engagement rather than
#: supporting one period's figure, and the category each files under.
#:
#: This mapping is the whole mechanism: nobody chooses a folder. An uploader
#: says what a document *is* — which they know — and the tree follows. A kind
#: that is not here is period evidence, which is the safe default, because
#: mis-filing a subrecipient agreement under 2025 costs a few seconds of
#: browsing while mis-filing an invoice out of its period hides it from the
#: year it belongs to.
#:
#: Deliberately conservative. `lease` is not here: the building lease is
#: foundational but a comparable lease uploaded to support a market-rate
#: analysis is evidence, and the kind alone cannot tell them apart. A
#: mapping that guesses would move the second one out of the period it
#: belongs to, which is the failure that is hard to notice.
FOUNDATION_KINDS = {
    "award-agreement": "awards",
    "award-modification": "awards",
    "subrecipient-agreement": "awards",
    "audited-financial-statements": "financial-statements",
    "single-audit": "financial-statements",
    "form-990": "tax-filings",
    "general-ledger": "accounting-records",
    "profit-and-loss": "accounting-records",
    "balance-sheet": "accounting-records",
    "trial-balance": "accounting-records",
    "grant-reconciliation-workbook": "accounting-records",
    "payroll-register": "accounting-records",
    "cost-policy": "policies",
    "travel-policy": "policies",
    "procurement-policy": "policies",
    "rate-agreement": "rate-agreements",
    "nicra": "rate-agreements",
}

#: The folders `foundation/` opens with — exactly the categories above, so
#: every one of them is a folder something actually lands in. An empty one is
#: a visible question: no written cost policy on file is a finding waiting to
#: happen, and it should be apparent from the tree rather than discovered in
#: fieldwork.
FOUNDATION_CATEGORIES = tuple(sorted(set(FOUNDATION_KINDS.values())))

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str, *, fallback: str = "other") -> str:
    """A directory name from a free-text field.

    `evidence.kind` is a text column, not an enum, and the inbox lets somebody
    type their own. So this has to survive `Market rate analysis (2025)`,
    an empty string and a filename someone pasted in by mistake. It truncates
    rather than refusing: a directory named after the first sixty characters
    of a sentence is still findable, and refusing would mean a document that
    cannot be stored because of how its label was typed.
    """
    out = _SLUG.sub("-", (text or "").strip().lower()).strip("-")
    return out[:60].strip("-") or fallback


def stored_name(sha256: str, filename: str | None) -> str:
    """`<sha16>_<original name>`, with the original name made safe.

    `Path(...).name` is doing real work: a filename is attacker-supplied on
    every one of these routes, and `../../etc/passwd` reaching a write would
    be the whole game. It strips any directory part, so what is left cannot
    escape the directory it is joined to.
    """
    return f"{sha256[:16]}_{Path(filename or 'document').name}"


def source_path(period: str, report: str, sha256: str, filename: str) -> Path:
    """A report as QuickBooks exported it, before anything is read out of it."""
    return SOURCE / slug(period, fallback="unknown-period") / \
        slug(report, fallback="report") / stored_name(sha256, filename)


def evidence_path(period: str, kind: str, sha256: str, filename: str) -> Path:
    """Where a document goes, given what it is.

    The one entry point the upload routes call. A foundational kind lands in
    `foundation/<category>/`; everything else is evidence for a period. The
    decision lives here rather than in the routes so that the inbox, the
    evidence route and any future importer cannot disagree about it.
    """
    category = FOUNDATION_KINDS.get(slug(kind, fallback="document"))
    if category:
        return foundation_path(category, sha256, filename)
    return EVIDENCE / slug(period, fallback="unknown-period") / \
        slug(kind, fallback="document") / stored_name(sha256, filename)


def foundation_path(category: str, sha256: str, filename: str) -> Path:
    """What governs the engagement rather than sitting inside one period."""
    return FOUNDATION / slug(category, fallback="other") / \
        stored_name(sha256, filename)


def place(path: Path, raw: bytes) -> Path:
    """Write the bytes, creating whatever directories that needs.

    Returns the path so a caller can store it. Directories are made here
    rather than at boot because kinds and periods are open sets — the skeleton
    below is a courtesy, not the full shape of the tree.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


README = """\
YBI cost allocation — document storage
======================================

This volume holds every document in the engagement. The PostgreSQL database
is the index: the `evidence` and `staging_batch` tables carry the SHA-256, the
period, the kind, who sent it in and what it supports. This tree exists so a
person can find a document without querying for it.

  source/<period>/<report>/   the QuickBooks and payroll exports as received
  foundation/<category>/      what governs the engagement across periods —
                              awards, audited statements, 990s, policy
  evidence/<period>/<kind>/   everything supporting a figure in the record

Filenames are `<first 16 of the SHA-256>_<the name it was sent under>`. The
hash prefix is why the same scan sent twice is one document.

Nothing here is read to decide what a document is. Paths are derived from the
database row, never parsed back into one. Moving a file by hand therefore
breaks only the ability to find it — and the register will then report the
document missing on download, which is the correct and visible failure.

Do not delete anything in this tree. A document referenced by a sealed
decision set is part of the audit record.
"""


def ensure_skeleton() -> list[str]:
    """Create the top of the tree and drop a README in it. Idempotent.

    Run at boot. The point is that somebody who opens the volume on the first
    day sees the shape of the thing and a note saying what it is, rather than
    an empty directory that gives them no way to tell a correctly-configured
    mount from a broken one.
    """
    made: list[str] = []
    for d in (SOURCE, FOUNDATION, EVIDENCE,
              *(FOUNDATION / c for c in FOUNDATION_CATEGORIES)):
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            made.append(str(d))
    readme = ROOT / "README.txt"
    current = readme.read_text() if readme.exists() else None
    if current != README:
        readme.write_text(README)
    return made
