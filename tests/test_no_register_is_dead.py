"""Nothing in the schema may be read by something and written by nothing.

This shape has now appeared twelve times — `space_partition`,
`rate.superseded_by`, the three `evidence` fact columns, `award_budget_line`,
`donation_rate`, the three `lane_*` override tables, `carve_out`,
`constraint_result`, `ledger_revision` — and every one was found by somebody
reading one area closely. `CLAUDE.md` has said *"assume there is a fifth"*
for months, which is a note to self rather than a check, and a note to self
is the hand-kept map applied to defects.

So: derive every table and column from the database, ask what could write
each, and fail on one that something reads and nothing writes. There is no
list of tables in here to fall out of date — the database is the list, the
same way `tests/test_sql_is_real.py` hands the schema the code rather than
asserting things about it.

**The allowlist is the part that has to stay honest.** An allowlist is how
this test becomes the thing it replaced, so two rules: every entry carries a
reason, and an entry that is no longer needed **fails the test**. The
allowlist can only shrink by somebody noticing, which is the opposite of how
the twelve got there.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Written by nothing on purpose, each with the reason. Anything here is a
#: decision somebody made, not an oversight — which is the whole difference
#: between this list and the twelve defects that preceded it.
EXPECTED_UNWRITTEN: dict[str, str] = {
    # ── Money that has not moved ──────────────────────────────────────
    "invoice.paid_on": (
        "No payment is recorded against any invoice. `receipt` is the live "
        "register for money in, and `drive_reverse` names this missing link "
        "rather than inventing one."),
    "invoice.paid_amount": (
        "With invoice.paid_on: the receipt register is empty, so nothing "
        "has a payment amount to record against an invoice."),
    "invoice.milestone_id": (
        "All four America Makes awards are cost reimbursement invoiced "
        "monthly and no statement of work carries a CLIN, a deliverable "
        "value or an acceptance date. The column is for a contract shape "
        "YBI does not have."),
    "invoice.restates": (
        "Nothing in this system issues an invoice, so nothing can issue one "
        "superseding another. A restatement is recorded in `restatement`, "
        "measured against the invoice already on file."),
    "invoice.rate_id": (
        "The rate an invoice was billed under. The three on file were "
        "issued before this system existed, at the 10% de minimis, and "
        "nothing here issues a new one."),

    # ── A citation with no document behind it ─────────────────────────
    # The `award_term.evidence_id` shape, twice more. Both carry a `citation`
    # in text and neither links the document it cites, so nothing can ask
    # whether the document contains what was claimed — which is what
    # `v_award_citation_check` was built to do for award terms. Recorded
    # here rather than fixed blind: what each should point at is a judgment.
    "chart_split_driver.evidence_id": (
        "The 2026 split drivers carry a citation in text and no link to the "
        "document behind it — the `award_term.evidence_id` shape in a "
        "second place. What each should point at is the controller's call."),
    "in_kind_claim.evidence_id": (
        "As chart_split_driver.evidence_id: the claim records a "
        "valuation_basis and a source_document as text, and links no "
        "document row."),
    "in_kind_claim.superseded_at": (
        "No in-kind claim has been restated. The column is the house "
        "supersession pattern, present before anything needed it."),

    # ── The facilities and equipment side, which has no door yet ──────
    "asset.footprint_sqft": (
        "Read by v_equipment_subsidy and v_lab_space_consumed; no route "
        "sets it. The equipment side of the facilities model is a question "
        "for the controller, not something to fill in blind."),
    "asset.market_hourly_rate": (
        "With asset.footprint_sqft: no route sets an hourly rate, so the "
        "equipment subsidy cannot be valued. v_equipment_subsidy reports "
        "NULL rather than zero, which is the honest answer."),
    "asset.actual_hourly_rate": (
        "With asset.market_hourly_rate: what was actually charged for use "
        "of a machine has no door either."),
    "asset.unit_id": (
        "Which suite an asset stands in. The asset register came from a "
        "fixed-asset schedule that has no such column, and nobody has "
        "walked the building against it."),
    "asset.disposal_proceeds": (
        "No asset has been disposed of in the period on the record."),

    # ── Present before anything needed them ───────────────────────────
    "lane.archived_at": (
        "A lane is a question somebody asked; none has been retired yet."),
    "lane_decision_override.base_decision": (
        "Migration 057 let a lane try a line the queue has not reached, so "
        "an override need not have a decision underneath it to point at."),
    "rate.lane_id": (
        "A rate computed over a lane rather than the baseline. No rate on "
        "the comparison screen, ever — a lane is not sealed, so it has no "
        "rate, and `rate_lane_check` is what holds that."),
    "project_claim.withdrawn_reason": (
        "Nothing withdraws a project claim. A claim that should not have "
        "been approved is superseded by the next one, which is how the rest "
        "of this record corrects itself."),
    "note.in_reply_to": (
        "Notes do not thread. A note is a remark on a thing, and nothing "
        "in the system replies to one."),
    "note.resolved_at": (
        "With note.in_reply_to: a note is not a ticket and nothing closes "
        "one."),
    "note.resolved_by": (
        "With note.resolved_at: nothing closes a note, so nobody is "
        "recorded as having closed it."),
    "staging_batch.rejected_reason": (
        "A staged batch that fails its controls is refused at preview and "
        "never lands as a rejected row."),
    "staging_batch.supersedes": (
        "With staging_batch.rejected_reason: a re-import is a new batch "
        "and nothing links it to the one before."),
    "staging_line.parse_warning": (
        "The parsers refuse a file they cannot read rather than staging a "
        "line with a warning attached to it."),
    "staging_line.matched_line_id": (
        "With staging_line.parse_warning: promote matches on a natural key "
        "at the time it runs and records no match on the staged row."),
}


def source() -> str:
    parts = []
    for d in ("app", "scripts"):
        for p in (ROOT / d).rglob("*"):
            if p.suffix in (".py", ".sql") and "__pycache__" not in str(p):
                parts.append(p.read_text(errors="ignore"))
    return "\n".join(parts)


def trigger_bodies() -> str:
    from app.db import query
    return "\n".join(r["src"] for r in query("""
        SELECT prosrc AS src FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'"""))


def views() -> dict[str, str]:
    from app.db import query
    return {r["viewname"]: r["definition"] for r in query(
        "SELECT viewname, definition FROM pg_views WHERE schemaname='public'")}


# ── Tables ────────────────────────────────────────────────────────────

def test_no_table_is_read_and_written_by_nothing():
    """`carve_out` is why this exists.

    It held the 2 CFR 200.465 facilities carve-out. `POST /api/rates/compute`
    applied that carve-out correctly in memory — $932,254.78 of a
    $1,678,057.27 overhead pool — and never wrote it down, while
    `v_pool_balance`, `v_rate_buildup` and the `/review/rate` screen all read
    the table, found nothing, and reported that nothing had been carved out.
    The largest adjustment in the rate model, absent from the workpaper an
    auditor reads, with a control-shaped view stating the opposite.
    """
    from app.db import query
    src = source() + "\n" + trigger_bodies()
    vs = views()
    dead = []
    for r in query("""SELECT table_name FROM information_schema.tables
                       WHERE table_schema='public' AND table_type='BASE TABLE'
                       ORDER BY table_name"""):
        t = r["table_name"]
        if any(re.search(rf"{verb}\s+{t}\b", src, re.I)
               for verb in (r"INSERT\s+INTO", "UPDATE", "COPY", r"DELETE\s+FROM")):
            continue
        readers = [v for v, d in vs.items() if re.search(rf"\b{t}\b", d)]
        readers += ["source"] if re.search(rf"(FROM|JOIN)\s+{t}\b", src, re.I) else []
        if readers:
            dead.append(f"{t} — read by {', '.join(readers[:4])}, written by nothing")
    assert not dead, (
        "a table that looks usable and is filled by nothing is an invitation "
        "to fill it again, and everything reading it is answering with an "
        "empty set as though that were a fact:\n  " + "\n  ".join(dead))


# ── Columns ───────────────────────────────────────────────────────────

def written_columns() -> set[tuple[str, str]]:
    """Every (table, column) something could write, scoped to its table.

    Table-scoped on purpose. A first draft matched `SET ... col =` and
    `"col":` anywhere in the source, which is wrong in both directions at
    once: it reported `milestone.delivered_on` dead — it is written through
    a dict of state to column name in `contracts.py` — and reported
    `invoice.milestone_id` written, because some unrelated `UPDATE` had a
    `WHERE milestone_id = %s` within its span. Both are the same mistake:
    a column belongs to a table, and a check that forgets which is the
    hand-kept map in a new costume.

    The dynamic case is handled by file rather than by pattern: a column
    name appearing as a quoted string in a file that also writes that table
    is treated as written. That errs toward silence, which is the right
    direction here — a test that argues against correct code is worse than
    no test, and the allowlist-pruning test below covers the other way.
    """
    files = []
    for d in ("app", "scripts"):
        for f in (ROOT / d).rglob("*"):
            if f.suffix in (".py", ".sql") and "__pycache__" not in str(f):
                files.append(f.read_text(errors="ignore"))
    files.append(trigger_bodies())

    written: set[tuple[str, str]] = set()
    for text in files:
        touched = set()
        # The `(?:--[^\n]*\n\s*)*` is not decoration. `load_labor.py` puts a
        # three-line comment between its column list and its SELECT, and
        # without this the loader that writes the entire payroll
        # distribution reads as writing nothing. That is this repository's
        # own recorded mistake — a detector that was itself an instance of
        # the class it detects, because semicolons hid inside `--` comments.
        for m in re.finditer(
                "INSERT\\s+INTO\\s+(\\w+)\\s*\\(([^;]*?)\\)\\s*"
                "(?:--[^\\n]*\\n\\s*)*(VALUES|SELECT|ON\\s+CONFLICT)",
                text, re.I | re.S):
            t = m.group(1).lower()
            touched.add(t)
            for c in re.split(r"[,\s]+", m.group(2)):
                c = c.strip().strip('"').lower()
                if c:
                    written.add((t, c))
        # UPDATE <table> [alias] SET <clause> — the clause ends at WHERE,
        # RETURNING, the end of the statement or the end of the string.
        for m in re.finditer(
                "UPDATE\\s+(\\w+)[^;]*?\\bSET\\b(.*?)"
                "(?:\\bWHERE\\b|\\bRETURNING\\b|;|\x22\x22\x22)",
                text, re.I | re.S):
            t = m.group(1).lower()
            touched.add(t)
            for c in re.findall(r"(\w+)\s*=", m.group(2)):
                written.add((t, c.lower()))
        for m in re.finditer(r"NEW\.(\w+)\s*:?=", text):
            for t in touched or {"*"}:
                written.add((t, m.group(1).lower()))
        # A column named as a string, in a file that writes its table.
        for t in touched:
            for c in re.findall(r"""['"](\w+)['"]""", text):
                written.add((t, c.lower()))
    return written


def unwritten_columns() -> list[str]:
    from app.db import query
    src = source()
    written = written_columns()
    out = []
    for r in query("""
        SELECT c.table_name, c.column_name, c.column_default, c.is_generated
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_name = c.table_name AND t.table_schema = c.table_schema
         WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
         ORDER BY c.table_name, c.ordinal_position"""):
        t, col = r["table_name"].lower(), r["column_name"].lower()
        if r["column_default"] or r["is_generated"] == "ALWAYS":
            continue                         # the database writes it
        if (t, col) in written or ("*", col) in written:
            continue
        if not re.search(rf"\b{col}\b", src):
            continue                         # read by nothing either
        out.append(f"{r['table_name']}.{r['column_name']}")
    return out


def test_no_column_is_read_and_written_by_nothing():
    """`rate.superseded_by` and the three `evidence` fact columns.

    A column that looks usable and is filled by nothing is worse than an
    absent one: `v_rate_buildup` filtered on `superseded_by`, which is a
    no-op, and presented four SUPERSEDED rates as the rate on file.
    """
    found = set(unwritten_columns())
    unexpected = sorted(found - set(EXPECTED_UNWRITTEN))
    assert not unexpected, (
        "read by something and written by nothing. Give it a writer, drop "
        "it, or add it to EXPECTED_UNWRITTEN with the reason it is "
        "deliberately empty:\n  " + "\n  ".join(unexpected))


def test_the_allowlist_cannot_outlive_its_entries():
    """The rule that stops this test becoming the thing it replaced.

    An allowlist nobody prunes is a hand-kept map of what the code does, and
    that has been wrong every single time it has appeared here. So an entry
    that is no longer unwritten — because somebody gave the column a writer,
    or dropped it — fails until it is removed.
    """
    from app.db import query
    live = {f"{r['table_name']}.{r['column_name']}" for r in query("""
        SELECT table_name, column_name FROM information_schema.columns
         WHERE table_schema='public'""")}
    found = set(unwritten_columns())
    stale = sorted(k for k in EXPECTED_UNWRITTEN
                   if k in live and k not in found)
    gone = sorted(k for k in EXPECTED_UNWRITTEN if k not in live)
    assert not stale, (
        "these are written now, so the reason recorded for them is no longer "
        "true — remove them from EXPECTED_UNWRITTEN:\n  " + "\n  ".join(stale))
    assert not gone, (
        "these columns no longer exist — remove them from "
        "EXPECTED_UNWRITTEN:\n  " + "\n  ".join(gone))


def test_every_allowed_entry_says_why():
    thin = sorted(k for k, v in EXPECTED_UNWRITTEN.items() if len(v.strip()) < 25)
    assert not thin, (
        "an allowlist entry with no reason is the defect wearing a "
        "permission slip:\n  " + "\n  ".join(thin))
