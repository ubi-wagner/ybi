"""Awards, constraint tests and invoice true-up."""

from fastapi import Depends, APIRouter

from app.auth import require_project, require_reader
from app.db import query

router = APIRouter(prefix="/awards", tags=["awards"],
                   dependencies=[Depends(require_reader)])


@router.get("")
def list_awards() -> list[dict]:
    return query("""SELECT a.*, o.label AS objective_label
                      FROM award a JOIN cost_objective o USING (objective_id)
                     ORDER BY a.award_id""")


@router.get("/{award_id}/constraints")
def constraints(award_id: str) -> list[dict]:
    return query("""SELECT code,citation,description,passed,blocking,detail,evaluated_at
                      FROM constraint_result WHERE award_id=%s
                     ORDER BY blocking DESC, passed, code""", (award_id,))


@router.get("/{award_id}/trueup")
def trueup(award_id: str) -> dict:
    a = query("SELECT * FROM award WHERE award_id=%s", (award_id,))
    blocking = query("""SELECT count(*) AS n FROM constraint_result
                         WHERE award_id=%s AND blocking AND NOT passed""", (award_id,))
    n = blocking[0]["n"] if blocking else 0
    return {"award": a[0] if a else None,
            "blocking_failures": n,
            "issuable": n == 0,
            "disposition": "INVOICE_ISSUABLE" if n == 0 else "DEFICIENCY_ACKNOWLEDGED"}
