"""What the system writes is what it reads back, and nothing else moves.

`scripts/drive_symbiosis.py` proves this against a running service: five
people change five registers, 258 figures are watched, and the record comes
back to the cent. These are the properties underneath that drive, held here so
a change that breaks one fails in the suite rather than in front of a
controller.

The load-bearing one is the **separation**: Form 990 is a statement about the
ledger and a rate is a statement about the pools, and neither may reach into
the other. Measured on the live record, five reclassifications moved the
combined rate from 24.71% to 34.68% and moved **not one figure** on the
return — which is only true for as long as the return's views do not read the
rate model.
"""

from __future__ import annotations

import os
import re

import pytest

db = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                        reason="needs a database")

#: The return's three financial statements.
STATEMENTS = ("v_form_990_part_ix", "v_form_990_part_viii",
              "v_form_990_part_x")

#: The rate model.
RATE_MODEL = ("v_pool_balance", "v_rate_buildup", "v_rate_anchor")


def _body(cur, view: str) -> str:
    cur.execute("SELECT pg_get_viewdef(%s, true) AS d", (view,))
    return re.sub(r"--[^\n]*", "", cur.fetchone()["d"])


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


@pytest.fixture()
def cur():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        with _cur(con) as c:
            yield c
        con.rollback()


@db
@pytest.mark.parametrize("view", STATEMENTS)
def test_the_return_does_not_read_the_rate_model(cur, view):
    """Part IX is driven by the account a cost sits in and the 990 function
    somebody judged; it must never be driven by the **pool**. A return that
    moved when a pool did would report a different tax position for every
    rate the controller tried, and the two are answers to different
    questions."""
    body = _body(cur, view)
    for forbidden in ("pool", "carve_out", "v_rate", "FROM rate", "join rate"):
        assert forbidden not in body, (
            f"{view} reads {forbidden!r}, so the return now moves with the "
            "rate model")


@db
@pytest.mark.parametrize("view", RATE_MODEL)
def test_the_rate_model_does_not_read_the_return(cur, view):
    """And the converse, which is the easier one to break: a pool that read
    a 990 line would make the rate depend on a tax presentation."""
    body = _body(cur, view)
    assert "form_990" not in body, (
        f"{view} reads the return, so a rate now depends on a tax "
        "presentation rather than on the ledger")


@db
def test_a_reclassification_moves_the_pools_and_leaves_the_return_alone(cur):
    """The property the drive measures, driven here in a transaction that is
    rolled back: move one group between two pools and read both sides."""
    # The whole of Part IX, every line and all four columns. A total alone
    # would miss a leak into the function columns, which is where the
    # judgment actually reaches the return.
    ix = """SELECT line_id, total, program, management, fundraising
              FROM v_form_990_part_ix WHERE period = '2025' ORDER BY line_id"""
    cur.execute(ix)
    ix_before = cur.fetchall()
    cur.execute("""SELECT pool::text AS pool, gross FROM v_pool_balance
                    WHERE period = '2025'""")
    pools_before = {r["pool"]: r["gross"] for r in cur.fetchall()}
    if not ix_before or not pools_before:
        pytest.skip("no classified ledger on this database")

    # A judgment inside a sealed set cannot be moved, which is the guarantee
    # the whole file rests on — so the seal comes off first, exactly as a
    # controller would have to.
    cur.execute("""UPDATE decision_set SET seal_hash = NULL, sealed_at = NULL
                    WHERE period = '2025'""")
    cur.execute("""SELECT d.decision_id, d.pool::text AS pool
                     FROM decision d
                    WHERE d.reversed_at IS NULL AND d.pool::text = 'G&A'
                      AND EXISTS (SELECT 1 FROM decision_line dl
                                   WHERE dl.decision_id = d.decision_id
                                     AND dl.live)
                    LIMIT 1""")
    row = cur.fetchone()
    if not row:
        pytest.skip("nothing classified to G&A on this database")
    # Moved to EXCLUDED deliberately. That is the pool a return view would
    # most plausibly filter out — it is the enum's word for cost the *pools*
    # must not carry — and a Part IX that dropped it would be reporting a
    # different tax position for a judgment about the rate model.
    cur.execute("UPDATE decision SET pool = 'EXCLUDED' WHERE decision_id = %s",
                (row["decision_id"],))

    cur.execute("""SELECT pool::text AS pool, gross FROM v_pool_balance
                    WHERE period = '2025'""")
    pools_after = {r["pool"]: r["gross"] for r in cur.fetchall()}
    assert pools_after["G&A"] != pools_before["G&A"], (
        "a judgment moved between pools and no pool moved")
    assert (pools_before["G&A"] - pools_after["G&A"]
            == pools_after["EXCLUDED"] - pools_before["EXCLUDED"]), (
        "what left one pool is not what arrived in the other")

    cur.execute(ix)
    after = cur.fetchall()
    moved = [(b["line_id"], k, b[k], a[k])
             for b, a in zip(ix_before, after) for k in
             ("total", "program", "management", "fundraising") if b[k] != a[k]]
    assert not moved, (
        f"Form 990 Part IX moved on a change to the cost pools: {moved[:4]}")


@db
def test_no_control_can_change_without_the_census_noticing():
    """The drive watches a fixed census, and a control added to the tie
    register after it was written would sit outside the propagation test with
    nothing saying so — the hand-kept map, one list wide.

    Both sides are derived: the census is taken for real, the register is
    read for real, and every anchor has to appear in it **by name**. The
    counts alone are not enough, because one control going OPEN while another
    came back would leave the tally standing — netting, in a census.
    """
    import importlib.util
    from pathlib import Path
    from app.db import open_pool, query

    path = Path(__file__).resolve().parent.parent / "scripts" / "drive_symbiosis.py"
    spec = importlib.util.spec_from_file_location("symbiosis", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    open_pool()
    anchors = query("""SELECT report, anchor FROM v_report_tie
                        WHERE period = '2025'""")
    if not anchors:
        pytest.skip("no tie register on this database")
    taken = mod.census("2025")
    missing = [f"{a['report']} · {a['anchor']}" for a in anchors
               if f"register.{a['report']}.{a['anchor']}.state" not in taken]
    assert not missing, (
        f"the propagation drive would not notice these controls changing: "
        f"{missing}")
    # The derived half above is the content and it holds on any database:
    # every anchor the register carries has to be in the census by name. This
    # is the magnitude smoke test beside it — *did somebody gut the census* —
    # and 250 is a figure only a loaded record produces, because most of what
    # the census counts is one entry per pool, per objective and per line of
    # the return. Asserting it over an empty ledger is asserting the size of
    # a population that is not there, which is the literal-threshold shape
    # this repository has been caught by before. So it states its premise.
    if not query("SELECT 1 FROM ledger_line WHERE period = '2025' LIMIT 1"):
        pytest.skip("no ledger on this database, so the census is the shape "
                    "of an empty record rather than a shrunken one. The "
                    "anchor-by-anchor assertion above ran; prove.sh covers "
                    "the magnitude against a loaded record.")
    assert len(taken) > 250, "the census has shrunk to something unwatchful"
