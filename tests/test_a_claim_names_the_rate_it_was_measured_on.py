"""A restatement rests on two things, and `088` only watched one of them.

That migration made a claim say when the **invoice population** had moved
underneath it — three restatements measured on one April-2026 invoice each,
standing as 2025 claims, with nothing anywhere saying they had been
overtaken. `still_agrees` is that control, the walk's step 10 stopped
reading DONE over such a claim, and both papers print it above their figures.

The other thing a restatement rests on is the **rate**, and nothing asked.
All four standing America Makes settlements on the reference record were
computed against INDIRECT_COMBINED at 24.71%; `131` changed how the 200.465
carve-out is built and a recompute gives 22.48%. The restatements went on
reading ACCEPTED, the walk went on reading DONE, the papers rendered
cleanly, and the only sign of it anywhere was
`scripts/restate_2025_invoices.py` — which reads the *live* rate — reporting
every award differing from its own settlement by four to eight thousand
dollars with no explanation available on the record.

It is the worse half of the two: a changed population moves which invoices a
claim covers, and a changed rate moves **every figure on it**.

Driven against a database inside a transaction that is rolled back, because
`091` records what reading an applied migration is worth.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


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


def _a_standing_claim(cur) -> dict | None:
    cur.execute("""SELECT restatement_id, rate_id, status
                     FROM v_restatement
                    WHERE status <> 'SUPERSEDED' LIMIT 1""")
    return cur.fetchone()


def test_the_register_says_what_rate_a_claim_was_measured_on(cur):
    cur.execute("""SELECT r.restatement_id, r.rate_status, r.rate_is_live,
                          rt.status AS actual
                     FROM v_restatement r
                     JOIN rate rt ON rt.rate_id = r.rate_id""")
    rows = cur.fetchall()
    if not rows:
        pytest.skip("no restatement on this record")
    for r in rows:
        assert r["rate_status"] == r["actual"]
        assert r["rate_is_live"] is (r["actual"] != "SUPERSEDED"), (
            "rate_is_live disagrees with the rate's own status")


def test_a_proposed_rate_is_live(cur):
    """`rate.status` carries the **sponsor** conversation. PROPOSED means YBI
    has put the rate to NCDMM and they have not answered, which is the
    ordinary state of this engagement — only SUPERSEDED says the arithmetic
    has moved. Reading this as `status = 'ACTIVE'` would report every
    restatement in the file as stale."""
    cur.execute("""SELECT count(*) AS n FROM v_restatement
                    WHERE rate_status = 'PROPOSED' AND NOT rate_is_live""")
    assert cur.fetchone()["n"] == 0, (
        "a restatement on a PROPOSED rate is reported as measured on a rate "
        "that no longer stands")


def test_a_claim_on_a_superseded_rate_reopens_the_walk(cur):
    """Made here rather than selected, so the test means the same thing on a
    record where every rate happens to be live and on one where none is."""
    claim = _a_standing_claim(cur)
    if not claim:
        pytest.skip("no restatement stands as a claim on this record")

    cur.execute("""SELECT period, state, detail FROM v_audit_walk
                    WHERE key = 'RESTATE'
                      AND period = (SELECT period FROM v_restatement
                                     WHERE restatement_id = %s)""",
                (claim["restatement_id"],))
    before = cur.fetchone()

    cur.execute("UPDATE rate SET status = 'SUPERSEDED' WHERE rate_id = %s",
                (claim["rate_id"],))

    cur.execute("""SELECT rate_is_live FROM v_restatement
                    WHERE restatement_id = %s""", (claim["restatement_id"],))
    assert cur.fetchone()["rate_is_live"] is False

    cur.execute("""SELECT state, detail FROM v_audit_walk
                    WHERE key = 'RESTATE' AND period = %s""",
                (before["period"],))
    after = cur.fetchone()
    assert after["state"] == "OPEN", (
        f"the walk reads {after['state']} over a claim measured on a rate "
        f"that no longer stands. The step whose whole job is to say what is "
        f"unfinished must not assert that it is finished.")
    assert "no longer stands" in after["detail"] or "superseded" in after["detail"], (
        f"the walk is OPEN and does not say why: {after['detail']!r}")
    assert "Recompute" in after["detail"], (
        "OPEN with no ask is a dead end, and a register that collects dead "
        "ends is a longer one")


def test_the_page_warns_above_its_figures_and_not_under_them(cur):
    """A reader who has to reach the last section to learn that every figure
    above it is against arithmetic the record has moved past has already
    formed a view. `088` put the overtaken notice above the walk's own steps
    for the same reason; this is the stronger case, so it is above the table
    as well, in the warning colour."""
    import io

    from app.db import open_pool
    from app.domain.reconciliation_document import render_reconciliation
    from app.routers.restate import _reconciliation

    pypdf = pytest.importorskip("pypdf")
    open_pool()
    try:
        r = _reconciliation("2025")
    except Exception:
        pytest.skip("no America Makes restatement stands on this record")
    if not r.warnings:
        pytest.skip("every standing claim on this record is on a live rate")

    text = pypdf.PdfReader(
        io.BytesIO(render_reconciliation(r))).pages[0].extract_text()
    assert "no longer stands" in text
    assert text.index("no longer stands") < text.index("THE RECONCILIATION"), (
        "the warning that every figure below it is stale prints below the "
        "figures")


def test_one_sentence_per_rate_and_not_one_per_award(cur):
    """Four awards measured on one rate is one fact. Four copies of it at the
    top of a one-page document is *thirty-two unread workbooks buried three
    real proposals*, and it costs the page the room the figures need."""
    from app.routers.restate import _stale_rate_warning

    rows = [{"objective_id": o, "rate_kind": "INDIRECT_COMBINED",
             "rate_applied": 0.2471, "rate_status": "SUPERSEDED",
             "rate_is_live": False}
            for o in ("DRIVE-AM", "HYBRID-II", "LTM")]
    said = _stale_rate_warning(rows)
    assert len(said) == 1, f"one rate produced {len(said)} warnings"
    for o in ("DRIVE-AM", "HYBRID-II", "LTM"):
        assert o in said[0], "the awards are counted rather than named"
    assert not _stale_rate_warning(
        [dict(r, rate_is_live=True) for r in rows]), (
        "a live rate is reported as stale")
