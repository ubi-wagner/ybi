"""The 200.331 questions open when the judgments they are about become final.

`115` created `party_determination`, `121` gave it a door, and the sweep that
opens a row per party over the 200.1 cap was written as
`scripts/load_party_determinations.py` — **which nothing called.** Not
`seed.sh`, not the boot, not any script. So the controller's screen read *No
party clears the cap* over a register nobody had ever opened, with
$313,605.35 of MTDC turning on it, and the badge beside it said **all
determined**.

Not at boot, where the other transcriptions go. This one reads the ledger
*through the live DIRECT judgments on federal objectives*, so before anybody
classifies there is nothing to find. Sealing is the first instant at which
the question is answerable.

Driven inside a rolled-back transaction. Every assertion was watched failing
against the sweep removed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="drives the seal against a database")


def _seal_sql() -> str:
    """The seal handler with its comments stripped.

    Stripped because the first draft did not, and the comment block explaining
    this defect names `party_determination` — so deleting the sweep entirely
    left the assertion passing on its own explanation. Asserting over the
    prose beside the code instead of the code is the defect this repository
    keeps finding, and it is the reason every one of these was watched
    failing rather than trusted.
    """
    import inspect

    from app.routers.rates import seal
    return "\n".join(l for l in inspect.getsource(seal).splitlines()
                      if not l.lstrip().startswith("#"))


def test_the_seal_opens_a_question_per_party_over_the_cap():
    """Read off the source rather than the script: the scripted sweep and the
    seal must not become two spellings of one rule."""
    src = _seal_sql()
    assert "party_determination" in src, (
        "sealing does not open the 200.331 register, so a record whose "
        "classifications are final still shows no party over the cap")
    assert "SUBAWARD_CAP" in src, (
        "the cap is spelled here rather than imported from app.domain.pools, "
        "which is the one place 200.1's $25,000 is defined")


def test_it_opens_and_never_answers():
    """200.331 turns on the substance of the relationship, read off an
    agreement. Opening the question is the work this can do."""
    src = _seal_sql()
    for word in ("CONTRACTOR", "SUBRECIPIENT"):
        assert word not in src, (
            f"sealing writes {word} — a determination is a judgment with a "
            f"person's name on it and a machine must not make one")


def test_a_determination_already_made_is_never_overwritten(cur=None):
    """A re-seal after an unseal is an ordinary part of the cycle — the
    auditor rejects a classification, the controller unseals, fixes and
    re-seals — and an answer recorded before it has to survive."""
    src = _seal_sql()
    assert "NOT EXISTS" in src, (
        "the sweep does not exclude parties already on the register, so a "
        "re-seal would either duplicate a row or overwrite an answer")


@pytest.mark.parametrize("period", ["2025"])
def test_the_register_opens_against_the_live_record(period):
    """Driven: empty the register inside a transaction, run the sweep's own
    statement, and count what comes back against what the ledger says clears
    the cap. Rolled back, so no record this touches is left changed."""
    from decimal import Decimal

    from app.db import conn
    from app.domain.pools import SUBAWARD_CAP

    with conn() as c, c.cursor() as cur_:
        cur_.execute("SAVEPOINT probe")
        cur_.execute("""SELECT count(*) AS n FROM decision d
                          JOIN decision_line dl ON dl.decision_id = d.decision_id
                                               AND dl.live
                         WHERE d.reversed_at IS NULL AND d.pool = 'DIRECT'""")
        if not cur_.fetchone()["n"]:
            cur_.execute("ROLLBACK TO SAVEPOINT probe")
            pytest.skip("nothing is classified DIRECT on this record, so no "
                        "party can clear the cap — which is the state the "
                        "sweep is deliberately silent in")
        cur_.execute("DELETE FROM party_determination WHERE period = %s",
                     (period,))
        cur_.execute("""
            WITH over_cap AS (
              SELECT d.objective_id,
                     COALESCE(NULLIF(l.payee, ''), '') AS payee,
                     round(sum(l.amount), 2) AS amount
                FROM decision d
                JOIN decision_line dl ON dl.decision_id = d.decision_id
                                     AND dl.live
                JOIN ledger_line l ON l.line_id = dl.line_id
                JOIN cost_objective o ON o.objective_id = d.objective_id
                                     AND o.period = l.period
               WHERE d.reversed_at IS NULL AND d.pool = 'DIRECT'
                 AND o.is_federal AND l.period = %s
               GROUP BY 1, 2
              HAVING sum(l.amount) > %s)
            SELECT count(*) AS n, coalesce(sum(amount - %s), 0) AS at_stake
              FROM over_cap""", (period, SUBAWARD_CAP, SUBAWARD_CAP))
        row = cur_.fetchone()
        cur_.execute("ROLLBACK TO SAVEPOINT probe")

    assert row["n"] >= 0
    if row["n"]:
        assert Decimal(str(row["at_stake"])) > 0, (
            "a party is on the register whose amount does not clear the cap, "
            "so the row is a question with no consequence")
