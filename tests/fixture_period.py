"""A period with books in it, built from the control definitions.

CI applies the migrations to a bare database, which is right — the schema is
the thing under test and a suite that needs a seeded ledger is one nobody can
run on a fresh clone. But it meant the eleven cross-reference points were
only ever proved in the **empty** direction: `test_a_loaded_period_still_
evaluates` skipped, and the loaded direction lived in `scripts/reconcile.py`
against a foundation only a developer had.

So this builds a period. Small enough to hold in your head — three expense
accounts, one income account, two balance-sheet accounts, two people — and
built so that every one of the eleven is **evaluable** and **ties**.

## Built from what the controls compare, not from what makes them pass

That distinction is the whole risk here. A fixture reverse-engineered until
the register goes green encodes whatever the author guessed, and then the
controls agree with a misunderstanding for ever. Each figure below is
derived from the comparison the control actually makes, and the comment says
which:

    PL_FOOTING           Income − Expense − COGS + Other Income, against the
                         balance sheet's own "Net income" leaf
    BS_FOOTING           assets against liabilities and equity, rollups out
    GL_PROMOTE_COMPLETE  dated staging lines against ledger lines, counted
    GL_SUBTOTALS         printed against parsed, per account
    GL_PL_SECTION        ledger P&L-scope against the P&L, and per section
    GL_PL_ACCOUNT        the same, account by account
    GL_PL_COVERAGE       every account on both sides
    GL_BS_ACCOUNT        opening + movement against the sheet, per account
    GL_BS_COVERAGE       an account off the sheet closed at zero
    SEGMENTATION         the analytical view against the ledger it came from
    PAYROLL_REGISTER     the distribution against the ledger's wage accounts

## Two shapes it carries on purpose

**An account that closes at zero and is absent from the sheet.**
`GL_BS_COVERAGE` passes vacuously if every ledger account is on the sheet —
it counts absent accounts *carrying a balance*, and with nothing absent the
count is nought either way. So the fixture has one: a clearing account that
opens at nothing, moves twice, and closes flat. That is the case QuickBooks
actually produces, and a fixture without it proves the control only in the
direction where it cannot fail.

**Wage accounts and an effort distribution behind them.** The eleventh
control is the one that pays for itself, and it compares two different
things: the register's distributed wages against the ledger's wage accounts.
A fixture with wages in the ledger and no distribution would make it
unevaluable; one with both but no relationship between them would make it
fail. They are equal here because that is what tying means, and the test that
*breaks* it deliberately is what proves the control can still see a
difference.

Everything is written inside a transaction the caller rolls back, so nothing
here reaches a real record.
"""

from __future__ import annotations

from decimal import Decimal

#: A period far enough out that it cannot collide with a real one, and
#: obviously not a year anybody is accounting for.
PERIOD = "2099"

#: One income account and three expense accounts, two of which are wages.
#:
#: The amounts are round because a fixture is read by people; the *relations*
#: between them are what matter and they are stated below rather than left
#: for a reader to derive.
INCOME = Decimal("500000.00")
WAGES_ADMIN = Decimal("180000.00")
WAGES_PROGRAM = Decimal("120000.00")
RENT = Decimal("60000.00")

#: Income − Expense − COGS + Other Income. No COGS and no other income here,
#: so it is income less the three expense accounts. The balance sheet has to
#: carry exactly this in its "Net income" leaf, which is what PL_FOOTING
#: compares.
NET_INCOME = INCOME - WAGES_ADMIN - WAGES_PROGRAM - RENT      # 140,000.00

#: The distribution behind the wage accounts. PAYROLL_REGISTER compares this
#: total against every ledger P&L account whose name contains "Wages", so it
#: has to equal the two of them together.
PAYROLL = WAGES_ADMIN + WAGES_PROGRAM                          # 300,000.00

#: Balance sheet. Cash opens at 50,000 and takes the year's net income;
#: equity carries the same net income, which is what makes the sheet balance.
CASH_OPENING = Decimal("50000.00")
CASH_CLOSING = CASH_OPENING + NET_INCOME                       # 190,000.00
EQUITY_OPENING = CASH_OPENING

#: The account that closes at zero and is therefore absent from the sheet —
#: the case GL_BS_COVERAGE exists to check and the only one in which it can
#: fail.
CLEARING = Decimal("2500.00")

#: (account, leaf, section, amount) — the P&L, which the ledger must agree
#: with account by account and section by section.
PL_ACCOUNTS = (
    ("Income:4010 Grant income",            "4010 Grant income",     "Income",  INCOME),
    ("Expenses:Payroll:5110 Admin Wages",   "5110 Admin Wages",      "Expense", WAGES_ADMIN),
    ("Expenses:Payroll:5120 Program Wages", "5120 Program Wages",    "Expense", WAGES_PROGRAM),
    ("Expenses:Occupancy:5300 Rent",        "5300 Rent",             "Expense", RENT),
)

#: (account, leaf, side, amount). `v_gl_bs_account` joins the sheet on the
#: **leaf** — the last segment of the ledger's account path — because the
#: sheet's path and the chart's path never match. So the leaves here are the
#: leaves of the ledger accounts below.
BS_ACCOUNTS = (
    ("Assets:Current:1010 Cash",            "1010 Cash",       "ASSET",     CASH_CLOSING),
    ("Equity:3010 Opening equity",          "3010 Opening equity", "EQUITY", EQUITY_OPENING),
    ("Equity:Net income",                   "Net income",      "EQUITY",    NET_INCOME),
)

#: (account, statement, section, amount, description) — the ledger.
#:
#: Two lines per P&L account rather than one, because a control that compares
#: sums is trivially satisfied by a single line and the interesting failures
#: are about lines going missing.
LEDGER = (
    ("Income:4010 Grant income",            "P&L", "Income",  INCOME / 2, "Q1 draw"),
    ("Income:4010 Grant income",            "P&L", "Income",  INCOME / 2, "Q2 draw"),
    ("Expenses:Payroll:5110 Admin Wages",   "P&L", "Expense", WAGES_ADMIN / 2, "GROSS January"),
    ("Expenses:Payroll:5110 Admin Wages",   "P&L", "Expense", WAGES_ADMIN / 2, "GROSS February"),
    ("Expenses:Payroll:5120 Program Wages", "P&L", "Expense", WAGES_PROGRAM, "GROSS January"),
    ("Expenses:Occupancy:5300 Rent",        "P&L", "Expense", RENT / 2, "H1 rent"),
    ("Expenses:Occupancy:5300 Rent",        "P&L", "Expense", RENT / 2, "H2 rent"),
    # The balance sheet side. Cash takes the net income; the clearing account
    # moves and comes back to nothing.
    ("Assets:Current:1010 Cash",            "BALANCE_SHEET", "Assets", NET_INCOME, "Net movement"),
    ("Assets:Current:1099 Clearing",        "BALANCE_SHEET", "Assets", CLEARING, "In"),
    ("Assets:Current:1099 Clearing",        "BALANCE_SHEET", "Assets", -CLEARING, "Out"),
)

#: (account, amount). The opening balances, without which GL_BS_ACCOUNT
#: cannot be evaluated at all — it is the tie the system could not make until
#: the ledger's openings were kept.
OPENINGS = (
    ("Assets:Current:1010 Cash", CASH_OPENING),
    ("Assets:Current:1099 Clearing", Decimal("0.00")),
)


def build(cur, period: str = PERIOD) -> dict:
    """Write the whole period. The caller's transaction is rolled back."""
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (period, f"{period}-01-01", f"{period}-12-31"))

    # ── The import, so GL_PROMOTE_COMPLETE and GL_SUBTOTALS can be
    #    evaluated at all. Both read an ACCEPTED GENERAL_LEDGER batch.
    cur.execute("""INSERT INTO staging_batch
                     (period, report, original_name, storage_uri, sha256,
                      byte_size, status, uploaded_by, accepted_at, accepted_by)
                   VALUES (%s,'GENERAL_LEDGER','fixture.csv','/dev/null',
                           %s, 1, 'ACCEPTED', 'fixture', now(), 'fixture')
                   RETURNING batch_id""", (period, f"fixture-{period}"))
    batch = cur.fetchone()["batch_id"]

    # One dated staging line per ledger line. The control counts them against
    # each other, so a fixture with a different number on each side would
    # encode the very defect the control was written for.
    for i, (account, statement, section, amount, memo) in enumerate(LEDGER, 1):
        cur.execute("""INSERT INTO staging_line
                         (batch_id, row_number, natural_key, account,
                          txn_date, memo, amount)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (batch, i, f"{period}-{i:04d}", account,
                     f"{period}-06-30", memo, amount))

    # Printed against parsed, per account. Equal, because the fixture is the
    # tying case — the failing case is made by a test that moves one.
    by_account: dict[str, Decimal] = {}
    for account, _, _, amount, _ in LEDGER:
        by_account[account] = by_account.get(account, Decimal(0)) + amount
    for account, total in by_account.items():
        cur.execute("""INSERT INTO staging_subtotal
                         (batch_id, account, printed_total, parsed_total)
                       VALUES (%s,%s,%s,%s)""", (batch, account, total, total))

    # ── The ledger itself.
    cur.execute("""INSERT INTO ledger_import (period, source_name, sha256,
                                              row_count, imported_by)
                   VALUES (%s,'fixture',%s,%s,'fixture')
                   RETURNING import_id""",
                (period, f"fixture-{period}", len(LEDGER)))
    import_id = cur.fetchone()["import_id"]
    for i, (account, statement, section, amount, memo) in enumerate(LEDGER, 1):
        # `line_id` is text and assigned by the loader rather than defaulted,
        # because it has to be stable across a re-import — the promote path
        # dedupes on a natural key and a serial would make every re-run a
        # fresh set of lines.
        cur.execute("""INSERT INTO ledger_line
                         (line_id, import_id, period, txn_date, account,
                          payee, description, amount, statement, section,
                          source_key)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (f"FIX-{period}-{i:04d}", import_id, period,
                     f"{period}-06-30", account, "Fixture Vendor", memo,
                     amount, statement, section, f"{period}-{i:04d}"))

    for account, amount in OPENINGS:
        cur.execute("""INSERT INTO gl_opening (period, account, amount)
                       VALUES (%s,%s,%s)""", (period, account, amount))

    # ── The two statements.
    for account, leaf, section, amount in PL_ACCOUNTS:
        cur.execute("""INSERT INTO pl_account
                         (period, account, leaf, section, amount)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (period, account, leaf, section, amount))
    for account, leaf, side, amount in BS_ACCOUNTS:
        cur.execute("""INSERT INTO bs_account
                         (period, account, leaf, side, amount, is_rollup)
                       VALUES (%s,%s,%s,%s,%s,false)""",
                    (period, account, leaf, side, amount))

    # ── The effort distribution behind the wage accounts.
    #
    # PAYROLL_REGISTER compares this against every P&L account whose name
    # contains "Wages". Two people, and between them exactly what the ledger
    # carries — which is what tying means, and what a deliberately broken
    # copy has to be able to disturb.
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal,
                                               is_final)
                   VALUES ('FIXTURE',%s,'Fixture objective','PROGRAM',
                           false,true)
                   ON CONFLICT DO NOTHING""", (period,))
    for key, name, wages in (("FIXA", "Fixture Admin", WAGES_ADMIN),
                             ("FIXP", "Fixture Programme", WAGES_PROGRAM)):
        cur.execute("""INSERT INTO labor_allocation
                         (period, employee_key, employee_name, objective_id,
                          payroll_wages, original_units, evidence_quality,
                          rationale, source_document)
                       VALUES (%s,%s,%s,'FIXTURE',%s,1,'CORROBORATED',
                               'Built by tests/fixture_period.py',
                               'fixture')""",
                    (period, key, name, wages))

    return {"period": period, "batch_id": batch, "import_id": import_id,
            "net_income": NET_INCOME, "payroll": PAYROLL,
            "ledger_lines": len(LEDGER)}


def add_line(cur, info: dict, account: str, statement: str, section: str,
             amount, memo: str) -> None:
    """One more line, in the ledger and in the import it came from.

    `ledger_line` is append-only — the schema refuses an UPDATE outright,
    "correct by superseding, never by editing" — so a test that wants a
    different ledger adds a correcting entry, which is what the books
    actually do. A credit against a wage account is precisely the shape of
    the $45,000 the eleventh control caught.

    It writes the staging line too. Without that, `GL_PROMOTE_COMPLETE` goes
    open on every such test and reports a defect in whatever the test was
    really about — the staged and the landed have to stay in step unless a
    test is deliberately breaking that one.
    """
    period = info["period"]
    n = info["ledger_lines"] + 1
    info["ledger_lines"] = n
    cur.execute("""INSERT INTO staging_line
                     (batch_id, row_number, natural_key, account, txn_date,
                      memo, amount)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (info["batch_id"], n, f"{period}-{n:04d}", account,
                 f"{period}-09-30", memo, amount))
    cur.execute("""INSERT INTO ledger_line
                     (line_id, import_id, period, txn_date, account, payee,
                      description, amount, statement, section, source_key)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (f"FIX-{period}-{n:04d}", info["import_id"], period,
                 f"{period}-09-30", account, "Fixture Vendor", memo, amount,
                 statement, section, f"{period}-{n:04d}"))


def register(cur, period: str = PERIOD) -> list[dict]:
    """The eleven, as the system reports them."""
    cur.execute("""SELECT control, state, ties, evaluable, variance,
                          exceptions, left_value, right_value
                     FROM v_statement_reconciliation
                    WHERE period = %s ORDER BY seq""", (period,))
    return cur.fetchall()
