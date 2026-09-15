"""The record is 2025. A governing document carries its own date.

    *"The system should have the GL, PL, BS, all invoices for 2025 that are
    federal, the labor breakdowns, etc. ALL supporting documents ONLY FOR
    2025."*

Three April-2026 invoices sat in the register of record for the life of the
system — a sample of the *shape* of an America Makes invoice, loaded by
`load_invoices.py` before the year's own register existed. Nothing downstream
asked whether a register of three was the year: four published figures were
computed off it, three restatements were measured against it, and the run
sheet printed those three as the position. Migration `089` removed them.

**This is the check that says it rather than me remembering it.** Every
register of *transactions* is swept and must hold one period only. The
population comes from `information_schema` — there is no list of tables in
here to fall out of date, which is `test_sql_is_real.py`'s rule and
`test_no_register_is_dead.py`'s.

`evidence` is the one exception and it is a rule rather than a hole: a
document is filed under **its own** date, because the five executed
agreements the year was worked under are 2021–2024, two prior-year Forms 990
and two audited statements are comparatives an auditor asks for, Hybrid's
Modification 001 is dated 22 January 2026 and is what the fourth award's
ceiling ties on, and `2026_YBI_Fixed-Asset-Schedule.xls` is where the 263
assets came from. Every one of those supports 2025. Only a transaction
belongs to a period.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

#: Filed under its own date rather than the period it supports, with the
#: reason. An entry here is a claim somebody has to defend, so it carries one
#: — the allowlist rule `test_no_register_is_dead.py` already follows.
DATED_BY_THE_DOCUMENT = {
    "evidence": "A governing document carries its own date: the executed "
                "agreements are 2021-2024, the comparative 990s and audited "
                "statements are prior years, Hybrid's Modification 001 is "
                "January 2026 and the asset schedule is the 2026 print of "
                "the register the 263 assets came from.",
    "fiscal_period": "The table of periods. It is the list, not a row in it.",
}


def _periods(cur, table: str) -> list[str]:
    cur.execute(f'SELECT DISTINCT period FROM "{table}" ORDER BY 1')
    return [r[0] for r in cur.fetchall()]


def test_every_transaction_register_holds_one_year():
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, con.cursor() as cur:
        cur.execute("""SELECT c.table_name
                         FROM information_schema.columns c
                         JOIN pg_tables t ON t.tablename = c.table_name
                                         AND t.schemaname = 'public'
                        WHERE c.table_schema = 'public'
                          AND c.column_name = 'period'
                        ORDER BY 1""")
        tables = [r[0] for r in cur.fetchall()]
        assert tables, "no table carries a period — is this the right database?"

        loaded = {t: _periods(cur, t) for t in tables}
        loaded = {t: p for t, p in loaded.items() if p}
        if not loaded:
            pytest.skip("nothing is loaded on this database")

        stray = {t: p for t, p in loaded.items()
                 if t not in DATED_BY_THE_DOCUMENT and p != ["2025"]}
        assert not stray, (
            "these registers hold something other than 2025:\n  "
            + "\n  ".join(f"{t}: {', '.join(p)}" for t, p in stray.items())
            + "\nThe record is one year. A row dated outside it is either "
              "example data, which does not belong here, or a document, "
              "which belongs in `evidence` under its own date.")


def test_the_exception_is_named_and_earns_it():
    """An allowlist entry with no reason is the defect wearing a permission
    slip, and one that is no longer needed is the list growing where it
    should only shrink."""
    import psycopg

    for table, why in DATED_BY_THE_DOCUMENT.items():
        assert len(why) >= 40, f"{table} is exempt for no stated reason"

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, con.cursor() as cur:
        cur.execute("""SELECT tablename FROM pg_tables WHERE schemaname='public'""")
        real = {r[0] for r in cur.fetchall()}
        gone = set(DATED_BY_THE_DOCUMENT) - real
        assert not gone, f"exempt tables that no longer exist: {sorted(gone)}"

        for table in DATED_BY_THE_DOCUMENT:
            if _periods(cur, table) == ["2025"]:
                pytest.fail(
                    f"{table} holds only 2025, so it no longer needs its "
                    f"exemption. Take it off the list — an allowlist that "
                    f"can only grow stops meaning anything.")


def test_no_invoice_is_dated_outside_the_period_it_is_filed_under():
    """The defect `089` removed, stated as a property rather than as three
    invoice numbers. A loader that writes the period as a constant puts an
    April-2026 invoice in the 2025 register, and every figure taken off that
    register then compares thirteen months to twelve."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, con.cursor() as cur:
        cur.execute("""SELECT invoice_number, period, invoice_date
                         FROM invoice
                        WHERE period <> to_char(invoice_date, 'YYYY')
                        ORDER BY invoice_number""")
        wrong = cur.fetchall()
        assert not wrong, (
            "invoice(s) filed under a year their own date does not name: "
            + "; ".join(f"{n} filed {p}, dated {d}" for n, p, d in wrong))
