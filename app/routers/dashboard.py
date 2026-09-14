"""The landing page: where the engagement stands, and what is left to do.

Three questions, answered in one call because they are one question:

  * where do the finances stand, and do the controls tie;
  * what has happened, and who did it;
  * what is still open, in the order it is worth doing.

The work list is ordered by money rather than by age. A hundred small groups
and one large one are not the same afternoon's work.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import (Actor, Portfolio, current_actor, require_any_portfolio,
                      require_own_work, require_reader)
from app.audit import record
from app.db import one, query
from app.settings import settings
from app.statelock import turn

#: No router-level gate, and that is the change. `require_reader` sat here
#: and covered five routes, four of which read the cost record and one of
#: which — `/worklist/mine` — is a person's own list of jobs. A router-level
#: dependency cannot be relaxed by a route, so the one screen written for a
#: narrow portfolio was gated on a permission a narrow portfolio does not
#: carry. Each route names what it needs now.
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(period: str = None, activity_limit: int = Query(25, le=200),
              product: str | None = None,
              actor: Actor = Depends(require_reader)) -> dict:
    period = period or settings.period

    rollup = one("SELECT * FROM v_dashboard WHERE period = %s", (period,))
    # Read, not computed. This handler carried its own copy of the scope —
    # `l.statement = 'P&L'` — which is the predicate `064` moved into
    # `v_cost_line` precisely because grant income is on the P&L and is not
    # cost to classify. So the denominator was 41% revenue and the controller's
    # home screen said **59.7% classified** while
    # `v_classification_coverage` said **100.0%**, at the same moment, over
    # the same 757 judgments. That is 13.0% and 2.2% exactly, in the place a
    # figure gets quoted from.
    #
    # `lines`, `dollars` and `decided_dollars` are kept as names because the
    # screen and the workbooks read them; they come off the one definition now.
    row = one("""SELECT total_lines, decided_lines, scope_dollars, classified,
                        unclassified, pct_dollars_covered
                   FROM v_classification_coverage WHERE period = %s""",
              (period,))
    coverage = None
    pct = 0.0
    if row:
        coverage = {"lines": row["total_lines"],
                    "decided_lines": row["decided_lines"],
                    "dollars": row["scope_dollars"],
                    "decided_dollars": row["classified"],
                    "unclassified": row["unclassified"]}
        pct = float(row["pct_dollars_covered"] or 0)

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

    # Scoped the same way `/worklist/mine` is, and off the same view, because
    # this card and that one were showing the same list to the same person at
    # the same moment with different contents — the audit home carried 43
    # uncertified timesheets in the rollup after they had been taken out of
    # the list above it. Two readings of one question is the shape this
    # repository keeps finding.
    #
    # Unknown is unfiltered, as it is there: a caller that does not say which
    # product it is gets everything.
    scope, args = "", []
    if product in ("audit", "fcs"):
        scope, args = " AND owner_product = %s", [product]
    #
    # `sum(amount)` and not `COALESCE(sum(amount), 0)`: SPACE_UNMEASURED
    # carries no amount at all — there is no dollar figure for "no building
    # has square footage" — and coercing that to zero says the facilities
    # carve-out is worth nothing, which is the opposite of true. It is the
    # single largest adjustment in the rate model. A sum over rows that all
    # hold NULL is NULL, and NULL reaches the screen as a blank; a kind that
    # genuinely nets to zero still reaches it as 0.00, which is a different
    # fact and now prints as one.
    worklist = query(f"""
        SELECT kind, severity, count(*) AS items, sum(amount) AS amount
          FROM v_worklist_owned WHERE period = %s{scope}
         GROUP BY kind, severity
         ORDER BY CASE severity WHEN 'BLOCKING' THEN 0 WHEN 'HIGH' THEN 1
                                ELSE 2 END, sum(amount) DESC NULLS LAST""",
        (period, *args))

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
             offset: int = 0,
             actor: Actor = Depends(require_reader)) -> dict:
    """One class of open work, largest first.

    Returns the true total alongside the page. A page length shown as a count
    tells the controller there are 200 things left when there are 990, which
    is the difference between an afternoon and a fortnight.
    """
    # `v_worklist_owned`, not `v_worklist`: the second is half the list.
    # `v_worklist_extra` holds the kinds added after 011 — the space items,
    # CHARGE_CODE_UNASSIGNED, AWARD_NO_CEILING — and only the owned view
    # unions them in. So this route answered `total = 0` for four kinds that
    # `/worklist/mine` was showing the same person at the same moment, and a
    # page reached by URL said there was nothing open in a class somebody had
    # just been told about. Two endpoints over one question, disagreeing:
    # 13.0% and 2.2% in a smaller place. The owned view is a superset with
    # the routing columns added, so nothing is lost by reading it.
    period = period or settings.period
    total = one("""SELECT count(*) AS n, COALESCE(sum(abs(amount)), 0) AS amount
                     FROM v_worklist_owned
                    WHERE period = %s AND (%s = '' OR kind = %s)""",
                (period, kind, kind))
    items = query("""
        SELECT kind, severity, label, entity, entity_id, amount, detail,
               owner_portfolio, goes_to
          FROM v_worklist_owned
         WHERE period = %s AND (%s = '' OR kind = %s)
         ORDER BY COALESCE(abs(amount), 0) DESC
         LIMIT %s OFFSET %s""", (period, kind, kind, limit, offset))
    return {"kind": kind, "total": total["n"] if total else 0,
            "amount": total["amount"] if total else 0,
            "shown": len(items), "items": items}


@router.get("/activity")
def activity(limit: int = Query(100, le=500), offset: int = 0,
             entity: str = "", entity_id: str = "",
             actor: Actor = Depends(require_reader)) -> list[dict]:
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



@router.get("/refusals")
def refusals(limit: int = 50, mine: bool = True,
             actor: Actor = Depends(current_actor)) -> dict:
    """What the system has refused, and what it said.

    Everybody sees their own without any grant: being told why your own
    button did nothing is not a privilege. Reading somebody else's needs
    `require_reader`, because a refusal names a person and what they were
    trying to do.

    **The gate used to be `require_reader` and the paragraph above was not
    true.** The narrowing four lines down is what protects another person's
    refusals — `everybody` is `actor.can_read and not mine`, so a caller who
    may not read the record only ever sees their own row however they ask.
    The dependency on top of that made "your own" a privilege as well, and
    the failure panel in the shell calls this on every page load: for
    somebody with a timesheet and nothing else it was a 403 every time, a
    console error every time, and a panel that could never show them the one
    thing it exists to show them. It never surfaced while every account in
    the record held a portfolio or a rank; self-registration makes that class
    of person real. A handler whose docstring and whose dependency disagree
    is the screen-and-server defect inside one function.

    `mine=false` from somebody who may not read the record quietly narrows to
    their own rather than refusing — a screen that answers 403 when you untick
    a box is a worse experience than one that shows you what you may see.
    """
    limit = max(1, min(limit, 200))
    everybody = actor.can_read and not mine
    scope, args = ("1=1", ()) if everybody else ("actor_id = %s",
                                                 (actor.actor_id,))

    rows = query(f"""SELECT refusal_id, occurred_at, actor, method, path,
                            status, detail, what_happened, is_a_fault
                       FROM v_refusals_recent
                      WHERE {scope}
                      ORDER BY occurred_at DESC
                      LIMIT {limit}""", args)
    faults = sum(1 for r in rows if r["is_a_fault"])
    return {"refusals": rows, "count": len(rows), "faults": faults,
            "scope": "mine" if scope != "1=1" else "everybody"}


@router.get("/worklist/mine")
def my_worklist(period: str = None, product: str | None = None,
                actor: Actor = Depends(require_own_work)) -> dict:
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
    # Which product is asking. The tabs were split into a year being closed
    # and a company being run, and the worklist was not — so the controller's
    # audit home opened on 43 uncertified timesheets and 43 missing
    # employment terms, two of its six rows being work behind the other door
    # and neither of them work a controller may do: 200.430(i) wants the
    # signature of the person whose effort it was.
    #
    # Unknown is *unfiltered* rather than empty. A caller that does not say
    # which product it is gets everything, which is what `/worklist` has
    # always answered and what a script reading the whole list expects.
    scope, args = "", []
    if product in ("audit", "fcs"):
        scope, args = " AND owner_product = %s", [product]

    columns = """kind, severity, label, entity, entity_id,
                 amount, detail, owner_portfolio, owner_product, goes_to"""
    order = """ORDER BY CASE severity WHEN 'BLOCKING' THEN 0
                                      WHEN 'HIGH' THEN 1 ELSE 2 END,
                        amount DESC NULLS LAST"""
    if Portfolio.CONTROLLER in actor.portfolios:
        rows = query(f"""SELECT {columns} FROM v_worklist_owned
                          WHERE period = %s{scope} {order}""",
                     (period, *args))
    elif held:
        rows = query(f"""SELECT {columns} FROM v_worklist_owned
                          WHERE period = %s AND owner_portfolio = ANY(%s)
                                {scope} {order}""",
                     (period, list(held), *args))
    else:
        rows = []

    # Grouped, because forty-three separate "so-and-so has not certified"
    # rows is a list somebody scrolls past rather than a thing they do.
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["kind"], {
            "kind": r["kind"], "severity": r["severity"],
            "owner_portfolio": r["owner_portfolio"], "goes_to": r["goes_to"],
            "items": 0, "amount": None, "examples": []})
        g["items"] += 1
        # Same rule as the rollup above, which this card has to agree with:
        # a kind with no amount on any of its rows keeps no amount, rather
        # than accumulating into a zero that reads as a figure.
        if r["amount"] is not None:
            g["amount"] = (g["amount"] or Decimal(0)) + Decimal(str(r["amount"]))
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


class RecommendIn(BaseModel):
    kind: str
    entity_id: str
    #: Required, and long enough to be a sentence. A recommendation with no
    #: reason is a reprint of the machine's list with a person's name on it,
    #: which is worth less than the machine's list — the reader now has to
    #: work out whether a human added anything. Same rule as `rationale` on
    #: a judgment and `basis` on a restatement.
    reason: str = Field(min_length=15, max_length=2000)
    #: Who to ask. A person naming a person beats a rule guessing between
    #: two — the lesson `060` learned on `hand_to`. Left out, the sole other
    #: CONTROLLER gets it, or nobody does and the reason says why.
    hand_to: str | None = None
    due_in_days: int = Field(default=14, ge=1, le=365)


@router.post("/worklist/recommend", status_code=201)
def recommend(body: RecommendIn, period: str = None,
              actor: Actor = Depends(require_any_portfolio)) -> dict:
    """Say that an outstanding item is worth somebody's attention, and whose.

    **The helper recommends; the controller verifies and seals.** Nothing
    here touches a decision set, a rate or a restatement — a recommendation
    raises *work*, never a number, so the guarantee the whole system is built
    on is untouched by it. What it adds is the fact the record could not
    hold: `audit_log` says who *decided*, and until now nothing said who
    *noticed*. An auditor asking why this invoice was restated and not that
    one has an answer with two names on it rather than one.

    Three rules, and each is one this system already follows somewhere:

    * **The item has to be outstanding.** It is looked up in
      `v_worklist_owned` inside the turn, so a recommendation cannot name
      something that has since been cleared. "Read what you are about to
      depend on inside the turn" — the lock rule, in a small place.
    * **You can only recommend what is on your own list.** Holding the
      portfolio the item is routed to, or CONTROLLER, which reaches
      everything. The refusal names whose list it is on, because "403" sends
      somebody to find an administrator without knowing what to ask for.
    * **Nobody recommends to themselves.** Handing yourself a job is taking
      one, which is a different act and reads differently on the record. The
      same rule as *nobody grants themselves a portfolio* and *nobody
      assigns themselves a charge code*.
    """
    from app.routers.projects import _hand_to

    period = period or settings.period
    held = {p.value for p in actor.portfolios}
    is_controller = Portfolio.CONTROLLER in actor.portfolios

    with turn(period) as cur:
        cur.execute("""SELECT kind, label, entity, entity_id, severity,
                              amount, detail, owner_portfolio, goes_to
                         FROM v_worklist_owned
                        WHERE period = %s AND kind = %s AND entity_id = %s""",
                    (period, body.kind, body.entity_id))
        item = cur.fetchone()
        if not item:
            raise HTTPException(
                404, f"{body.kind} on {body.entity_id} is not outstanding in "
                     f"{period}. Either it has been cleared since the screen "
                     f"was drawn — which is the good outcome — or the name is "
                     f"wrong. Reload the list.")

        if not (is_controller or item["owner_portfolio"] in held):
            raise HTTPException(
                403, f"{body.kind} is {item['owner_portfolio']}'s to deal "
                     f"with and {actor.display_name} holds "
                     f"{', '.join(sorted(held)) or 'none'}. You can only "
                     f"recommend something that is on your own list.")

        if body.hand_to:
            # By id or by email, the way `/projects` takes it. A screen has
            # the id and a person typing has the address, and refusing one of
            # them makes the field usable from only one of the two places it
            # is reached from.
            cur.execute("""SELECT actor_id, display_name FROM actor
                            WHERE (actor_id::text = %s OR email = %s)
                              AND is_active""",
                        (body.hand_to, body.hand_to))
            who = cur.fetchone()
            if not who:
                raise HTTPException(
                    404, f"No active account matching {body.hand_to!r}. Give "
                         f"an account id or an email address, or leave it out "
                         f"and it goes to whoever holds CONTROLLER.")
            if str(who["actor_id"]) == str(actor.actor_id):
                raise HTTPException(
                    422, "Handing yourself a job is taking one, which is a "
                         "different act. Open a todo on it instead — a "
                         "recommendation is a thing you ask of somebody "
                         "else, and the record should read that way.")
            assignee, to_whom = str(who["actor_id"]), who["display_name"]
        else:
            assignee, to_whom = _hand_to(cur, actor, Portfolio.CONTROLLER.value)

        title = str(item["label"])[:200]
        detail = (f"Recommended by {actor.display_name}: {body.reason.strip()}"
                  f"\n\nWhat the list says: {item['detail'] or item['label']}"
                  f"\nDealt with on {item['goes_to']}.")
        try:
            cur.execute("""INSERT INTO todo (period, title, detail, due_on,
                                             status, worklist_kind,
                                             worklist_entity_id,
                                             assignee_actor, opened_by)
                           VALUES (%s,%s,%s,%s,'OPEN',%s,%s,%s::uuid,%s)
                        RETURNING todo_id""",
                        (period, title, detail,
                         dt.date.today() + dt.timedelta(days=body.due_in_days),
                         item["kind"], item["entity_id"], assignee,
                         actor.display_name))
        except Exception as exc:                       # noqa: BLE001
            if "one_live_job_per_worklist_item" not in str(exc):
                raise
            raise HTTPException(
                409, f"Somebody already has this one. {item['label']} carries "
                     f"a live job already, and two people each told to clear "
                     f"it is two people each assuming the other has. Open the "
                     f"existing one rather than raising a second.") from exc

        todo_id = str(cur.fetchone()["todo_id"])
        record(actor, "TODO_RECOMMEND", "todo", todo_id,
               after={"kind": item["kind"], "entity_id": item["entity_id"],
                      "label": item["label"], "to_whom": to_whom,
                      "assigned": assignee is not None},
               reason=body.reason.strip(), cursor=cur)

    return {"todo_id": todo_id, "period": period,
            "kind": item["kind"], "entity_id": item["entity_id"],
            "label": item["label"],
            "recommended_by": actor.display_name,
            #: Says it rather than leaving it to be inferred: `assigned` false
            #: with a reason is a real outcome, not a failure.
            "assigned": assignee is not None, "to_whom": to_whom}
