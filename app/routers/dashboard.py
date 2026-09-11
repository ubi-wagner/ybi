"""The landing page: where the engagement stands, and what is left to do.

Three questions, answered in one call because they are one question:

  * where do the finances stand, and do the controls tie;
  * what has happened, and who did it;
  * what is still open, in the order it is worth doing.

The work list is ordered by money rather than by age. A hundred small groups
and one large one are not the same afternoon's work.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.auth import Actor, Portfolio, current_actor, require_reader
from app.db import one, query
from app.settings import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"],
                   dependencies=[Depends(require_reader)])


@router.get("")
def dashboard(period: str = None, activity_limit: int = Query(25, le=200),
              actor: Actor = Depends(require_reader)) -> dict:
    period = period or settings.period

    rollup = one("SELECT * FROM v_dashboard WHERE period = %s", (period,))
    coverage = one("""
        WITH d AS (
          SELECT l.line_id, l.amount,
                 (dl.decision_id IS NOT NULL) AS decided
            FROM ledger_line l
            LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
           WHERE l.period = %s AND l.statement = 'P&L')
        SELECT count(*)                                            AS lines,
               count(*) FILTER (WHERE decided)                     AS decided_lines,
               COALESCE(sum(abs(amount)), 0)                       AS dollars,
               COALESCE(sum(abs(amount)) FILTER (WHERE decided), 0) AS decided_dollars
          FROM d""", (period,))

    pct = 0.0
    if coverage and coverage["dollars"]:
        pct = round(float(coverage["decided_dollars"]) /
                    float(coverage["dollars"]) * 100, 1)

    # The cross-reference register is the one place the controls live. The
    # dashboard used to keep its own short list of three, which meant a
    # control could tie here and be open on the reconciliation, and nobody
    # would see the second one.
    controls = query("""
        SELECT description AS control,
               CASE WHEN basis = 'VARIANCE' THEN variance ELSE exceptions END
                   AS variance,
               ties, state
          FROM v_statement_reconciliation
         WHERE period = %s ORDER BY seq""", (period,)) or []
    controls += query("""
        SELECT 'Asset register agrees with the ledger' AS control,
               variance, (variance = 0) AS ties
          FROM v_asset_control WHERE period = %s""", (period,))

    worklist = query("""
        SELECT kind, severity, count(*) AS items,
               COALESCE(sum(amount), 0) AS amount
          FROM v_worklist WHERE period = %s
         GROUP BY kind, severity
         ORDER BY CASE severity WHEN 'BLOCKING' THEN 0 WHEN 'HIGH' THEN 1
                                ELSE 2 END, sum(amount) DESC NULLS LAST""",
        (period,))

    activity = query("""
        SELECT occurred_at, kind, actor, entity, entity_id, label, amount, detail
          FROM v_activity
         WHERE occurred_at IS NOT NULL
         ORDER BY occurred_at DESC LIMIT %s""", (activity_limit,))

    return {
        "period": period,
        "actor": {"name": actor.display_name, "role": actor.role.value,
                  "can_write": actor.can_write},
        "rollup": rollup,
        "coverage": {**(coverage or {}), "pct_dollars": pct},
        "controls": controls,
        "worklist": worklist,
        "activity": activity,
    }


@router.get("/worklist")
def worklist(period: str = None, kind: str = "", limit: int = Query(50, le=500),
             offset: int = 0) -> dict:
    """One class of open work, largest first.

    Returns the true total alongside the page. A page length shown as a count
    tells the controller there are 200 things left when there are 990, which
    is the difference between an afternoon and a fortnight.
    """
    period = period or settings.period
    total = one("""SELECT count(*) AS n, COALESCE(sum(abs(amount)), 0) AS amount
                     FROM v_worklist
                    WHERE period = %s AND (%s = '' OR kind = %s)""",
                (period, kind, kind))
    items = query("""
        SELECT kind, severity, label, entity, entity_id, amount, detail
          FROM v_worklist
         WHERE period = %s AND (%s = '' OR kind = %s)
         ORDER BY COALESCE(abs(amount), 0) DESC
         LIMIT %s OFFSET %s""", (period, kind, kind, limit, offset))
    return {"kind": kind, "total": total["n"] if total else 0,
            "amount": total["amount"] if total else 0,
            "shown": len(items), "items": items}


@router.get("/activity")
def activity(limit: int = Query(100, le=500), offset: int = 0,
             entity: str = "", entity_id: str = "") -> list[dict]:
    """The audit spine. Filterable to one object, which is how a reviewer
    asks "what happened to this"."""
    return query("""
        SELECT occurred_at, kind, actor, entity, entity_id, label, amount, detail
          FROM v_activity
         WHERE occurred_at IS NOT NULL
           AND (%s = '' OR entity = %s)
           AND (%s = '' OR entity_id = %s)
         ORDER BY occurred_at DESC LIMIT %s OFFSET %s""",
        (entity, entity, entity_id, entity_id, limit, offset))


@router.get("/worklist/mine")
def my_worklist(period: str = None,
                actor: Actor = Depends(current_actor)) -> dict:
    """What *this* person owes, rather than what is outstanding in general.

    v_worklist has always known what is undone and never whose job it is, so
    every screen showed everybody the same list. That is fine for a dashboard
    and useless as a morning: Heidi should open the application and see that
    the buildings have no square footage, Stephanie should see who on her
    projects has not signed for their own effort, and neither should have to
    read past four items belonging to somebody else.

    A CONTROLLER holds everything, so they see everything — that is what the
    portfolio means, not a special case. An item whose portfolio nobody in
    the organisation holds still reaches the controller rather than falling
    off the end.
    """
    period = period or settings.period
    held = {p.value for p in actor.portfolios}
    if Portfolio.CONTROLLER in actor.portfolios:
        rows = query("""SELECT kind, severity, label, entity, entity_id,
                               amount, detail, owner_portfolio, goes_to
                          FROM v_worklist_owned WHERE period = %s
                          ORDER BY CASE severity WHEN 'BLOCKING' THEN 0
                                                 WHEN 'HIGH' THEN 1 ELSE 2 END,
                                   amount DESC NULLS LAST""", (period,))
    elif held:
        rows = query("""SELECT kind, severity, label, entity, entity_id,
                               amount, detail, owner_portfolio, goes_to
                          FROM v_worklist_owned
                         WHERE period = %s AND owner_portfolio = ANY(%s)
                         ORDER BY CASE severity WHEN 'BLOCKING' THEN 0
                                                WHEN 'HIGH' THEN 1 ELSE 2 END,
                                  amount DESC NULLS LAST""",
                     (period, list(held)))
    else:
        rows = []

    # Grouped, because forty-three separate "so-and-so has not certified"
    # rows is a list somebody scrolls past rather than a thing they do.
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["kind"], {
            "kind": r["kind"], "severity": r["severity"],
            "owner_portfolio": r["owner_portfolio"], "goes_to": r["goes_to"],
            "items": 0, "amount": Decimal(0), "examples": []})
        g["items"] += 1
        g["amount"] += Decimal(str(r["amount"] or 0))
        if len(g["examples"]) < 3:
            g["examples"].append({"label": r["label"], "detail": r["detail"]})

    # The project manager's chase list. A manager cannot sign a certification
    # on somebody's behalf — 200.430(i) wants the person whose effort it was
    # — so this is who to go and ask, grouped by the work it is on.
    chase = []
    if held & {"PROJECT", "CONTROLLER"}:
        chase = query("""SELECT objective_id, objective_label, award_id,
                                count(*)          AS people,
                                sum(wages)        AS wages,
                                count(*) FILTER (WHERE stale) AS stale
                           FROM v_certification_chase
                          WHERE period = %s
                          GROUP BY objective_id, objective_label, award_id
                          ORDER BY sum(wages) DESC""", (period,))

    # Your own signature, if you keep a timesheet. Nobody else can give it.
    mine = None
    if actor.employee_key:
        mine = one("""SELECT certified, stale, signed_at, objectives,
                             payroll_wages
                        FROM v_certification_status
                       WHERE period = %s AND employee_key = %s""",
                   (period, actor.employee_key))

    return {"period": period,
            "portfolios": sorted(held),
            "groups": sorted(groups.values(),
                             key=lambda g: (g["severity"] != "BLOCKING",
                                            -float(g["amount"] or 0))),
            "certification_chase": chase,
            "my_certification": mine}
