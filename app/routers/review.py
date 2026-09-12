"""Final review, and the three things that leave the building.

The rate, the auditor's report and the Form 990 are the deliverables of the
engagement. Each one is a view over judgments already recorded — the queue
decided them, the seal froze them, the controls proved the ledger behind
them — so nothing here computes a figure. A number that first appears on a
review screen is a number that was never classified, sealed or controlled.

What these routes do add is the honest statement of what is not finished.
Every one of them answers with its readiness alongside its content, because
a reviewer handed a functional allocation with no indication that two thirds
of the cost is unjudged will read it as an answer.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends

from app.audit import record
from app.auth import Actor, require_reader
from app.db import one, query
from app.settings import settings

router = APIRouter(prefix="/review", tags=["review"],
                   dependencies=[Depends(require_reader)])

#: The three columns the return prints, in the order it prints them.
FUNCTIONS = ["PROGRAM", "MANAGEMENT_AND_GENERAL", "FUNDRAISING"]


@router.get("/rate")
def rate_buildup(period: str | None = None) -> dict:
    """The rate, and everything a reviewer needs to reproduce it.

    Pool, carve-outs, base, rate, seal. The build-up rather than the number,
    because the number on its own is something they have to take on trust.
    """
    period = period or settings.period
    rates = query("""SELECT kind, pool_amount, base_type, base_amount, rate,
                            status, seal_hash, computed_at, computed_by,
                            decision_set, sealed_at, sealed_by,
                            pool_gross, pool_carved, pool_allocable, carve_outs,
                            -- The control on the build-up itself: what the
                            -- computation used against what the ledger says
                            -- is left after recorded carve-outs. A workpaper
                            -- that shows the pool and not whether it ties is
                            -- asking the reader to take the tie on trust,
                            -- which is the thing this screen exists to stop.
                            pool_variance, pool_state
                       FROM v_rate_buildup
                      WHERE period = %s
                      ORDER BY CASE kind WHEN 'FRINGE' THEN 1
                                         WHEN 'OVERHEAD' THEN 2
                                         WHEN 'G&A' THEN 3 ELSE 4 END""",
                  (period,))
    carves = query("""SELECT pool::text AS pool, name, citation, amount,
                             driver, grade::text AS grade, created_by
                        FROM carve_out WHERE period = %s
                        ORDER BY pool, name""", (period,))
    cov = one("""SELECT classified, unclassified, pct_dollars_covered
                   FROM v_classification_coverage WHERE period = %s""",
              (period,))
    open_controls = query("""SELECT control, description, state, note
                               FROM v_statement_reconciliation
                              WHERE period = %s AND NOT ties ORDER BY seq""",
                          (period,))
    # What the rate as a whole is anchored to, beyond each pool tying to
    # itself: that the pools account for every judgment made, and that the
    # fringe denominator is the payroll register rather than the ledger's
    # wage accounts. NO DATA is not a pass, and `classification_complete`
    # says whether these are read over a finished queue or a partial one.
    anchors = query("""SELECT control, description, expected, actual, variance,
                              state, note, unit, classification_complete
                         FROM v_rate_anchor WHERE period = %s ORDER BY seq""",
                    (period,))
    return {"period": period, "rates": rates, "carve_outs": carves,
            "anchors": anchors,
            "coverage": cov, "open_controls": open_controls,
            # A rate is final when the judgments under it are finished and the
            # books they came from agree. Neither is a matter of opinion, so
            # the screen does not have to ask anybody.
            "final": bool(rates) and not open_controls
                     and Decimal(str((cov or {}).get("pct_dollars_covered") or 0)) >= 100}


@router.get("/form-990")
def form_990(period: str | None = None) -> dict:
    """Part IX, the Statement of Functional Expenses, as the ledger has it.

    Rows are natural categories, columns are the three functions the return
    prints — plus one the return does not: cost nobody has judged yet. It is
    never spread across the other three. A functional allocation that
    distributes unjudged cost is one nobody can support, and the total is
    meant to look wrong until the queue is empty.
    """
    period = period or settings.period
    rows = query("""SELECT natural_category, function_990, amount, lines
                      FROM v_form_990_functional WHERE period = %s""",
                 (period,))

    by_cat: dict[str, dict] = {}
    for r in rows:
        cat = by_cat.setdefault(r["natural_category"], {
            "natural_category": r["natural_category"], "total": Decimal(0),
            "lines": 0, **{f: Decimal(0) for f in FUNCTIONS},
            "NOT_YET_CLASSIFIED": Decimal(0)})
        amount = Decimal(str(r["amount"] or 0))
        key = r["function_990"] if r["function_990"] in cat else "NOT_APPLICABLE"
        if key == "NOT_APPLICABLE":
            # The enum carries NOT_APPLICABLE for cost that is on the ledger
            # but outside the return's scope. It is still shown, under its own
            # name, rather than folded into a function it does not belong to.
            cat.setdefault("NOT_APPLICABLE", Decimal(0))
        cat[key] = cat.get(key, Decimal(0)) + amount
        cat["total"] += amount
        cat["lines"] += r["lines"]

    categories = sorted(by_cat.values(), key=lambda c: -abs(c["total"]))
    totals = {k: sum((c.get(k) or Decimal(0)) for c in categories)
              for k in (*FUNCTIONS, "NOT_YET_CLASSIFIED", "NOT_APPLICABLE",
                        "total")}
    ready = one("SELECT * FROM v_form_990_readiness WHERE period = %s",
                (period,))
    return {"period": period, "functions": FUNCTIONS,
            "categories": categories, "totals": totals, "readiness": ready}


@router.get("/attachments")
def attachments(period: str | None = None) -> dict:
    """What the return and the report rest on, and what each supports.

    An attachment nobody can produce is a citation, not evidence — so the
    register is read here rather than a list being kept alongside it, and a
    document whose file has gone missing says so.
    """
    period = period or settings.period
    docs = query("""SELECT e.evidence_id, e.kind, e.uri, e.sha256, e.byte_size,
                           e.mime_type, e.received_at, e.note,
                           COALESCE(a.display_name, e.received_from) AS from_whom,
                           (SELECT count(*) FROM attachment a2
                             WHERE a2.evidence_id = e.evidence_id
                               AND a2.detached_at IS NULL) AS supports
                      FROM evidence e
                      LEFT JOIN actor a ON a.actor_id = e.uploaded_by
                     WHERE e.period = %s
                     ORDER BY e.kind, e.received_at""", (period,))
    for d in docs:
        d["filename"] = str(d.pop("uri", "")).rsplit("/", 1)[-1].split("_", 1)[-1]
    return {"period": period, "documents": docs,
            "unattached": sum(1 for d in docs if not d["supports"])}


@router.get("/auditors-report")
def auditors_report(period: str | None = None,
                    actor: Actor = Depends(require_reader)) -> dict:
    """Everything the engagement asserts, with what proves each assertion.

    Assembled in the order a reviewer works: do the books agree with
    themselves, what was judged and on what evidence, where the standard was
    bent and why, what the rate came to, and what is still open. Reading it
    is logged, which is the auditor's side of the same guarantee the record
    gives everybody else.
    """
    period = period or settings.period
    controls = query("""SELECT control, description, left_label, left_value,
                               right_label, right_value, variance, exceptions,
                               ties, state, note
                          FROM v_statement_reconciliation
                         WHERE period = %s ORDER BY seq""", (period,))
    asset = one("""SELECT assets, gross_cost, register_depreciation,
                          ledger_depreciation, variance, state, needs
                     FROM v_asset_control WHERE period = %s""", (period,))
    exceptions = query("""SELECT kind, subject, detail, reason, amount,
                                 actor, occurred_at
                            FROM v_exceptions WHERE period = %s
                            ORDER BY kind, occurred_at""", (period,))
    coverage = one("""SELECT classified, unclassified, pct_dollars_covered
                        FROM v_classification_coverage WHERE period = %s""",
                   (period,))
    evidence = query("""SELECT pool::text AS pool, dollars, documented,
                               pct_documented
                          FROM v_evidence_coverage WHERE period = %s
                          ORDER BY dollars DESC""", (period,))
    rates = query("""SELECT kind, pool_amount, base_type, base_amount, rate,
                            status, seal_hash, sealed_at, sealed_by
                       FROM v_rate_buildup WHERE period = %s ORDER BY kind""",
                  (period,))
    items = query("""SELECT control, from_account, to_account, amount,
                            kind::text AS kind, explanation, recorded_by,
                            (SELECT count(*) FROM reconciling_item_line rl
                              WHERE rl.item_id = ri.item_id) AS lines
                       FROM reconciling_item ri
                      WHERE period = %s AND retracted_at IS NULL
                      ORDER BY control, item_id""", (period,))
    record(actor, "REVIEW_READ", "period", period,
           after={"report": "auditors", "period": period},
           reason="auditor's report read on screen")
    return {"period": period, "controls": controls, "asset_control": asset,
            "exceptions": exceptions, "coverage": coverage,
            "evidence_coverage": evidence, "rates": rates,
            "reconciling_items": items}
