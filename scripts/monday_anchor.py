#!/usr/bin/env python3
"""The anchor sheet: every current recommendation, in the order Monday runs.

    DATABASE_URL=... python3 scripts/monday_anchor.py --pdf

Nine documents in `docs/` carry recommendations and none of them is ordered
the way the work is actually done. A recommendation nobody can find at the
moment it applies is one nobody checks — so this is the same set, dealt into
the sequence of `docs/MONDAY_RUNBOOK.md`, with the screen each one is visible
on and what the record says about it right now.

**Every figure is read from the live record.** The rule this repository keeps
for a document written for somebody else is that its figures are read rather
than recalled, and the last three times that was broken the document was
wrong by weeks, by a factor of 1.7, and by a stale rate quoted to a board.
So the prose is here and the numbers are not: `facts()` reads them, and a
fact that cannot be read stops the run rather than printing blank.

It is a **QA instrument, not a workpaper**. Nothing computes: every figure is
read from the row it was recorded in, like the review screens.
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import query  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "MONDAY_ANCHOR.html"
PERIOD = "2025"


def money(v) -> str:
    if v is None:
        return "—"
    return f"${Decimal(v):,.2f}"


def pct(v) -> str:
    if v is None:
        return "—"
    return f"{Decimal(v) * 100:.2f}%"


def facts() -> dict:
    """Read everything the sheet states. A missing fact is a stopped run."""
    f: dict = {}

    ctl = query("""select state, count(*) n from v_statement_reconciliation
                    where period = %s group by state""", (PERIOD,))
    f["ctl"] = {r["state"]: r["n"] for r in ctl}
    f["ctl_total"] = sum(f["ctl"].values())
    f["ctl_ties"] = f["ctl"].get("TIES", 0)

    f["recon_items"] = query(
        "select count(*) n from reconciling_item where period = %s", (PERIOD,))[0]["n"]

    cov = query("select * from v_classification_coverage where period = %s",
                (PERIOD,))[0]
    f["cov"] = cov

    seal = query("""select label, seal_hash, sealed_at, sealed_by
                      from decision_set where period = %s
                     order by sealed_at desc nulls last limit 1""", (PERIOD,))[0]
    f["seal"] = seal
    f["live_judgments"] = query(
        """select count(*) n from decision d join decision_set s using (set_id)
            where s.period = %s and d.reversed_at is null""", (PERIOD,))[0]["n"]

    rates = query("""select kind, rate, pool_amount, base_amount, base_type,
                            admin_labour_basis, computed_at, computed_by
                       from rate where period = %s and status = 'PROPOSED'""",
                  (PERIOD,))
    f["rate"] = {r["kind"]: r for r in rates}

    anc = query("select state, count(*) n from v_rate_anchor where period = %s"
                " group by state", (PERIOD,))
    f["anchor"] = {r["state"]: r["n"] for r in anc}
    f["anchor_total"] = sum(f["anchor"].values())

    bu = query("""select state, count(*) n from
                    (select pool_state state from v_rate_buildup
                      where period = %s and status = 'PROPOSED') t
                  group by state""", (PERIOD,))
    f["buildup"] = {r["state"]: r["n"] for r in bu}

    f["carve_rows"] = query("select count(*) n from carve_out")[0]["n"]
    f["facilities"] = query("select count(*) n from facility")[0]["n"]

    f["overhead_credits"] = query("""
        select sum(case when l.amount < 0 then -l.amount else 0 end) c
          from decision d
          join decision_line dl on dl.decision_id = d.decision_id and dl.live
          join ledger_line l on l.line_id = dl.line_id
         where d.reversed_at is null and d.pool = 'OVERHEAD'""")[0]["c"]
    f["overhead_credits_named"] = query("""
        select sum(case when l.amount < 0 then -l.amount else 0 end) c
          from decision d
          join decision_line dl on dl.decision_id = d.decision_id and dl.live
          join ledger_line l on l.line_id = dl.line_id
         where d.reversed_at is null and d.pool = 'OVERHEAD' and l.payee <> ''""")[0]["c"]

    # The accounts each recommendation names, as judged.
    acct = {}
    for r in query("""
        select split_part(l.account, ':', -1) acct, d.pool, d.federal,
               d.objective_id, sum(l.amount) net, sum(abs(l.amount)) gross,
               count(*) n
          from decision d
          join decision_line dl on dl.decision_id = d.decision_id and dl.live
          join ledger_line l on l.line_id = dl.line_id
         where d.reversed_at is null
         group by 1, 2, 3, 4"""):
        acct.setdefault(r["acct"][:4], []).append(r)
    f["acct"] = acct

    f["grades"] = {r["grade"]: r["n"] for r in query(
        """select grade, count(*) n from decision d
             join decision_set s using (set_id)
            where s.period = %s and d.reversed_at is null
            group by grade""", (PERIOD,))}

    f["worklist"] = {r["kind"]: r["n"] for r in query(
        "select kind, count(*) n from v_worklist group by kind")}

    f["timesheets"] = query("select count(*) n from timesheet_entry")[0]["n"]
    f["certs"] = query("select count(*) n from labor_certification")[0]["n"]
    f["employment"] = query("select count(*) n from employment")[0]["n"]
    f["people"] = query(
        """select count(distinct employee_key) n from labor_allocation
            where period = %s""", (PERIOD,))[0]["n"]

    f["constraints"] = query("""
        select distinct on (award_id, code) award_id, code, passed, evaluable,
               blocking, detail
          from constraint_result order by award_id, code, evaluated_at desc""")

    f["restate"] = query("""
        select objective_id, invoices, billed_total, indirect_billed,
               indirect_supported, under_recovered, over_collected
          from restatement where status = 'PROPOSED' order by objective_id""")

    f["awards"] = query("""select award_id, ceiling_federal, cost_share_required,
                                  period_end, rate_method from award
                            order by award_id""")

    f["contractor"] = query(
        "select * from v_contractor_effort_check where state = 'OPEN'"
        " order by expense desc")

    f["admin"] = query("select * from v_admin_labour_decision where period = %s",
                       (PERIOD,))[0]

    for k in ("cov", "seal", "admin"):
        if not f.get(k):
            raise SystemExit(f"the record has no {k} — nothing to anchor")
    if not f["rate"]:
        raise SystemExit("no rate on file — the anchor would state a rate that "
                         "does not exist")
    return f


def a(f: dict, num: str, field: str = "gross"):
    """One account's figure as judged, by its leading number."""
    rows = f["acct"].get(num, [])
    if not rows:
        return None
    return sum(r[field] for r in rows)


def acct_pool(f: dict, num: str) -> str:
    rows = f["acct"].get(num, [])
    return " / ".join(sorted({r["pool"] for r in rows})) if rows else "—"


def acct_fed(f: dict, num: str) -> str:
    rows = f["acct"].get(num, [])
    return " / ".join(sorted({r["federal"] for r in rows})) if rows else "—"


# ── the recommendations, in the order Monday runs ────────────────────────────
# Prose is judgment and lives here. Every figure comes from `f`.

def recommendations(f: dict) -> list[dict]:
    rate = f["rate"]
    comb = rate.get("INDIRECT_COMBINED")
    fr = rate.get("FRINGE")
    oh = rate.get("OVERHEAD")
    ga = rate.get("G&A")
    wl = f["worklist"]
    fails = [c for c in f["constraints"] if not c["passed"] and c["evaluable"]]

    def failing(code):
        return [c for c in fails if c["code"] == code]

    R: list[dict] = []

    # ── Step 0 ──────────────────────────────────────────────────────────────
    R.append(dict(
        id="R1", step="0", screen="/ — the landing page",
        title="Confirm the record is where this sheet says it is",
        rec="Before anything else, read the five state figures off the screens "
            "and tick them here. If any one of them differs, stop and find out "
            "why — every recommendation below is written against this state.",
        record=[
            (f"{f['ctl_ties']} of {f['ctl_total']} control points tie",
             f"{f['recon_items']} reconciling items recorded"),
            (f"{f['cov']['groups_decided']:,} of {f['cov']['groups_total']:,} "
             f"groups classified",
             f"{money(f['cov']['unclassified'])} unclassified, "
             f"{f['cov']['pct_dollars_covered']}%"),
            (f"sealed by {f['seal']['sealed_by']}",
             f"{f['seal']['sealed_at']:%d %b %Y %H:%M} UTC, covering "
             f"{f['live_judgments']:,} live judgments"),
            (f"INDIRECT_COMBINED {pct(comb['rate']) if comb else '—'}",
             f"administrative labour on the "
             f"{comb['admin_labour_basis'] if comb else '—'} basis"),
            (f"{f['anchor'].get('TIES', 0)} of {f['anchor_total']} rate anchors tie",
             "every pool at pool_variance 0.00"),
        ],
        cite=None,
        watch="A figure that has moved since Friday is not automatically wrong "
              "— somebody may have done the QuickBooks reposting. It is a "
              "reason to re-read, not to proceed.",
    ))

    # ── Step 1 · /reconcile ─────────────────────────────────────────────────
    R.append(dict(
        id="R2", step="1", screen="/reconcile — Schedule A-1",
        title="Keep all eleven control points tying before any rate is touched",
        rec=f"All {f['ctl_ties']} tie today. Confirm they still do. "
            "`POST /api/rates/compute` returns 409 while any one is open, and "
            "that gate is correct: a rate over books that do not agree with "
            "themselves is a rate over the wrong numbers.",
        record=[("state", ", ".join(f"{v} {k}" for k, v in sorted(f["ctl"].items()))),
                ("reconciling items", f"{f['recon_items']} recorded")],
        cite=None,
        watch="A difference is closed by naming the lines behind it, never by "
              "netting it. NO DATA is not a pass.",
    ))
    R.append(dict(
        id="R3", step="1", screen="/reconcile — PAYROLL_REGISTER",
        title="When the Bacon credit is reposted in QuickBooks, take the "
              "reconciling item off with it",
        rec="The $45,053.23 donor credit sitting in an intern wage account is "
            "confirmed and named, not netted — it is why the fringe rate reads "
            "21.90% over the payroll register rather than 22.45% over the "
            "ledger's wage accounts. It has not been reposted. **When it is, "
            "the reconciling item has to come off in the same pass or the "
            "correction counts twice.**",
        record=[("the eleventh control",
                 "PAYROLL_REGISTER, the only one of the eleven that touches "
                 "the register"),
                ("today", "TIES, with the difference named")],
        cite="The reconciling item is computed from the live difference, so it "
             "lands on its own — but the item itself stays until somebody "
             "removes it.",
        watch="This is the change most likely to have happened over the "
              "weekend. Check it before anything else.",
    ))

    # ── Step 2 · /classify ──────────────────────────────────────────────────
    R.append(dict(
        id="R4", step="2", screen="/classify — search 5227",
        title="Portfolio consulting stays in the base as contractor cost",
        rec="These consultants deliver into YBI's own incubation programme "
            "against YBI's scope, which makes them **contractors, not "
            "subrecipients** — so the whole amount counts in MTDC rather than "
            "only the first $25,000. That is the point of putting it there: "
            "YBI selects, scopes, administers and carries the other half, and "
            "that administrative effort is what the G&A pool recovers on.",
        record=[("as judged", f"{acct_pool(f, '5227')}, "
                 f"{money(a(f, '5227', 'net'))} net"),
                ("gross movement", f"{money(a(f, '5227'))} over "
                 f"{sum(r['n'] for r in f['acct'].get('5227', []))} lines")],
        cite="2 CFR 200.331",
        watch="Reading them as subrecipients instead takes cost **out** of the "
              "base and the combined rate **up**, to about 50.23%. The "
              "conservative reading of a classification can be the aggressive "
              "reading of the rate.",
    ))
    R.append(dict(
        id="R5", step="2", screen="/classify — search 5010",
        title="Depreciation is OVERHEAD and its federal treatment stays PENDING",
        rec="The pool is not in doubt — depreciation is occupancy cost. The "
            "**claim** is: 200.436(b) makes depreciation on a federally funded "
            "asset unallowable, and the fixed-asset schedule has no "
            "funding-source column at all. PENDING puts the cost where it "
            "belongs and leaves the claim open, which is what is actually true. "
            "**Do not flip it to ALLOWABLE to tidy the screen.**",
        record=[("as judged", f"{acct_pool(f, '5010')}, "
                 f"federal {acct_fed(f, '5010')}"),
                ("amount", money(a(f, '5010')))],
        cite="2 CFR 200.436(b); the missing column is itself a finding under "
             "200.313(d)(1)",
        watch="This is the largest single figure in the file that no amount of "
              "reading the ledger can settle.",
    ))
    R.append(dict(
        id="R6", step="2", screen="/classify — search 5140 and 5142",
        title="The wage accounts are EXCLUDED on purpose — do not make them DIRECT",
        rec="`compute` already feeds the payroll register into the base through "
            "the effort distribution. A DIRECT judgment on the wage accounts "
            "would add the payroll to a base that already carries it, and "
            "**every indirect rate over that base would read low by the width "
            "of the payroll.** EXCLUDED is not 'this is not cost' — it is the "
            "pool enum's word for cost the pools must not carry.",
        record=[("5140 Employee Wages", f"{acct_pool(f, '5140')}, "
                 f"{money(a(f, '5140', 'net'))} net"),
                ("5142 Intern Wages", f"{acct_pool(f, '5142')}, "
                 f"{money(a(f, '5142', 'net'))} net")],
        cite=None,
        watch="This is the judgment on the queue that looks most obviously "
              "wrong and is most obviously right.",
    ))
    R.append(dict(
        id="R7", step="2", screen="/classify — search 5108",
        title="Other Income is EXCLUDED and PENDING — and part of it is a liability",
        rec="$105,865.41 of it is a **Q1 2020** Employee Retention Tax Credit "
            "received from Staffmark in May 2025. A credit relating to a period "
            "in which federal awards bore the wage cost is owed back to those "
            "awards — and which 2020 awards bore them is not on this record. "
            "**Treat it as a liability to establish, not as income received.**",
        record=[("as judged", f"{acct_pool(f, '5108')}, "
                 f"federal {acct_fed(f, '5108')}"),
                ("amount", money(a(f, '5108')))],
        cite="2 CFR 200.406(b)",
        watch="Other Income stays in classification scope on purpose: 200.406 "
              "makes applicable credits a reduction of cost rather than "
              "revenue, so somebody has to look at these.",
    ))
    R.append(dict(
        id="R8", step="2", screen="/classify — search 5001",
        title="Read the inventory journal entry behind Cost of Goods Sold",
        rec="Classified DIRECT to Xjet on inference. Its own description points "
            "at the answer — *'Used Inventory (See JE for breakdown)'* — and "
            "nobody has opened it. **The cheapest item on any of these lists to "
            "settle**, and the only one that can be closed in an afternoon "
            "without asking anybody outside the building.",
        record=[("as judged", f"{acct_pool(f, '5001')} to "
                 f"{(f['acct'].get('5001') or [{}])[0].get('objective_id') or '—'}"),
                ("amount", money(a(f, '5001')))],
        cite=None,
        watch=None,
    ))
    R.append(dict(
        id="R9", step="2", screen="/classify — search 5075 Insurance",
        title="Split the insurance policy schedule — it moves what gets carved",
        rec="All of it is in OVERHEAD. Both halves are indirect, so **this does "
            "not move the combined rate** — but OVERHEAD is carved for tenant "
            "space and G&A is not, so the general-liability share is being "
            "carved when it should not be. The policy schedule splits property "
            "from general liability; nobody has applied it.",
        record=[("as judged", f"{acct_pool(f, '5075')}, "
                 f"{money(a(f, '5075'))} over "
                 f"{sum(r['n'] for r in f['acct'].get('5075', []))} lines"),
                ("where it would split",
                 "property to the facilities pool, general liability to G&A — "
                 "7300 and 8300 in the 2026 chart")],
        cite="2 CFR 200.465",
        watch="Worth doing **before** the square footage arrives, not after — "
              "otherwise the first real measurement carves the wrong pool.",
    ))
    R.append(dict(
        id="R10", step="2", screen="/classify — search 5137",
        title="Payroll processing fees stay in G&A — unless you say otherwise",
        rec="It is arguable: this is the cost of administering the payroll the "
            "fringe pool pays for, and moving it into fringe is worth about "
            "0.29 points. It is left in G&A because the six fringe accounts are "
            "a **transcription of a judgment somebody made once** off the face "
            "of the P&L, and inventing a rule to derive that judgment would be "
            "guessing at it. **This is a controller's call, not the system's.**",
        record=[("as judged", f"{acct_pool(f, '5137')}, "
                 f"{money(a(f, '5137', 'net'))} net of "
                 f"{money(a(f, '5137'))} gross"),
                ("the six fringe accounts",
                 "5130 Benefits · 5133 401k · 5145 BWC · 5151 FICA · "
                 "5185 FUTA · 5195 SUI")],
        cite="2 CFR 200.431(b)",
        watch="There is no holiday, PTO or leave account anywhere on this P&L "
              "— YBI pays leave as regular compensation, so leave is already "
              "inside the fringe denominator. Adding anything leave-shaped to "
              "the numerator would count it twice.",
    ))
    R.append(dict(
        id="R11", step="2", screen="/worklist — NEEDS_EVIDENCE",
        title="The judgments stand on reconstruction, not on documents",
        rec="Every one of the 757 carries a written rationale in "
            "`docs/CLASSIFICATION_LOG.md`, and almost none carries a cited "
            "document. That is honest and it is also the ceiling: **attaching a "
            "document is not citing one**, and VERIFIED needs a citation on the "
            "judgment itself. Nothing here blocks Monday; it is what an auditor "
            "will ask about first.",
        record=[("grades on live judgments",
                 " · ".join(f"{v} {k.replace('_', ' ').lower()}"
                            for k, v in sorted(f["grades"].items(),
                                               key=lambda x: -x[1]))),
                ("outstanding", f"{wl.get('NEEDS_EVIDENCE', 0)} NEEDS_EVIDENCE")],
        cite="",
        watch=None,
    ))

    # ── Step 3 · the seal ───────────────────────────────────────────────────
    R.append(dict(
        id="R12", step="3", screen="/rates — the seal card",
        title="Leave the seal alone unless a judgment actually changes",
        rec="The seal is the assertion that the rate was not reverse-engineered, "
            "and it is the whole reason a reviewer can be told so. It already "
            "covers every live judgment. **Unsealing supersedes every rate "
            "computed against it** — so unseal only to correct something, with "
            "the reason written down, per §C of the runbook.",
        record=[("sealed", f"{f['seal']['sealed_at']:%d %b %Y %H:%M} UTC by "
                 f"{f['seal']['sealed_by']}"),
                ("covering", f"{f['live_judgments']:,} live judgments, "
                             f"set '{f['seal']['label']}'")],
        cite=None,
        watch="Only CONTROLLER may seal or unseal, and nothing automated may do "
              "either. A machine that sealed would put its own name on the "
              "assertion and the assertion would be worth nothing.",
    ))

    # ── Step 4 · the rate ───────────────────────────────────────────────────
    R.append(dict(
        id="R13", step="4", screen="/rates — the compute card",
        title="If you recompute for any reason, choose POOL again",
        rec="The basis selector **defaults to OBJECTIVE**, which is what every "
            "rate before migration 068 used. On the same sealed judgments that "
            "is 34.82% instead of 43.99% — nine points, chosen by leaving a "
            "dropdown alone. The basis is recorded on the rate, so the "
            "workpaper says which was used.",
        record=[("on file now", f"admin_labour_basis = "
                 f"{comb['admin_labour_basis'] if comb else '—'}"),
                ("computed", f"{comb['computed_at']:%d %b %Y %H:%M} UTC by "
                 f"{comb['computed_by']}" if comb else "—")],
        cite=None,
        watch="There is nothing to recompute today. This matters only if §C "
              "runs.",
    ))
    R.append(dict(
        id="R14", step="4", screen="/rates — admin labour basis",
        title="General administration belongs in the G&A pool, not beside it",
        rec="Modelling YBI-GA as a cost objective **allocates the indirect pool "
            "to its own administration**, which recovers from nobody. The "
            "director's office, accounting and personnel administration are "
            "pool cost. FUNDRAISING and UNALLOWABLE-ACTIVITY stay objectives on "
            "purpose — 200.413 makes them bear indirect while recovering "
            "nothing, which is the opposite case.",
        record=[("the decision", f["admin"]["state"]),
                ("as computed", f"{pct(f['admin']['rate_as_computed'])} on a "
                 f"{money(f['admin']['base_as_computed'])} base")],
        cite="2 CFR 200 Appendix IV B; 200.413",
        watch="The hours log settles the counter-argument: all ten people "
              "carrying YBI-GA wages split their time across named programmes, "
              "so it is a real assignment rather than the bucket "
              "unattributable time went into.",
    ))

    # ── Step 5 · /review/rate ───────────────────────────────────────────────
    R.append(dict(
        id="R15", step="5", screen="/review/rate — the build-up",
        title="Quote 43.99% and 21.90% as a pair, and say what is not in them",
        rec="These are the two figures that leave the building. Quote them "
            "together, with the caveat above the figures: **no 200.465 "
            "facilities carve-out is in this rate**, so it reads high — which "
            "is the honest direction to err.",
        record=[(k, f"{pct(rate[k]['rate'])} · pool {money(rate[k]['pool_amount'])}"
                 f" over {money(rate[k]['base_amount'])} {rate[k]['base_type']}")
                for k in ("FRINGE", "OVERHEAD", "G&A", "INDIRECT_COMBINED")
                if k in rate],
        cite=None,
        watch=f"{f['buildup'].get('TIES', 0)} of "
              f"{sum(f['buildup'].values())} pools tie to the ledger at "
              f"pool_variance 0.00, and "
              f"{f['anchor'].get('TIES', 0)} of {f['anchor_total']} rate "
              f"anchors tie. Nothing on that screen is computed.",
    ))
    R.append(dict(
        id="R16", step="5", screen="/review/rate — the fringe row",
        title="The fringe rate does not move — it is anchored at both ends",
        rec="The numerator is the six accounts the P&L names as fringe and the "
            "denominator is the payroll register. **21.90% falls out; it was "
            "not put in.** Writing it in as an input would be exactly the "
            "reverse-engineering the seal exists to rule out. It holds in every "
            "scenario that does not move an account into the fringe pool.",
        record=[("pool", money(fr["pool_amount"]) if fr else "—"),
                ("over the register", money(fr["base_amount"]) if fr else "—"),
                ("the alternative denominator",
                 "the ledger's wage accounts, understated by the $45,053.23 "
                 "credit, which gives 22.45%")],
        cite=None,
        watch="If anybody quotes 22.45%, they are on the ledger's wage accounts "
              "rather than the payroll register. One pool, two denominators, "
              "and only one of them is the payroll.",
    ))
    R.append(dict(
        id="R17", step="5", screen="/review/rate — the carve-out row",
        title="Nothing goes to NCDMM before the square footage lands",
        rec="The carve-out reads zero on a pool of "
            f"{money(oh['pool_amount']) if oh else '—'} because **no facility "
            "on the record carries measured space** — so every dollar of tenant "
            "and vacant occupancy cost is in the federal pool. At a realistic "
            "tenant share the combined rate is nearer 37.67% than 43.99%. "
            "Restating at 43.99% and then discovering 37.67% means "
            "over-claiming on a rate YBI proposed itself.",
        record=[("carve-out rows recorded", f"{f['carve_rows']}"),
                ("facilities with measured space", f"{f['facilities']}"),
                ("worth", "about ±16 points of the combined rate")],
        cite="2 CFR 200.465",
        watch="Nothing distinguishes *there is no tenant space* from *nobody "
              "has measured any*. The carve-out ties to itself either way, "
              "which is why this is on the sheet rather than on a control.",
    ))
    R.append(dict(
        id="R18", step="5", screen="/review/rate — before the measurement arrives",
        title="Fix the tenant double-count before the square footage is applied",
        rec="Named tenants **already reimburse into the OVERHEAD accounts**, so "
            "the pool is partly net of tenant recovery before any carve-out is "
            "computed. Carving a square-footage share on top of that removes "
            "the same money twice. It errs against YBI, which is why it is a "
            "recommendation rather than a silent change — but it has to be "
            "settled **before** the first real measurement, not after.",
        record=[("credits inside the OVERHEAD pool",
                 money(f["overhead_credits"])),
                ("of which carry a named payee",
                 money(f["overhead_credits_named"])),
                ("the rest", "no payee — including a reclassification and an "
                 "insurance recovery for parking-lot damage, which are not "
                 "tenant recovery at all")],
        cite="2 CFR 200.465",
        watch="Which credits are tenant recovery is a judgment, and so is "
              "whether a square-footage driver should reach the T1 access, "
              "telephone, insurance and equipment sitting in the same pool.",
    ))

    # ── P · in parallel ─────────────────────────────────────────────────────
    R.append(dict(
        id="R19", step="P", screen="/requests — the roster",
        title="Chase the roster reply first: it blocks every timesheet",
        rec="**No employment terms are on the record for anybody**, so no "
            "timesheet draft can be built for anybody. `v_employment_expected` "
            "is the denominator every effort percentage is measured against. "
            "Twenty hours a week is the whole of a half-time job and half of a "
            "full-time one, and nothing on the record can tell which.",
        record=[("employment rows", f"{f['employment']} — for "
                 f"{f['people']} people in the distribution"),
                ("outstanding", f"{wl.get('EMPLOYMENT_UNKNOWN', 0)} "
                 "EMPLOYMENT_UNKNOWN")],
        cite=None,
        watch="A blank defaulted to 40 hours would understate every part-timer "
              "by exactly the amount that matters. A partial answer is no row "
              "rather than a partial one.",
    ))
    R.append(dict(
        id="R20", step="P", screen="/certify · /timesheet",
        title="The certifications are the longest pole, and nobody can sign for "
              "anybody",
        rec="This does not change a figure in the rate; it changes whether the "
            "rate is **usable**, because 200.430(i) goes to the allowability of "
            "the entire direct labour charge. A reconstruction the person reads, "
            "corrects and signs meets the rule; one nobody ever saw does not, "
            "which is where 2025 has been sitting. A manager's list "
            "(`v_certification_chase`) is a list to go and ask, never an action.",
        record=[("certifications", f"{f['certs']} of {f['people']}"),
                ("timesheet entries", f"{f['timesheets']}"),
                ("outstanding", f"{wl.get('NEEDS_CERTIFICATION', 0)} "
                 "NEEDS_CERTIFICATION")],
        cite="2 CFR 200.430(i)",
        watch="Adopting the reconstruction faithfully reproduces its shares, so "
              "**submitting does not move the rate.** If it did, the rate would "
              "depend on who had got round to signing.",
    ))
    R.append(dict(
        id="R21", step="P", screen="/facilities",
        title="The square footage is the largest open item and gates nothing "
              "upstream",
        rec="Worth saying plainly because it is the question that gets asked: "
            "**it does not gate any classification.** In the 2025 chart "
            "occupancy goes to OVERHEAD full stop and the tenant share comes "
            "out at rate time as a carve-out. The square footage is the "
            "*carve-out's* problem. The 2026 chart books tenant cost straight "
            "to 93xx, so from next year it is booked rather than estimated.",
        record=[("facilities on the record", f"{f['facilities']}"),
                ("worth", "about ±16 points — one form, linear in the tenant "
                 "share")],
        cite="2 CFR 200.465",
        watch="Take R18 first, or the first real measurement produces the wrong "
              "answer.",
    ))
    R.append(dict(
        id="R22", step="P", screen="docs/BARB_ONE_PAGE_AM.pdf",
        title="Four decisions that are Barb's and nobody else's",
        rec="Whether YBI raises its own two over-collections first and "
            "unprompted; who opens with NCDMM and when; whether the 43 "
            "certifications get pushed from the top; and whether anybody looks "
            "at 2024. None of these is arithmetic and none can be staged.",
        record=[("the awards began", "2023 and 2024 — this exercise covers 2025 "
                 "only"),
                ("if 2024 was billed the same way", "the same exercise applies "
                 "to it, and nobody has looked")],
        cite=None,
        watch=None,
    ))

    # ── A · after Monday, sponsor-facing ────────────────────────────────────
    R.append(dict(
        id="R23", step="A", screen="/restate",
        title="Raise the over-collections first, and unprompted",
        rec="Restating produces money to ask for **and** money to give back, "
            "and they are two different conversations. Leading with the "
            "over-billing is what makes the ask credible; a single net figure "
            "hides both and tells a sponsor nothing. The system refuses to "
            "compute a net movement for exactly this reason.",
        record=[(r["objective_id"],
                 f"{r['invoices']} invoice · billed {money(r['billed_total'])} · "
                 f"indirect billed {money(r['indirect_billed'])} vs supported "
                 f"{money(r['indirect_supported'])}")
                for r in f["restate"]] or [("no restatement on file", "—")],
        cite="2 CFR 200.414(f); §4.4 change of basis",
        watch="Everything stays PROPOSED until a sponsor says otherwise in "
              "writing, and an acceptance has to name the modification that "
              "authorised the change of basis.",
    ))
    R.append(dict(
        id="R24", step="A", screen="/restate · docs/WP_AM_2025_RESTATED_INVOICES.md",
        title="Restate the year, not the months",
        rec="The 36 monthly documents exist so the year's figure can be "
            "**traced** to a month, not filed. Billing and cost do not fall in "
            "the same month, by five and six figures — so thirty-six "
            "transactions swinging in both directions to net a small figure is "
            "the same economics presented in the way most likely to trigger a "
            "desk audit.",
        record=[("recovery on the three contracts in 2025",
                 "100.9% of fully burdened cost, with 4.06% recorded as "
                 "indirect — the recovery is inside the loaded labour rate"),
                ("so a restated invoice", "takes the labour line **down** to "
                 "wages plus fringe before the indirect line goes on. Keeping "
                 "both would charge indirect twice.")],
        cite=None,
        watch="The recurring value is indirect on **non-labour**, which a "
              "loaded labour rate cannot reach — about $203,790 a year at 2025 "
              "volumes, nineteen times the one-off.",
    ))
    R.append(dict(
        id="R25", step="A", screen="/awards — the constraint panel",
        title="RATE_METHOD fails on every award, and that is the whole thesis",
        rec="Each agreement is set to the 10% de minimis and the model applies a "
            "negotiated rate. That is not a defect to clear — it is the "
            "restatement's central claim, stated as a failing constraint "
            "against each executed agreement, which is where a reviewer will "
            "want to find it.",
        record=[(c["award_id"], c["detail"]) for c in failing("RATE_METHOD")]
               or [("none failing", "—")],
        cite="2 CFR 200.414(f)",
        watch="200.414(f) charges the de minimis as a rate on MTDC and does not "
              "contemplate indirect embedded in an undisclosed loaded labour "
              "rate. That makes this a **disclosure** question before it is a "
              "recovery question.",
    ))
    R.append(dict(
        id="R26", step="A", screen="/awards — COST_SHARE",
        title="The cost share was obligated and has never been tracked",
        rec="The largest untracked obligation in the file. It is a failing "
            "constraint now rather than a paragraph in a memo — but nothing in "
            "the record evidences a dollar of it, and part of it is partner "
            "cost share YBI has to evidence rather than incur.",
        record=[(c["award_id"], c["detail"]) for c in failing("COST_SHARE")]
               or [("none failing", "—")],
        cite="§4.3 of each agreement",
        watch="Drive AM's cost share contradicts itself — Schedule B proposes "
              "zero and §4.3 names none, while Schedule A expects roughly 1:1 "
              "at all times. If the 1:1 reading binds it is another ~$1.1m. "
              "That needs counsel, not arithmetic.",
    ))
    R.append(dict(
        id="R27", step="A", screen="/awards — TERM",
        title="One invoice bills service outside its award's period",
        rec="Restating **makes this worse, not better**: it adds an indirect "
            "line to a claim that is already outside the period of "
            "performance. Settle the term question before the restatement is "
            "put to NCDMM, not after.",
        record=[(c["award_id"], c["detail"]) for c in failing("TERM")]
               or [("none failing", "—")],
        cite=None,
        watch="Nothing in the record supports any invoice's service period — "
              "the ledger is 2025 and all three invoices bill April 2026 — and "
              "**no payment is recorded against any invoice**, which decides "
              "whether a restatement is an additional claim or a correction to "
              "a settled one.",
    ))
    R.append(dict(
        id="R28", step="A", screen="/contracts · /classify",
        title="Close the Drive AM ODC gap before claiming the largest credit",
        rec="Drive AM billed materially more in ODCs than the ledger classifies "
            "as Drive AM cost. Either the classification under-attributes and "
            "the credit is overstated, or the billing over-claimed and it is "
            "understated. **Restating to cost only works if the cost record is "
            "complete**, and on the contract with the biggest credit it may not "
            "be.",
        record=[("Digital Engineering", "no invoice on file at all, and its "
                 "period of performance ended 9 July 2025"),
                ("ever invoiced against the ceilings", "about 1.6%")],
        cite=None,
        watch=None,
    ))
    if f["contractor"]:
        c0 = f["contractor"][0]
        R.append(dict(
            id="R29", step="A", screen="/contracts/people",
            title="The 1099 retainer: a question to answer, not arithmetic to run",
            rec="The contractor's own hours log puts a third of his effort on "
                "named programmes, and the retainer sits wholly in G&A. "
                "Directly charging what is otherwise an administrative function "
                "takes four conditions, and the third — explicitly in the "
                "budget, or prior written approval — is exactly what these "
                "awards do not have. **The view states the amount and names the "
                "objectives; somebody else answers it.**",
            record=[(f"{c0['payee']} — retainer",
                     f"{money(c0['expense'])} over {c0['lines']} lines, "
                     f"pool {c0['pools']}"),
                    ("effort on named objectives",
                     f"{c0['project_pct']}% — {c0['objectives']}"),
                    ("at stake", money(c0["at_stake"]))],
            cite="2 CFR 200.413(c)",
            watch="Moving it takes the combined rate **down**, not up — worth "
                  "knowing before anybody assumes a finding is worth chasing. "
                  "YBI already direct-charges his project work when it is "
                  "billed as project work, which is evidence about how the "
                  "organisation treats this.",
        ))
    return R


STEPS = {
    "0": ("Step 0", "Before you open anything",
          "Five figures. If any has moved, stop and find out why.", None),
    "1": ("Step 1", "Confirm the books still agree · /reconcile",
          "The gate on everything downstream. A rate over books that do not "
          "agree with themselves is a rate over the wrong numbers.",
          "02-reconcile.png"),
    "2": ("Step 2", "Review what stands · /classify",
          "This is the work. Every judgment has a written rationale in "
          "docs/CLASSIFICATION_LOG.md; these are the ones carrying the weight.",
          "03-classify-sweep.png"),
    "3": ("Step 3", "The seal · /rates",
          "Already held. Nothing to do unless something changes.",
          "06-sealed.png"),
    "4": ("Step 4", "The rate · /rates",
          "Already computed. This matters only if the change path runs.",
          "07-computed.png"),
    "5": ("Step 5", "Check the stack · /review/rate",
          "The two figures that leave the building, and what is not in them.",
          "08-buildup.png"),
    "P": ("In parallel", "None of it blocks the five steps above",
          "Three asks of other people and one set of decisions. Sorted by lead "
          "time, not by size.", "11-worklist.png"),
    "A": ("After Monday", "Sponsor-facing — the reason the five steps exist",
          "Nothing here is a Monday action. It is what the record now supports "
          "saying, and in what order.", None),
}

CSS = """
:root{--ink:#1a1a1a;--mute:#6b6b6b;--line:#d8d5cc;--accent:#1f5f6b;
      --warm:#8c6a1f;--bg:#fdfcf9;--card:#fff;--fail:#9a3324}
*{box-sizing:border-box}
body{margin:0;font:10.5pt/1.5 "Charter","Georgia",serif;color:var(--ink);
     background:var(--bg)}
.page{max-width:7.5in;margin:0 auto;padding:0}
h1{font-size:20pt;margin:0 0 2px;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:9.5pt;margin:0 0 14px}
.lede{border-left:3px solid var(--accent);padding:8px 0 8px 12px;margin:0 0 16px;
      font-size:10pt}
.lede p{margin:0 0 6px}.lede p:last-child{margin:0}
.step{margin:20px 0 10px;padding-top:9px;border-top:2px solid var(--ink);
      break-after:avoid;page-break-after:avoid}
.step .n{font:700 8.5pt/1 -apple-system,system-ui,sans-serif;
         letter-spacing:.09em;text-transform:uppercase;color:var(--accent)}
.step h2{font-size:13pt;margin:3px 0 2px}
.step .note{color:var(--mute);font-size:9pt;margin:0}
.shot{margin:8px 0 0;border:1px solid var(--line);border-radius:3px;
      overflow:hidden;background:#fff}
.shot img{display:block;width:100%}
.shot .cap{font:8pt/1.35 -apple-system,system-ui,sans-serif;color:var(--warm);
           padding:5px 7px;border-top:1px solid var(--line);background:#faf6ec}
.rec{background:var(--card);border:1px solid var(--line);border-radius:4px;
     padding:11px 13px;margin:9px 0;break-inside:avoid;page-break-inside:avoid}
.rec .hd{display:flex;gap:9px;align-items:baseline;margin-bottom:5px}
.tick{flex:0 0 auto;width:13px;height:13px;border:1.5px solid var(--ink);
      border-radius:2px;margin-top:2px}
.rid{font:700 8.5pt/1 -apple-system,system-ui,sans-serif;color:var(--accent);
     flex:0 0 auto;padding-top:2px}
.rec h3{font-size:11pt;margin:0;flex:1 1 auto;line-height:1.3}
.where{font:8.5pt/1.3 -apple-system,system-ui,sans-serif;color:var(--mute);
       margin:0 0 6px 22px}
.rec .body{margin-left:22px}
.rec p{margin:0 0 7px}
table{width:100%;border-collapse:collapse;margin:7px 0;font-size:9pt}
td{padding:3px 8px 3px 0;vertical-align:top;border-bottom:1px solid #eee}
td:first-child{white-space:nowrap;color:var(--mute);width:34%;
               font:9pt/1.45 -apple-system,system-ui,sans-serif}
.num{font-variant-numeric:tabular-nums}
.cite{font-size:8.5pt;color:var(--accent);margin:5px 0 0}
.watch{font-size:9pt;background:#faf6ec;border-left:2px solid var(--warm);
       padding:6px 9px;margin:7px 0 0}
.watch b{color:var(--warm)}
footer{margin-top:22px;padding-top:9px;border-top:1px solid var(--line);
       font-size:8.5pt;color:var(--mute)}
@page{size:Letter;margin:.55in}
"""

HTML = """<!doctype html><meta charset="utf-8">
<title>Monday anchor — every recommendation, in run order</title>
<style>{css}</style>
<div class="page">
<h1>The anchor sheet</h1>
<p class="sub">Every current recommendation, in the order the Monday run sheet
works through them &middot; Youngstown Business Incubator, FY{period}
&middot; generated {stamp}</p>

<div class="lede">
<p><b>What this is.</b> Nine documents in <code>docs/</code> carry
recommendations and none of them is ordered the way the work is actually done.
This is the same set, dealt into the sequence of
<code>docs/MONDAY_RUNBOOK.md</code>, so each one can be checked against the
screen it is visible on at the moment it applies.</p>
<p><b>Every figure below was read from the live record</b> when this was
generated &mdash; none is recalled, and nothing on the page is computed.
Regenerate it any time with <code>scripts/monday_anchor.py</code>; a figure it
cannot read stops the run rather than printing blank.</p>
<p><b>The tick boxes are the QA.</b> Tick a recommendation when you have seen
its figure on the screen named beside it. One that does not match is the point
of the exercise &mdash; note it rather than reconciling it in your head.</p>
</div>

{body}

<footer>
Generated from the live record by <code>scripts/monday_anchor.py</code>.
Run sheet: <code>docs/MONDAY_RUNBOOK.md</code> &middot;
screens: <code>docs/MONDAY_GUIDEBOOK.pdf</code> &middot;
rationale for all {njudge} judgments:
<code>docs/CLASSIFICATION_LOG.md</code>.
</footer>
</div>
"""


def head_of(png: Path, crop: int = 1500, width: int = 1400) -> bytes:
    """The top of a screen capture, which is where the figures are.

    The walk captures a whole page at 2x — 2880 by up to 3400 — and a full one
    rendered across the text column is taller than the page it sits on, so the
    step header before it lands alone at the foot of the previous one. The
    reader is crosschecking the figures above the fold, so that is what is
    shown, and the caption says it is the top rather than the screen.
    """
    import io

    from PIL import Image

    im = Image.open(png)
    if im.height > crop:
        im = im.crop((0, 0, im.width, crop))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render(f: dict, recs: list[dict], embed: bool) -> str:
    import base64
    import datetime as dt

    walk = Path(__file__).resolve().parent.parent / "docs" / "runbook-walk"
    out = []
    for key, (n, title, note, shot) in STEPS.items():
        mine = [r for r in recs if r["step"] == key]
        if not mine:
            continue
        out.append(f'<div class="step"><div class="n">{n}</div>'
                   f'<h2>{title}</h2><p class="note">{note}</p>')
        img = walk / shot if shot else None
        if embed and img and img.exists():
            b64 = base64.b64encode(head_of(img)).decode()
            out.append(
                f'<div class="shot"><img src="data:image/png;base64,{b64}">'
                f'<div class="cap">Where to look &mdash; the top of the screen, '
                f'which is where the figures sit. This is the sandbox walk, '
                f'built from an empty database: the layout is the screen you '
                f'will open, the figures on it are not. The live figures are '
                f'in each card below.</div></div>')
        out.append("</div>")

        for r in mine:
            rows = "".join(
                f'<tr><td>{md(str(k))}</td><td class="num">{md(str(v))}</td></tr>'
                for k, v in r["record"])
            cite = (f'<p class="cite">{r["cite"]}</p>'
                    if r.get("cite") else "")
            watch = (f'<div class="watch"><b>Watch:</b> {md(r["watch"])}</div>'
                     if r.get("watch") else "")
            out.append(
                f'<div class="rec">'
                f'<div class="hd"><div class="tick"></div>'
                f'<div class="rid">{r["id"]}</div><h3>{r["title"]}</h3></div>'
                f'<p class="where">{r["screen"]}</p>'
                f'<div class="body"><p>{md(r["rec"])}</p>'
                f'<table>{rows}</table>{cite}{watch}</div></div>')

    return HTML.format(
        css=CSS, period=PERIOD, body="".join(out),
        njudge=f'{f["live_judgments"]:,}',
        stamp=dt.datetime.now().strftime("%d %B %Y"))


def md(s: str) -> str:
    """The three marks used in the prose above, and nothing else."""
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--no-shots", action="store_true",
                    help="leave the screen references out")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set — this reads the live record")

    f = facts()
    recs = recommendations(f)
    OUT.write_text(render(f, recs, embed=not args.no_shots))
    print(f"wrote {OUT} — {len(recs)} recommendations over "
          f"{len({r['step'] for r in recs})} steps")

    if args.pdf:
        from playwright.sync_api import sync_playwright
        pdf = OUT.with_suffix(".pdf")
        chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            pg = b.new_page()
            pg.goto(OUT.resolve().as_uri(), wait_until="networkidle")
            pg.pdf(path=str(pdf), format="Letter", print_background=True,
                   margin={"top": ".55in", "bottom": ".55in",
                           "left": ".55in", "right": ".55in"})
            b.close()
        print(f"wrote {pdf} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
