"""Chart of accounts: the 2026 structure, and the crosswalk that proves it
carries every 2025 dollar."""

from __future__ import annotations

from fastapi import Depends, APIRouter
from fastapi.responses import Response

from app.auth import require_controller, require_reader
from app.db import query
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
