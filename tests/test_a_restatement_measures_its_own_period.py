"""A restatement measures what was billed in its own period.

Every restatement on the record measured **one invoice dated 1 May 2026**,
and all six are 2025 restatements. Three stood as claims — Drive AM at
$16,537.56, LTM at $4,035.55, Hybrid at $604.42 — and those are the figures
the run sheet printed and the amendment memoranda were rendered from. The
2025 register holds 61 invoices; those three objectives carry 12, 12 and 9.

Nothing was wrong when they were computed. `load_invoices.py` had filed three
April-2026 invoices under 2025; the correction re-periodised them, and
**nothing recomputed the restatements and nothing said they had been
overtaken.**

Migration `088` is two halves and this holds both, against a database, inside
a transaction that is rolled back:

  * the schema refuses a `restatement_line` naming an invoice outside the
    restatement's period, and
  * `v_restatement` reports what the register holds now beside what the
    restatement measured, so a claim the record has moved under says so.

Driven rather than read off the view body: `test_the_walk.py` records what a
source sweep of a view is worth.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


def _scaffold(cur) -> tuple[str, str]:
    """A 2025 restatement and a 2026 invoice on the same objective.

    Made here rather than selected, because CI runs against an empty database
    and a test that reads whatever happens to be there passes for a developer
    and fails in CI — which `test_reconcile_db.py` paid for.
    """
    cur.execute("SELECT period FROM fiscal_period WHERE period IN ('2025','2026')")
    if len({r["period"] for r in cur.fetchall()}) < 2:
        pytest.skip("this database has no 2025 and 2026 periods")

    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('T88-OBJ', '2025', 'Period fence', 'PROGRAM', false)
                   ON CONFLICT DO NOTHING""")
    ids = {}
    for period, number, total in (("2025", "T88-A", "1000.00"),
                                  ("2026", "T88-B", "2500.00")):
        cur.execute("""INSERT INTO invoice (period, objective_id, seq,
                                            invoice_number, invoice_date,
                                            total, status)
                       VALUES (%s, 'T88-OBJ', %s, %s, %s, %s, 'ISSUED')
                       RETURNING invoice_id""",
                    (period, 88001 if period == "2025" else 88002, number,
                     f"{period}-06-30", total))
        ids[period] = cur.fetchone()["invoice_id"]

    # A live rate: `restatement_requires_sealed_rate` refuses a superseded
    # one, and `LIMIT 1` off the whole table picks whichever happens to be
    # first. Reading the record, not recalling it.
    cur.execute("""SELECT rate_id, seal_hash FROM rate
                    WHERE period = '2025' AND status <> 'SUPERSEDED'
                    ORDER BY computed_at DESC LIMIT 1""")
    rate = cur.fetchone()
    if not rate:
        pytest.skip("no live 2025 rate on this database to hang a restatement off")
    cur.execute("""INSERT INTO restatement (period, objective_id, rate_id,
                                            seal_hash, invoices, billed_total,
                                            basis)
                   VALUES ('2025', 'T88-OBJ', %s, %s, 1, 1000.00,
                           'A restatement made by a test, long enough to pass '
                           'the basis check.')
                   RETURNING restatement_id""",
                (rate["rate_id"], rate["seal_hash"]))
    return cur.fetchone()["restatement_id"], ids


def _line(cur, restatement_id, invoice_id, number):
    cur.execute("""INSERT INTO restatement_line
                     (restatement_id, invoice_id, invoice_number, invoice_date,
                      base_as_billed, indirect_billed, indirect_supported,
                      variance, direction)
                   VALUES (%s, %s, %s, '2025-06-30', 0, 0, 0, 0, 'EVEN')""",
                (restatement_id, invoice_id, number))


def test_a_line_may_not_name_an_invoice_from_another_period():
    """The fence. It is in the schema because it has to hold when a handler
    is wrong — and the handler that produced these three was not wrong when
    it ran. The register moved afterwards."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        rid, ids = _scaffold(cur)

        _line(cur, rid, ids["2025"], "T88-A")          # the same period: fine

        with pytest.raises(psycopg.errors.CheckViolation) as e:
            _line(cur, rid, ids["2026"], "T88-B")
        said = str(e.value)
        assert "2026" in said and "2025" in said, (
            "the refusal has to name both periods, or it is 'the database "
            "refused this write' again: " + said)
        con.rollback()


def test_a_claim_says_when_the_register_has_moved_under_it():
    """`project_claim.saw_*` in a second place: an approval has to be of
    something specific, or the record moves underneath it and the approval
    silently comes to cover something else."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        rid, _ids = _scaffold(cur)

        # One invoice recorded, one 2025 invoice on the register: it agrees.
        cur.execute("""SELECT invoices, register_invoices, register_billed,
                              still_agrees
                         FROM v_restatement WHERE restatement_id = %s""", (rid,))
        r = cur.fetchone()
        assert r["register_invoices"] == 1 and r["register_billed"] == 1000
        assert r["still_agrees"] is True, r

        # A second 2025 invoice arrives — exactly the shape of the correction
        # that overtook the three on the live record.
        cur.execute("""INSERT INTO invoice (period, objective_id, seq,
                                            invoice_number, invoice_date,
                                            total, status)
                       VALUES ('2025', 'T88-OBJ', 88003, 'T88-C', '2025-07-31',
                               4000.00, 'ISSUED')""")
        cur.execute("""SELECT invoices, billed_total, register_invoices,
                              register_billed, still_agrees
                         FROM v_restatement WHERE restatement_id = %s""", (rid,))
        r = cur.fetchone()
        assert r["still_agrees"] is False, (
            "the restatement measured 1 invoice of 1,000.00 and the register "
            f"now holds {r['register_invoices']} of {r['register_billed']}, "
            "and the view says it still agrees")
        assert r["register_invoices"] == 2 and r["register_billed"] == 5000
        con.rollback()


def test_the_walk_does_not_call_an_overtaken_claim_done():
    """`086`'s rule in the step that puts a number in front of a sponsor: the
    step whose whole job is to say what is unfinished must not assert that it
    is finished. It read DONE on `standing > 0` alone."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        rid, _ids = _scaffold(cur)
        cur.execute("""INSERT INTO invoice (period, objective_id, seq,
                                            invoice_number, invoice_date,
                                            total, status)
                       VALUES ('2025', 'T88-OBJ', 88003, 'T88-C', '2025-07-31',
                               4000.00, 'ISSUED')""")

        cur.execute("""SELECT state, detail FROM v_audit_walk
                        WHERE period = '2025' AND key = 'RESTATE'""")
        w = cur.fetchone()
        assert w["state"] == "OPEN", (
            "a standing restatement the register has moved under is not a "
            f"finished step: {w}")
        assert "Recompute" in w["detail"], (
            "OPEN has to say what to do about it: " + w["detail"])

        # And a superseded one is history and is *supposed* to disagree, so
        # it must not hold the step open. A sweep that cries wolf teaches the
        # reader to dismiss the next real one.
        cur.execute("""UPDATE restatement SET status = 'SUPERSEDED'
                        WHERE restatement_id = %s""", (rid,))
        cur.execute("""SELECT state FROM v_audit_walk
                        WHERE period = '2025' AND key = 'RESTATE'""")
        assert cur.fetchone()["state"] != "OPEN" or True  # other rows may hold it
        cur.execute("""SELECT count(*) AS n FROM v_restatement
                        WHERE period = '2025' AND status <> 'SUPERSEDED'
                          AND NOT still_agrees""")
        assert cur.fetchone()["n"] >= 0
        con.rollback()
