"""Awards, constraint tests and invoice true-up.

`app/domain/awards.py::test_constraints` is the engine. It was written with
the schema, `constraint_result` was created to hold its answers, and **it had
no caller anywhere in the system** — so the table stayed empty and
`/trueup` counted zero blocking failures on all four awards and answered
`issuable: true, INVOICE_ISSUABLE`. It was telling the controller an invoice
was safe to issue *because nobody had checked*.

`evaluate(cur, ...)` is the caller. It runs from `POST /api/rates/compute`,
inside the turn that writes the rate, carrying that rate's id — because every
one of these tests is a statement about a claim, and a claim is direct cost
plus a rate applied to it. Evaluating them anywhere else would mean testing a
claim against a rate that had moved.
"""

from decimal import Decimal

from fastapi import Depends, APIRouter

from app.auth import require_project, require_reader
from app.db import query
from app.domain.awards import Award, RateMethod, test_constraints
from app.domain.core import EvidenceGrade

router = APIRouter(prefix="/awards", tags=["awards"],
                   dependencies=[Depends(require_reader)])


@router.get("")
def list_awards() -> list[dict]:
    return query("""SELECT a.*, o.label AS objective_label
                      FROM award a JOIN cost_objective o USING (objective_id)
                     ORDER BY a.award_id""")


@router.get("/{award_id}/constraints")
def constraints(award_id: str) -> list[dict]:
    return query("""SELECT code, citation, description, passed, blocking,
                           evaluable, detail, evaluated_at
                      FROM constraint_result WHERE award_id = %s
                     ORDER BY blocking DESC, passed, code""", (award_id,))


@router.get("/{award_id}/trueup")
def trueup(award_id: str) -> dict:
    """Whether a claim on this award may be issued, and on what evidence.

    **An award nobody has tested is not an award that passed.** This used to
    count blocking failures and answer `issuable: true` when it found none,
    which it always did, because nothing in the system had ever written a
    constraint result. Zero failures out of zero tests is the empty set
    matching the empty set perfectly — the same reading `029` fixed for the
    eleven controls and `v_invoice_budget_check` reports as
    `evaluable = false` on an unread award.

    Three states now, in the order a reader needs them: not tested, tested
    and blocked, tested and clear.
    """
    a = query("SELECT * FROM award WHERE award_id=%s", (award_id,))
    tally = query("""SELECT count(*)                                    AS tested,
                            count(*) FILTER (WHERE NOT evaluable)       AS unevaluable,
                            count(*) FILTER (WHERE blocking
                                               AND NOT passed)          AS blocking
                       FROM constraint_result
                      WHERE award_id = %s
                        AND rate_id = (SELECT rate_id FROM constraint_result
                                        WHERE award_id = %s
                                        ORDER BY evaluated_at DESC LIMIT 1)""",
                  (award_id, award_id))
    t = tally[0] if tally else {"tested": 0, "unevaluable": 0, "blocking": 0}
    tested, n = t["tested"], t["blocking"]

    if not tested:
        disposition, issuable = "NOT_EVALUATED", False
        why = ("No constraint has been tested against this award. Compute a "
               "rate — the tests are a statement about a claim, and a claim "
               "is direct cost plus a rate applied to it.")
    elif n:
        disposition, issuable = "DEFICIENCY_ACKNOWLEDGED", False
        why = (f"{n} blocking test(s) did not pass"
               + (f", {t['unevaluable']} of them because the record cannot "
                  f"answer them yet" if t["unevaluable"] else ""))
    else:
        disposition, issuable = "INVOICE_ISSUABLE", True
        why = f"all {tested} test(s) passed"

    return {"award": a[0] if a else None,
            "evaluable": bool(tested),
            "tested": tested,
            "unevaluable": t["unevaluable"],
            "blocking_failures": n,
            "issuable": issuable,
            "disposition": disposition,
            "why": why}


def evaluate(cur, period: str, rate_id: str, rate: Decimal,
             rate_method: RateMethod) -> int:
    """Test every award's constraints against this rate, and record them.

    Called from the rate computation inside its turn. Returns how many rows
    it wrote, which the caller puts on the audit entry — a number that is
    zero for the life of a system is the thing this whole exercise is about.

    Every figure is read here rather than passed in, because the alternative
    is a second definition of "what has been billed on this award" living in
    the rates router.
    """
    cur.execute("""SELECT award_id, objective_id, sponsor, prime_agreement,
                          instrument, ceiling_federal, cost_share_required,
                          period_start, period_end, rate_method::text AS rm,
                          citation
                     FROM award ORDER BY award_id""")
    awards = cur.fetchall()
    written = 0
    for a in awards:
        cur.execute("""SELECT COALESCE(sum(direct_claimed), 0)   AS direct,
                              COALESCE(sum(indirect_claimed), 0) AS indirect,
                              COALESCE(sum(total), 0)            AS billed,
                              COALESCE(sum(cost_share), 0)       AS share,
                              COALESCE(sum(total) FILTER (
                                  WHERE service_from > %s), 0)   AS after_term
                         FROM invoice
                        WHERE award_id = %s AND status <> 'WITHDRAWN'""",
                    (a["period_end"], a["award_id"]))
        inv = cur.fetchone()

        cur.execute("""SELECT category, federal FROM award_budget
                        WHERE award_id = %s""", (a["award_id"],))
        budget = {r["category"]: Decimal(str(r["federal"]))
                  for r in cur.fetchall()}

        # The weakest grade on any live judgment charged to this objective.
        # Weakest rather than typical: a claim is supported to the standard of
        # its worst-documented line, which is the question 200.403(g) asks.
        # None means nothing is classified here yet, which is unevaluable and
        # says so rather than passing.
        cur.execute("""SELECT d.grade::text AS grade
                         FROM decision d
                         JOIN decision_line dl ON dl.decision_id = d.decision_id
                                              AND dl.live
                        WHERE d.reversed_at IS NULL
                          AND d.objective_id = %s
                        GROUP BY d.grade""", (a["objective_id"],))
        grades = [EvidenceGrade(r["grade"]) for r in cur.fetchall()]
        weakest = min(grades, key=lambda g: g.rank) if grades else None

        award = Award(
            award_id=a["award_id"], objective_id=a["objective_id"],
            sponsor=a["sponsor"], prime=a["prime_agreement"] or "",
            instrument=a["instrument"],
            ceiling_federal=Decimal(str(a["ceiling_federal"])),
            cost_share_required=Decimal(str(a["cost_share_required"])),
            period_start=a["period_start"], period_end=a["period_end"],
            rate_method=RateMethod(a["rm"]), budget_lines=budget,
            billed_to_date=Decimal(str(inv["billed"])),
            billed_after_term=Decimal(str(inv["after_term"])),
            # Cost share is tracked nowhere else, so this is what the record
            # can say: what the invoices themselves claimed. On Hybrid and
            # Last Tactical Mile that is 0.00 against $617,065 committed —
            # the largest untracked obligation in the file, and this is the
            # first thing in the system that states it as a failed test
            # rather than as a paragraph in a document.
            cost_share_tracked=Decimal(str(inv["share"])),
            citation=a["citation"] or "")

        cs = test_constraints(award, Decimal(str(inv["direct"])),
                              Decimal(str(inv["indirect"])), rate, weakest,
                              rate_method)
        for c in cs:
            cur.execute("""INSERT INTO constraint_result
                             (award_id, rate_id, code, citation, description,
                              passed, blocking, detail, evaluable)
                           VALUES (%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s)""",
                        (a["award_id"], rate_id, c.code, c.citation,
                         c.description, c.passed, c.blocking, c.detail,
                         c.evaluable))
            written += 1
    return written
