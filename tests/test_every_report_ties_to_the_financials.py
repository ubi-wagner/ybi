"""Whether everything this system publishes ties to the financials, in one
place — and whether that place can be trusted.

Twenty-two control-shaped views and nothing collecting them, so *does every
report tie to the books* had twenty-two answers on twenty-two screens and the
reader kept the list. That is the hand-kept map at its purest, and this
repository has been wrong four times in one run of the system review for
exactly that shape.

`v_report_tie` is one row per report and anchor. Everything here holds the
three rules that make such a register worth reading rather than worth
dismissing:

  * **it reads controls and computes nothing** — a second derivation of a
    control is one figure computed twice, and the two can disagree;
  * **it speaks one vocabulary** — `084` shipped a walk step that passed a
    view's private words straight through and printed a state nothing
    renders, and `v_labor_hours_check` has four of its own;
  * **OPEN says how much, or what it wants** — which is `086`, `093` and
    `102`, the same defect three times in this family already.

Driven against a database inside a transaction that is rolled back. A sweep
of the migration text would be the fourth instance of a test asserting prose,
and `091` records what reading an applied migration is worth: the file and
the running database had drifted by a column and three functions.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

STATES = {"TIES", "OPEN", "NO DATA"}


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


@pytest.fixture()
def cur():
    """A cursor whose work is always rolled back."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        with _cur(con) as c:
            yield c
        con.rollback()


# ── The register speaks one vocabulary ───────────────────────────────

def test_every_state_is_one_of_the_three(cur):
    cur.execute("SELECT DISTINCT state FROM v_report_tie")
    said = {r["state"] for r in cur.fetchall()}
    assert said <= STATES, (
        f"the register is speaking a view's private vocabulary: {said - STATES}")


def test_every_anchor_names_what_it_ties_to(cur):
    """*Ties* with nothing said about *to what* is the citation-with-no-
    document shape: it cannot be checked, so it never is."""
    cur.execute("SELECT report, anchor, ties_to FROM v_report_tie")
    for r in cur.fetchall():
        assert (r["ties_to"] or "").strip(), (
            f"{r['report']} · {r['anchor']} ties to nothing in particular")


def test_no_anchor_speaks_sql(cur):
    """`v_rate_anchor` names its controls the way a database does, and the
    register passed four of them straight through — `WAGE_BASE_IS_THE_
    REGISTER` beside *The depreciation entry balances*, on the panel a
    reviewer reads first. The failure mode is never a broken screen: it is a
    screen that starts speaking SQL, which is this file's own phrase for
    `DONATION_RATE_MISSING` reaching the controller with no destination.

    So a new anchor still reaches the register — nothing falls off the end —
    and fails here until somebody writes the sentence.
    """
    cur.execute("SELECT report, anchor, ties_to, needs FROM v_report_tie")
    for r in cur.fetchall():
        # `needs` too: it is the sentence the controller acts on, and naming a
        # view in it is the same defect one column along.
        for field in ("anchor", "ties_to", "needs"):
            said = r[field] or ""
            assert "_" not in said or field == "needs", (
                f"{r['report']} · {r[field]} is a database identifier, not a "
                "sentence a reviewer reads")
            assert not re.search(r"\bv_[a-z_]+", said), (
                f"{r['report']} · {r[field]} names a view on the screen")


def test_an_open_anchor_says_how_much_or_what_it_wants(cur):
    """A control that reports OPEN and neither the variance nor the ask is a
    dead end, and a register that collects dead ends is a longer one. This is
    what `102` had to fix in the one report on the live record that does not
    tie: the state was right and `needs` had gone blank underneath it."""
    cur.execute("""SELECT report, anchor, variance, needs
                     FROM v_report_tie WHERE state = 'OPEN'""")
    for r in cur.fetchall():
        assert r["variance"] is not None or (r["needs"] or "").strip(), (
            f"{r['report']} · {r['anchor']} is OPEN and says nothing about why")


# ── It reads controls, and computes nothing ──────────────────────────

def test_every_arm_reads_a_control(cur):
    """Read from the running database rather than from `app/sql`, because
    editing an applied migration mutates nothing — `091` is a column and
    three functions that existed in the file and in no database for as long
    as they had been written."""
    cur.execute("SELECT pg_get_viewdef('v_report_tie', true) AS d")
    body = re.sub(r"\s+", " ", cur.fetchone()["d"])
    read = {m for m in re.findall(r"(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", body)}
    read -= {"arms"}                       # the register's own CTE
    assert read, "no relations found in the register at all"
    bare = {r for r in read if not r.startswith("v_")}
    assert not bare, (
        f"the register reaches past the controls to a base table: {bare}. "
        "A second derivation of a control is one figure computed twice.")


# ── The one line is the register, and never rounds it up ─────────────

def test_the_summary_is_the_register(cur):
    cur.execute("""SELECT period, anchors, ties, open, no_data, state,
                          open_anchors FROM v_report_tie_summary""")
    for s in cur.fetchall():
        assert s["ties"] + s["open"] + s["no_data"] == s["anchors"], (
            f"{s['period']}: the summary counts do not add to its anchors — "
            "which means the register is emitting a fourth state")

        if s["state"] == "TIES":
            assert s["open"] == 0 and s["no_data"] == 0, (
                f"{s['period']}: the summary reports TIES over "
                f"{s['open']} open and {s['no_data']} that cannot be "
                "evaluated. A control that cannot be evaluated has not passed.")
        else:
            assert s["open"] or s["no_data"] or s["anchors"] == 0

        cur.execute("""SELECT count(*) AS n FROM v_report_tie
                        WHERE period = %s AND state = 'OPEN'""", (s["period"],))
        named = len([p for p in (s["open_anchors"] or "").split(";") if p.strip()])
        assert named == cur.fetchone()["n"] == s["open"], (
            f"{s['period']}: the one line names {named} open anchors of "
            f"{s['open']}. A summary that shortens the list is the reason "
            "nobody reads the next one.")


# ── A named difference is closed, and the name is on the record ──────

def _ghost(cur) -> str:
    """Somebody with hours logged against a project and no payroll row.

    Made here rather than selected: CI applies the migrations to a bare
    Postgres, and a test that reads whatever happens to be in the database
    passes for a developer and fails in CI — which `test_reconcile_db.py`
    already paid for.
    """
    cur.execute("SELECT 1 FROM fiscal_period WHERE period = '2025'")
    if not cur.fetchone():
        pytest.skip("this database has no 2025 period")

    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('T104-OBJ', '2025', 'Contractor effort', 'PROGRAM',
                           false)
                   ON CONFLICT DO NOTHING""")
    cur.execute("""INSERT INTO labor_month (period, employee_key, month_start,
                                            objective_id, logged_hours,
                                            adjusted_hours, source_label)
                   VALUES ('2025', 'T104-GHOST', '2025-01-01', 'T104-OBJ',
                           120, 120, 'made by a test')""")
    return "T104-GHOST"


def _state(cur, key: str) -> dict:
    cur.execute("""SELECT state, explained_by FROM v_labor_hours_check
                    WHERE period = '2025' AND employee_key = %s""", (key,))
    return cur.fetchone()


def test_the_control_reads_the_register_built_to_explain_it(cur):
    """`072` reported Tom Metzinger as HOURS WITHOUT WAGES — 781 hours, no
    payroll row. `073` answered it: he is 1099, paid as `Metz Consulting,
    LLC.`, and `contractor_identity` holds the link and the note. **And the
    control went on reporting HOURS WITHOUT WAGES ever since**, which is the
    dead-register shape pointed the other way — a table nothing *reads*.
    """
    key = _ghost(cur)
    assert _state(cur, key)["state"] == "HOURS WITHOUT WAGES"

    cur.execute("""INSERT INTO contractor_identity (period, employee_key,
                                                    payee, basis, note)
                   VALUES ('2025', %s, 'T104 Consulting, LLC.', 'W9_1099',
                           'Paid on a retainer against 1099, not payroll.')""",
                (key,))

    said = _state(cur, key)
    assert said["state"] == "EXPLAINED", (
        "the register names this person and the control cannot see it")
    assert "T104 Consulting, LLC." in (said["explained_by"] or ""), (
        "EXPLAINED with nothing saying by what is a pass dressed up — the "
        "hours genuinely do not tie to wages, they tie to a contractor "
        "payment, and the state is never the whole answer")


def test_an_explained_difference_reaches_the_register_as_a_named_tie(cur):
    """The mapping is the point of one vocabulary. EXPLAINED is not a state
    anything downstream renders, and *a difference is closed by naming it*
    — so it becomes TIES **with the name in `needs`**, never a bare pass.
    """
    cur.execute("""SELECT count(*) AS n FROM v_labor_hours_check
                    WHERE period = '2025' AND state = 'TIES'""")
    if not cur.fetchone()["n"]:
        pytest.skip("no hours log on this database for the arm to evaluate")

    def arm() -> dict:
        cur.execute("""SELECT state, needs FROM v_report_tie
                        WHERE period = '2025' AND report = 'TIMESHEET'
                          AND anchor = 'The hours account for the wages'""")
        return cur.fetchone()

    before = arm()["state"]
    key = _ghost(cur)
    assert arm()["state"] == "OPEN", (
        f"effort with no cost behind it and nothing saying why read {before} "
        "and still does")

    cur.execute("""INSERT INTO contractor_identity (period, employee_key,
                                                    payee, basis, note)
                   VALUES ('2025', %s, 'T104 Consulting, LLC.', 'W9_1099',
                           'Paid on a retainer against 1099, not payroll.')""",
                (key,))

    said = arm()
    assert said["state"] == "TIES", (
        f"a difference the record names is still reading {said['state']}")
    assert key in (said["needs"] or ""), (
        "the tie does not say who it is explained for: " + repr(said["needs"]))


# ── The two reports that do not tie, named to the cent ───────────────

def test_the_depreciation_entry_balances_on_both_statements(cur):
    """The anchor the fixed-asset register is measured against, and nothing
    had ever compared them: the balance sheet's accumulated depreciation
    movement against the profit and loss's depreciation expense."""
    cur.execute("""SELECT profit_and_loss, balance_sheet, contra_accounts,
                          variance, state, needs
                     FROM v_depreciation_posted_check WHERE period = '2025'""")
    r = cur.fetchone()
    if not r or r["state"] == "NO DATA":
        pytest.skip("no general ledger on this database")

    assert r["contra_accounts"] > 0, (
        "the check found no accumulated-depreciation accounts at all, so it "
        "is comparing the expense against zero — which is `029` inside the "
        "control written to anchor the register")
    assert r["state"] in ("TIES", "OPEN")
    if r["state"] == "OPEN":
        assert r["needs"], "open and silent about which entry is incomplete"
        assert r["variance"] != 0
    else:
        assert r["variance"] == 0 and r["profit_and_loss"] != 0


def test_the_asset_register_names_the_whole_of_its_difference(cur):
    """A difference is closed by *naming* it, and a naming that does not add
    up to the figure it explains is a plug with extra steps — which is the
    rule `reconciling_item` has held in the schema since the first migration.

    One number for a $22,429.02 difference is a dead end; per cost account it
    is four differences with four causes, and the parts have to be the whole.
    Written out rather than parametrised over the relation name, because
    `test_sql_is_real.py` hands every literal statement to `PREPARE` and an
    interpolated table name is one it cannot check.
    """
    cur.execute("""SELECT sum(variance) AS named
                     FROM v_asset_register_tie WHERE period = '2025'""")
    named = cur.fetchone()["named"]
    if named is None:
        pytest.skip("no asset register on this database")

    cur.execute("SELECT variance FROM v_asset_control WHERE period = '2025'")
    assert named == cur.fetchone()["variance"], (
        f"the per-class breakdown attributes {named} of a difference the "
        "control puts at something else, so part of it is named nowhere")


def test_the_invoice_register_names_the_whole_of_its_difference(cur):
    """The same rule on the other open anchor: the register arm carries the
    sum of the open objectives, so an objective missing from the breakdown
    would be a difference reported and not attributed."""
    cur.execute("""SELECT sum(variance) FILTER (WHERE state = 'OPEN') AS named,
                          count(*) FILTER (WHERE state = 'OPEN') AS n
                     FROM v_invoice_income_tie WHERE period = '2025'""")
    r = cur.fetchone()
    if not r["n"]:
        pytest.skip("nothing open on the invoice register of this database")

    cur.execute("""SELECT variance, needs FROM v_report_tie
                    WHERE period = '2025' AND report = 'INVOICES'""")
    arm = cur.fetchone()
    assert arm["variance"] == r["named"]
    assert (arm["needs"] or "").count(";") == r["n"] - 1, (
        "the register reports a difference it does not name per objective: "
        + repr(arm["needs"]))


def test_the_asset_control_says_what_it_wants_while_it_is_open(cur):
    """`085` gave `needs` a branch for a register nobody had answered the
    funding source on, because until then that was the only way it could be
    open. The close answered all 263, the branch fell through to the empty
    string, and the control went on reporting OPEN with nothing saying what it
    wanted — on the figure the 200.436(b) carve-out turns on.

    And the ask that goes with `state` is `tie_needs`, not `needs`. One column
    was answering two questions: `v_partition_coverage` reads `needs` for the
    partition and this control's `state` is the depreciation tie, so filling
    the one in printed a sentence about depreciation on a partition that was
    finished. Two asks, two columns, and each reader gets its own.
    """
    cur.execute("""SELECT state, variance, needs, tie_needs, funding_unknown
                     FROM v_asset_control WHERE period = '2025'""")
    r = cur.fetchone()
    if not r or r["state"] == "NO DATA":
        pytest.skip("no asset register on this database")

    if r["state"] == "OPEN":
        assert (r["tie_needs"] or "").strip(), (
            "the asset control is open and silent. `OPEN` with no reason is "
            "the dead end this whole register exists to stop collecting.")
    else:
        assert not (r["tie_needs"] or "").strip(), (
            "it ties and still asks for something")

    if not r["funding_unknown"]:
        assert not (r["needs"] or "").strip(), (
            "every asset names its funding source and the partition is still "
            "asking for one: " + repr(r["needs"]))


def test_a_grant_with_no_register_is_not_reported_as_an_over_billing(cur):
    """`v_invoice_income_tie` mapped grant income to an objective through a
    six-row list written out by hand, and the ledger carries ten — so
    $348,402.98 of MBAC, AM Workforce, CDBG and DLA was not covered by the
    anchor called *the invoice register is the grant income* at all.

    A grant nothing has been loaded for now appears, and it appears as
    `NO REGISTER` rather than as a difference of its whole amount. Reporting
    it as OPEN would say YBI over-billed every dollar of it, when what is
    true is that nobody has loaded its invoices — and `029` decides the rest:
    the register reads that as NO DATA, which is never a pass.
    """
    cur.execute("SELECT import_id FROM ledger_import WHERE period = '2025' LIMIT 1")
    imp = cur.fetchone()
    if not imp:
        pytest.skip("no ledger on this database")

    cur.execute("""INSERT INTO ledger_line (line_id, import_id, period,
                                            txn_date, account, amount,
                                            statement, section, source_key)
                   VALUES ('T108-1', %s, '2025', '2025-06-30',
                           '3900 Grant Income:T108 Unmapped Grant', 5000.00,
                           'P&L', 'Income', 'T108-1')""", (imp["import_id"],))

    cur.execute("""SELECT invoices, billed, grant_income, variance, state
                     FROM v_invoice_income_tie
                    WHERE period = '2025'
                      AND objective_id LIKE '%T108 Unmapped Grant%'""")
    r = cur.fetchone()
    assert r, ("a grant income account the transcription does not name fell "
               "off the end of the register entirely")
    assert r["state"] == "NO REGISTER", (
        f"income with no invoice register reads {r['state']}, so the absence "
        "of a register is being reported as a difference")
    assert r["grant_income"] == 5000

    cur.execute("""SELECT state, variance, needs FROM v_report_tie
                    WHERE period = '2025' AND report = 'INVOICES'""")
    arm = cur.fetchone()
    assert "no invoice register at all" in (arm["needs"] or ""), (
        "the anchor does not say that part of its scope could not be "
        "evaluated: " + repr(arm["needs"]))
    assert arm["state"] != "TIES", (
        "a grant nobody has loaded a register for is not a pass")


def test_nothing_ties_over_a_period_with_no_books(cur):
    """*A control that cannot be evaluated has not passed*, and the way it
    fails is always the same: an empty period compares zero against zero and
    looks green. Two anchors did, in opposite directions — the fringe pool
    read TIES over a P&L that names no fringe, and Part VII reported every
    officer as one the payroll register does not carry, on a record with no
    payroll register at all.

    Found only by running the register against a database built from empty,
    which is the population nobody tests against and the one a recovery
    lands in.
    """
    cur.execute("""SELECT p.period FROM fiscal_period p
                    WHERE NOT EXISTS (SELECT 1 FROM ledger_line l
                                       WHERE l.period = p.period)""")
    empty = [r["period"] for r in cur.fetchall()]
    if not empty:
        pytest.skip("every period on this database carries a ledger")

    cur.execute("""SELECT period, report, anchor, state FROM v_report_tie
                    WHERE period = ANY(%s) AND state <> 'NO DATA'""", (empty,))
    said = cur.fetchall()
    assert not said, (
        "an anchor answers over a period with no books at all: "
        + "; ".join(f"{r['period']} {r['report']} · {r['anchor']} = "
                    f"{r['state']}" for r in said))
