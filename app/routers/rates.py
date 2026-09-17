"""Rates and allocation.

Sealing is the gate. A rate cannot be computed from an unsealed decision set,
in this handler or anywhere else — a database trigger enforces it too, so the
guarantee survives a bug here.
"""

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # pragma: no cover
    # `_build_model` annotates a parameter "AllocationBase | None" as a
    # string, so nothing evaluates it at runtime and the name was never
    # imported — harmless until anything asks for the function's type hints,
    # and an unresolvable annotation either way. pyflakes had been reporting
    # it as the one undefined name in the application and nobody had run
    # pyflakes.
    from app.domain.core import AllocationBase

from fastapi import Depends, APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth import require_controller, require_reader
from app.audit import record
from app.auth import Actor
from app.db import one, query, transaction
from app.statelock import turn

router = APIRouter(prefix="/rates", tags=["rates"],
                   dependencies=[Depends(require_reader)])


class SealIn(BaseModel):
    sealed_by: str = ""
    note: str = ""


@router.post("/seal")
def seal(body: SealIn, period: str = "2025",
         actor: Actor = Depends(require_controller)) -> dict:
    """Hash every live classification and freeze the set. After this the rate
    phase unlocks and classifications can only change by unsealing, with a
    reason, which supersedes any rate already computed.

    The seal is the moment the whole guarantee rests on, so it is recorded as
    the signed-in controller and body.sealed_by is only a label. An identity
    the client supplies is not evidence of who did this.
    """
    # One transaction, with the period held.
    #
    # This used to be four statements on four pooled connections: find the
    # open set, hash every live judgment in it, count them, write the hash. A
    # classification committing between the hash and the write landed in a
    # set whose seal_hash does not cover it — and nothing would ever have
    # shown it, because the hash is only recomputed when somebody unseals.
    # That is the one guarantee the whole engagement rests on, so it is now
    # taken as a single act over a period nobody else can be mid-turn on.
    with turn(period) as cur:
        cur.execute("""SELECT set_id FROM decision_set
                        WHERE period=%s AND seal_hash IS NULL
                        ORDER BY set_id LIMIT 1""", (period,))
        st = cur.fetchone()
        if not st:
            raise HTTPException(409, "No open decision set — this period is "
                                     "already sealed.")
        cur.execute("""
            SELECT encode(digest(string_agg(fp,'' ORDER BY fp),'sha256'),'hex') AS seal
              FROM (SELECT encode(digest(
                       d.decision_id::text || d.pool::text || d.function_990::text ||
                       d.federal::text || coalesce(d.objective_id,'') || d.grade::text,
                       'sha256'),'hex') AS fp
                      FROM decision d
                     WHERE d.set_id=%s AND d.reversed_at IS NULL) x
        """, (st["set_id"],))
        h = cur.fetchone()
        # string_agg over no rows is NULL, so sealing a set with nothing in it
        # produced a null hash and a raw constraint violation — which is exactly
        # the state a fresh deployment is in on its first morning, and exactly
        # the wrong first impression. Sealing nothing is meaningless anyway: the
        # seal is a hash across judgments, and there are none.
        if not h or not h["seal"]:
            raise HTTPException(409, {
                "error": "NOTHING_TO_SEAL",
                "message": ("There are no classifications to seal yet. The seal "
                            "is a hash across every judgment in the set, and it "
                            "is what lets a rate be computed — so it has to come "
                            "after the work, not before it.")})

        sealed_by = actor.display_name or body.sealed_by
        cur.execute("""SELECT count(*) AS decisions,
                              count(*) FILTER (WHERE grade IN ('UNSUPPORTED',
                                                               'TEST_ASSUMPTION'))
                                AS weak
                         FROM decision
                        WHERE set_id = %s AND reversed_at IS NULL""",
                    (st["set_id"],))
        counts = cur.fetchone()
        cur.execute("""UPDATE decision_set SET seal_hash=%s, sealed_at=now(),
                              sealed_by=%s
                        WHERE set_id=%s""",
                    (h["seal"], sealed_by, st["set_id"]))
        record(actor, "SEAL", "decision_set", str(st["set_id"]),
               after={"seal_hash": h["seal"], "decisions": counts["decisions"],
                      "weakly_graded": counts["weak"]},
               reason=body.note.strip() or "decision set sealed", cursor=cur)
    return {"set_id": str(st["set_id"]), "seal_hash": h["seal"],
            "decisions": counts["decisions"]}


@router.post("/unseal")
def unseal(reason: str, period: str = "2025",
           actor: Actor = Depends(require_controller)) -> dict:
    if not reason.strip():
        raise HTTPException(422, "Unsealing requires a reason for the audit trail.")
    # A certified rate is not unsealed by accident.
    #
    # Unsealing supersedes every rate, which kills the certificate on its own
    # — so this refusal changes no outcome. What it changes is whether the act
    # was deliberate. An auditor rejecting a classification inside a sealed set
    # is the case this whole chain exists for, and it should cost the
    # controller two conscious acts with two reasons on the record, not one
    # that quietly takes his signature off the rate on the way past.
    #
    # It is the `password_round.py` rule in a smaller place: the one act that
    # takes something away from the person who made it is never automatic.
    certified = one("""SELECT signature, certified_by FROM v_rate_certified
                        WHERE period = %s AND certified""", (period,))
    if certified:
        raise HTTPException(
            409,
            f"The rate for {period} is certified — signed by "
            f"{certified['certified_by']}. Unsealing supersedes it, so "
            f"withdraw the signature first and say why: that is two acts on "
            f"the record rather than one that removes a signature on the way "
            f"past.")
    # Also one act. Unsealing and superseding the rates it invalidates were
    # two separate transactions, so there was a moment where the set was open
    # and a rate on file still read as current — the exact state `/review`
    # presents as the rate on file.
    with turn(period) as cur:
        cur.execute("""SELECT set_id FROM decision_set
                        WHERE period=%s AND seal_hash IS NOT NULL
                        ORDER BY sealed_at DESC LIMIT 1""", (period,))
        st = cur.fetchone()
        if not st:
            raise HTTPException(404, "No sealed decision set for this period.")
        cur.execute("""UPDATE decision_set SET seal_hash=NULL, sealed_at=NULL,
                              unsealed_reason=%s WHERE set_id=%s""",
                    (reason, st["set_id"]))
        cur.execute("""UPDATE rate SET status='SUPERSEDED'
                        WHERE set_id=%s AND status<>'ACCEPTED'""", (st["set_id"],))
        record(actor, "UNSEAL", "decision_set", str(st["set_id"]), reason=reason,
               cursor=cur)
    return {"set_id": str(st["set_id"]), "status": "unsealed"}


class ComputeIn(BaseModel):
    """What to compute, and under which policies.

    **An unknown key is a 422 here, and nowhere else in this file.** The rest
    of the API keeps accepting a field it no longer uses, deliberately, so an
    older client is not rejected — `DecideIn.decided_by` says so in as many
    words. A rate is the one body where that is the wrong trade: every field
    on it is a *policy*, each has a default, and pydantic's ordinary
    behaviour is to drop what it does not recognise and quietly apply the
    default instead.

    So `admin_labour_basis` — the name of the column the answer is stored in,
    which is the name anybody reads off the schema — computes and persists a
    rate under `OBJECTIVE`, answers 200, and says nothing. Nine points of
    combined rate, chosen by a typo. Measured: it happened while building the
    min/max band in `docs/RATE_RECOMMENDATION.md`, and only a check on the
    stored basis caught it.

    It also catches the same shape pointing the other way. `period` is a
    query parameter; `scripts/review_system.py` sent it in the body, where it
    did nothing and the default happened to agree.
    """

    model_config = ConfigDict(extra="forbid")

    #: Fringe is recovered on a salary base, not on MTDC. Left to the caller
    #: because the base is a policy choice the controller makes and defends,
    #: not something to infer.
    fringe_base: str = "SALARIES_WAGES"
    combined: bool = True
    note: str = ""
    #: How general-administration labour is treated. `OBJECTIVE` leaves
    #: YBI-GA in the base taking an allocation of indirect — what every rate
    #: before migration 068 did. `POOL` puts its wages and fringe into the
    #: G&A pool, per Appendix IV B.
    #:
    #: **The default is deliberately the old behaviour.** This is a judgment
    #: about whether YBI-GA is genuinely general administration or the bucket
    #: unattributable time went into, and only the person who built the
    #: reconstruction can answer it. Worth 34.82% against 43.99% on the same
    #: sealed judgments, so it is recorded on the rate rather than decided by
    #: whichever branch of the code ran.
    admin_labour: str = "OBJECTIVE"


#: The objective that carries general-administration effort. Named once: a
#: second spelling of it in the handler would be a hand-kept map of a value
#: the distribution decides.
ADMIN_OBJECTIVE = "YBI-GA"


def _build_model(period: str,
                 fringe_base: "AllocationBase | None" = None,
                 admin_labour: str = "OBJECTIVE"):
    """Assemble the domain model from what is on file.

    The engine is pure and knows nothing about Postgres; this is the seam.
    Everything it is given comes from live rows — live decisions, live
    segments, the effective labour distribution — so a rate cannot be computed
    from anything superseded.
    """
    from decimal import Decimal

    from app.domain.core import (Decision, DecisionSet, EvidenceGrade,
                                 FederalTreatment, Function990, PoolType)
    from app.domain.core import AllocationBase
    from app.domain.ingest import Ledger, LedgerLine
    from app.domain.core import money
    from app.domain.pools import CarveOut, PoolModel, SUBAWARD_CAP

    fringe_base = fringe_base or AllocationBase.SALARIES_WAGES

    rows = query("""SELECT line_id::text AS line_id, period,
                           txn_date::text AS date, account,
                           COALESCE(payee, '') AS payee,
                           COALESCE(description, '') AS description,
                           amount, statement AS pl_scope,
                           COALESCE(section, '') AS pl_section,
                           COALESCE(source_key, line_id::text) AS source_key
                      FROM ledger_line
                     WHERE period = %s AND statement = 'P&L'""", (period,))
    ledger = Ledger(period, [LedgerLine(**r) for r in rows])

    decisions = query("""
        SELECT d.decision_id::text AS decision_id, d.scope, d.pool::text AS pool,
               d.function_990::text AS function_990, d.federal::text AS federal,
               d.objective_id, d.grade::text AS grade, d.rationale,
               d.citation, d.decided_by,
               array_agg(DISTINCT dl.line_id::text) AS line_ids,
               -- The documents cited on the judgment. Without these a
               -- VERIFIED grade arrives looking unsupported and the domain
               -- layer rejects the whole set, which is exactly what it should
               -- do — the omission was here, not there.
               COALESCE((SELECT array_agg(de.evidence_id)
                           FROM decision_evidence de
                          WHERE de.decision_id = d.decision_id), '{}') AS refs
          FROM decision d
          JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
         WHERE d.reversed_at IS NULL
         GROUP BY d.decision_id, d.scope, d.pool, d.function_990, d.federal,
                  d.objective_id, d.grade, d.rationale, d.citation, d.decided_by""")

    ds = DecisionSet(period)
    for r in decisions:
        ds.record(Decision(
            decision_id=r["decision_id"], scope=r["scope"],
            line_ids=tuple(r["line_ids"]),
            pool=PoolType(r["pool"]),
            function_990=Function990(r["function_990"]),
            federal=FederalTreatment(r["federal"]),
            objective_id=r["objective_id"],
            evidence=EvidenceGrade(r["grade"]),
            rationale=r["rationale"] or "", citation=r["citation"],
            evidence_refs=tuple(r["refs"] or ()),
            decided_by=r["decided_by"] or ""))

    model = PoolModel(ledger, ds, period)
    model.build()

    # Labour, from whichever record speaks for each employee — a submitted
    # timesheet where there is one, the controller's reconstruction otherwise.
    # backed is the part resting on the employee's own record, which is what
    # the evidence ratio reports.
    labour = query("""
        SELECT objective_id,
               sum(distributed_wages)                                AS wages,
               sum(distributed_wages) FILTER (WHERE source = 'TIMESHEET')
                                                                     AS backed
          FROM v_labor_effective WHERE period = %s
         GROUP BY objective_id""", (period,))
    federal = {r["objective_id"] for r in
               query("SELECT objective_id FROM cost_objective WHERE is_federal")}
    model.add_labor({r["objective_id"]: {"wages": r["wages"] or Decimal(0),
                                         "backed": r["backed"] or Decimal(0)}
                     for r in labour},
                    fringe_rate=Decimal(0),
                    objective_map={}, federal=federal)
    # And now the fringe, at this model's own rate rather than at whatever
    # rate happened to be on file. See `PoolModel.apply_fringe`: reading it
    # from the rate table made the first computation after a seal build its
    # base with no fringe in it, so one sealed set answered 37.82% and then
    # 34.82% depending on how many times the button had been pressed.
    model.apply_fringe(fringe_base)

    # Administration into the pool, if that is the decision on this run. It
    # happens after `apply_fringe` on purpose: what moves is wages *and* the
    # fringe on them, and the fringe does not exist until the rate that
    # carries it has been applied.
    if admin_labour == "POOL":
        model.administration_into_the_pool(ADMIN_OBJECTIVE)

    # Carve-outs from the facilities work: tenant, vacant and committed space
    # is the rental operation's cost and never reaches a federal pool.
    #
    # **The denominator is the estate, not the building.** There is one
    # OVERHEAD pool and it carries the occupancy cost of every building
    # together — the ledger identifies only a handful of accounts to a
    # building and none of them completely. So the honest driver is square
    # footage across the whole estate: a building's excluded space carves
    # its share of the pool, and the shares add to one.
    #
    # It was `overhead_gross * excluded_f / usable_f` per facility, summed.
    # That is exactly right with one building and wrong with any more: five
    # buildings each half let would have carved 250% of the pool and left
    # the overhead rate negative. Nothing could have caught it — the pool
    # ties to itself whatever the carve-outs say, so `v_rate_buildup` reads
    # TIES either way, and the reference record has had exactly one
    # building for the life of the rate engine.
    #
    # One row per building still, because the disclosure is per building:
    # a reviewer asks which building carried what, and the sum of the rows
    # is the adjustment.
    occupancy = query("""SELECT name, tenant_sqft, vacant_sqft, committed_sqft,
                                usable_sqft, rental_share
                           FROM v_facility_occupancy WHERE period = %s""",
                      (period,))
    overhead_gross = model.pools[PoolType.OVERHEAD].gross
    estate = sum((Decimal(str(f["usable_sqft"] or 0)) for f in occupancy),
                 Decimal(0))
    for f in occupancy:
        usable = Decimal(str(f["usable_sqft"] or 0))
        rental = Decimal(str(f["rental_share"] or 0))
        if usable <= 0 or estate <= 0 or overhead_gross <= 0 or rental <= 0:
            continue
        excluded = (Decimal(str(f["tenant_sqft"] or 0))
                    + Decimal(str(f["vacant_sqft"] or 0))
                    + Decimal(str(f["committed_sqft"] or 0)))
        share = ((usable / estate) * rental).quantize(Decimal("0.000001"))
        model.add_carve_out(PoolType.OVERHEAD, CarveOut(
            name=f"Rental and vacant space — {f['name']}",
            citation="2 CFR 200.465",
            amount=(overhead_gross * share).quantize(Decimal("0.01")),
            driver=(f"{rental:.1%} of this building is let, committed or "
                    f"vacant ({excluded:,.0f} sq ft); the building is "
                    f"{usable:,.0f} of the estate's {estate:,.0f}"),
            evidence=EvidenceGrade.MANAGEMENT_RECONSTRUCTION))

    # And the second carve-out the registers can now support: 2 CFR 200.436(b)
    # makes depreciation on an asset bought with federal money unallowable, so
    # it must not sit in a pool that is charged to federal awards.
    #
    # It waited on `asset_funding` having an answer in it. Until `085` loaded
    # the register there was nothing to ask, and until Heidi answers the
    # funding source the federal share of every asset is zero — which is not
    # the same fact as *no federal money bought any of this*, and is why the
    # walk's ASSETS step reads OPEN rather than DONE while the column is blank.
    #
    # The ceiling is the depreciation the pool actually holds. A register that
    # disagrees with the ledger is a control of its own (`v_asset_control`),
    # not a licence to carve cost the pool does not carry.
    unallowable = one("""SELECT COALESCE(sum(depreciation
                                            - allowable_depreciation), 0)
                                AS amount,
                                count(*) FILTER (WHERE federal_share > 0)
                                AS assets
                           FROM v_asset_allowability
                          WHERE period = %s AND in_use""", (period,))
    in_the_pool = one("""SELECT COALESCE(sum(l.amount), 0) AS amount
                           FROM decision d
                           JOIN decision_line dl USING (decision_id)
                           JOIN ledger_line l USING (line_id)
                          WHERE d.reversed_at IS NULL AND dl.live
                            AND d.pool = 'OVERHEAD' AND l.period = %s
                            AND l.account LIKE %s""", (period, "%5010%"))
    federally_funded = Decimal(str(unallowable["amount"] or 0))
    ceiling = Decimal(str(in_the_pool["amount"] or 0))
    if federally_funded > 0 and ceiling > 0:
        amount = min(federally_funded, ceiling)
        model.add_carve_out(PoolType.OVERHEAD, CarveOut(
            name="Depreciation on federally funded assets",
            citation="2 CFR 200.436(b)",
            amount=amount.quantize(Decimal("0.01")),
            driver=(f"{unallowable['assets']} asset(s) on the fixed-asset "
                    f"register carry a federal funding source; the "
                    f"depreciation on the federally funded share of them is "
                    f"{federally_funded:,.2f}, against {ceiling:,.2f} of "
                    f"depreciation classified to this pool"),
            evidence=EvidenceGrade.CORROBORATED))

    # And the third adjustment to the base, which is not a carve-out at all:
    # 2 CFR 200.1 takes the first $25,000 of each **subaward** into MTDC and a
    # contract for services whole. That sits on the objective rather than on a
    # pool — it changes the denominator a rate is allocated over, not the
    # numerator — which is why `ObjectiveCost.subaward_excess` has been on the
    # domain model since it was written.
    #
    # **And nothing had ever written it.** `115` opened the register, priced
    # the exposure at $313,605.35 of MTDC across six parties, and the engine
    # went on reading a field that was zero for everybody. The fourteenth
    # instance of the dead-register shape and the softest: the table has a
    # writer, and its *answer* reached no figure.
    #
    # **Nothing changes by default, and that is the property to keep.**
    # UNDETERMINED contributes nothing, because it is not a number — it is
    # `NO DATA`, and defaulting it either way would decide a 200.331 question
    # by omission. So a record where nobody has determined anything computes
    # exactly the rate it computed before this existed, and only a
    # determination somebody signed their name to moves the base.
    for party in query("""SELECT objective_id, payee, amount
                            FROM party_determination
                           WHERE period = %s AND determination = 'SUBRECIPIENT'""",
                       (period,)):
        obj = model.objectives.get(party["objective_id"])
        if obj is None:
            continue
        excess = max(Decimal(str(party["amount"])) - SUBAWARD_CAP, Decimal(0))
        obj.subaward_excess = money(obj.subaward_excess + excess)
    return model


@router.post("/compute")
def compute(body: ComputeIn, period: str = "2025",
            actor: Actor = Depends(require_controller)) -> dict:
    """Compute the rates from the sealed set, and persist them.

    The sequence is one-directional and the database enforces the first step
    of it: ``rate_requires_seal`` refuses a rate whose seal does not match a
    sealed decision set, so this cannot produce a number from judgments that
    are still moving — in this handler or in any future one.

    Both proofs run before anything is written. A pool that does not tie to
    the ledger, or an allocation that does not land every allocable dollar on
    exactly one objective, is a finding rather than a rate.
    """
    from decimal import Decimal

    from app.domain.core import AllocationBase, PoolType

    # A rate over a ledger that does not agree with the statements it came
    # from is a rate over the wrong numbers, however carefully the pools were
    # built on top of it. The cross-reference register is checked here rather
    # than left as a report somebody was supposed to read.
    #
    # An explained difference is not an open one: a reconciling item with the
    # ledger lines behind it closes the control. What this refuses is a
    # difference nobody has accounted for.
    open_controls = query("""SELECT control, description, note, state,
                                    variance::text AS variance,
                                    exceptions::text AS exceptions
                               FROM v_statement_reconciliation
                              WHERE period = %s AND NOT ties ORDER BY seq""",
                          (period,))
    if open_controls:
        raise HTTPException(409, {
            "error": "STATEMENTS_DO_NOT_RECONCILE",
            "message": ("The books do not yet agree with themselves. A rate "
                        "built on them would be built on the wrong numbers. "
                        "Points marked OPEN have a difference to name; points "
                        "marked NO DATA are waiting on a document that has "
                        "not been imported."),
            "open": open_controls})

    sealed = one("""SELECT set_id, seal_hash FROM decision_set
                     WHERE period = %s AND seal_hash IS NOT NULL
                     ORDER BY sealed_at DESC LIMIT 1""", (period,))
    if not sealed:
        raise HTTPException(
            409, "No sealed decision set for this period. Seal the "
                 "classifications first — the rate has to be a consequence of "
                 "the judgments, not an input to them.")

    try:
        base_type = AllocationBase(body.fringe_base)
    except ValueError:
        raise HTTPException(422, f"Unknown base {body.fringe_base!r}.")

    if body.admin_labour not in ("OBJECTIVE", "POOL"):
        raise HTTPException(
            422, f"admin_labour must be OBJECTIVE or POOL, not "
                 f"{body.admin_labour!r}. OBJECTIVE leaves general "
                 f"administration in the base taking an allocation of "
                 f"indirect; POOL puts it in the G&A pool per Appendix IV B.")

    model = _build_model(period, base_type, body.admin_labour)
    model.decisions._sealed_hash = sealed["seal_hash"]   # the seal on file
    # The payroll, not the allocation base: administration moved into the
    # G&A pool is out of one and still in the other.
    fringe_base = model.base_amount(base_type, fringe_denominator=True)

    rates = model.compute_rates(fringe_base=fringe_base)
    model.allocate(use_combined=body.combined)

    ledger_total = one("""SELECT COALESCE(sum(amount), 0) AS t FROM ledger_line
                           WHERE period = %s AND statement = 'P&L'""",
                       (period,))["t"]
    recon = model.reconciliation(Decimal(str(ledger_total)))
    proof = model.allocation_proof()
    if proof["variance"] != Decimal("0.00"):
        raise HTTPException(409, {
            "error": "ALLOCATION_DOES_NOT_TIE",
            "message": f"The allocation distributes {proof['distributed']} "
                       f"against {proof['allocable']} allocable. An allocation "
                       f"that does not tie is a finding, not a rate.",
            "variance": str(proof["variance"])})

    base_for = {
        "FRINGE": (fringe_base, base_type),
        "OVERHEAD": (model.base_amount(model.pools[PoolType.OVERHEAD].base_type),
                     model.pools[PoolType.OVERHEAD].base_type),
        "G&A": (model.base_amount(model.pools[PoolType.GA].base_type),
                model.pools[PoolType.GA].base_type),
        "INDIRECT_COMBINED": (model.base_amount(model.pools[PoolType.GA].base_type),
                              model.pools[PoolType.GA].base_type),
    }
    pool_for = {
        "FRINGE": model.pools[PoolType.FRINGE].allocable,
        "OVERHEAD": model.pools[PoolType.OVERHEAD].allocable,
        "G&A": model.pools[PoolType.GA].allocable,
        "INDIRECT_COMBINED": (model.pools[PoolType.OVERHEAD].allocable
                              + model.pools[PoolType.GA].allocable),
    }

    written = []
    rate_ids: dict[str, str] = {}
    with turn(period) as cur:
        # The model above was built from live rows on other connections, which
        # takes long enough for somebody to unseal underneath it. The period is
        # held from here, so re-reading the seal settles it: if it moved, every
        # figure computed above describes a set that no longer exists, and
        # writing them would produce a rate carrying a seal nobody can
        # reproduce. `rate_requires_seal` would refuse the insert anyway — as
        # a raw constraint violation, which tells the controller nothing.
        cur.execute("""SELECT seal_hash FROM decision_set WHERE set_id = %s""",
                    (sealed["set_id"],))
        still = cur.fetchone()
        if not still or still["seal_hash"] != sealed["seal_hash"]:
            raise HTTPException(409, {
                "error": "SEAL_MOVED",
                "message": ("The decision set was unsealed while this rate was "
                            "being computed, so the figures describe a set that "
                            "is no longer sealed. Nothing was written. Seal "
                            "again and recompute."),
                "seal_hash": sealed["seal_hash"]})

        # A recomputation supersedes what it replaces rather than sitting
        # beside it. Anything already accepted is left alone: an accepted rate
        # is a position taken with a sponsor and is not ours to overwrite.
        cur.execute("""UPDATE rate SET status = 'SUPERSEDED'
                        WHERE period = %s AND status = 'PROPOSED'""", (period,))

        # And the carve-outs the model applied, written down beside the rate
        # they are part of.
        #
        # This was the largest hole in the system and it was invisible from
        # the code: `_build_model` applies the 200.465 facilities carve-out
        # correctly and `rate.pool_amount` is net of it, so every figure the
        # computation produced was right. It simply never recorded *what* it
        # excluded — and `v_pool_balance`, `v_rate_buildup` and the
        # `/review/rate` screen all read `carve_out`, found nothing, and
        # reported that nothing had been carved out.
        #
        # Against the live record that was $932,254.78 of a $1,678,057.27
        # overhead pool: the single largest adjustment in the rate model,
        # missing from the workpaper an auditor reads, with a control-shaped
        # view stating the opposite. A rate whose largest adjustment cannot
        # be seen is exactly the rate somebody asks whether you
        # reverse-engineered.
        #
        # Rewritten each time rather than appended to, because a carve-out
        # belongs to the computation that applied it: leaving the previous
        # run's rows would make `v_pool_balance` net a superseded exclusion
        # off a live pool. The delete and the insert are one statement apart
        # inside the turn that writes the rate, so no reader sees neither and
        # no reader sees both.
        cur.execute("DELETE FROM carve_out WHERE period = %s", (period,))
        for pool in model.pools.values():
            for c in pool.carve_outs:
                cur.execute("""INSERT INTO carve_out
                                 (pool, period, name, citation, amount,
                                  driver, grade, created_by)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (pool.pool_type.value, period, c.name, c.citation,
                             c.amount, c.driver, c.evidence.value,
                             actor.display_name))
        for kind, value in rates.items():
            base_amount, bt = base_for[kind]
            if base_amount <= 0:
                continue          # a rate on no base is not a rate
            cur.execute("""INSERT INTO rate
                             (period, set_id, seal_hash, kind, pool_amount,
                              base_type, base_amount, rate, computed_by,
                              admin_labour_basis)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING rate_id""",
                        (period, sealed["set_id"], sealed["seal_hash"], kind,
                         pool_for[kind], bt.value, base_amount, value,
                         actor.display_name, body.admin_labour))
            rate_id = cur.fetchone()["rate_id"]
            rate_ids[kind] = str(rate_id)
            written.append({"kind": kind, "rate": str(value),
                            "pool": str(pool_for[kind]),
                            "base": str(base_amount),
                            "base_type": bt.value, "rate_id": str(rate_id)})

            if kind == ("INDIRECT_COMBINED" if body.combined else "G&A"):
                for o in model.objectives.values():
                    allocated = o.indirect
                    if not allocated:
                        continue
                    cur.execute("""INSERT INTO allocation
                                     (rate_id, objective_id, base_amount,
                                      allocated)
                                   VALUES (%s,%s,%s,%s)
                                   ON CONFLICT (rate_id, objective_id)
                                     DO UPDATE SET allocated = EXCLUDED.allocated""",
                                (rate_id, o.objective_id, o.mtdc, allocated))

        # The contract constraints, tested against the rate that was just
        # written and recorded against its id. `domain/awards.py` has had
        # this engine since the schema was written and no caller anywhere,
        # so `/trueup` answered INVOICE_ISSUABLE on every award because it
        # counted zero blocking failures out of zero tests.
        from app.domain.awards import RateMethod
        from app.routers.awards import evaluate as evaluate_awards
        combined = "INDIRECT_COMBINED" if body.combined else "G&A"
        tested = evaluate_awards(
            cur, period, rate_ids.get(combined), rates.get(combined, Decimal(0)),
            RateMethod.NEGOTIATED)

        record(actor, "RATE_COMPUTE", "decision_set", str(sealed["set_id"]),
               after={"seal_hash": sealed["seal_hash"],
                      "constraints_tested": tested,
                      "carve_outs": [c.name for p in model.pools.values()
                                     for c in p.carve_outs],
                      "rates": {k: str(v) for k, v in rates.items()},
                      "objectives": len(model.objectives),
                      "unclassified": str(model.unclassified)},
               reason=body.note.strip() or "rates computed from the sealed set",
               cursor=cur)

    return {
        "period": period, "seal_hash": sealed["seal_hash"], "rates": written,
        "allocation": [{"objective_id": o.objective_id,
                        "mtdc": str(o.mtdc),
                        "direct": str(o.total_direct),
                        "indirect": str(o.indirect),
                        "fully_burdened": str(o.fully_burdened),
                        "evidence_ratio": (str(o.evidence_ratio)
                                           if o.evidence_ratio is not None else None)}
                       for o in sorted(model.objectives.values(),
                                       key=lambda x: -x.mtdc)],
        "proofs": {"reconciliation": {k: str(v) for k, v in recon.items()},
                   "allocation": {k: str(v) for k, v in proof.items()},
                   "rounding_residual": str(model.rounding_residual)},
        "carve_outs": [{"name": c.name, "citation": c.citation,
                        "amount": str(c.amount), "driver": c.driver}
                       for p in model.pools.values() for c in p.carve_outs],
        "unclassified": str(model.unclassified),
    }


@router.get("/current")
def current(period: str = "2025") -> dict:
    """The rates on file, and whether the set behind them is sealed.

    `sealed` is here because the screen has to know and **must not remember**.
    Sealing unlocks computing, so the rate screen offers that action only
    against a sealed set — and a flag set when the seal call returns is wrong
    the moment somebody reloads, or the moment the other controller unseals.
    It is the same rule the timesheet draft card follows for `adopted`: the
    answer is already on the record, so read it.
    """
    rates = query("""SELECT kind, pool_amount, base_type, base_amount, rate, status,
                            seal_hash, computed_at
                       FROM rate WHERE period=%s AND status<>'SUPERSEDED'
                      ORDER BY computed_at DESC""", (period,))
    state = one("""SELECT seal_hash IS NOT NULL AS sealed, sealed_at, sealed_by
                     FROM decision_set WHERE period = %s
                    ORDER BY sealed_at DESC NULLS LAST LIMIT 1""", (period,))
    return {"period": period, "rates": rates,
            "sealed": bool(state and state["sealed"]),
            "sealed_at": state.get("sealed_at") if state else None,
            "sealed_by": state.get("sealed_by") if state else None}


class CertifyIn(BaseModel):
    """Typing your own name is the signature. Nothing else is."""
    signature: str = Field(..., min_length=2, max_length=120)
    note: str = ""
    #: What kind of act this is. A person signing leaves it alone; a drive
    #: proving the mechanism sends REHEARSAL, and every paper resting on the
    #: signature then prints REHEARSAL instead of a name.
    #:
    #: **It can only ever be used to weaken a signature.** A caller may label
    #: its own certification a rehearsal; nothing here lets one claim to be a
    #: controller's that was not already, because CONTROLLER is the default
    #: and the column is write-once. The direction is the whole safety of it:
    #: the failure this exists for is a script that typed a person's name into
    #: `signature` and put it on a memorandum to a sponsor.
    origin: str = "CONTROLLER"


@router.post("/certify")
def certify(body: CertifyIn, period: str = "2025",
            actor: Actor = Depends(require_controller)) -> dict:
    """Put your name on the rate build-up.

    Everything up to here is free-order and nothing after here is blocked.
    What this changes is whether the paper that comes out says it is
    certified: an invoice regenerated or a workbook produced without a
    signature carries **NOT CERTIFIED**, which is the rule
    `invoice_document.py` already follows for a reproduction, pointed at the
    one fact every output depends on.

    It is not `rate.status`. That is the sponsor conversation — PROPOSED means
    YBI has put the rate to NCDMM. This is the controller asserting the rate
    is final and his.

    **The signature does not wait for the record to be complete.** Tom may
    certify with the square footage still missing; refusing would stop him
    signing for as long as a document somebody else holds is outstanding. What
    must not happen is the caveat being lost, so the certificate records the
    walk's unfinished steps as they stood and every document rendered under it
    can say what the signature covered.

    Signing for somebody else is not possible: the actor comes from the
    session, `require_controller` refuses anybody else, and
    `refuse_issued_password` refuses an account still on a password somebody
    else chose.
    """
    with turn(period):
        rates = query("""SELECT rate_id, kind, seal_hash FROM rate
                          WHERE period = %s AND status <> 'SUPERSEDED'
                          ORDER BY computed_at DESC""", (period,))
        if not rates:
            raise HTTPException(
                409, "No rate stands for this period. Seal the "
                     "classifications and compute before signing — a "
                     "signature on an arithmetic nobody has done yet is a "
                     "signature on nothing.")
        seals = {r["seal_hash"] for r in rates}
        if len(seals) > 1:
            raise HTTPException(
                409, "The live rates carry more than one seal, so there is "
                     "no single build-up to sign. Recompute and try again.")
        seal_hash = seals.pop()

        # What the signature covers. Read inside the turn, because a step
        # that clears between the read and the write would leave the
        # certificate describing a record that never existed.
        # Everything still open **except this act**. The certification step
        # is necessarily open at the instant it is read — it is the thing
        # being done — and listing it put "The rate certified — open" on the
        # face of the certificate, which is a document contradicting itself.
        # Excluded by key rather than by number: the sequence has already been
        # renumbered once and a literal 9 here would have followed it silently.
        outstanding = query(
            """SELECT seq, key, step, state, detail FROM v_audit_walk
                WHERE period = %s AND state <> 'DONE' AND key <> 'CERTIFY'
                ORDER BY seq""",
            (period,))

        # Read the one definition, not a second copy of it. A first draft
        # checked `withdrawn_at IS NULL` on the same seal here, which refused
        # a perfectly good signature on a *recomputed* build-up: the
        # judgments were unchanged so the seal came back the same, and the
        # dead certificate was not withdrawn — it was superseded, which is a
        # different fact. The schema holds the same rule through the same
        # view, so the handler and the trigger cannot disagree.
        origin = (body.origin or "CONTROLLER").strip().upper()
        if origin not in ("CONTROLLER", "REHEARSAL"):
            raise HTTPException(
                422, "A signature is a controller's or a rehearsal's. "
                     "Leave it alone to sign, or send REHEARSAL if a script "
                     "is proving the mechanism rather than a person signing.")

        live = one("""SELECT cert_id FROM v_rate_certified
                       WHERE period = %s AND certified""", (period,))
        if live:
            raise HTTPException(
                409, "This build-up is already certified. Withdraw the "
                     "signature first if it needs to be made again.")

        with transaction() as cur:
            cur.execute(
                """INSERT INTO rate_certification
                       (period, seal_hash, signature, certified_by,
                        outstanding, note, origin)
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING cert_id, certified_at""",
                (period, seal_hash, body.signature.strip(), actor.actor_id,
                 json.dumps([dict(o) for o in outstanding], default=str),
                 body.note.strip(), origin))
            row = cur.fetchone()
            # The rate rows this signature is on. Recomputing supersedes them
            # and the certificate dies with them, which is what stops an
            # unseal-and-reseal cycle silently reviving a signature on
            # arithmetic nobody signed.
            cur.executemany(
                """INSERT INTO rate_certification_line (cert_id, rate_id)
                   VALUES (%s, %s)""",
                [(row["cert_id"], r["rate_id"]) for r in rates])
            record(actor, "RATE_CERTIFY", "rate_certification",
                   str(row["cert_id"]),
                   after={"seal_hash": seal_hash,
                          "signature": body.signature.strip(),
                          "rates": [r["kind"] for r in rates],
                          "outstanding": len(outstanding)},
                   reason=body.note.strip() or
                          "Certified the 2025 rate build-up.",
                   cursor=cur)

    return {"period": period, "cert_id": str(row["cert_id"]),
            "certified_at": row["certified_at"], "seal_hash": seal_hash,
            "signature": body.signature.strip(),
            "rates": [r["kind"] for r in rates],
            "outstanding": outstanding}


class WithdrawIn(BaseModel):
    reason: str = Field(..., min_length=20)


@router.post("/certify/withdraw")
def withdraw(body: WithdrawIn, period: str = "2025",
             actor: Actor = Depends(require_controller)) -> dict:
    """Take your name off it again.

    A lock nobody can open is a lock somebody works around, so this exists;
    and a signature withdrawn without a reason is the next person's puzzle, so
    the schema refuses one under twenty characters. The certificate is not
    deleted — it stands as the record that a position was taken and then
    withdrawn, which is the rule `restatement` already follows.
    """
    with turn(period):
        # The *live* certificate, from the one definition. Reading
        # `withdrawn_at IS NULL` here picked the wrong row the moment a
        # recompute had superseded an earlier signature: that certificate is
        # not withdrawn, it is dead, and withdrawing it left the live one
        # standing while the route answered 200. Superseded and withdrawn are
        # different facts and only one view knows which is which.
        live = one("""SELECT cert_id, seal_hash FROM v_rate_certified
                       WHERE period = %s AND certified""", (period,))
        if not live:
            raise HTTPException(
                409, "There is no live signature on this period's rate.")
        with transaction() as cur:
            cur.execute(
                """UPDATE rate_certification
                      SET withdrawn_at = now(), withdrawn_by = %s,
                          withdrawn_reason = %s
                    WHERE cert_id = %s""",
                (actor.actor_id, body.reason.strip(), live["cert_id"]))
            record(actor, "RATE_CERTIFY_WITHDRAW", "rate_certification",
                   str(live["cert_id"]),
                   after={"withdrawn": True},
                   reason=body.reason.strip(), cursor=cur)
    return {"period": period, "cert_id": str(live["cert_id"]),
            "withdrawn": True}


def rate_certification(period: str) -> dict | None:
    """What `v_rate_certified` says, for anything that prints a band.

    The endpoint below answers the same question to a screen. Both read this
    so a workbook and the screen that produced it cannot hold two opinions
    about whether anybody has signed — which is the whole point of the band,
    and is why this is a function rather than three queries.

    Returns None where the period has no row at all. `certification_lines`
    treats that as unsigned and says so, rather than printing nothing: a
    document silent about its own signature is read generously.
    """
    return one("""SELECT period, certified, cert_id, signature, certified_at,
                         certified_by, seal_hash, outstanding, note, why_not,
                         origin, rehearsal
                    FROM v_rate_certified WHERE period = %s""", (period,))


@router.get("/certification")
def certification(period: str = "2025") -> dict:
    """Whether the rate is certified right now, and the sentence if not.

    One fact, read from one view, by every screen and every renderer — so a
    footer cannot say one thing while a screen says another.
    """
    row = rate_certification(period)
    if not row:
        raise HTTPException(404, "No such period.")
    return row


@router.get("/allocation")
def allocation(rate_id: str) -> dict:
    """What one rate allocated, and whether that rate still stands.

    The caller names the rate, so a superseded one is a legitimate thing to
    ask for — a workpaper that cited it has to keep resolving. What is not
    legitimate is showing its allocation without saying so, which is exactly
    the trap `v_rate_buildup` fell into when it presented four superseded
    rates as the rate on file.

    Unsealing supersedes every rate and leaves its allocations in place, so
    this is not a rare state: it is what the record looks like the moment a
    controller reopens classification.
    """
    r = one("""SELECT status, kind, seal_hash, computed_at
                 FROM rate WHERE rate_id = %s""", (rate_id,))
    if not r:
        raise HTTPException(404, "No such rate.")
    rows = query("""SELECT a.objective_id, o.label, o.is_federal,
                           a.base_amount, a.allocated, a.rounding_adj
                      FROM allocation a JOIN cost_objective o USING (objective_id)
                     WHERE a.rate_id=%s ORDER BY a.allocated DESC""", (rate_id,))
    superseded = r["status"] == "SUPERSEDED"
    return {
        "rate_id": rate_id, "kind": r["kind"], "status": r["status"],
        "seal_hash": r["seal_hash"], "computed_at": r["computed_at"],
        "superseded": superseded,
        "caveat": ("This rate has been superseded — the classifications under "
                   "it have been reopened. The allocation below is what it "
                   "produced when it stood, not the allocation on file."
                   if superseded else ""),
        "allocation": rows,
    }
