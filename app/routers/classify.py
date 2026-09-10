"""
Classification queue.

This is the screen that decides whether the project succeeds. Everything else
is reporting. Three rules shape the API:

  1. Work at group grain. 4,020 ledger lines collapse to ~751 account x payee
     groups, and the top 200 carry 94.7% of the dollars. A row-by-row queue is
     a workload that does not need to exist and will not finish by November.

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

from decimal import Decimal

from fastapi import Depends, APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_controller, require_reader
from app.audit import record
from app.auth import Actor
from app.db import execute, one, query, transaction
from app.domain.segment import Part, SegmentError, plan_segments

router = APIRouter(prefix="/classify", tags=["classify"],
                   dependencies=[Depends(require_reader)])

POOLS = ["DIRECT", "FRINGE", "OVERHEAD", "G&A", "RENTAL_DIRECT",
         "FUNDRAISING", "UNALLOWABLE", "EXCLUDED"]
FUNCTIONS = ["PROGRAM", "MANAGEMENT_AND_GENERAL", "FUNDRAISING", "NOT_APPLICABLE"]
FEDERAL = ["ALLOWABLE", "UNALLOWABLE", "NOT_APPLICABLE", "PENDING"]
GRADES = ["UNSUPPORTED", "TEST_ASSUMPTION", "MANAGEMENT_RECONSTRUCTION",
          "CORROBORATED", "VERIFIED"]


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
    proposal: dict | None = None
    evidence_count: int = 0
    note_count: int = 0


class DecideIn(BaseModel):
    group_keys: list[str] = Field(..., min_length=1)
    pool: str
    function_990: str
    federal: str
    objective_id: str | None = None
    grade: str = "CORROBORATED"
    rationale: str = ""
    citation: str | None = None
    evidence_ids: list[str] = []
    decided_by: str
    supersedes: str | None = None


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
    r = one("""
        WITH d AS (
          SELECT l.line_id, l.amount, l.account, l.payee,
                 (dl.decision_id IS NOT NULL) AS decided
            FROM ledger_line l
            LEFT JOIN decision_line dl ON dl.line_id = l.line_id
            LEFT JOIN decision dd ON dd.decision_id = dl.decision_id
                                 AND dd.reversed_at IS NULL
           WHERE l.period = %s
             -- Balance sheet accounts are not cost. Including them makes
             -- dollar coverage, the measure that gates sealing, meaningless.
             AND l.statement = 'P&L'
        )
        SELECT count(*)                                               AS total_lines,
               count(*) FILTER (WHERE decided)                        AS decided_lines,
               coalesce(sum(abs(amount)), 0)                          AS total_dollars,
               coalesce(sum(abs(amount)) FILTER (WHERE decided), 0)   AS decided_dollars,
               count(DISTINCT (account, payee))                       AS groups_total,
               count(DISTINCT (account, payee)) FILTER (WHERE decided) AS groups_decided
          FROM d
    """, (period,))
    if not r:
        raise HTTPException(404, "No ledger loaded for that period.")
    total = Decimal(r["total_dollars"] or 0)
    decided = Decimal(r["decided_dollars"] or 0)
    return CoverageOut(
        period=period,
        total_lines=r["total_lines"], decided_lines=r["decided_lines"],
        total_dollars=total, decided_dollars=decided,
        pct_dollars=(decided / total * 100).quantize(Decimal("0.1")) if total else Decimal(0),
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
               bool_or(rev.revision_id IS NOT NULL)  AS stale,
               count(DISTINCT att.attachment_id)     AS evidence_count,
               count(DISTINCT n.note_id)             AS note_count
          FROM ledger_line l
          LEFT JOIN decision_line dl ON dl.line_id = l.line_id
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

    return None


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

    st = one("""SELECT set_id FROM decision_set
                 WHERE period = %s AND seal_hash IS NULL
                 ORDER BY set_id LIMIT 1""", (period,))
    if not st:
        raise ValueError("No open decision set for this period. "
                         "A sealed set cannot be modified — unseal it, with a reason.")
    set_id = st["set_id"]

    created = 0
    for key in body.group_keys:
        account, _, payee = key.partition("\x1f")
        with_lines = query("""SELECT line_id FROM ledger_line
                               WHERE period = %s AND account = %s AND payee = %s""",
                           (period, account, payee))
        if not with_lines:
            continue
        # One transaction: the VERIFIED gate is a deferred constraint trigger
        # that fires at COMMIT, so the decision and the evidence it cites must
        # land together or an evidenced judgment is refused as unevidenced.
        with transaction() as cur:
            cur.execute("""
                INSERT INTO decision (set_id, scope, pool, function_990, federal,
                                      objective_id, grade, rationale, citation,
                                      decided_by, supersedes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING decision_id
            """, (set_id, f"account={account}|payee={payee}", body.pool,
                  body.function_990, body.federal, body.objective_id, body.grade,
                  body.rationale, body.citation, decided_by, body.supersedes))
            did = cur.fetchone()["decision_id"]
            for l in with_lines:
                cur.execute("""INSERT INTO decision_line (decision_id, line_id)
                               VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                            (did, l["line_id"]))
            for ev in body.evidence_ids:
                cur.execute("""INSERT INTO decision_evidence (decision_id, evidence_id)
                               VALUES (%s,%s) ON CONFLICT DO NOTHING""", (did, ev))
            # Inside the transaction: an audit row that survived a rolled
            # back decision would describe something that never happened.
            record(actor, "CLASSIFY", "decision", str(did),
                   after=body.model_dump(mode="json"), reason=body.rationale,
                   cursor=cur)
        created += 1

    return {"decisions_created": created, "set_id": str(set_id)}


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
    created_by: str


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
    with transaction() as cur:
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
        cur.execute("""INSERT INTO audit_log (actor, action, entity, entity_id,
                                              after_state, reason)
                       VALUES (%s,'SEGMENT','ledger_group',%s,%s,%s)""",
                    (actor.display_name, body.group_key, body.model_dump_json(),
                     "; ".join(p.rationale for p in parts)))
        record(actor, "SEGMENT", "ledger_group", body.group_key,
               after={"batch_key": batch_key,
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


@router.post("/segment/{batch_key}/reverse")
def reverse_segment(batch_key: str, reason: str, reversed_by: str = "",
                    actor: Actor = Depends(require_controller)) -> dict:
    reversed_by = actor.display_name or reversed_by
    """Reverse a segmentation. The parent lines become the analytical unit again."""
    if not reason.strip():
        raise HTTPException(422, "A reversal needs a reason.")
    with transaction() as cur:
        cur.execute("""UPDATE ledger_segment
                          SET reversed_at = now(), reversed_by = %s,
                              reversal_reason = %s
                        WHERE batch_key = %s AND reversed_at IS NULL
                        RETURNING segment_id""",
                    (reversed_by, reason, batch_key))
        reversed_ids = [r["segment_id"] for r in cur.fetchall()]
        if not reversed_ids:
            raise HTTPException(404, "No live segmentation with that key.")
        cur.execute("""INSERT INTO audit_log (actor, action, entity, entity_id,
                                              reason)
                       VALUES (%s,'SEGMENT_REVERSE','ledger_segment',%s,%s)""",
                    (reversed_by, batch_key, reason))
        record(actor, "SEGMENT_REVERSE", "ledger_segment", batch_key,
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
