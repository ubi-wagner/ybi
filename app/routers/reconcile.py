"""Cross-reference reconciliation: the ledger against both statements.

The register lives in the database (``v_statement_reconciliation``). This is
the screen and the API over it, plus the one thing the register cannot do on
its own — help a controller name a difference instead of shrugging at it.

The naming follows this codebase's rule: the system proposes, a person
decides. ``/propose`` will tell you that exactly these four lines add to the
$622.26 the ledger puts in Rising Tides and the P&L puts in Travel. It will
not record that. Recording it is a written judgment with a reason attached,
and a deferred trigger checks that the lines named really do add to the
amount claimed before it commits.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import one, query, transaction
from app.domain.reconcile import Candidate, attribute
from app.settings import settings
from app.vocab import ReconcilingKind

router = APIRouter(prefix="/reconcile", tags=["reconcile"],
                   dependencies=[Depends(require_reader)])


@router.get("")
def register(period: str | None = None) -> dict:
    """Every point the three documents are required to agree, and what is
    left at each."""
    period = period or settings.period
    # `note` already carries what a NO DATA control is waiting on — the view
    # folds it in as "Nothing to compare yet — this needs X." — so there is
    # nothing extra to select. The column itself is internal to the view.
    controls = query("""SELECT control, basis, description, left_label, left_value,
                               right_label, right_value, variance, exceptions,
                               ties, evaluable, state, note
                          FROM v_statement_reconciliation
                         WHERE period = %s ORDER BY seq""", (period,))
    return {"period": period, "controls": controls,
            "failing": [c["control"] for c in controls if not c["ties"]],
            "open": [c["control"] for c in controls if c["state"] == "OPEN"],
            "no_data": [c["control"] for c in controls if c["state"] == "NO DATA"],
            "ties": bool(controls) and all(c["ties"] for c in controls)}


@router.get("/gl-pl")
def gl_pl(period: str | None = None, only_differences: bool = True) -> list[dict]:
    period = period or settings.period
    where = "AND gross_variance <> 0" if only_differences else ""
    return query(f"""SELECT account, section, gl_amount, gl_lines, pl_amount,
                            reconciling, gross_variance, unexplained
                       FROM v_gl_pl_account
                      WHERE period = %s {where}
                      ORDER BY abs(gross_variance) DESC, account""", (period,))


@router.get("/gl-bs")
def gl_bs(period: str | None = None, only_differences: bool = True) -> list[dict]:
    period = period or settings.period
    where = "AND (variance <> 0 OR NOT on_balance_sheet)" if only_differences else ""
    return query(f"""SELECT account, bs_leaf, matched_by_alias, opening, activity,
                            lines, closing, bs_amount, side, on_balance_sheet,
                            variance, absent_because_zero
                       FROM v_gl_bs_account
                      WHERE period = %s {where}
                      ORDER BY abs(variance) DESC, account""", (period,))


@router.get("/payroll")
def payroll(period: str | None = None) -> dict:
    """The payroll register against the ledger's wage accounts.

    The fourth source document, and the one the fringe base actually comes
    from — so the two readings of the fringe rate are returned beside each
    other. Fifty-five basis points apart on the 2025 data, and the difference
    is one misposted line.
    """
    period = period or settings.period
    row = one("""SELECT * FROM v_payroll_reconciliation WHERE period = %s""",
              (period,))
    if not row:
        raise HTTPException(404, "No payroll data for that period.")
    items = query("""SELECT i.item_id, i.from_account, i.to_account, i.amount,
                            i.kind::text AS kind, i.explanation, i.recorded_by,
                            i.recorded_at,
                            (SELECT count(*) FROM reconciling_item_line rl
                              WHERE rl.item_id = i.item_id) AS lines
                       FROM reconciling_item i
                      WHERE i.period = %s AND i.control = 'PAYROLL_REGISTER'
                        AND i.retracted_at IS NULL
                      ORDER BY abs(i.amount) DESC""", (period,))
    # Candidates: anything in a wage account that does not look like payroll.
    # A reading aid, not an accusation — the controller decides.
    # `named_by` is what stops a line being explained twice from the screen.
    # The schema refuses it outright (`reconciling_line_explained_once`), and
    # a button that would meet that refusal is a screen offering what the
    # server will not take — so the candidate says whether it is spoken for.
    odd = query("""SELECT l.line_id, l.txn_date, l.account, l.payee,
                          l.description, l.amount,
                          (SELECT rl.item_id
                             FROM reconciling_item_line rl
                             JOIN reconciling_item i ON i.item_id = rl.item_id
                            WHERE rl.line_id = l.line_id
                              AND i.retracted_at IS NULL
                            ORDER BY rl.item_id LIMIT 1) AS named_by
                     FROM ledger_line l
                    WHERE l.period = %s AND l.statement = 'P&L'
                      AND l.account ILIKE '%%Wages%%'
                      AND l.description NOT ILIKE 'GROSS%%'
                      AND l.description NOT ILIKE '%%accrual%%'
                      AND l.description NOT ILIKE '%%- Wages%%'
                    ORDER BY abs(l.amount) DESC LIMIT 25""", (period,))
    return {"period": period, "reconciliation": row,
            "reconciling_items": items,
            "unlike_payroll": odd,
            "note": ("Lines in a wage account whose memo does not look like a "
                     "payroll run, an accrual or a named correction. A place "
                     "to look, not a finding.")}


@router.get("/items")
def items(period: str | None = None, include_retracted: bool = False) -> list[dict]:
    period = period or settings.period
    where = "" if include_retracted else "AND i.retracted_at IS NULL"
    return query(f"""SELECT i.item_id, i.control, i.from_account, i.to_account,
                            i.amount, i.kind, i.explanation, i.recorded_by,
                            i.recorded_at, i.retracted_at, i.retracted_reason,
                            (SELECT count(*) FROM reconciling_item_line rl
                              WHERE rl.item_id = i.item_id) AS lines
                       FROM reconciling_item i
                      WHERE i.period = %s {where}
                      ORDER BY abs(i.amount) DESC""", (period,))


@router.get("/propose")
def propose(period: str | None = None) -> dict:
    """For each account where the ledger and the P&L disagree, the lines that
    would account for the difference — if exactly one set of lines does.

    A proposal, not a finding. Nothing here is recorded, and an ambiguous
    difference proposes nothing at all rather than picking a set.
    """
    period = period or settings.period
    gaps = query("""SELECT account, section, gl_amount, pl_amount, unexplained
                      FROM v_gl_pl_account
                     WHERE period = %s AND unexplained <> 0
                     ORDER BY abs(unexplained) DESC""", (period,))
    # The account the ledger overstates is the one the lines sit in; the
    # accounts it understates are where the P&L puts them. Pair each
    # understatement against the overstatement large enough to contain it.
    over = [g for g in gaps if g["unexplained"] > 0]
    under = [g for g in gaps if g["unexplained"] < 0]
    out = []
    for u in under:
        want = -u["unexplained"]
        for o in over:
            lines = query("""SELECT line_id, amount, txn_date, payee, description
                               FROM ledger_line
                              WHERE period = %s AND account = %s""",
                          (period, o["account"]))
            a = attribute(Decimal(want), [
                Candidate(line_id=l["line_id"], amount=Decimal(l["amount"]),
                          date=str(l["txn_date"]), payee=l["payee"] or "",
                          memo=l["description"] or "")
                for l in lines])
            out.append({
                "control": "GL_PL_ACCOUNT",
                "from_account": o["account"],
                "to_account": u["account"],
                "amount": str(want),
                "proposed": a.unique,
                "why_not": a.why_not(),
                "searched_lines": a.searched,
                "lines": [{"line_id": c.line_id, "amount": str(c.amount),
                           "date": c.date, "payee": c.payee, "memo": c.memo}
                          for c in a.lines],
            })
            if a.unique:
                break
    return {"period": period, "proposals": out,
            "note": ("Proposed, not recorded. A difference that more than one "
                     "set of lines could explain proposes nothing.")}


class ItemIn(BaseModel):
    control: str = Field(default="GL_PL_ACCOUNT")
    from_account: str
    to_account: str
    amount: Decimal
    kind: ReconcilingKind
    explanation: str = Field(min_length=30)
    #: Required for every kind but ROUNDING, which is the one case where the
    #: difference has no transaction behind it. The database enforces the
    #: same rule and the caps that go with it — a rounding item must explain
    #: at length why attribution was impossible, and may not exceed a
    #: thousand dollars. This model only declines to contradict it.
    line_ids: list[str] = []
    period: str | None = None

    @model_validator(mode="after")
    def lines_unless_rounding(self):
        if self.kind is not ReconcilingKind.ROUNDING and not self.line_ids:
            raise ValueError(
                "A reconciling item names the ledger lines it consists of. "
                "Only a ROUNDING item may have none, and it has to say why.")
        return self


@router.post("/items", status_code=201)
def add_item(body: ItemIn, actor: Actor = Depends(require_controller)) -> dict:
    """Record a reconciling item. The lines must add to the amount claimed —
    a deferred trigger checks, so the guarantee holds even if this is wrong."""
    period = body.period or settings.period
    try:
        with transaction() as cur:
            cur.execute("""INSERT INTO reconciling_item
                             (period, control, from_account, to_account, amount,
                              kind, explanation, recorded_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING item_id""",
                        (period, body.control, body.from_account, body.to_account,
                         body.amount, body.kind.value, body.explanation, actor.email))
            item_id = cur.fetchone()["item_id"]
            for line_id in body.line_ids:
                cur.execute("""INSERT INTO reconciling_item_line (item_id, line_id)
                               VALUES (%s,%s)""", (item_id, line_id))
            record(actor, "RECONCILE_ITEM", "reconciling_item", str(item_id),
                   after={"from": body.from_account, "to": body.to_account,
                          "amount": str(body.amount), "kind": body.kind.value,
                          "lines": len(body.line_ids)},
                   reason=body.explanation, cursor=cur)
    except Exception as exc:                       # trigger, FK or check
        raise HTTPException(status_code=409, detail={
            "error": "RECONCILING_ITEM_REFUSED",
            "message": str(exc).split("\n")[0].strip()}) from exc
    return {"item_id": item_id}


class RetractIn(BaseModel):
    reason: str = Field(min_length=20)


@router.post("/items/{item_id}/retract")
def retract(item_id: int, body: RetractIn,
            actor: Actor = Depends(require_controller)) -> dict:
    before = one("SELECT * FROM reconciling_item WHERE item_id=%s", (item_id,))
    if not before:
        raise HTTPException(404, "no such reconciling item")
    if before["retracted_at"]:
        raise HTTPException(409, "already retracted")
    with transaction() as cur:
        cur.execute("""UPDATE reconciling_item
                          SET retracted_at=now(), retracted_by=%s, retracted_reason=%s
                        WHERE item_id=%s""", (actor.email, body.reason, item_id))
        record(actor, "RECONCILE_RETRACT", "reconciling_item", str(item_id),
               before={"amount": str(before["amount"]),
                       "from": before["from_account"], "to": before["to_account"]},
               reason=body.reason, cursor=cur)
    return {"item_id": item_id, "retracted": True}


class AliasIn(BaseModel):
    gl_account: str
    statement: str = Field(pattern="^(P&L|BALANCE_SHEET)$")
    statement_account: str
    reason: str = Field(min_length=20)
    period: str | None = None


@router.post("/aliases", status_code=201)
def add_alias(body: AliasIn, actor: Actor = Depends(require_controller)) -> dict:
    """One account, two labels. Written down with a reason, because a silent
    mapping table is how two different accounts quietly become one."""
    period = body.period or settings.period
    with transaction() as cur:
        cur.execute("""INSERT INTO account_alias
                         (period, gl_account, statement, statement_account,
                          reason, recorded_by)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (period, gl_account, statement)
                         DO UPDATE SET statement_account = EXCLUDED.statement_account,
                                       reason = EXCLUDED.reason,
                                       recorded_by = EXCLUDED.recorded_by,
                                       recorded_at = now()""",
                    (period, body.gl_account, body.statement,
                     body.statement_account, body.reason, actor.email))
        record(actor, "RECONCILE_ALIAS", "account_alias", body.gl_account,
               after={"statement": body.statement,
                      "statement_account": body.statement_account},
               reason=body.reason, cursor=cur)
    return {"gl_account": body.gl_account, "statement": body.statement}


@router.get("/aliases")
def aliases(period: str | None = None) -> list[dict]:
    period = period or settings.period
    return query("""SELECT gl_account, statement, statement_account, reason,
                           recorded_by, recorded_at
                      FROM account_alias WHERE period = %s
                     ORDER BY gl_account""", (period,))
