"""Two standing claims on one objective, and a rehearsal called a signature.

Both came out of walking everything *after* the rate is locked — certify,
restate, report — which is the half of the year nothing had ever driven end
to end.

**The register carried two live positions for one award and every reader
added them together.** Recomputing DRIVE-AM on the locked rate left the
accepted $128,474.23 standing and wrote $136,534.61 beside it, so the
acceptance form NCDMM signs would have asked for $265,008.84 — a position
plus its own replacement, on the one page that goes to a sponsor.
`POST /api/restate` supersedes only a `PROPOSED` predecessor, which is right
about what it protects and then writes the new row anyway. The index that
would have caught it was already there, on the right columns, with the right
predicate, and not unique.

**And the walk printed "Signed by Tom Metzinger" over a rehearsal.** `122`
gave the row a value for the kind of act and fixed the six places that
composed their own sentence; the walk is the seventh and is in SQL, where
that sweep cannot reach, and it is the screen that tells the controller the
year is finished.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

STANDING = ("PROPOSED", "SUBMITTED", "ACCEPTED")


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


def _a_standing_one(cur):
    cur.execute("""SELECT * FROM restatement
                    WHERE status = ANY(%s) LIMIT 1""", (list(STANDING),))
    return cur.fetchone()


# ── one objective, one claim ─────────────────────────────────────────

def test_an_objective_cannot_carry_two_standing_claims(cur):
    """Made here rather than selected, so it means the same thing on a
    record that happens to be clean and on one that is not."""
    row = _a_standing_one(cur)
    if not row:
        pytest.skip("no restatement stands on this record")

    cols = [k for k in row if k not in
            ("restatement_id", "computed_at", "submitted_at", "decided_at")]
    names = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    with pytest.raises(Exception) as caught:
        cur.execute(f"INSERT INTO restatement ({names}) VALUES ({placeholders})",
                    [row[c] for c in cols])
    assert "one_standing_restatement_per_objective" in str(caught.value), (
        f"a second standing claim on {row['objective_id']} was accepted: "
        f"{caught.value}. Every reader sums over the standing set, so the "
        f"papers would put a position and its own replacement in front of "
        f"the sponsor as one figure.")


def test_a_rejected_position_does_not_block_measuring_again(cur):
    """Being told no is the reason to measure again. An index that blocked
    that would be a control nobody can clear by doing the work."""
    cur.execute("""SELECT pg_get_indexdef(indexrelid) AS d FROM pg_index
                    WHERE indexrelid = 'one_standing_restatement_per_objective'::regclass""")
    body = cur.fetchone()["d"]
    assert "REJECTED" not in body, (
        "a rejected restatement counts as standing, so a sponsor saying no "
        "would stop YBI measuring again")
    for s in STANDING:
        assert s in body, f"{s} is not held by the index"


def test_the_repair_left_the_later_computation_standing(cur):
    """The newest is the position and the rest are history — this system's
    model of change everywhere else. Nothing is erased: a superseded row
    keeps its dates, so *the sponsor accepted this figure, on that day* is
    still readable and no longer stands as a claim."""
    cur.execute("""SELECT period, objective_id, count(*) AS n
                     FROM restatement WHERE status = ANY(%s)
                    GROUP BY period, objective_id HAVING count(*) > 1""",
                (list(STANDING),))
    doubled = cur.fetchall()
    assert not doubled, f"objectives carrying more than one claim: {doubled}"

    cur.execute("""SELECT r.objective_id FROM restatement r
                    WHERE r.status = 'SUPERSEDED'
                      AND EXISTS (SELECT 1 FROM restatement s
                                   WHERE s.period = r.period
                                     AND s.objective_id = r.objective_id
                                     AND s.status = ANY(%s)
                                     AND s.computed_at < r.computed_at)""",
                (list(STANDING),))
    backwards = cur.fetchall()
    assert not backwards, (
        f"a superseded row is newer than the claim that replaced it: "
        f"{backwards}")


# ── a rehearsal is not a signature ───────────────────────────────────

def test_the_walk_does_not_print_a_name_over_a_rehearsal(cur):
    """Driven, because the question is what the sentence says and a sweep of
    the view body would be asserting prose."""
    cur.execute("SELECT * FROM v_rate_certified WHERE period = '2025'")
    cert = cur.fetchone()
    if not cert or not cert.get("certified"):
        pytest.skip("no live certification on this record")

    # `origin` is write-once — relabelling a signature is exactly what `122`
    # refuses — so the rehearsal is a *new* certification, which is the only
    # honest way to make one. The live signature is withdrawn first because
    # a period carries one, and the whole transaction is rolled back.
    cur.execute("""UPDATE rate_certification
                      SET withdrawn_at = now(), withdrawn_by = (SELECT actor_id FROM actor WHERE is_active LIMIT 1),
                          withdrawn_reason = 'Making a rehearsal to read the '
                                             'walk back; rolled back.'
                    WHERE cert_id = %s""", (cert["cert_id"],))
    cur.execute("""INSERT INTO rate_certification
                     (period, seal_hash, signature, certified_by, outstanding,
                      note, origin)
                   SELECT period, seal_hash, 'REHEARSAL', certified_by,
                          outstanding, 'Rehearsal, for the test.', 'REHEARSAL'
                     FROM rate_certification WHERE cert_id = %s
                RETURNING cert_id""",
                (cert["cert_id"],))
    fresh = cur.fetchone()["cert_id"]
    # `082`: a certificate names the rate rows it covers, and dies with them.
    # A copy without the lines reads as superseded rather than as a
    # rehearsal, which would have this test passing over the wrong sentence.
    cur.execute("""INSERT INTO rate_certification_line (cert_id, rate_id)
                   SELECT %s, rate_id FROM rate_certification_line
                    WHERE cert_id = %s""", (fresh, cert["cert_id"]))
    cur.execute("""SELECT state, detail FROM v_audit_walk
                    WHERE period = '2025' AND key = 'CERTIFY'""")
    said = cur.fetchone()

    assert (cert.get("certified_by") or "zzz") not in said["detail"], (
        f"the walk names a signatory over a signature no person gave: "
        f"{said['detail']!r}")
    assert "REHEARSAL" in said["detail"].upper()
    assert said["state"] == "OPEN", (
        "a rehearsal reads DONE. Nothing resting on it may go to a sponsor, "
        "which is the definition of outstanding — the step whose whole job "
        "is to say what is unfinished must not assert that it is finished.")


def test_a_signature_somebody_gave_still_reads_done(cur):
    """The other direction, because a fix that reported every certification
    as a rehearsal would pass the test above perfectly."""
    cur.execute("SELECT * FROM v_rate_certified WHERE period = '2025'")
    cert = cur.fetchone()
    if not cert or not cert.get("certified") or cert.get("rehearsal"):
        pytest.skip("no live controller certification on this record")
    cur.execute("""SELECT state, detail FROM v_audit_walk
                    WHERE period = '2025' AND key = 'CERTIFY'""")
    said = cur.fetchone()
    assert said["state"] == "DONE"
    assert cert["certified_by"] in said["detail"]
