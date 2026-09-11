"""
Classification queue.

This is the screen that decides whether the project succeeds. Everything else
is reporting. Three rules shape the API:

  1. Work at group grain. The 5,096 P&L lines collapse to 999 account x payee
     groups, and the top 200 carry 93.3% of the dollars — the top 100 carry
     84.4%. A row-by-row queue is a workload that does not need to exist and
     will not finish by November.

     Those figures are read off `v_classification_coverage` and the queue
     itself; the ones here were written against a 4,020-line extract that
     predates the full ledger, said 751 groups and 94.7%, and were quoted
     into a status memo for the board before anybody checked them.

  2. Propose, never ask blind. Every group arrives pre-filled from the QBO
     Customer:Job segment, the account name, or a prior-year decision. Tom
     confirms or overrides.

  3. The rate is not computed here and not returned by any endpoint in this
     module. Progress is measured in dollar coverage, not in the number the
     classifications will eventually produce.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import Depends, APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_controller, require_reader
from app.audit import record
from app.domain.core import money
from app.vocab import (EvidenceGrade, FederalTreatment, Function990,
                       Pool)
from app.auth import Actor
from app.db import execute, one, query, transaction
from app.statelock import turn
from app.domain.advice import GroupFacts, advise
from app.domain.chart import pool_for
from app.domain.crosswalk import CROSSWALK
from app.domain.segment import Part, SegmentError, plan_segments

router = APIRouter(prefix="/classify", tags=["classify"],
                   dependencies=[Depends(require_reader)])

# The vocabulary endpoint serves these to the UI. Derived from the same enums
# the request models validate against, so the list a person is offered and the
# list the server accepts cannot drift apart.
POOLS = [p.value for p in Pool]
FUNCTIONS = [f.value for f in Function990]
FEDERAL = [f.value for f in FederalTreatment]
GRADES = [g.value for g in EvidenceGrade]


class GroupOut(BaseModel):
    group_key: str
    account: str
    payee: str
    line_count: int
    amount: Decimal
    abs_amount: Decimal
    objective_hint: str = ""
    sample_memos: list[str] = []
    decided: bool = False
    stale: bool = False
    #: What is live on this group right now — a decision id, "none", or
    #: "several" where the group is covered by more than one judgment. The
    #: screen sends it straight back as `based_on` so a judgment made from a
    #: stale queue is refused with a sentence rather than silently replacing
    #: a colleague's work.
    live_decision: str = "none"
    #: Who made it, for that sentence.
    decided_by: str = ""
    proposal: dict | None = None
    evidence_count: int = 0
    note_count: int = 0


class DecideIn(BaseModel):
    group_keys: list[str] = Field(..., min_length=1)
    # Typed against the database's own enums, so a wrong value is a 422 that
    # names what is allowed rather than a 500 from the driver.
    pool: Pool
    function_990: Function990
    federal: FederalTreatment
    objective_id: str | None = None
    grade: EvidenceGrade = EvidenceGrade.CORROBORATED
    rationale: str = ""
    citation: str | None = None
    evidence_ids: list[str] = []
    #: Ignored — the decision is recorded as the signed-in actor.
    #: Kept so an older client is not rejected, optional so a
    #: newer one need not send a field that means nothing.
    decided_by: str = ""
    supersedes: str | None = None
    #: What the screen believed was live for each group when it was drawn:
    #: group_key -> the live decision_id it showed, or "none" where it showed
    #: the group unjudged. Where a key is present and what is actually live
    #: differs, the judgment is refused and the person is told who changed it
    #: and when — rather than silently superseding a colleague's work off a
    #: screen drawn before they did it.
    #:
    #: Optional, and absent means "not participating". A script doing a bulk
    #: reclassification has no screen to be stale, and refusing it would make
    #: the crosswalk unloadable.
    based_on: dict[str, str] = {}


class CoverageOut(BaseModel):
    period: str
    total_lines: int
    decided_lines: int
    total_dollars: Decimal
    decided_dollars: Decimal
    pct_dollars: Decimal
    groups_total: int
    groups_decided: int
    groups_remaining: int
    dollars_remaining: Decimal


@router.get("/coverage", response_model=CoverageOut)
def coverage(period: str = "2025") -> CoverageOut:
    """The only progress metric that matters. Tom stops when dollar coverage
    is high enough to defend, not when the row count reaches zero."""
    # Read, never re-derived. This handler used to carry its own copy of
    # the scope — the right one, with the reason in a comment — while
    # v_classification_coverage carried a different one, and the two answered
    # 13.0% and 2.2% at the same moment over the same decision. The
    # definition lives in the view now (039); this reads it.
    r = one("""SELECT total_lines, decided_lines, groups_total, groups_decided,
                      scope_dollars, classified, pct_dollars_covered
                 FROM v_classification_coverage WHERE period = %s""",
            (period,))
    if not r:
        raise HTTPException(404, "No ledger loaded for that period.")
    total = Decimal(r["scope_dollars"] or 0)
    decided = Decimal(r["classified"] or 0)
    return CoverageOut(
        period=period,
        total_lines=r["total_lines"], decided_lines=r["decided_lines"],
        total_dollars=total, decided_dollars=decided,
        # The percentage comes from the view as well rather than being
        # computed again here from the same two numbers — which would be a
        # third implementation of one figure.
        pct_dollars=Decimal(str(r["pct_dollars_covered"] or 0)),
        groups_total=r["groups_total"], groups_decided=r["groups_decided"],
        groups_remaining=r["groups_total"] - r["groups_decided"],
        dollars_remaining=total - decided,
    )


@router.get("/queue", response_model=list[GroupOut])
def queue(period: str = "2025",
          status: str = Query("undecided", pattern="^(undecided|decided|stale|all)$"),
          search: str = "",
          limit: int = Query(50, le=200),
          offset: int = 0) -> list[GroupOut]:
    """Groups ordered by absolute dollars, largest first. Working top-down is
    what turns 751 decisions into 80% coverage in 200."""
    rows = query("""
        SELECT l.account, l.payee,
               count(*)                              AS line_count,
               sum(l.amount)                         AS amount,
               sum(abs(l.amount))                    AS abs_amount,
               max(l.customer_job_hint)              AS objective_hint,
               (array_agg(l.description ORDER BY abs(l.amount) DESC)
                  FILTER (WHERE l.description <> ''))[1:3] AS sample_memos,
               bool_or(d.decision_id IS NOT NULL)    AS decided,
               -- What the screen has to send back to prove it was not drawn
               -- before somebody else's judgment. Exactly one live decision
               -- is the ordinary case; the other two are named rather than
               -- collapsed, because "several" and "none" are different
               -- states and a judgment made against either is stale in a
               -- different way.
               count(DISTINCT d.decision_id)         AS live_decisions,
               max(d.decision_id::text)              AS live_decision,
               max(d.decided_by)                     AS decided_by,
               bool_or(rev.revision_id IS NOT NULL)  AS stale,
               count(DISTINCT att.attachment_id)     AS evidence_count,
               count(DISTINCT n.note_id)             AS note_count
          FROM ledger_line l
          -- `dl.live` is load-bearing. Without it a line that has been
          -- reclassified joins once per judgment it has ever carried, and
          -- every sum in this query multiplies: a group judged four times
          -- printed four times its amount, on the screen the whole
          -- engagement is worked from.
          LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
          LEFT JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
          LEFT JOIN ledger_revision rev ON rev.line_id = l.line_id
                                       AND rev.affects_decision IS NOT NULL
          LEFT JOIN attachment att ON att.target_type = 'LEDGER_LINE'
                                  AND att.target_id = l.line_id
                                  AND att.detached_at IS NULL
          LEFT JOIN note n ON n.target_type = 'LEDGER_LINE' AND n.target_id = l.line_id
         WHERE l.period = %(period)s
           AND l.statement = 'P&L'
           AND (%(search)s = '' OR l.account ILIKE %(like)s OR l.payee ILIKE %(like)s)
         GROUP BY l.account, l.payee
        HAVING CASE %(status)s
                 WHEN 'undecided' THEN NOT bool_or(d.decision_id IS NOT NULL)
                 WHEN 'decided'   THEN bool_or(d.decision_id IS NOT NULL)
                 WHEN 'stale'     THEN bool_or(rev.revision_id IS NOT NULL)
                 ELSE true END
         ORDER BY sum(abs(l.amount)) DESC
         LIMIT %(limit)s OFFSET %(offset)s
    """, {"period": period, "status": status, "search": search,
          "like": f"%{search}%", "limit": limit, "offset": offset})

    out: list[GroupOut] = []
    for r in rows:
        g = GroupOut(
            group_key=f"{r['account']}\x1f{r['payee']}",
            account=r["account"], payee=r["payee"] or "",
            line_count=r["line_count"],
            amount=Decimal(r["amount"] or 0), abs_amount=Decimal(r["abs_amount"] or 0),
            objective_hint=r["objective_hint"] or "",
            sample_memos=[m for m in (r["sample_memos"] or []) if m],
            decided=bool(r["decided"]), stale=bool(r["stale"]),
            live_decision=("none" if not r["live_decisions"]
                           else r["live_decision"] if r["live_decisions"] == 1
                           else "several"),
            decided_by=r["decided_by"] or "",
            evidence_count=r["evidence_count"] or 0, note_count=r["note_count"] or 0,
        )
        g.proposal = propose(g)
        out.append(g)
    return out


def propose(g: GroupOut) -> dict | None:
    """A proposal, never a decision.

    Ordered by strength of signal: QuickBooks already knowing the objective
    beats a name pattern, and a name pattern beats a guess. Anything without a
    signal returns None and stays in the queue rather than being defaulted
    into a pool — the rate should be overstated while work is unfinished, not
    quietly completed.
    """
    a = (g.account or "").lower()

    if g.objective_hint:
        return {"pool": "DIRECT", "function_990": "PROGRAM", "federal": "ALLOWABLE",
                "objective_id": g.objective_hint, "grade": "CORROBORATED",
                "citation": "2 CFR 200.413(a)",
                "rationale": f"QuickBooks Customer:Job identifies {g.objective_hint}",
                "source": "customer_job", "confidence": "high"}

    if any(k in a for k in ("benefit", "social security", "401k", "futa", "sui",
                            "worker's comp", "workers comp")):
        return {"pool": "FRINGE", "function_990": "NOT_APPLICABLE", "federal": "ALLOWABLE",
                "objective_id": None, "grade": "CORROBORATED", "citation": "2 CFR 200.431",
                "rationale": "Employee benefit cost, pooled and applied on a wage base",
                "source": "account_name", "confidence": "high"}

    if any(k in a for k in ("depreciation", "maintenance", "electric", "heating",
                            "real estate tax", "utilit", "janitor", "security",
                            "t1 access", "insurance - building")):
        return {"pool": "OVERHEAD", "function_990": "PROGRAM", "federal": "ALLOWABLE",
                "objective_id": None, "grade": "CORROBORATED",
                "citation": "2 CFR 200 Appendix IV B.3",
                "rationale": "Facilities and related occupancy cost",
                "source": "account_name", "confidence": "medium"}

    if any(k in a for k in ("meals & entertainment", "interest", "bad debt",
                            "government relations", "lobby", "contributions")):
        return {"pool": "UNALLOWABLE", "function_990": "MANAGEMENT_AND_GENERAL",
                "federal": "UNALLOWABLE", "objective_id": None, "grade": "CORROBORATED",
                "citation": "2 CFR 200.420-475",
                "rationale": "Expressly unallowable federally; still reportable on Form 990",
                "source": "account_name", "confidence": "medium"}

    if any(k in a for k in ("advertising", "special events", "shark tank",
                            "fundrais", "workshops")):
        return {"pool": "FUNDRAISING", "function_990": "FUNDRAISING",
                "federal": "UNALLOWABLE", "objective_id": None, "grade": "CORROBORATED",
                "citation": "2 CFR 200.442",
                "rationale": "Fundraising and bid & proposal activity",
                "source": "account_name", "confidence": "medium"}

    prior = one("""
        SELECT d.pool, d.function_990, d.federal, d.objective_id
          FROM decision d
          JOIN decision_line dl ON dl.decision_id = d.decision_id
          JOIN ledger_line l ON l.line_id = dl.line_id
         WHERE l.account = %s AND l.period <> %s AND d.reversed_at IS NULL
         ORDER BY d.decided_at DESC LIMIT 1
    """, (g.account, "2025"))
    if prior:
        return {**prior, "grade": "CORROBORATED", "citation": None,
                "rationale": f"Consistent with the prior-year treatment of {g.account}",
                "source": "prior_year", "confidence": "medium"}

    # The 2026 crosswalk, which is a mapping somebody already built and
    # reviewed: every one of the 85 accounts in the 2025 chart against the
    # account number it becomes, and `pool_for()` reads the pool off that
    # number. Sixty-one map one-to-one and are a real signal.
    #
    # The other twenty-four are splits — depreciation by square footage,
    # wages by timesheet — and those return nothing. A split needs a
    # documented driver, which is a judgment with a person's name on it, and
    # proposing one side of it would be inventing the driver.
    leaf = (g.account or "").rsplit(":", 1)[-1].strip()
    mapped = CROSSWALK.get(leaf)
    if mapped and "/" not in mapped[0]:
        try:
            pool = pool_for(mapped[0]).value
        except Exception:                          # noqa: BLE001
            pool = None
        if pool:
            return {
                "pool": pool,
                # The 990 function and the federal treatment do not fall out
                # of an account number, so they stay at the safe reading and
                # the person confirming sets them. A proposal that guesses
                # the function would put cost in a column of the return
                # nobody chose.
                "function_990": "PROGRAM" if pool in ("DIRECT", "OVERHEAD")
                                else "NOT_APPLICABLE",
                "federal": "PENDING",
                "objective_id": None,
                "grade": "CORROBORATED",
                "citation": "2026 chart crosswalk",
                "rationale": (f"The 2026 crosswalk maps {leaf} to account "
                              f"{mapped[0]}, which is a {pool} account"),
                "source": "crosswalk", "confidence": "medium"}

    return None


class MaterialityIn(BaseModel):
    verified_above: float = Field(ge=0)
    corroborated_above: float = Field(ge=0)
    federal_corroborated_above: float = Field(ge=0)
    basis: str


@router.get("/materiality")
def materiality(period: str = "2025") -> dict:
    """The evidence standard each size of cost has to meet, and who is short.

    Without a written policy, a $600 group and a $600,000 group are held to
    the same standard — which means either the small ones are over-worked or
    the large ones are under-worked, and nothing says which. With one, doing
    less on small items is a stated position rather than an omission.
    """
    policy = one("""SELECT policy_id, verified_above, corroborated_above,
                           federal_corroborated_above, basis, set_by_name, set_at
                      FROM materiality_policy
                     WHERE period = %s AND superseded_at IS NULL""", (period,))
    rows = query("""SELECT scope, pool, amount, grade::text AS grade,
                           required_grade::text AS required_grade,
                           meets_standard, federal::text AS federal, decided_by
                      FROM v_materiality_compliance
                     WHERE period = %s ORDER BY meets_standard, amount DESC""",
                 (period,))
    return {"period": period, "policy": policy,
            "judgments": len(rows),
            "short": [r for r in rows if not r["meets_standard"]],
            "short_amount": sum(float(r["amount"]) for r in rows
                                if not r["meets_standard"])}


@router.put("/materiality")
def put_materiality(body: MaterialityIn, period: str = "2025",
                    actor: Actor = Depends(require_controller)) -> dict:
    """Set the policy. Superseded, never edited — the standard in force when a
    judgment was made is part of that judgment's defence."""
    if body.verified_above < body.corroborated_above:
        raise HTTPException(
            422, "The verified threshold cannot be below the corroborated "
                 "one — a larger cost cannot need weaker evidence.")
    with transaction() as cur:
        cur.execute("""UPDATE materiality_policy SET superseded_at = now()
                        WHERE period = %s AND superseded_at IS NULL""", (period,))
        cur.execute("""INSERT INTO materiality_policy
                         (period, verified_above, corroborated_above,
                          federal_corroborated_above, basis, set_by, set_by_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING policy_id""",
                    (period, body.verified_above, body.corroborated_above,
                     body.federal_corroborated_above, body.basis.strip(),
                     actor.actor_id, actor.display_name))
        pid = cur.fetchone()["policy_id"]
        record(actor, "MATERIALITY", "materiality_policy", str(pid),
               after={"verified_above": body.verified_above,
                      "corroborated_above": body.corroborated_above,
                      "federal_corroborated_above":
                          body.federal_corroborated_above},
               reason=body.basis.strip()[:400], cursor=cur)
    return {"policy_id": pid}


@router.get("/advice")
def advice(group_key: str, period: str = "2025") -> dict:
    """What is worth thinking about before this group is classified.

    Advice, never a decision — the same rule that governs proposals. It reads
    the shape of the group and the treatment of the same account elsewhere,
    and every item carries the rule it rests on, because "split this" without
    the citation is an opinion.
    """
    account, _, payee = group_key.partition("\x1f")
    facts = one("""
        SELECT %s::text AS account, %s::text AS payee,
               COALESCE(sum(l.amount), 0)                   AS amount,
               count(*)                                     AS line_count,
               COALESCE(array_agg(DISTINCT l.customer_job_hint)
                        FILTER (WHERE COALESCE(l.customer_job_hint,'') <> ''), '{}')
                                                            AS objective_hints,
               COALESCE(array_agg(DISTINCT left(l.description, 120))
                        FILTER (WHERE COALESCE(l.description,'') <> ''), '{}')
                                                            AS memos
          FROM ledger_line l
         WHERE l.period = %s AND l.account = %s
           AND coalesce(l.payee,'') = %s""",
        (account, payee, period, account, payee))
    if not facts or not facts["line_count"]:
        raise HTTPException(404, "No lines in that group.")

    # How the same account is treated elsewhere in the period, and last year.
    prior = query("""SELECT DISTINCT d.pool::text AS pool
                       FROM decision d
                       JOIN decision_line dl ON dl.decision_id = d.decision_id
                                            AND dl.live
                       JOIN ledger_line l ON l.line_id = dl.line_id
                      WHERE d.reversed_at IS NULL AND l.period = %s
                        AND l.account = %s
                        AND coalesce(l.payee,'') <> %s""",
                  (period, account, payee))

    evidence = one("""SELECT count(DISTINCT a.evidence_id) AS n
                        FROM attachment a
                        JOIN ledger_line l ON l.line_id::text = a.target_id
                       WHERE a.target_type = 'LEDGER_LINE'
                         AND a.detached_at IS NULL AND l.period = %s
                         AND l.account = %s AND coalesce(l.payee,'') = %s""",
                   (period, account, payee))

    g = GroupFacts(
        account=facts["account"], payee=facts["payee"] or "",
        amount=facts["amount"], line_count=facts["line_count"],
        objective_hints=list(facts["objective_hints"] or []),
        memos=list(facts["memos"] or []),
        evidence_count=(evidence or {}).get("n", 0),
        prior_pools=[r["pool"] for r in prior])

    return {"group_key": group_key,
            "advice": [{"kind": a.kind, "headline": a.headline,
                        "detail": a.detail, "citation": a.citation,
                        "weight": a.weight} for a in advise(g)]}


@router.post("/decide")
def decide(body: DecideIn, period: str = "2025",
           actor: Actor = Depends(require_controller)) -> dict:
    """Record decisions for one or more groups. Fans out to every line in the
    group; the audit trail is at line grain even though the work is at group
    grain.

    The decision is recorded as the signed-in actor. body.decided_by is
    ignored: a cost judgment cannot be recorded in someone else's name."""
    decided_by = actor.display_name
    if body.pool not in POOLS:
        raise ValueError(f"Unknown pool {body.pool}")
    if body.function_990 not in FUNCTIONS:
        raise ValueError(f"Unknown 990 function {body.function_990}")
    if body.federal not in FEDERAL:
        raise ValueError(f"Unknown federal treatment {body.federal}")
    if body.grade not in GRADES:
        raise ValueError(f"Unknown evidence grade {body.grade}")
    if (body.pool == "DIRECT") != bool(body.objective_id):
        raise ValueError("Direct cost requires a cost objective; pooled cost must not carry one.")
    if body.grade not in ("UNSUPPORTED", "TEST_ASSUMPTION") and not body.rationale.strip():
        raise ValueError("A supported grade requires a written rationale.")

    created = 0
    replaced = 0
    lines_covered = 0
    amount_covered = Decimal(0)
    # One turn for the whole request, not one per group.
    #
    # Two reasons. The VERIFIED gate is a deferred constraint trigger that
    # fires at COMMIT, so a decision and the evidence it cites have to land
    # together or an evidenced judgment is refused as unevidenced. And a
    # refusal partway through a batch used to leave the groups before it
    # recorded while the response said nothing was — so a bulk judgment over
    # eleven groups could half happen. Either all of it is on the record or
    # none of it is, which is what the message below is entitled to claim.
    with turn(period) as cur:
        # Inside the turn, not before it.
        #
        # This lookup used to sit above, on its own connection, and that is
        # how a judgment got into a sealed set: seven requests all read "set
        # X is open", the seal took the lock and froze X, and the four
        # judgments still queued behind it inserted into X afterwards — so
        # the stored hash covered two judgments and the set held six. The
        # concurrency drive reproduces it exactly. Read under the lock, a
        # judgment arriving after the seal finds no open set and is refused,
        # which is the whole meaning of sealing.
        cur.execute("""SELECT set_id FROM decision_set
                        WHERE period = %s AND seal_hash IS NULL
                        ORDER BY set_id LIMIT 1""", (period,))
        st = cur.fetchone()
        if not st:
            raise HTTPException(409, {
                "error": "SET_IS_SEALED",
                "message": ("The classifications for this period are sealed, so "
                            "nothing can be added to them. Unsealing takes a "
                            "written reason and supersedes any rate computed "
                            "from them.")})
        set_id = st["set_id"]

        for key in body.group_keys:
            account, _, payee = key.partition("\x1f")
            # `amount` as well as `line_id`, so the response can say what
            # the judgment covered without a second round trip — and from
            # the same rows the decision is attached to, rather than from a
            # separate sum that could disagree with them.
            cur.execute("""SELECT line_id, amount FROM ledger_line
                            WHERE period = %s AND account = %s AND payee = %s""",
                        (period, account, payee))
            with_lines = cur.fetchall()
            if not with_lines:
                continue
            # Reclassifying supersedes; it does not stack.
            #
            # `one_live_decision_per_unit` means a line already carrying a
            # live decision cannot take a second, and the line insert below
            # used to swallow that with ON CONFLICT DO NOTHING. So a second
            # judgment on a decided group produced a live decision with *no
            # lines*, the handler answered 200 "decisions_created: 1", and
            # nothing moved: the pools still read the old pool, two live
            # decisions disagreed with each other, and the controller was
            # told it had worked.
            #
            # That is the worst shape a bug can take here. Not a refusal —
            # a refusal is visible — but a success that does nothing, over
            # the figures a rate is built from.
            cur.execute("""SELECT DISTINCT d.decision_id
                             FROM decision d
                             JOIN decision_line dl USING (decision_id)
                            WHERE dl.live
                              AND d.reversed_at IS NULL
                              AND dl.line_id = ANY(%s)""",
                        ([l["line_id"] for l in with_lines],))
            superseded = [r["decision_id"] for r in cur.fetchall()]

            # Is the screen this came from still describing the record?
            #
            # Two controllers work the queue at once. Tom judges 5227 at
            # 10:31; Barb's queue was drawn at 10:29 and still shows it
            # unjudged, so her Enter at 10:32 silently replaces a judgment
            # she never saw. The lock makes that ordering deterministic —
            # it does not make it comprehensible. This does.
            expected = body.based_on.get(key)
            if expected is not None:
                actual = str(superseded[0]) if len(superseded) == 1 else (
                    "none" if not superseded else "several")
                if expected != actual:
                    cur.execute("""SELECT d.decided_by, d.decided_at, d.pool::text
                                          AS pool
                                     FROM decision d
                                     JOIN decision_line dl USING (decision_id)
                                    WHERE dl.live AND d.reversed_at IS NULL
                                      AND dl.line_id = ANY(%s)
                                    ORDER BY d.decided_at DESC LIMIT 1""",
                                ([l["line_id"] for l in with_lines],))
                    cur_live = cur.fetchone()
                    if cur_live:
                        detail = (f"{cur_live['decided_by'] or 'Somebody'} "
                                  f"classified it as {cur_live['pool']} at "
                                  f"{cur_live['decided_at']:%H:%M}")
                    else:
                        detail = "the judgment it carried has since been undone"
                    raise HTTPException(409, {
                        "error": "GROUP_MOVED",
                        "group_key": key,
                        "message": (f"{account} changed while this screen was "
                                    f"open — {detail}. Nothing was recorded. "
                                    f"Reload the queue and decide again if you "
                                    f"still want to replace it."),
                        "expected": expected, "actual": actual})

            for old_id in superseded:
                # A trigger flips decision_line.live when reversed_at is set,
                # which is what frees the lines for the judgment replacing
                # them. Reversing is the same mechanism undo uses; there is
                # deliberately not a second one.
                # `decision` carries reversed_at and reversal_reason; who
                # did it comes from the audit entry, which names the session.
                cur.execute("""UPDATE decision
                                  SET reversed_at = now(),
                                      reversal_reason = %s
                                WHERE decision_id = %s
                                  AND reversed_at IS NULL""",
                            (f"Superseded by {decided_by}, judging the same "
                             f"group again: {body.rationale}"[:500], old_id))

            cur.execute("""
                INSERT INTO decision (set_id, scope, pool, function_990, federal,
                                      objective_id, grade, rationale, citation,
                                      decided_by, supersedes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING decision_id
            """, (set_id, f"account={account}|payee={payee}", body.pool,
                  body.function_990, body.federal, body.objective_id, body.grade,
                  body.rationale, body.citation, decided_by,
                  # Which judgment this one replaces. Only where exactly one
                  # did: a group covered by two is a state worth seeing in
                  # the audit reason rather than half-recorded in a column
                  # that holds one.
                  body.supersedes or (str(superseded[0])
                                      if len(superseded) == 1 else None)))
            did = cur.fetchone()["decision_id"]
            for l in with_lines:
                cur.execute("""INSERT INTO decision_line (decision_id, line_id)
                               VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                            (did, l["line_id"]))
            # Prove it landed. ON CONFLICT DO NOTHING is how the silent
            # failure above was possible, so the handler now checks rather
            # than assumes — a judgment that did not attach to the cost it
            # judges is not a judgment, and it must not be reported as one.
            cur.execute("SELECT count(*) AS n FROM decision_line "
                        "WHERE decision_id = %s AND live", (did,))
            attached = cur.fetchone()["n"]
            if attached != len(with_lines):
                raise HTTPException(
                    409,
                    f"That judgment would have covered {attached} of "
                    f"{len(with_lines)} lines in {account}. Something else "
                    f"holds the rest — most likely they are split into "
                    f"segments judged separately. Nothing was recorded.")
            for ev in body.evidence_ids:
                cur.execute("""INSERT INTO decision_evidence (decision_id, evidence_id)
                               VALUES (%s,%s) ON CONFLICT DO NOTHING""", (did, ev))
            # Inside the transaction: an audit row that survived a rolled
            # back decision would describe something that never happened.
            record(actor, "CLASSIFY", "decision", str(did),
                   before=({"superseded": [str(x) for x in superseded]}
                           if superseded else None),
                   after=body.model_dump(mode="json"), reason=body.rationale,
                   cursor=cur)
            created += 1
            replaced += len(superseded)
            lines_covered += attached
            amount_covered += sum(l["amount"] for l in with_lines)

    # `superseded` says so plainly, because "decisions_created: 1" read the
    # same whether a group was judged for the first time or rejudged — and
    # the screen has no other way to tell a person their change replaced
    # something.
    #
    # `lines` and `amount` for the same reason one step along. **Classifying
    # a group of forty-five lines records one decision with a scope, not
    # forty-five** — which is right, and which from the outside is
    # indistinguishable from a judgment that only landed on one of them. The
    # system review's proportion check could not tell the difference, and
    # neither can a person reading "1 decision recorded" after judging
    # $1.2m across thirteen lines. The count is already computed to prove
    # the lines landed; this is saying it out loud.
    return {"decisions_created": created, "superseded": replaced,
            "lines": lines_covered, "amount": str(money(amount_covered)),
            "set_id": str(set_id)}


@router.post("/defer")
def defer(group_key: str, reason: str, period: str = "2025",
          actor: Actor = Depends(require_controller)) -> dict:
    """Explicitly park a group. Deferred is a state, not an absence of one —
    it keeps the item visible instead of letting it drift out of view."""
    if not reason.strip():
        raise HTTPException(422, "Deferring needs a reason; that is the point of it.")
    account, _, payee = group_key.partition("\x1f")
    execute("""INSERT INTO note (target_type, target_id, body, author, is_workpaper)
               VALUES ('LEDGER_GROUP', %s, %s, %s, true)""",
            (group_key, f"Deferred: {reason}", actor.display_name))
    record(actor, "DEFER", "ledger_group", group_key, reason=reason)
    return {"deferred": group_key}


@router.get("/vocabulary")
def vocabulary() -> dict:
    """Four independent dimensions, because one enum cannot serve both Form 990
    Part IX and 2 CFR 200 Subpart E. Interest is federally unallowable and a
    reportable 990 expense; lobbying is unallowable and triggers Schedule C."""
    return {"pools": POOLS, "functions": FUNCTIONS,
            "federal": FEDERAL, "grades": GRADES,
            "objectives": query("""SELECT objective_id, label, is_federal
                                     FROM cost_objective WHERE active
                                    ORDER BY objective_id""")}


class PartIn(BaseModel):
    label: str
    share: Decimal
    rationale: str
    citation: str | None = None


class SegmentIn(BaseModel):
    group_key: str
    parts: list[PartIn]
    #: Ignored, as decided_by is. Identity comes from the session.
    created_by: str = ""


@router.post("/segment")
def segment(body: SegmentIn, period: str = "2025",
            actor: Actor = Depends(require_controller)) -> dict:
    """Split a group's lines into analytically distinct parts.

    The source ledger is untouched. Every line reconciles to the cent, or the
    whole segmentation is refused at COMMIT — which is why this runs in one
    transaction rather than line by line.
    """
    account, _, payee = body.group_key.partition("\x1f")
    rows = query("""SELECT line_id, amount FROM ledger_line
                     WHERE period=%s AND account=%s AND coalesce(payee,'')=%s""",
                 (period, account, payee))
    if not rows:
        raise HTTPException(404, "No lines in that group.")

    live = one("""SELECT count(*) AS n FROM ledger_segment s
                   JOIN ledger_line l USING (line_id)
                  WHERE l.period=%s AND l.account=%s AND coalesce(l.payee,'')=%s
                    AND s.reversed_at IS NULL""", (period, account, payee))
    if live and live["n"]:
        raise HTTPException(
            409, "This group is already segmented. Reverse the existing "
                 "segmentation before splitting it differently.")

    # Identity comes from the session, exactly as it does for a decision.
    # body.created_by is a label the client may send; it is not a claim about
    # who did this.
    created_by = actor.display_name or body.created_by
    parts = [Part(label=p.label, share=p.share, rationale=p.rationale,
                  citation=p.citation or "") for p in body.parts]
    plan = plan_segments({r["line_id"]: r["amount"] for r in rows}, parts)

    batch_key = f"SEG-{uuid4().hex[:12]}"
    with turn(period) as cur:
        for line_id, entries in plan.by_line.items():
            for index, amount in entries:
                part = parts[index]
                cur.execute(
                    """INSERT INTO ledger_segment
                         (segment_id, line_id, period, amount, label, rationale,
                          citation, created_by, batch_key)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (f"{batch_key}-{line_id[:12]}-{index}", line_id, period,
                     amount, part.label, part.rationale, part.citation or None,
                     created_by, batch_key))
        # One entry, through record(), which carries the role and the session
        # as well as the name. There was a hand-written INSERT here as well,
        # so every split logged twice — once properly and once as a row that
        # could not be traced to a session.
        record(actor, "SEGMENT", "ledger_group", body.group_key,
               after={"batch_key": batch_key, "request": body.model_dump_json(),
                      "parts": [p.label for p in parts]},
               reason="; ".join(p.rationale for p in parts), cursor=cur)

    return {
        "batch_key": batch_key,
        "lines_segmented": len(plan.by_line),
        "segments_created": plan.segment_count,
        "group_total": str(plan.total()),
        "by_part": [{"label": p.label, "share": str(p.share),
                     "amount": str(plan.part_total(i))}
                    for i, p in enumerate(parts)],
    }


@router.post("/segment/reverse")
def reverse_segment(batch_key: str, reason: str, reversed_by: str = "",
                    actor: Actor = Depends(require_controller)) -> dict:
    """Reverse a segmentation. The parent lines become the analytical unit again.

    The batch key is a query parameter rather than a path segment because a
    group key is an account and a payee joined by a unit separator (0x1f),
    and a non-printable character in a URL path is not something every client
    will encode for you — httpx refuses outright. The route was uncallable
    for any real group until it moved.
    """
    reversed_by = actor.display_name or reversed_by
    if not reason.strip():
        raise HTTPException(422, "A reversal needs a reason.")
    # The period comes off the batch rather than from the caller: a reversal
    # names the segmentation it undoes, and the period is a property of that,
    # not something a client should be able to disagree with.
    b = one("""SELECT DISTINCT period FROM ledger_segment WHERE batch_key = %s""",
            (batch_key,))
    if not b:
        raise HTTPException(404, "No segmentation with that key.")
    with turn(b["period"]) as cur:
        cur.execute("""UPDATE ledger_segment
                          SET reversed_at = now(), reversed_by = %s,
                              reversal_reason = %s
                        WHERE batch_key = %s AND reversed_at IS NULL
                        RETURNING segment_id""",
                    (reversed_by, reason, batch_key))
        reversed_ids = [r["segment_id"] for r in cur.fetchall()]
        if not reversed_ids:
            raise HTTPException(404, "No live segmentation with that key.")
        record(actor, "SEGMENT_REVERSE", "ledger_segment", batch_key,
               after={"segments_reversed": len(reversed_ids)},
               reason=reason, cursor=cur)
    return {"batch_key": batch_key, "segments_reversed": len(reversed_ids)}


@router.get("/segments")
def list_segments(period: str = "2025") -> list[dict]:
    return query("""SELECT s.batch_key, s.label, count(*) AS segments,
                           sum(s.amount) AS amount, min(s.created_at) AS created_at,
                           s.created_by, bool_or(s.reversed_at IS NOT NULL) AS reversed
                      FROM ledger_segment s
                     WHERE s.period = %s
                     GROUP BY s.batch_key, s.label, s.created_by
                     ORDER BY min(s.created_at) DESC, s.label""", (period,))
