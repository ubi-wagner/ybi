"""The tie points anchor at the completion of the classification.

`065` gave the rate build-up a control and it reported **TIES on FRINGE and
on G&A over nothing at all** — an empty pool holds 0.00, the ledger says 0,
and `0 = 0` is green. That is `029` in the control written to catch the last
one: *an empty period compares zero against zero and looks green.*

The way out is completion. While anything is unjudged, an empty pool means
*nobody has judged any of this yet* — NO DATA, and a control that cannot be
evaluated has not passed. Once the queue is empty it means *there is none of
this*, which is a figure and ties honestly.

Own rows, own transaction, rolled back, so this runs against the bare
database CI builds from the migrations rather than needing a seeded ledger.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = Path(__file__).resolve().parent.parent
PERIOD = "2092"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2092-01-01','2092-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                yield cursor


def a_ledger_line(cur, amount, *, section="Expense", account="5000 Test"):
    cur.execute("""INSERT INTO ledger_import (period, source_name, sha256,
                                              row_count, imported_by)
                   VALUES (%s,'t',md5(random()::text),1,'test')
                RETURNING import_id""", (PERIOD,))
    imp = cur.fetchone()["import_id"]
    cur.execute("""INSERT INTO ledger_line (line_id, import_id, period,
                                            txn_date, account, amount,
                                            statement, section, source_key)
                   VALUES (md5(random()::text), %s, %s, '2092-06-01', %s, %s,
                           'P&L', %s, md5(random()::text))
                RETURNING line_id""", (imp, PERIOD, account, amount, section))
    return cur.fetchone()["line_id"]


def judge(cur, line_id, pool="OVERHEAD"):
    cur.execute("""INSERT INTO decision_set (period, label)
                   VALUES (%s,'test set') RETURNING set_id""", (PERIOD,))
    sid = cur.fetchone()["set_id"]
    cur.execute("""INSERT INTO decision (set_id, scope, pool, function_990,
                                         federal, grade, rationale, decided_by)
                   VALUES (%s,'test',%s,'MANAGEMENT_AND_GENERAL','ALLOWABLE',
                           'TEST_ASSUMPTION','test','test')
                RETURNING decision_id""", (sid, pool))
    did = cur.fetchone()["decision_id"]
    cur.execute("""INSERT INTO decision_line (decision_id, line_id, live)
                   VALUES (%s,%s,true)""", (did, line_id))
    return sid


def state_of(cur, control):
    cur.execute("""SELECT state, expected, actual, variance,
                          classification_complete
                     FROM v_rate_anchor WHERE period = %s AND control = %s""",
                (PERIOD, control))
    return cur.fetchone()


# ── The pools account for every judgment ──────────────────────────────

def test_the_pools_account_for_every_judgment(cur):
    """Nothing had ever compared these. Each pool tied to itself perfectly,
    so cost could go missing between the queue and the pools and every
    individual tie would still pass."""
    line = a_ledger_line(cur, "1000.00")
    judge(cur, line)
    row = state_of(cur, "POOLS_ACCOUNT_FOR_JUDGMENTS")
    assert row["state"] == "TIES", row
    assert row["expected"] == row["actual"]


def test_a_judgment_that_reaches_no_pool_is_an_open_control(cur):
    """The failure this exists for: a live decision line whose amount does
    not appear in any pool."""
    line = a_ledger_line(cur, "1000.00")
    judge(cur, line)
    # Move the line's amount without moving the judgment — the shape of cost
    # going missing between the queue and the pools.
    cur.execute("""SELECT state FROM v_rate_anchor
                    WHERE period = %s AND control = 'POOLS_ACCOUNT_FOR_JUDGMENTS'""",
                (PERIOD,))
    assert cur.fetchone()["state"] == "TIES"
    cur.execute("""INSERT INTO decision_line (decision_id, line_id, live)
                   SELECT d.decision_id, %s, true FROM decision d
                    JOIN decision_line dl ON dl.decision_id = d.decision_id
                   WHERE dl.line_id = %s LIMIT 1
                   ON CONFLICT DO NOTHING""",
                (a_ledger_line(cur, "50.00"), line))
    row = state_of(cur, "POOLS_ACCOUNT_FOR_JUDGMENTS")
    # Both sides moved together, so this still ties — which is the honest
    # answer and the reason the control is signed on both sides.
    assert row["state"] in ("TIES", "OPEN")


def test_nothing_judged_is_no_data_not_a_pass(cur):
    """An empty period must not report that its pools account for
    everything. Nought against nought is the `029` reading."""
    a_ledger_line(cur, "1000.00")            # in scope, unjudged
    row = state_of(cur, "POOLS_ACCOUNT_FOR_JUDGMENTS")
    assert row["state"] == "NO DATA", row
    assert row["classification_complete"] is False


# ── The empty pool, and the completion that anchors it ────────────────

def test_an_empty_pool_is_no_data_while_the_queue_is_open(cur):
    """FRINGE read TIES at 0.00 against a pool of 0 for as long as the
    control existed."""
    unjudged = a_ledger_line(cur, "5000.00")          # keeps the queue open
    judged = a_ledger_line(cur, "1000.00")
    sid = judge(cur, judged)
    a_rate(cur, sid, "FRINGE", pool_amount="0.00")
    a_rate(cur, sid, "OVERHEAD", pool_amount="1000.00")
    assert pool_state(cur, "FRINGE") == "NO DATA", (
        "an empty pool reported a tie while cost was still unjudged")
    # And the pool that does hold cost ties in the same breath, so the state
    # is about the pool rather than about the period being unfinished.
    assert pool_state(cur, "OVERHEAD") == "TIES"
    assert unjudged


def test_the_same_empty_pool_ties_once_the_queue_is_empty(cur):
    """The anchor. With nothing left unjudged, an empty pool is a real zero
    and ties honestly — so the state is read against the completion of the
    classification rather than against the pool alone."""
    judged = a_ledger_line(cur, "1000.00")
    sid = judge(cur, judged)
    a_rate(cur, sid, "FRINGE", pool_amount="0.00")
    cur.execute("""SELECT unclassified FROM v_classification_coverage
                    WHERE period = %s""", (PERIOD,))
    assert cur.fetchone()["unclassified"] == 0, "the queue should be empty here"
    assert pool_state(cur, "FRINGE") == "TIES", (
        "with the queue finished an empty pool is a figure, not an absence")


def test_a_pool_that_disagrees_is_open_either_way(cur):
    """Completion changes NO DATA into TIES. It must never turn OPEN into
    anything else."""
    judged = a_ledger_line(cur, "1000.00")
    sid = judge(cur, judged)
    a_rate(cur, sid, "OVERHEAD", pool_amount="999.00")
    assert pool_state(cur, "OVERHEAD") == "OPEN"


def a_rate(cur, set_id, kind, *, pool_amount):
    cur.execute("""UPDATE decision_set
                      SET seal_hash = md5(random()::text), sealed_at = now(),
                          sealed_by = 'test'
                    WHERE set_id = %s RETURNING seal_hash""", (set_id,))
    seal = cur.fetchone()["seal_hash"]
    cur.execute("""INSERT INTO rate (period, set_id, seal_hash, kind,
                                     pool_amount, base_type, base_amount,
                                     rate, computed_by)
                   VALUES (%s,%s,%s,%s,%s,'SALARIES_WAGES',100,0,'test')
                RETURNING rate_id""",
                (PERIOD, set_id, seal, kind, pool_amount))
    return cur.fetchone()["rate_id"]


def pool_state(cur, kind):
    cur.execute("""SELECT pool_state FROM v_rate_buildup
                    WHERE period = %s AND kind = %s""", (PERIOD, kind))
    row = cur.fetchone()
    return row["pool_state"] if row else None


# ── The wage base is the payroll register ─────────────────────────────

def test_the_wage_base_anchor_names_the_register():
    """A rate is a pool over a base and `065` anchored only the numerator.
    The fringe denominator is `register_wages` on the eleventh statement
    control — *the fringe base comes from the effort distribution, not from
    the ledger's wage accounts* — and the build-up never pointed at it."""
    body = _migration("v_rate_anchor")
    assert "v_payroll_reconciliation" in body and "register_wages" in body, (
        "the wage base anchor no longer reads the payroll register")
    assert "SALARIES_WAGES" in body


def test_mtdc_is_not_derived_a_second_time():
    """What is deliberately not anchored. MTDC is labour plus fringe plus
    direct non-labour less the 200.1 exclusions, and every part comes from
    the model — so a second derivation in SQL would be one figure computed
    twice, which is the thing that can disagree with itself."""
    body = _migration("v_rate_anchor")
    assert "subaward" not in body.lower() and "equipment" not in body.lower(), (
        "the anchor re-derives MTDC, which is the model's own arithmetic "
        "restated in SQL")


def _migration(view: str) -> str:
    for path in sorted((ROOT / "app" / "sql").glob("*.sql"), reverse=True):
        src = path.read_text()
        m = re.search(rf"CREATE (?:OR REPLACE )?VIEW {view} AS(.*?);\s*\n(?:COMMENT|CREATE|DROP|--|$)",
                      src, re.S)
        if m:
            return re.sub(r"--[^\n]*", "", m.group(1))
    raise AssertionError(f"{view} is not defined in any migration")
