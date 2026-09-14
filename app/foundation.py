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

**The roster and the document list live here and are read from here.**
`provision.py` and `seed_documents.py` import them rather than keeping their
own copies. Two lists of the same six people is the defect this file is
about, one level up.

What it deliberately does **not** restore is everything that is a judgment:
the ledger, the classifications, the seal, the rate. Those come from
`scripts/seed.sh` and from people. A boot that classified would be the
machine putting its name on the seal.
"""

from __future__ import annotations

import hashlib
import logging
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


# ── The three acts ───────────────────────────────────────────────────

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
    if accounts:
        log.warning("opened %d account(s) on the organisation's password: %s",
                    len(accounts), ", ".join(accounts))
    if documents:
        log.info("filed %d foundational document(s)", len(documents))
    # Guides are deliberately absent: they are served from the image by
    # `guide_path()` and are not documents in the cost record.
    return {"accounts": accounts, "documents": documents}
