"""The deployment brings itself back.

A Postgres service was rebuilt and the record came back with the schema and
without the people in it. Migrations run on startup, so every table, view,
constraint and trigger returned on the first boot — and nothing could sign
in, because the six accounts were made by `scripts/provision.py`, which is a
thing somebody runs from a laptop against a URL. Anything that only exists
because a person remembered to run it does not survive a recovery.

That is the shape this repository keeps finding, applied to the deployment
rather than to a table: *the twenty-six contract provisions read out of the
executed agreements lived in one developer's database and in no script.*
`scripts/seed.sh` was written for exactly that lesson and it stops one step
short — it writes the steps down, and still waits for somebody to run them.

So this module is what the boot itself does, beside `run_migrations()`:

    the six accounts           on the organisation's password, so the round
                               opens the way it is documented to
    the foundational documents content-addressed, so a second boot files
                               nothing twice
    the registers              everything that is a transcription of one of
                               those documents — see **The registers** below
    the guides                 the manuals and the three generated PDFs,
                               readable in the library like anything else

**Four rules, and the first one is the whole of it.**

**It never overwrites.** An account that exists is left exactly as it is —
its password, its name, its rank, its portfolios. A boot that reset a
password would be a deploy that silently took an account away from the
person using it, and a deploy happens far more often than a recovery. The
same for a document: a row whose SHA-256 is already on file is skipped, not
rewritten.

**It opens an account on the organisation's password and never on one of its
own.** A new row gets `password_set_by = 'SEED'` and a random hash nobody
holds, so the only way in is `YBI_INITIAL_PASSWORD` — the Railway variable —
and `refuse_issued_password` still stops that session writing anything but
its own new password. No credential is invented here and none is at rest in
the image.

**It does nothing at all unless that variable is set.** Opening accounts
nobody can sign into is not a recovery, it is a row. The gate is also what
keeps this out of the way of `scripts/provision.py`, which is the other door
to the same room: a development machine has no organisational password, so
the ladder script runs against an empty roster exactly as it always has.

**The roster, the document list and the register list live here and are
read from here.** `provision.py` and `seed_documents.py` import the first
two, and `scripts/seed.sh` walks the third rather than keeping its own copy
of it. Two lists of the same six people is the defect this file is about,
one level up.

What it deliberately does **not** restore is everything that is a judgment:
the classifications, the seal, the rate, the certification, the
restatement. A boot that classified would be the machine putting its name
on the seal.

**The ledger is on neither side of that line, and putting it on the wrong
one cost the deployment its books.** An earlier draft of this paragraph
read *"everything that is a judgment: the ledger, the classifications, the
seal, the rate"* — and a ledger is not a judgment, it is a transcription of
a document this same boot has already filed. What keeps the ledger itself
out is narrower and is not this rule at all: it is loaded through the API as
a person, and `refuse_issued_password` means a boot has nobody to be. See
**The registers**.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app import storage
from app.auth import shared_initial_password, unusable_password_hash
from app.db import execute, one, query

log = logging.getLogger("ybi.foundation")

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DOCUMENTS = ROOT / "docs" / "source-documents"
GUIDE_DIR = ROOT / "docs"


# ── The people ───────────────────────────────────────────────────────

ALL_PORTFOLIOS = ("CONTROLLER", "INVENTORY", "PROJECT", "FACILITIES", "OFFICE")


@dataclass(frozen=True)
class Person:
    """One account, and why it holds what it holds.

    `why` is not decoration: `actor_portfolio.reason` is NOT NULL with a
    ten-character floor, because a grant of authority over the cost record
    with no stated reason is the next person's puzzle.
    """

    email: str
    display_name: str
    role: str
    employee_key: str | None
    portfolios: tuple[str, ...] = ()
    why: str = ""


#: The organisation, in the order the ladder runs.
#:
#: Everybody whose email address is actually known. The payroll register has
#: forty-three people in it but carries surnames only, and an account at a
#: guessed address is an account nobody can sign into — so the rest are
#: surfaced as a gap on the administrator's screen instead of invented here.
SYSTEM_ADMIN = Person(
    "eric.c.wagner@gmail.com", "Eric Wagner", "SYSTEM_ADMIN", None)

ORG_ADMIN = Person(
    "bewing@ybi.org", "Barb Ewing", "ORG_ADMIN", "EWING", (),
    "Chief executive and the organisation's administrator: sets up the "
    "finance accounts and hands out access. Deliberately holds no portfolio "
    "— provisioning people and judging cost are different jobs.")

STAFF = (
    # tmetzinger@, not tom@. Read off the From: header of his own email of
    # 10 September 2026 — the four YBI addresses in this roster are all
    # confirmed from that one message rather than from the naming
    # convention, which is the difference between a lookup and a guess.
    # An account at the wrong address is an account nobody can sign into.
    Person("tmetzinger@ybi.org", "Tom Metzinger", "CONTROLLER", None,
           ("CONTROLLER",),
           "Controller for the 2025 engagement: classification, the seal, and "
           "the rate that follows from it."),
    Person("sgaffney@ybi.org", "Stephanie Gaffney", "CONTROLLER", "GAFFNEY",
           ALL_PORTFOLIOS,
           "Project manager. Holding every portfolio for the 2025 push so the "
           "classification backlog is not gated on one person; the intent is "
           "PROJECT once the year is closed."),
    Person("hruby@ybi.org", "Heidi Ruby", "CONTROLLER", "RUBY", ALL_PORTFOLIOS,
           "Facilities and inventory manager. Holding every portfolio for the "
           "2025 push; the intent is FACILITIES and INVENTORY once the year "
           "is closed."),
    Person("auditor@ybi.org", "Engagement Auditor", "AUDITOR", None),
)

ROSTER = (SYSTEM_ADMIN, ORG_ADMIN, *STAFF)

#: Addresses by the name everybody says out loud, derived from the roster
#: above rather than written a second time.
#:
#: Fifty-two literal `tom@ybi.org` across twenty-seven scripts is what this
#: replaces — every drive, the classification log and the request issuer each
#: carrying its own copy of one person's address. That was the naming
#: convention rather than a lookup, and when `079` retired the old address
#: every one of them would have exited on a 401 against a system that was
#: working perfectly: the proof harness going red for a reason that is not a
#: defect is how a reader learns to ignore it.
#:
#: There is one list of who these people are, and this reads it.
#: Keyed on the first name because that is what the scripts were saying —
#: `sign_in(base, "tom@ybi.org")` means *sign in as Tom*. A first draft
#: offered `CONTROLLER_EMAIL` instead and picked by position: Stephanie and
#: Heidi hold CONTROLLER too, so it returned Tom only because he is listed
#: first, which is a hand-kept map wearing a derivation.
EMAIL = {p.display_name.split()[0].lower(): p.email for p in ROSTER}
assert len(EMAIL) == len(ROSTER), (
    "two people on the roster share a first name, so EMAIL would silently "
    "drop one of them; key it on something that tells them apart")

#: The organisation's administrator holds no portfolio, and the reason column
#: is where that is said rather than inferred from an empty set.
BARB_REASON = ORG_ADMIN.why

NDA_REASON = (
    "Engagement lead for the 2025 cost allocation initiative, under a "
    "non-disclosure agreement with YBI. Reads the record at the same level "
    "as the organisation's administrator; holds no portfolio and makes no "
    "cost judgments.")

#: Why a portfolio granted here says it was granted here.
#:
#: `granted_by` names the organisation's administrator because that is who
#: grants a portfolio, and it would be a lie by omission to leave it at that:
#: she did not sit down and decide this on the morning of the recovery. The
#: reason column is where the difference belongs, and it is the first thing
#: anybody reading the grant will see.
RESTORED_REASON = (
    "Restored by the deployment bootstrap after the record was rebuilt — the "
    "portfolio this account held before. Recorded against the organisation's "
    "administrator because a portfolio is hers to grant; confirm it on "
    "/people. Original reason: ")


# ── The documents ────────────────────────────────────────────────────
#
# Lifted from scripts/seed_documents.py, which imports it from here now.
# Two lists of the same eighteen documents is the defect this module is
# about, one level down.

#: filename -> (kind, period, what it is for)
#:
#: Spelled out rather than inferred from the directory name. A directory is a
#: convenience; the kind is a claim about what a document is, and every one of
#: these was read before it was written down. The period is the year the
#: document is *of*, which for an agreement is the year it was signed — not
#: the year whose cost it governs, because that is every year until it ends.
DOCUMENTS: dict[str, tuple[str, str, str]] = {
    "2023-09-08_NCDMM_SubRecipient_Agreement_Hybrid-Phase-2.pdf": (
        "subrecipient-agreement", "2023",
        "Hybrid Phase 2. The cost-share obligation of $104,000 is in here, "
        "and it has never been tracked."),
    "2024-09-24_NCDMM_SubRecipient_Agreement_Proj88_Last-Tactical-Mile.pdf": (
        "subrecipient-agreement", "2024",
        "Project 88, Last Tactical Mile. The 10% de minimis basis being "
        "restated is the one this agreement set."),
    "2023_YBI_Audited_Financial_Statements_and_Single_Audit.pdf": (
        "audited-financial-statements", "2023",
        "Prior-prior year. Where a reviewer checks whether this year's "
        "treatment is a change in accounting."),
    "2024_YBI_Audited_Financial_Statements_and_Single_Audit.pdf": (
        "audited-financial-statements", "2024",
        "Prior year, and the comparative figures in the 2025 statements."),
    "2023_Form-990_ProPublica_full-filing.pdf": (
        "form-990", "2023",
        "As filed. Functional expense allocation to compare against."),
    "2024_Form-990_ProPublica_full-filing.pdf": (
        "form-990", "2024",
        "As filed. The 2025 return has to be consistent with this or explain "
        "why it is not."),
    "2025_General-Ledger_QuickBooks.xlsx": (
        "general-ledger", "2025",
        "The ledger under review, as exported. Schedule A."),
    "2025_Profit-and-Loss_QuickBooks.xlsx": (
        "profit-and-loss", "2025",
        "One of the three statements the eleven cross-reference points tie."),
    "2025_Balance-Sheet_QuickBooks.xlsx": (
        "balance-sheet", "2025",
        "Carries the opening balances the ledger is proved against."),
    "2025_Grant-Reconciliation-Workbook_controller.xlsx": (
        "grant-reconciliation-workbook", "2025",
        "The controller's own workbook. The source of the 22.45% fringe "
        "rate that the payroll register shows to be 21.90%."),
    "2024-01-30_NCDMM_SubRecipient_Agreement_Drive-AM.pdf": (
        "subrecipient-agreement", "2024",
        "Drive AM. $1,103,594, no cost share named in §4.3 and none in the "
        "budget — while the statement of work expects a 1:1 ratio. A scan: "
        "the text here came from OCR and the figures were read off the "
        "image."),
    "2024-02-05_NCDMM_SubRecipient_Agreement_SRA-0350_ICAM-Digital-Engineering.pdf": (
        "subrecipient-agreement", "2024",
        "ICAM Digital Engineering Workforce, $1,000,690, cost reimbursement "
        "no fee, under Grant N00174-20-1-0031 (CFDA 12.300). Attachment 3 "
        "budgets indirect at 10% of ODCs only — $27,500 on $275,000 — with "
        "no indirect at all on $655,190 of labor."),
    "2026-01-22_NCDMM_Hybrid_20240061_Modification-001.pdf": (
        "award-modification", "2026",
        "Extends Hybrid to 30 June 2026 and raises the obligation by "
        "$12,366 to $512,409. The $104,000 cost share is carried forward "
        "unchanged, so the obligation that was never tracked is now live "
        "in a second year."),
    "2021-07-13_EDA_CD-450_Award_06-79-06300.pdf": (
        "grant-agreement", "2021",
        "The EDA award behind the building assets. A scan with no text "
        "layer — it needs OCR before anything can be read out of it."),
    "2025-11-17_EDA_Closeout-Letter_06-79-06300.pdf": (
        "closeout-letter", "2025",
        "Closes EDA 06-79-06300. Final project cost $2,376,344, EDA share "
        "$1,903,179, disbursed $1,712,861, leaving $188,214.54 still to be "
        "drawn. Records retained three years from this date."),
    "2022-02-02_JobsOhio_Grant-Agreement_SFPN-2021-493762-VCG.pdf": (
        "grant-agreement", "2022",
        "JobsOhio, $475,000 toward $2,428,974 of project investment "
        "including $2,092,861 of building fixed assets. Not federal, which "
        "is what makes it the other half of the funding-source question."),
    "2026_YBI_Fixed-Asset-Schedule.xls": (
        "asset-register", "2026",
        "The asset register. $23,419,573.64 of cost against $10,452,995.43 "
        "of accumulated depreciation. Carries life, method and in-service "
        "date per asset — and no funding source column, which is the one "
        "field 200.436(b) turns on."),
    "2025_YBI_Lease-Schedule.xlsx": (
        "lease-schedule", "2025",
        "Twenty-six tenant leases by building with monthly and annual rent. "
        "The tenant side of the facilities carve-out; square footage is "
        "still missing."),
}


# ── The guides ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Guide:
    """One document somebody is handed, rather than one they are asked to
    judge.

    `audience` is whose job it describes, and it decides what the Guidebook
    puts at the top — not what it hides. The manual inside the application is
    assembled from what the reader holds so that it never describes a screen
    they cannot open; a *shelf* is the other case. Hiding the auditor's
    manual from an employee would teach them the shelf is short, and there is
    nothing on any of these pages they may not read.
    """

    path: str        # relative to docs/
    title: str
    note: str
    audience: str    # "everybody", a portfolio, "admin", or a role


#: In the order they are read. The audience values are the same vocabulary
#: `tabsFor` uses, because a second spelling of "who is this for" is a map
#: kept by hand in two places.
GUIDES = (
    Guide("manuals/everybody.md", "Everybody",
          "The screens every account has: your time, your documents, and "
          "what the system is doing with them.", "everybody"),
    Guide("manuals/controller.md", "The controller",
          "The queue, the seal and the rate that follows from it — the whole "
          "of the classification job in the order it is done.", "CONTROLLER"),
    Guide("manuals/administrator.md", "The administrator",
          "Accounts, access and the roster: who may do what, and how to give "
          "somebody their way in.", "admin"),
    Guide("manuals/facilities-and-inventory.md", "Facilities and inventory",
          "The two measurements the rate cannot be computed without: the "
          "square footage of each building, and which assets federal money "
          "paid for.", "FACILITIES"),
    Guide("manuals/classification-team.md", "Working the classification",
          "Reviewing the 757 working positions, citing the paper behind "
          "them, and the timesheet every person on the payroll signs for "
          "themselves.", "CONTROLLER"),
    Guide("manuals/auditor.md", "The auditor",
          "What to read and in what order, and where every figure on a "
          "workpaper comes from.", "AUDITOR"),
    Guide("MONDAY_RUNBOOK.md", "The run sheet",
          "Where the record stands and what is left to do, generated from "
          "the crosscheck and never written over a figure that does not tie.",
          "CONTROLLER"),
    Guide("MONDAY_GUIDEBOOK.pdf", "The illustrated walk",
          "Every screen in the run sheet, photographed, in the order you "
          "meet them.", "everybody"),
    Guide("MONDAY_ANCHOR.pdf", "The recommendations",
          "Every recommendation the record makes, to read and tick.",
          "CONTROLLER"),
    Guide("BARB_ONE_PAGE_AM.pdf", "America Makes, on one page",
          "The four awards, what was billed against them and what the "
          "restatement asks for — the decisions, without the arithmetic.",
          "admin"),
)

#: The year the guides describe. Not a document period — nothing about a
#: guide reaches the cost record — but the manuals are written about this
#: engagement and the shelf says so.
GUIDE_PERIOD = "2025"


# ── The registers ────────────────────────────────────────────────────
#
# The books, and everything else that is a **transcription** of a document
# already in the image.
#
# `ensure_documents()` files `2025_General-Ledger_QuickBooks.xlsx` into the
# library as bytes and reads no row out of it. `scripts/load_assets.py`
# parses `2026_YBI_Fixed-Asset-Schedule.xls` out of the same directory, and
# waited for somebody to run it. So a rebuilt service came back with the
# paper on the shelf and every register behind it empty — measured on a
# replayed first boot: six accounts, eighteen documents, and nought ledger
# lines, nought assets, nought invoices, nought labour rows, with all eleven
# steps of the walk reading NO DATA or WAITING.
#
# That is this module's own defect, one level down. Its opening says
# `scripts/seed.sh` *"writes the steps down, and still waits for somebody to
# run them"* — and then it did two of the eleven steps and waited for
# somebody for the other nine. **Anything that only exists because a person
# remembered to run it does not survive a recovery**, the ledger included,
# because a ledger is not a judgment. It is a transcription of a document,
# like the document it is transcribed from.
#
# The line this draws is not the one the docstring above used to draw:
#
#   transcription   the effort distribution, the working calendar and the
#                   hours log under it, 263 assets, four awards, their
#                   budget schedules, the text of the agreements
#   judgment        the classification, the seal, the rate, the
#                   certification, the restatement — and none of those is in
#                   `seed.sh` either, so nothing here moves that line
#
# **Four of `seed.sh`'s steps are deliberately not on this list**, for one
# reason: they write through the API as a person, and
# `refuse_issued_password` means an account still on the organisation's
# password can write nothing at all. The ledger, the contract provisions,
# the projects and the eleven control points reach the record when somebody
# who has set their own password runs them. A boot cannot do that, and the
# fact that it cannot is the rule working rather than a gap in it.
#
# And a fifth declines on its own authority. `load_invoices_2025.py` checks
# the register against `3900 Grant Income` before it writes, and against a
# ledger of 0.00 it writes nothing and says why — *"the register has to
# agree with the ledger before it is worth having"*. It belongs with the
# ledger, so it stays with the half a person runs.


@dataclass(frozen=True)
class Register:
    """One transcription, and the question that says it is already in.

    `loaded` is the whole of *it never overwrites*, held here rather than
    trusted to seven scripts. A register with anything in it has been loaded
    and its loader is not run at all — so a loader that turns out not to be
    idempotent still cannot reach a record somebody is using. All seven were
    measured idempotent; the point is that the guarantee does not depend on
    that staying true.

    `always` is the one exception, and there is exactly one of it. No count
    on `award` can tell *load_awards has run* from the placeholder row `004`
    seeds and `058` names, so a count cannot be the skip. The loader carries
    its own rule instead — it fills a ceiling that is zero and an
    agreement_name that is NULL, and otherwise prints `exists` — and it is
    run every time. `loaded` still counts, because **whether it changed
    anything is read from the record and never from the fact that it ran.**
    The first draft appended it to the list of what it had transcribed on
    every redeploy, so a boot that did nothing reported a load.

    `args` is the argv `scripts/seed.sh` passes, verbatim. A loader must not
    behave one way for a person and another way for the boot.
    """

    name: str
    script: str
    args: tuple[str, ...]
    loaded: str
    why: str
    always: bool = False


#: Everything a boot can transcribe, in the order it has to happen.
REGISTERS: tuple[Register, ...] = (
    Register(
        "the effort distribution", "load_labor.py", (),
        "SELECT count(*) FROM labor_allocation",
        "The distribution the whole rate model rests on, read off the "
        "controller's workbook: $1,835,047.17 across forty-three people. "
        "The fringe base is taken over this and not over the ledger's wage "
        "accounts, which is the eleventh control point."),
    Register(
        "the calendar and the hours log", "load_calendar.py", (),
        "SELECT count(*) FROM work_month",
        "YBI counts 261 work days and 2,088 hours in 2025 and takes no "
        "holiday out — their calendar, not a derived one. The hours log "
        "beneath it is the independent source `v_labor_hours_check` "
        "measures the distribution against. After the labour, because the "
        "log maps its objective headings through labor_objective_map."),
    Register(
        "the fixed-asset register", "load_assets.py", (),
        "SELECT count(*) FROM asset",
        "263 assets, $23,419,573.64 of cost, every printed subtotal tying. "
        "The funding source is deliberately not loaded: the schedule has no "
        "such column, which is 200.313(d)(1) unanswered and is exactly what "
        "Heidi answers one asset at a time."),
    Register(
        "the four awards", "load_awards.py", (),
        "SELECT count(*) FROM award WHERE agreement_name IS NOT NULL",
        "The ceiling, the term and the clause each was read out of. Run "
        "every time, because `004` seeds one of these four as a placeholder "
        "and `058` names it, so a count cannot tell a loaded register from "
        "an empty one. It is its own guard: it fills a ceiling that is zero "
        "and an agreement_name that is NULL, and otherwise prints `exists`.",
        always=True),
    Register(
        "the budget schedules", "load_award_budgets.py", (),
        "SELECT count(*) FROM award_budget",
        "What each award funds by category, which decides the line set on "
        "an invoice. A category named at zero and a category absent are "
        "different findings, and only a loaded schedule can tell them "
        "apart. After the awards, which it hangs off."),
    Register(
        "the text of the agreements", "read_documents.py", ("--write",),
        "SELECT count(*) FROM evidence WHERE extracted_text IS NOT NULL",
        "A citation with no document behind it is somebody's recollection. "
        "`_file()` reads a document as it files it, so on a boot this is "
        "already done and skips; it fires on a record whose evidence rows "
        "predate that, which is what it was written for."),
    Register(
        "the awards to their agreements", "link_agreements.py", (),
        "SELECT count(*) FROM award WHERE agreement_evidence_id IS NOT NULL",
        "Points each award at the paper it was read out of, so "
        "`v_award_citation_check` can ask the document whether the cited "
        "clause is in it. Needs the documents filed, which is why the walk "
        "is safe to run twice and `seed.sh` does."),
)


# ── Filing one document, the same way the upload route does ──────────

#: Addressed by filename, which is the key a guide has. These eight are
#: distinct, and the map is what stops a request naming a path of its own.
GUIDES_BY_NAME = {Path(g.path).name: g for g in GUIDES}


def _file(path: Path, kind: str, period: str, note: str, channel: str,
          uploaded_by: str | None, received_from: str) -> str | None:
    """Put one file on the volume and in the register. None if it is already.

    The shape is lifted from `POST /api/evidence/upload` and holds its three
    rules: the bytes decide the content type, `storage.place()` decides the
    path, and the SHA-256 decides identity — so this cannot file a second
    copy of a document somebody has already sent in, whichever door they
    used.
    """
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    held = one("SELECT uri FROM evidence WHERE sha256 = %s", (sha,))
    if held:
        # The register and the volume are two things and either can be the
        # one that was lost. A row whose bytes are gone is a library entry
        # that opens on nothing, and for these documents the bytes are in
        # the image — so put them back, at the path the row records rather
        # than at one derived again here. The database is the index; a
        # repair that moved the file would be the index and the tree
        # disagreeing, which is the whole thing storage.py exists to stop.
        uri = Path(held["uri"])
        if not uri.exists():
            storage.place(uri, raw)
            log.warning("put the bytes of %s back on the volume", uri)
        return None
    safe = path.name
    mime = storage.sniff_type(raw, safe)
    dest = storage.place(storage.evidence_path(period, kind, sha, safe), raw)
    text, pages = storage.read_text(raw, mime)
    eid = f"EV-{sha[:12]}"
    execute("""INSERT INTO evidence (evidence_id,period,kind,uri,sha256,
                                     received_from,byte_size,mime_type,
                                     ingest_channel,uploaded_by,filename,
                                     extracted_text,page_count,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (eid, period, kind, str(dest), sha, received_from, len(raw),
             mime, channel, uploaded_by, safe, text, pages, note))
    return eid


def _note(action: str, entity: str, entity_id: str, reason: str) -> None:
    """An audit row for something the deployment did, in its own name.

    `actor_id` is deliberately NULL and `actor` is the boot rather than a
    person. Naming an administrator here would put her signature on an act
    she was not present for, which is the one thing the audit trail is for.
    `SEAL`, `ACTOR_CREATE` and the rest of `v_activity`'s list carry this to
    the activity screen, so a recovery is visible rather than inferred.
    """
    execute("""INSERT INTO audit_log (actor, action, entity, entity_id, reason)
               VALUES ('deployment bootstrap', %s, %s, %s, %s)""",
            (action, entity, entity_id, reason))


# ── The four acts ────────────────────────────────────────────────────

def ensure_accounts() -> list[str]:
    """Open any of the six accounts that is missing. Touch none that is not.

    Returns the addresses opened, which is what the boot log prints.
    """
    opened: list[str] = []
    held = {r["email"]: r for r in query(
        "SELECT actor_id, email, role::text AS role FROM actor")}
    taken = {r["employee_key"] for r in query(
        "SELECT employee_key FROM actor WHERE employee_key IS NOT NULL")}

    for person in ROSTER:
        if person.email in held:
            continue
        # An EMPLOYEE must carry a key; nobody in this roster is one, so a
        # key already spoken for by a payroll account is dropped rather than
        # fought over. Two rows claiming one person is worse than one row
        # with a key somebody can add later on /people.
        key = person.employee_key
        if key and key in taken:
            log.warning("employee key %s is already held, opening %s without "
                        "it", key, person.email)
            key = None
        # provisioned_by stays NULL on purpose. The ladder trigger reads it
        # as "seeded; the roster shows it as such", which is the truth: no
        # person created this account.
        execute("""INSERT INTO actor (email, display_name, role, password_hash,
                                      employee_key, password_set_by)
                   VALUES (%s,%s,%s,%s,%s,'SEED')
                   ON CONFLICT (email) DO NOTHING""",
                (person.email, person.display_name, person.role,
                 unusable_password_hash(), key))
        if key:
            taken.add(key)
        opened.append(person.email)
        _note("ACTOR_CREATE", "actor", person.email,
              f"opened by the deployment bootstrap on the organisation's "
              f"password, as {person.role}")

    if not opened:
        return []

    ids = {r["email"]: r["actor_id"] for r in query(
        "SELECT actor_id, email FROM actor WHERE email = ANY(%s)",
        ([p.email for p in ROSTER],))}
    admin = ids.get(ORG_ADMIN.email)

    # Authority, and only for the accounts this run opened. A portfolio is a
    # grant over the cost record; adding one to an account somebody is
    # already using is not a restoration, it is a change.
    for person in ROSTER:
        if person.email not in opened or not person.portfolios or not admin:
            continue
        for portfolio in person.portfolios:
            execute("""INSERT INTO actor_portfolio (actor_id, portfolio,
                                                    granted_by, reason)
                       VALUES (%s,%s,%s,%s)""",
                    (ids[person.email], portfolio, admin,
                     RESTORED_REASON + (person.why or "none recorded")))

    # And the engagement lead's read of the client's books, granted by YBI's
    # own administrator to the account above her in rank. That direction is
    # deliberate and is the same one provision.py records: the data is
    # theirs, so they are who lets somebody read it.
    if SYSTEM_ADMIN.email in opened and admin:
        execute("""UPDATE actor SET record_access = true,
                                    record_access_reason = %s,
                                    record_access_granted_by = %s,
                                    record_access_granted_at = now()
                    WHERE email = %s AND NOT record_access""",
                (NDA_REASON, admin, SYSTEM_ADMIN.email))
    return opened


def ensure_documents() -> list[str]:
    """File any foundational document the register does not already carry."""
    if not SOURCE_DOCUMENTS.exists():
        log.warning("no %s in the image — the foundational documents cannot "
                    "be filed from here", SOURCE_DOCUMENTS)
        return []
    controller = one("""SELECT actor_id FROM actor
                         WHERE role = 'CONTROLLER' ORDER BY created_at LIMIT 1""")
    filed: list[str] = []
    for name, (kind, period, note) in DOCUMENTS.items():
        matches = sorted(SOURCE_DOCUMENTS.rglob(name))
        if not matches:
            log.warning("foundational document not in the image: %s", name)
            continue
        eid = _file(matches[0], kind, period, note, "UPLOAD",
                    controller["actor_id"] if controller else None,
                    "deployment bootstrap")
        if eid:
            filed.append(name)
            _note("EVIDENCE_UPLOAD", "evidence", eid,
                  f"filed by the deployment bootstrap: {name}")
    return filed


#: How long one transcription may take, and how long the whole walk may.
#:
#: `railway.json` waits 60 seconds for the first healthy answer, and the
#: lifespan runs before anything is served — so an unbounded walk is a
#: deployment that never comes up. Measured, the seven take 2.6 seconds
#: together; the budget is what stops a cold volume or a pathological
#: spreadsheet turning that into a failed deploy. Going over it is not a
#: loss: every step is skipped rather than half-done, and the next boot or
#: `scripts/seed.sh` picks up exactly where this one stopped.
REGISTER_TIMEOUT = 30
REGISTER_BUDGET = 40


def _rows_in(r: Register) -> int:
    """How many rows say this register is in.

    As a scalar subquery rather than by appending an alias: `count(*)` names
    its own column `count`, and a predicate ending in a WHERE clause cannot
    take an `AS` after it. Both were true of the first draft, which reported
    every register unreadable and — correctly — left all seven alone.
    """
    row = one(f"SELECT ({r.loaded}) AS n")
    return int(row["n"]) if row else 0


def ensure_registers() -> list[str]:
    """Transcribe every register that is not already in, in order.

    Run as a subprocess, with exactly the argv `scripts/seed.sh` uses, for
    two reasons that are worth keeping apart.

    **A parser must not be able to take the deployment down.** These read
    spreadsheets and PDFs off a volume; `restartPolicyMaxRetries` is 3 and
    the fourth outcome is a service that does not start. A register that is
    missing and says so is a far better answer than a healthcheck that never
    goes green — which this repository already records as *the worst shape a
    configuration fault can take*. So a failure is logged with what the
    loader actually said and the walk continues.

    **And there is one door.** Running the same command a person runs, rather
    than an imported entry point, is what stops a loader growing a boot-only
    path. It is also why `args` is `seed.sh`'s argv verbatim.

    Safe to run twice, and `seed.sh` does: once with the books, and once
    after the documents are filed, for the two steps that need them.
    """
    done: list[str] = []
    started = time.monotonic()
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(
               [str(ROOT)] + [q for q in os.environ.get("PYTHONPATH", "")
                              .split(os.pathsep) if q])}
    for r in REGISTERS:
        path = ROOT / "scripts" / r.script
        if not path.exists():
            log.warning("register loader not in the image: %s", r.script)
            continue
        try:
            before = _rows_in(r)
        except Exception as exc:                          # pragma: no cover
            log.warning("cannot tell whether %s is in (%s); leaving it alone",
                        r.name, exc)
            continue
        if before and not r.always:
            log.info("%s is already in (%d rows)", r.name, before)
            continue
        left = REGISTER_BUDGET - (time.monotonic() - started)
        if left <= 1:
            log.warning("the register walk is out of time; %s and anything "
                        "after it will be loaded on the next boot or by "
                        "scripts/seed.sh", r.name)
            break
        # The figure in the message is the one that was used. Capped by
        # what is left of the budget, so a run that was stopped at five
        # seconds must not report thirty — a log that states a number it did
        # not act on is the shape this repository keeps finding.
        allowed = int(min(REGISTER_TIMEOUT, left))
        try:
            out = subprocess.run(
                [sys.executable, str(path), *r.args], cwd=str(ROOT), env=env,
                capture_output=True, text=True, timeout=allowed)
        except subprocess.TimeoutExpired:
            log.warning("%s did not finish inside %ds and was stopped; "
                        "nothing it had not committed was written",
                        r.name, allowed)
            continue
        except Exception as exc:                          # pragma: no cover
            log.warning("%s could not be run: %s", r.name, exc)
            continue
        said = (out.stdout or out.stderr or "").strip().splitlines()
        tail = said[-1].strip() if said else ""
        try:
            after = _rows_in(r)
        except Exception as exc:                          # pragma: no cover
            # Never out of this function. The whole reason these run in
            # their own process is that a boot must come up; raising here
            # would hand back the failure mode the subprocess was for.
            log.warning("%s ran and cannot be read back (%s)", r.name, exc)
            continue
        if out.returncode != 0:
            # **Loud, because the next boot will not try again.** A loader
            # that wrote some of its rows and then failed leaves the
            # register non-empty, and non-empty is exactly what the skip
            # reads as *already in* — so a half-loaded register would be
            # treated as complete for ever, silently. The first draft
            # reported a non-zero exit as "not loaded" without looking, and
            # that is only true when nothing moved.
            if after != before:
                log.error("%s exited %d PART WAY THROUGH — %d rows where "
                          "there were %d. The next boot will read that as "
                          "already in and skip it: clear the register and "
                          "run scripts/load_registers.py. It said: %s",
                          r.name, out.returncode, after, before, tail[:200])
            else:
                log.warning("%s exited %d and loaded nothing: %s",
                            r.name, out.returncode, tail[:200])
            continue
        # What the loader said it did is not the question; whether the rows
        # moved is. A loader that declines on its own authority —
        # load_invoices_2025 against a ledger of 0.00 — exits 0 and writes
        # nothing, and a walk that called that a load would be reading the
        # loader's prose rather than the record.
        if after != before:
            done.append(r.name)
            log.info("loaded %s (%d rows)", r.name, after)
        elif after:
            log.info("%s is already in (%d rows)", r.name, after)
        else:
            log.info("%s had nothing to load yet: %s", r.name, tail[:200])
    return done


def guide_path(name: str) -> Path | None:
    """Where a guide lives on disk, or None if the name is not one.

    Guides are **not documents and must not be filed as evidence.** They were,
    for one morning: `ensure_guides()` put eight manuals and PDFs into
    `evidence`, which put them in the document register beside the eighteen
    foundational documents the 2025 audit rests on. The audit's register is
    the paper the engagement stands on — an agreement, a statement, a return,
    a ledger export — and a manual about how to use the software is none of
    those. A reviewer opening the library should find the lease and nothing
    that is not of that kind.

    So the shelf reads from the image instead. `foundation.GUIDES` names the
    files, they ship in `docs/`, and nothing about them touches the database:
    no row, no SHA, no period, no inbox, no library. The name is the key, and
    it is checked against the definition rather than joined against anything —
    a caller cannot ask for a path this module does not name.
    """
    guide = GUIDES_BY_NAME.get(name)
    if not guide:
        return None
    path = GUIDE_DIR / guide.path
    return path if path.exists() else None


def restore() -> dict[str, list[str]]:
    """Everything above, in order, or nothing at all.

    The gate is `YBI_INITIAL_PASSWORD`. Without it there is no way for
    anybody to sign into an account this would open, and `provision.py` —
    the other door to the same room — is the one that should run instead.
    """
    if not shared_initial_password():
        log.info("no organisation password is set, so the foundation "
                 "bootstrap stands down; scripts/provision.py is the other "
                 "door")
        return {}
    accounts = ensure_accounts()
    documents = ensure_documents()
    # After the documents, because two of the seven read them: the text of
    # the agreements, and the link from each award to the paper it was read
    # out of. Before nothing, because the four steps that need a person come
    # later and from somewhere else entirely.
    registers = ensure_registers()
    if accounts:
        log.warning("opened %d account(s) on the organisation's password: %s",
                    len(accounts), ", ".join(accounts))
    if documents:
        log.info("filed %d foundational document(s)", len(documents))
    if registers:
        log.info("transcribed %d register(s): %s",
                 len(registers), ", ".join(registers))
    # Guides are deliberately absent: they are served from the image by
    # `guide_path()` and are not documents in the cost record.
    return {"accounts": accounts, "documents": documents,
            "registers": registers}
