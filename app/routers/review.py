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

from fastapi import APIRouter, Depends, HTTPException

from app.audit import record
from app.auth import Actor, require_reader
from app.db import one, query
# The administrative objective, from the one place it is named. The rate
# computation moves it into the G&A pool and `v_rate_buildup` reports how
# much; a second spelling here is how a screen and the figure it is breaking
# down come to disagree, which is why `publish.py` imports `STANDING` from
# the router that owns it rather than repeating the three statuses.
from app.routers.rates import ADMIN_OBJECTIVE
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
    # Whether the set is sealed, read from the record rather than inferred
    # from whether a rate came back. The screen needs it to say *why* there is
    # no rate: with the queue finished and the books tying, an unsealed set is
    # the only reason left, and it was the one reason the gate could not
    # print — so a controller who had done everything asked of him met a red
    # box with an empty list under it. "Not yet, because", never an empty
    # list, which is the restatement screen's own rule one screen along.
    # Read the way `v_audit_walk` reads it, so the landing page and this
    # screen cannot hold two opinions about whether a year is sealed.
    sealed = bool(one("""SELECT 1 FROM decision_set
                          WHERE period = %s AND sealed_at IS NOT NULL""",
                      (period,)))
    return {"period": period, "rates": rates, "carve_outs": carves,
            "anchors": anchors, "sealed": sealed,
            "coverage": cov, "open_controls": open_controls,
            # A rate is final when the judgments under it are finished and the
            # books they came from agree. Neither is a matter of opinion, so
            # the screen does not have to ask anybody.
            "final": bool(rates) and not open_controls
                     and Decimal(str((cov or {}).get("pct_dollars_covered") or 0)) >= 100}


# ------------------------------------------------------- inside the figures
#
# `/rate` above answers with the build-up: pool, carve-outs, base, rate. That
# is what a reviewer needs to reproduce the arithmetic and it is **not** what
# somebody walking into a negotiation needs, which is the question underneath
# every one of those figures: *what is in it.* The controller asked for it in
# those words — "high-level amounts of what makes up the individual amounts as
# well as detailed by transaction" — having downloaded the build-up workbook
# and found it was the same four rows he was already looking at.
#
# **Nothing here is a second derivation of a published figure.** The rule the
# review screens exist on is that a figure read twice is one that can disagree
# with itself, and a decomposition is the one shape that genuinely needs
# care: the moment it is a *separate* reading of the same cost it can foot to
# something other than the rate on file, and a breakdown that does not add up
# is worse in a negotiation than no breakdown at all.
#
# So every part of this is the same rows the computation read, partitioned
# rather than recomputed — and **every partition states whether it foots**,
# against the figure `v_rate_buildup` recorded. `foots` false is not a defect
# in this endpoint; it is the thing a controller has to know before he quotes
# the breakdown to a sponsor, which is `pool_variance`'s own rule one level
# in.

#: Which ledger pools each rate kind is taken over. INDIRECT_COMBINED is two,
#: which is why it is a list — the same table `v_rate_buildup` keeps as
#: `pool_for_kind`, and the reason the view aggregates before it adds the
#: administrative labour on.
KIND_POOLS: dict[str, tuple[str, ...]] = {
    "FRINGE": ("FRINGE",),
    "OVERHEAD": ("OVERHEAD",),
    "G&A": ("G&A",),
    "INDIRECT_COMBINED": ("OVERHEAD", "G&A"),
}


def _part(rows: list[dict], key: str, recorded, *, needs: str = "") -> dict:
    """A partition, with the one question a partition has to answer.

    `total` is what the rows add to and `recorded` is the figure on file. They
    are both printed because a reader comparing a breakdown to a workpaper
    compares two numbers, and a single number would make them take the tie on
    trust — which is the whole thing this screen is against.

    **Three states, not two.** No rows against a figure that is not zero is
    not a failed tie: it is a partition nobody can draw, which is a different
    fact and leads somewhere else. The per-objective base is the case — the
    allocation is recorded once, against the rate it was computed on, so
    asking OVERHEAD for its own objective base reports a $5m difference over
    a table that was never meant to exist. A control that cries wolf teaches
    the reader to dismiss the next real one, which is why `needs` says what
    is missing rather than printing a variance.
    """
    total = sum((Decimal(str(r[key] or 0)) for r in rows), Decimal(0))
    rec = Decimal(str(recorded or 0))
    if not rows and rec != 0:
        return {"rows": [], "total": Decimal(0), "recorded": rec,
                "variance": Decimal(0), "foots": None,
                "state": "NO DATA", "needs": needs}
    return {"rows": rows, "total": total, "recorded": rec,
            "variance": total - rec, "foots": total == rec,
            "state": "TIES" if total == rec else "OPEN", "needs": ""}


@router.get("/rate/composition")
def rate_composition(period: str | None = None) -> dict:
    """What makes up every figure on the rate build-up, one level down.

    Four partitions per rate, each the same rows the computation read:

      * the pool's **gross**, by ledger account — and for the pools floor
        area is a driver of, the `131` split between the occupancy that
        square footage drives and the part of the pool it does not;
      * the **carve-outs**, each with the authority it was taken under and
        the driver that sized it, plus that driver's own detail: per building
        for 200.465 and per asset for 200.436(b);
      * the **administrative labour** the G&A pool carries under the POOL
        basis, by person, because it comes from the effort distribution
        rather than from a classification;
      * the **base**, by cost objective, as the allocation recorded it.
    """
    period = period or settings.period
    rates = query("""SELECT kind, pool_amount, pool_gross, pool_carved,
                            pool_allocable, pool_admin_labour, base_type,
                            base_amount, rate, admin_labour_basis, rate_id
                       FROM v_rate_buildup
                      WHERE period = %s
                      ORDER BY CASE kind WHEN 'FRINGE' THEN 1
                                         WHEN 'OVERHEAD' THEN 2
                                         WHEN 'G&A' THEN 3 ELSE 4 END""",
                  (period,))
    # The whole pool side, by account, in one read rather than per rate: the
    # four kinds are drawn from three pools and INDIRECT_COMBINED is two of
    # them, so a query per kind would read OVERHEAD and G&A twice.
    #
    # `AND dl.live` because that is the rule for every join to
    # `decision_line` by line, and because it is what `_build_model` reads —
    # so this partitions the cost the rate was actually computed from.
    by_account = query("""SELECT d.pool::text AS pool, l.account,
                                 sum(l.amount) AS amount,
                                 count(*) AS lines,
                                 count(DISTINCT COALESCE(l.payee, '')) AS payees
                            FROM decision d
                            JOIN decision_line dl
                              ON dl.decision_id = d.decision_id AND dl.live
                            JOIN ledger_line l ON l.line_id = dl.line_id
                           WHERE d.reversed_at IS NULL AND l.period = %s
                           GROUP BY 1, 2
                           ORDER BY abs(sum(l.amount)) DESC""", (period,))
    carves = query("""SELECT pool::text AS pool, name, citation, amount,
                             driver, grade::text AS grade, created_by
                        FROM carve_out WHERE period = %s
                        ORDER BY pool, amount DESC""", (period,))
    # The two drivers, read from the registers that size them. Neither is a
    # figure this endpoint derives: 200.465 is sized by floor area and
    # 200.436(b) by what bought the asset, and the carve-out row names which.
    estate = query("""SELECT name, usable_sqft, assignable, common,
                             tenant_sqft, vacant_sqft, committed_sqft,
                             program_sqft, admin_sqft, rental_share
                        FROM v_facility_occupancy WHERE period = %s
                        ORDER BY usable_sqft DESC""", (period,))
    split = one("""SELECT pool_gross, occupancy, not_area_driven
                     FROM v_overhead_split WHERE period = %s""", (period,))
    # Which accounts floor area drives is a transcription somebody made, not
    # a rule — `overhead_driver` holds the exceptions with a reason each, and
    # the default is that floor area drives it. A negotiation turns on
    # exactly this list, so it travels with the split.
    drivers = query("""SELECT account_fragment, driven_by_area, reason
                         FROM overhead_driver ORDER BY account_fragment""")
    funded = query("""SELECT description, gl_account, gross_cost, depreciation,
                             federal_funding, total_funding, federal_share,
                             allowable_depreciation, funding_unknown
                        FROM v_asset_allowability
                       WHERE period = %s AND federal_funding > 0
                       ORDER BY depreciation DESC""", (period,))
    admin = query("""SELECT employee_key, employee_name, objective_id,
                            distributed_wages, source::text AS source,
                            evidence_quality::text AS grade
                       FROM v_labor_effective
                      WHERE period = %s AND objective_id = %s
                      ORDER BY distributed_wages DESC""",
                  (period, ADMIN_OBJECTIVE))
    out = []
    for r in rates:
        pools = KIND_POOLS.get(r["kind"], ())
        gross_rows = [a for a in by_account if a["pool"] in pools]
        carve_rows = [c for c in carves if c["pool"] in pools]
        # **The base is held in a different register depending on what it
        # is**, and reading the wrong one reports a difference rather than a
        # breakdown.
        #
        #   * a wage base is the payroll register, by person — the eleventh
        #     control's own denominator, and the half of the fringe rate a
        #     sponsor asks about after the six accounts;
        #   * MTDC is the allocation, by cost objective. That is recorded
        #     once, against the rate the allocation was computed on, so the
        #     three rates that are not it carry a placeholder row at 0.00 and
        #     have no per-objective base to show.
        if r["base_type"] == "SALARIES_WAGES":
            # **By person, not by row.** `v_labor_effective` is one row per
            # person *per objective*, so a straight read of it answers 97
            # over a register of 43 people — a figure on the page that
            # nobody can tie to the forty-three the rest of it talks about.
            # The run sheet printed exactly that once.
            base_rows = query("""SELECT employee_key,
                                        min(employee_name) AS employee_name,
                                        sum(distributed_wages) AS base_amount,
                                        count(*) AS objectives,
                                        string_agg(DISTINCT source::text, ', ')
                                          AS source,
                                        string_agg(DISTINCT
                                          evidence_quality::text, ', ')
                                          AS grade
                                   FROM v_labor_effective
                                  WHERE period = %s
                                  GROUP BY employee_key
                                  ORDER BY sum(distributed_wages) DESC""",
                              (period,))
            base_by = "PERSON"
            base_needs = ("Nothing on the record distributes this base by "
                          "person yet.")
        else:
            base_rows = [b for b in query(
                """SELECT a.objective_id, o.label, o.objective_type,
                          o.is_federal, a.base_amount, a.allocated
                     FROM allocation a
                     LEFT JOIN cost_objective o
                            ON o.objective_id = a.objective_id
                           AND o.period = %s
                    WHERE a.rate_id = %s
                    ORDER BY a.base_amount DESC""", (period, r["rate_id"]))
                if Decimal(str(b["base_amount"] or 0)) != 0]
            base_by = "OBJECTIVE"
            base_needs = ("The allocation is recorded against the rate it "
                          "was computed on, and this one carries none, so "
                          "there is no per-objective base to draw. The "
                          "combined rate is the one that holds it.")
        # The administrative labour is in the G&A pool only under the POOL
        # basis, and `v_rate_buildup` already says how much. Reported against
        # that figure rather than re-derived from the distribution: the
        # fringe inside it is the rate's own, applied in the computation.
        admin_part = None
        if Decimal(str(r["pool_admin_labour"] or 0)) != 0:
            wages = sum((Decimal(str(a["distributed_wages"] or 0))
                         for a in admin), Decimal(0))
            admin_part = {
                "rows": admin, "wages": wages,
                "recorded": Decimal(str(r["pool_admin_labour"])),
                "fringe_on_it": Decimal(str(r["pool_admin_labour"])) - wages,
                "objective": ADMIN_OBJECTIVE,
                "basis": r["admin_labour_basis"]}
        out.append({
            "kind": r["kind"], "rate": r["rate"],
            "pool_amount": r["pool_amount"], "base_type": r["base_type"],
            "pools": list(pools),
            # The gross on file is the accounts plus the administrative
            # labour, so the accounts are footed against the accounts' share
            # of it. Comparing them to the whole would report OPEN by exactly
            # the administrative labour under the POOL basis — a control
            # firing on a figure that is correctly somewhere else.
            "gross": _part(gross_rows, "amount",
                           Decimal(str(r["pool_gross"] or 0))
                           - Decimal(str(r["pool_admin_labour"] or 0))),
            "carved": _part(carve_rows, "amount", r["pool_carved"]),
            "base": _part(base_rows, "base_amount", r["base_amount"],
                          needs=base_needs) | {"by": base_by},
            "admin_labour": admin_part,
            # Floor area drives a share of the occupancy inside the pool and
            # none of the rest, which is the whole of `131`. It is reported
            # where the carve-out it sizes is, and nowhere else.
            "driver_split": split if "OVERHEAD" in pools else None,
        })
    return {"period": period, "rates": out,
            "estate": estate, "overhead_drivers": drivers,
            "federally_funded_assets": funded}


def rate_lines(period: str) -> dict:
    """Every transaction in every pool a rate is taken over, with its judgment.

    Not a route. The screen reaches transactions one account at a time —
    `/rate/account` — because 4,038 cost lines is not a payload and the
    drill-down is a question about one account. A workbook is the other case:
    it is what goes across the table, so it carries all of them, and the
    export is its only caller.
    """
    pools = sorted({p for ps in KIND_POOLS.values() for p in ps})
    rows = query("""SELECT d.pool::text AS pool, l.account,
                           l.txn_date::text AS date,
                           COALESCE(l.payee, '') AS payee,
                           COALESCE(l.description, '') AS description,
                           l.amount, d.function_990::text AS function_990,
                           d.federal::text AS federal, d.objective_id,
                           d.grade::text AS grade, d.citation, d.rationale,
                           d.decided_by
                      FROM decision d
                      JOIN decision_line dl
                        ON dl.decision_id = d.decision_id AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND l.period = %s
                       AND d.pool::text = ANY(%s)
                     ORDER BY d.pool, l.account, l.txn_date, l.line_id""",
                 (period, pools))
    # Footed against the pools' own gross rather than against a rate's: these
    # are every pool together, and no single rate is taken over all of them.
    gross = one("""SELECT COALESCE(sum(gross), 0) AS g FROM v_pool_balance
                    WHERE period = %s AND pool::text = ANY(%s)""",
                (period, pools))
    return {"rows": rows,
            "part": _part(rows, "amount", (gross or {}).get("g"))}


@router.get("/rate/account")
def rate_account(pool: str, account: str, period: str | None = None,
                 limit: int = 200, offset: int = 0,
                 actor: Actor = Depends(require_reader)) -> dict:
    """One account inside one pool: who was paid, and every transaction.

    The bottom of the drill-down. `pool` and `account` are query parameters
    and not a path, because an account is `Grant Expenses:Drive AM` and a
    group key is an account and a payee joined by 0x1f — a composite key in a
    path is not something every client will encode.

    Paged, because the largest account on this record carries 442 lines and
    the ledger carries 15,500. The payee rollup is **not** paged: it is the
    high-level answer to *where did this money go*, and a partial one would
    be read as the whole.
    """
    period = period or settings.period
    if pool not in {p for ps in KIND_POOLS.values() for p in ps}:
        raise HTTPException(422, f"{pool!r} is not a pool a rate is taken "
                                 f"over. One of: "
                                 f"{', '.join(sorted({p for ps in KIND_POOLS.values() for p in ps}))}.")
    where = """FROM decision d
               JOIN decision_line dl
                 ON dl.decision_id = d.decision_id AND dl.live
               JOIN ledger_line l ON l.line_id = dl.line_id
              WHERE d.reversed_at IS NULL AND l.period = %s
                AND d.pool::text = %s AND l.account = %s"""
    head = one(f"""SELECT COALESCE(sum(l.amount), 0) AS amount,
                          count(*) AS lines
                   {where}""", (period, pool, account))
    payees = query(f"""SELECT COALESCE(l.payee, '') AS payee,
                              sum(l.amount) AS amount, count(*) AS lines
                       {where}
                       GROUP BY 1 ORDER BY abs(sum(l.amount)) DESC""",
                   (period, pool, account))
    # The judgment each line sits under travels with it. A transaction on its
    # own says what was spent; what a sponsor asks is why it is in this pool,
    # and the rationale and the citation are on the decision that put it
    # there.
    lines = query(f"""SELECT l.line_id, l.txn_date::text AS date,
                             COALESCE(l.payee, '') AS payee,
                             COALESCE(l.description, '') AS description,
                             l.amount, d.function_990::text AS function_990,
                             d.federal::text AS federal, d.objective_id,
                             d.grade::text AS grade, d.citation, d.rationale,
                             d.decided_by, d.origin::text AS origin
                      {where}
                      ORDER BY l.txn_date, l.line_id
                      LIMIT %s OFFSET %s""",
                  (period, pool, account, max(1, min(limit, 1000)), max(0, offset)))
    # `RATE_DRILL_DOWN` and deliberately not `EXPORT`. Nothing left the
    # building here — this is the screen reading, and `v_export_activity` and
    # `v_shared_password_acts` both name `EXPORT` explicitly, so labelling a
    # pane open as one would put a click in the register where a file is
    # claimed to have gone out. Reading and taking a copy are different acts,
    # which is already why `EVIDENCE_VIEW` sits beside `EVIDENCE_DOWNLOAD`
    # and is on neither list.
    record(actor, "RATE_DRILL_DOWN", "rate_account", f"{pool}|{account}",
           after={"lines": len(lines), "offset": offset},
           reason="read the transactions behind an account in the rate pool")
    return {"period": period, "pool": pool, "account": account,
            "amount": head["amount"], "lines_total": head["lines"],
            "payees": payees, "lines": lines,
            "offset": offset, "limit": limit,
            "more": offset + len(lines) < int(head["lines"] or 0)}


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
            # Both of the return's non-function columns start at zero rather
            # than being created on demand. A category with no not-applicable
            # cost genuinely holds none of it, and the sheet's rule is that a
            # blank means nobody has answered — which is a different fact.
            "NOT_YET_CLASSIFIED": Decimal(0), "NOT_APPLICABLE": Decimal(0)})
        amount = Decimal(str(r["amount"] or 0))
        key = r["function_990"] if r["function_990"] in cat else "NOT_APPLICABLE"
        # The enum carries NOT_APPLICABLE for cost that is on the ledger but
        # outside the return's scope — contra-income sitting in the expense
        # section, and nothing else since `092`. It is shown under its own
        # name rather than folded into a function it does not belong to, and
        # the column is printed so every row cross-foots.
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


@router.get("/ties")
def report_ties(period: str | None = None) -> dict:
    """Whether everything this system publishes ties to the financials.

    Twenty-two control-shaped views and nothing collecting them, so the
    question a reviewer actually arrives with — *does all of this tie to the
    books* — had twenty-two answers on twenty-two screens and the reader kept
    the list. `v_report_tie` is one row per report and anchor, each reading
    the control that already owns its figure.

    Nothing is computed here or on the screen, for the reason every review
    route gives: a figure derived twice is one that can disagree with itself.
    """
    period = period or settings.period
    return {
        "period": period,
        "summary": one("""SELECT anchors, ties, open, no_data, state,
                                 open_anchors
                            FROM v_report_tie_summary WHERE period = %s""",
                       (period,)) or {"anchors": 0, "ties": 0, "open": 0,
                                      "no_data": 0, "state": "NO DATA",
                                      "open_anchors": ""},
        "anchors": query("""SELECT seq, report, anchor, ties_to, state,
                                   variance, needs
                              FROM v_report_tie WHERE period = %s
                             ORDER BY seq, anchor""", (period,)),
    }
