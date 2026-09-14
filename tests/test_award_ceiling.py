"""The ceiling the register enforces must be the ceiling the agreement states.

Hybrid Phase 2 was seeded from the executed agreement at $500,043 with
performance to 10 October 2025. Modification 001 of 22 January 2026 raised it
to $512,409 and extended performance to 30 June 2026; the modification is on
file as a document and was read into `award_term` by the controller. The award
row was never brought into line.

So two records of one fact disagreed by $12,366 and eight months, and the one
`POST /api/restate` reads to cap a claim was the stale one — it would have
reported $12,366 of headroom YBI does not have, against a sponsor, in writing.

Nothing tied them together. The ceiling is not a derived figure, so none of the
eleven cross-reference controls touched it; it is read off a clause, and the
control is simply that the register says what the clause says.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

SQL = Path(__file__).resolve().parent.parent / "app" / "sql"
MIGRATION = SQL / "049_a_modification_moves_the_ceiling.sql"


def test_the_control_exists_in_the_schema():
    body = MIGRATION.read_text()
    assert "CREATE VIEW v_award_ceiling_check" in body
    assert "Total obligation" in body, (
        "the control has to compare against the term the controller records "
        "the money limit under"
    )


def test_an_unread_agreement_does_not_report_as_tying():
    """`evaluable` is the same idea as `state` on the reconciliation register:
    a control that cannot be evaluated has not passed. An award whose
    agreement nobody has been through has no clause to compare against, and
    calling that a tie would make an unread award look checked."""
    body = MIGRATION.read_text()
    assert "NO CLAUSE READ" in body
    assert "evaluable" in body


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_every_award_ties_to_its_clause():
    from app.db import query

    open_points = query("""SELECT award_id, register, clause, variance, citation
                             FROM v_award_ceiling_check
                            WHERE state = 'OPEN'""")
    assert not open_points, "\n".join(
        f"{r['award_id']}: the register enforces {r['register']:,.2f} and "
        f"{r['citation']} states {r['clause']:,.2f} — off by {r['variance']:,.2f}"
        for r in open_points)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_modification_reached_the_register():
    from app.db import one

    row = one("""SELECT ceiling_federal, period_end FROM award
                  WHERE award_id = 'AM-HYBRID-P2'""")
    assert row is not None
    assert row["ceiling_federal"] == 512409, (
        "the ceiling is the one Modification 001 set, not the one the "
        "original agreement carried"
    )
    assert row["period_end"].isoformat() == "2026-06-30"
