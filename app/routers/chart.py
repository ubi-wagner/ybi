"""Chart of accounts: the 2026 structure, and the crosswalk that proves it
carries every 2025 dollar."""

from __future__ import annotations

from fastapi import Depends, APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import query, transaction
from app.domain import chart as C
from app.domain.crosswalk import CROSSWALK, build

router = APIRouter(prefix="/chart", tags=["chart"],
                   dependencies=[Depends(require_reader)])


@router.get("/summary")
def summary() -> dict:
    s = C.summary()
    s["principle"] = ("Account number carries the cost pool, Class carries the Form 990 "
                      "function, Customer:Job carries the cost objective, Location carries "
                      "the facility. Four dimensions off every transaction, no "
                      "classification work.")
    return s


@router.get("/accounts")
def accounts() -> list[dict]:
    return C.mapping_rows()


@router.get("/crosswalk")
def crosswalk(period: str = "2025") -> dict:
    rows = query("""SELECT l.account AS "Source Account",
                           sum(l.amount) AS "Booked Amount",
                           count(*)      AS lines
                      FROM ledger_line l WHERE l.period = %s
                     GROUP BY l.account""", (period,))
    src = [{"Source Account": r["Source Account"],
            "Booked Amount": r["Booked Amount"],
            "Cost Disposition": ""} for r in rows]
    if not src:
        return {"rows": [], "tieout": None,
                "note": "No ledger imported yet — the crosswalk needs 2025 actuals to tie against."}
    xw, tie = build(src, {a.number: a.full_name for a in C.CHART})
    return {"rows": xw, "tieout": tie}


class SplitPart(BaseModel):
    target_account: str
    share: float = Field(gt=0, le=1)
    driver: str = Field(..., min_length=21)
    citation: str = ""


class SplitIn(BaseModel):
    source_account: str
    parts: list[SplitPart] = Field(..., min_length=2)


@router.get("/splits")
def splits(period: str = "2025") -> dict:
    """The 2025 accounts that divide across several 2026 accounts.

    Twenty-four of the eighty-five. Each is a real judgment about what drives
    the division — square footage, a timesheet, a funded-versus-private basis
    — and until the driver is written down the crosswalk carries every dollar
    arithmetically rather than deliberately. A split without a driver is
    arithmetic wearing the clothes of a judgment.
    """
    # Cost sections only, and matched on the leaf segment rather than
    # anywhere in the path. Four leaves — Drive AM, Digital Engineering, DLA
    # Grant, Youth Entrepreneurship — exist under both an income and an
    # expense parent, and a substring match adds the revenue side to the cost
    # side: Drive AM read $761,122 against a real cost of $181,881.
    rows = query("""SELECT l.account AS account, sum(l.amount) AS amount,
                           count(*) AS lines,
                           split_part(l.account, ':',
                             array_length(string_to_array(l.account, ':'), 1))
                             AS leaf
                      FROM ledger_line l
                     WHERE l.period = %s AND l.statement = 'P&L'
                       AND l.section IN ('Expense', 'COGS')
                     GROUP BY l.account""", (period,))
    booked = {r["account"]: r for r in rows}

    recorded = {r["source_account"]: r for r in
                query("SELECT * FROM v_chart_split_status WHERE period = %s",
                      (period,))}

    out = []
    for source, (target, note) in CROSSWALK.items():
        if "/" not in target:
            continue
        # The ledger's account paths are qualified; the crosswalk keys are the
        # leaf names, so a split is matched on the leaf appearing in the path.
        matches = [v for v in booked.values()
                   if v["leaf"] == source or v["account"] == source]
        amount = sum(float(v["amount"]) for v in matches)
        lines = sum(v["lines"] for v in matches)
        got = recorded.get(source)
        out.append({
            "source_account": source,
            "targets_suggested": [t.strip() for t in target.split("/")],
            "suggested_driver": note,
            "amount_2025": amount, "lines": lines,
            "recorded": bool(got),
            "divides_whole": bool(got and got["divides_whole"]),
            "every_target_has_a_driver":
                bool(got and got["every_target_has_a_driver"]),
            "targets_recorded": got["targets"] if got else 0,
        })
    out.sort(key=lambda r: (r["recorded"], -abs(r["amount_2025"])))
    done = [r for r in out if r["recorded"] and r["divides_whole"]]
    return {
        "period": period, "splits": out,
        "total": len(out), "documented": len(done),
        "amount_undocumented": sum(abs(r["amount_2025"]) for r in out
                                   if not (r["recorded"] and r["divides_whole"])),
    }


@router.put("/splits")
def put_split(body: SplitIn, period: str = "2025",
              actor: Actor = Depends(require_controller)) -> dict:
    """Record how one 2025 account divides, and why.

    The shares must come to one — an account that does not divide whole loses
    or invents money in the crosswalk — and every part must name its driver.
    Both are held by the schema, the first at COMMIT so a split can be entered
    a part at a time.
    """
    total = sum(p.share for p in body.parts)
    if abs(total - 1) > 0.0001:
        raise HTTPException(
            422, f"The parts come to {total:.4f}, not 1. An account that does "
                 f"not divide whole loses or invents money in the crosswalk.")
    with transaction() as cur:
        cur.execute("""UPDATE chart_split_driver SET superseded_at = now()
                        WHERE period = %s AND source_account = %s
                          AND superseded_at IS NULL""",
                    (period, body.source_account))
        for part in body.parts:
            cur.execute("""INSERT INTO chart_split_driver
                             (period, source_account, target_account, share,
                              driver, citation, recorded_by, recorded_name)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (period, body.source_account, part.target_account,
                         part.share, part.driver.strip(), part.citation.strip(),
                         actor.actor_id, actor.display_name))
        record(actor, "CHART_SPLIT", "chart_split_driver", body.source_account,
               after={"parts": [{"target": p.target_account,
                                 "share": p.share} for p in body.parts]},
               reason="; ".join(p.driver.strip() for p in body.parts)[:400],
               cursor=cur)
    return {"source_account": body.source_account, "parts": len(body.parts)}


@router.get("/export/{kind}")
def export(kind: str) -> Response:
    bodies = {"accounts": (C.chart_csv, "YBI_2026_Chart_of_Accounts_QBO.csv"),
              "classes": (C.classes_csv, "YBI_2026_Classes_QBO.csv"),
              "customers": (C.customers_csv, "YBI_2026_Customers_Jobs_QBO.csv")}
    if kind not in bodies:
        return Response(status_code=404, content="unknown export")
    fn, name = bodies[kind]
    return Response(content=fn(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
