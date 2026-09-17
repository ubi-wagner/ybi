#!/usr/bin/env python3
"""Is everybody ready to do their part, and what is waiting for a human?

Run it before Monday. It answers one question per section — *can this person
do their job today, and if not, what is in the way* — and it **writes
nothing at all**. Not a classification, not an adoption, not a seal.

That is the design, not a limitation. Everything this report describes is a
judgment with somebody's name on it:

- a **classification** is the controller's, and the seal exists so a reviewer
  can be told the rate was not reverse-engineered. A script that applied 757
  recommendations and sealed them would put the machine's name on the seal
  and throw the guarantee away.
- a **timesheet** is the employee's. 2 CFR 200.430(i) wants the record of the
  person whose effort it was, so adopting the reconstruction is theirs to do
  and the draft is offered as a convenience they may decline.
- a **certification** is a signature. Nothing may produce one but the person.
- a **rate** is arithmetic and could be computed — and is deliberately not,
  because computing before the books reconcile is a rate over the wrong
  numbers, and reconciliation is the Monday gate.

So the exit code says whether the *machinery* is sound, never whether the
*work* is finished. Outstanding work is the normal state of an engagement in
progress and a report that failed on it would be one nobody reads twice.

    2   something is structurally broken — a view missing, a control that
        cannot be evaluated where it should be, a rate that does not tie
    0   the machinery is sound; the summary says what is waiting for a human

`--json` prints the same findings as data, for a check that wants to assert
on them rather than read them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, one, query

PERIOD = "2025"

BOLD, DIM, OK, WARN, BAD, OFF = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")


class Report:
    """Findings, and the one distinction that matters.

    `blocked` is the machinery being wrong and fails the run. `waiting` is a
    human not having acted yet, which is not a fault and must never be
    reported as one — the `FACILITY_UNPARTITIONED` lesson applied to a
    status report: an item nobody can clear by doing the work teaches the
    reader that the list is wrong.
    """

    def __init__(self) -> None:
        self.blocked: list[str] = []
        self.waiting: list[str] = []
        self.notes: list[dict] = []

    def head(self, title: str) -> None:
        print(f"\n{BOLD}{title}{OFF}")

    def line(self, state: str, label: str, detail: str = "") -> None:
        colour = {"ok": OK, "waiting": WARN, "blocked": BAD, "note": DIM}[state]
        mark = {"ok": "ok", "waiting": "--", "blocked": "!!", "note": "  "}[state]
        print(f"  {colour}{mark}{OFF}  {label:<42} {DIM}{detail}{OFF}")
        self.notes.append({"state": state, "label": label, "detail": detail})
        if state == "blocked":
            self.blocked.append(f"{label}: {detail}")
        elif state == "waiting":
            self.waiting.append(f"{label}: {detail}")


def money(x) -> str:
    return f"{Decimal(str(x or 0)):,.2f}"


# ── the baseline ──────────────────────────────────────────────────────

def baseline(r: Report) -> None:
    r.head("The baseline")
    lines = one("SELECT count(*) n, count(DISTINCT account) accounts, "
                "sum(abs(amount)) moved FROM ledger_line WHERE period = %s",
                (PERIOD,))
    if not lines or not lines["n"]:
        r.line("blocked", "the ledger", "no lines — run scripts/seed.sh first")
        return
    r.line("ok", "the ledger",
           f"{lines['n']:,} lines over {lines['accounts']} accounts")

    for label, sql in [
        ("the payroll distribution",
         "SELECT count(*) n, count(DISTINCT employee_key) k FROM labor_allocation "
         "WHERE period = %s"),
        ("the hours log", "SELECT count(*) n, count(DISTINCT employee_key) k "
                          "FROM labor_month WHERE period = %s"),
        ("the awards", "SELECT count(*) n, count(*) k FROM award"),
        ("contract provisions", "SELECT count(*) n, count(DISTINCT award_id) k "
                                "FROM award_term"),
        ("documents on file", "SELECT count(*) n, count(*) k FROM evidence"),
    ]:
        row = one(sql, (PERIOD,) if "%s" in sql else ())
        n = row["n"] if row else 0
        r.line("ok" if n else "blocked", label,
               f"{n:,} rows" if n else "empty — the foundation is not in")


# ── the Monday gate ───────────────────────────────────────────────────

def reconciliation(r: Report) -> None:
    """The eleven points, read rather than run.

    `POST /api/rates/compute` returns 409 while any of these is open, so this
    is the gate everything downstream waits behind. **A control that cannot
    be evaluated has not passed** — `NO DATA` is counted apart from `TIES`,
    because an empty period compares zero against zero and looks green.
    """
    r.head("The eleven control points — Monday's gate")
    rows = query("SELECT seq, control, state, variance, note "
                 "FROM v_statement_reconciliation WHERE period = %s "
                 "ORDER BY seq", (PERIOD,))
    if not rows:
        r.line("blocked", "v_statement_reconciliation", "returned nothing")
        return
    ties = [x for x in rows if x["state"] == "TIES"]
    open_ = [x for x in rows if x["state"] == "OPEN"]
    nodata = [x for x in rows if x["state"] not in ("TIES", "OPEN")]
    for x in open_:
        r.line("blocked", x["control"], f"OPEN by {money(x['variance'])}")
    for x in nodata:
        r.line("blocked", x["control"],
               f"{x['state']} — cannot be evaluated, so it has not passed")
    r.line("ok" if not (open_ or nodata) else "note",
           f"{len(ties)} of {len(rows)} tie",
           "a rate may be computed" if not (open_ or nodata)
           else "compute is refused while any is open")


# ── what the controller team has to review ────────────────────────────

def classification(r: Report) -> None:
    r.head("The classification — for the controller to review, accept and seal")
    cov = one("SELECT * FROM v_classification_coverage WHERE period = %s",
              (PERIOD,))
    if not cov:
        r.line("blocked", "v_classification_coverage", "returned nothing")
        return
    r.line("ok", "coverage",
           f"{cov['pct_dollars_covered']}% of {money(cov['scope_dollars'])} "
           f"— {cov['groups_decided']} of {cov['groups_total']} groups")
    if Decimal(str(cov["unclassified"])) > 0:
        r.line("waiting", "still to judge",
               f"{money(cov['unclassified'])} across "
               f"{cov['groups_total'] - cov['groups_decided']} groups")

    log = Path("docs/CLASSIFICATION_LOG.md")
    r.line("ok" if log.exists() else "waiting", "the recommendation log",
           f"{log} — a reasoned treatment per group, proposing nothing to the "
           f"record" if log.exists()
           else "not written — run scripts/classification_log.py --write")

    st = one("SELECT label, seal_hash IS NOT NULL AS sealed, sealed_at, "
             "       sealed_by, unsealed_reason "
             "FROM decision_set WHERE period = %s "
             "ORDER BY sealed_at DESC NULLS FIRST LIMIT 1", (PERIOD,))
    if not st:
        r.line("waiting", "the decision set", "none open yet")
    elif st["sealed"]:
        r.line("ok", "sealed", f"by {st['sealed_by']} at {st['sealed_at']:%Y-%m-%d %H:%M}")
    else:
        r.line("waiting", "the seal",
               "open — sealing is the controller's judgment and nothing here "
               "may make it")


# ── whether forty-three people can do their part ──────────────────────

def certification(r: Report) -> None:
    """Who can adopt and sign today, and who is blocked on what.

    The draft is a **convenience the person may decline**, so nobody is
    reported as failing for not having taken it. What is reported is the one
    thing that stops them even having the choice: no employment terms on the
    record means no denominator, and no draft can be built.
    """
    r.head("The forty-three — their own timesheets, at their own pace")
    people = query(
        "SELECT c.employee_key, c.employee_name, c.certified, c.reconstructed, "
        "       e.expected_hours, m.months "
        "FROM v_certification_status c "
        "LEFT JOIN v_employment_expected e "
        "       ON e.period = c.period AND e.employee_key = c.employee_key "
        "LEFT JOIN (SELECT employee_key, count(DISTINCT month_start) months "
        "           FROM labor_month WHERE period = %s GROUP BY 1) m "
        "       ON m.employee_key = c.employee_key "
        "WHERE c.period = %s ORDER BY c.employee_key", (PERIOD, PERIOD))
    if not people:
        r.line("blocked", "v_certification_status", "returned nothing")
        return

    signed = [p for p in people if p["certified"]]
    no_terms = [p for p in people if not p["expected_hours"]]
    monthly = [p for p in people if (p["months"] or 0) > 1]

    r.line("ok", "people in the distribution", f"{len(people)}")
    r.line("ok" if not no_terms else "waiting", "can be offered a draft",
           f"{len(people) - len(no_terms)} of {len(people)}"
           + (f" — {len(no_terms)} have no employment terms on the record, so "
              f"there is no denominator to divide and no draft can be built. "
              f"That is the roster reply, not a fault here."
              if no_terms else ""))
    r.line("note", "with a month-by-month hours log",
           f"{len(monthly)} — the rest get the year's distribution, and the "
           f"draft says which it is showing")
    r.line("ok" if len(signed) == len(people) else "waiting", "certified",
           f"{len(signed)} of {len(people)} — theirs to sign, and nobody "
           f"signs for them. A page they have already signed is filed on "
           f"their behalf from Time · File signed, which records their "
           f"signature and your filing as two different facts.")


# ── the rate stack ────────────────────────────────────────────────────

def rate_stack(r: Report) -> None:
    r.head("The rate stack")
    rows = query("SELECT kind, rate, pool_amount, base_amount, pool_variance, "
                 "       ties, pool_state, admin_labour_basis "
                 "FROM v_rate_buildup WHERE period = %s AND status = 'PROPOSED' "
                 "ORDER BY kind", (PERIOD,))
    if not rows:
        r.line("waiting", "no rate on file",
               "expected before a seal — compute is the step after Monday's "
               "reconciliation")
        return
    for x in rows:
        pct = Decimal(str(x["rate"])) * 100
        state = "ok" if x["ties"] else ("note" if x["pool_state"] == "NO DATA"
                                        else "blocked")
        r.line(state, x["kind"],
               f"{pct:.2f}%  pool {money(x['pool_amount'])} over "
               f"{money(x['base_amount'])}"
               + ("" if x["ties"]
                  else f"  [{x['pool_state']}, variance "
                       f"{money(x['pool_variance'])}]"))
    r.line("note", "administrative labour",
           f"{rows[0]['admin_labour_basis']} — a recorded choice on the rate")

    for a in query("SELECT control, state, variance, note FROM v_rate_anchor "
                   "WHERE period = %s ORDER BY seq", (PERIOD,)):
        r.line("ok" if a["state"] == "TIES"
               else ("note" if a["state"] == "NO DATA" else "blocked"),
               a["control"],
               a["state"] + ("" if a["state"] == "TIES"
                             else f" — {money(a['variance'])}"))

    # `facility`, not `building` — the first draft of this line recalled the
    # name and the report failed on the one adjustment it exists to watch.
    # Read the schema, never recall it.
    carve = one("SELECT count(*) n FROM carve_out WHERE period = %s", (PERIOD,))
    measured = one("SELECT count(*) n FROM v_space_unit_control "
                   "WHERE period = %s AND ties", (PERIOD,))
    facilities = one("SELECT count(*) n FROM facility")
    if not (facilities and facilities["n"]):
        r.line("waiting", "200.465 facilities carve-out",
               "no facility on the record, so it has never been evaluated — "
               "every dollar of tenant and vacant occupancy cost is in the "
               "federal pool and the rate reads high, which is the honest "
               "direction to err")
    elif not (measured and measured["n"]):
        r.line("waiting", "200.465 facilities carve-out",
               f"{facilities['n']} facilities on file, none with space units "
               f"that account for them in full — Kelly's measurement is what "
               f"closes it")
    elif not (carve and carve["n"]):
        r.line("blocked", "200.465 facilities carve-out",
               "space is measured and accounted for, and no carve-out was "
               "written — the largest adjustment in the rate model, absent")
    else:
        r.line("ok", "200.465 facilities carve-out", f"{carve['n']} recorded")


# ── what is on somebody's list ────────────────────────────────────────

def worklist(r: Report) -> None:
    r.head("Outstanding, by whose job it is")
    for row in query(
            "SELECT owner_portfolio, count(*) n, "
            "       count(*) FILTER (WHERE severity = 'BLOCKING') blocking "
            "FROM v_worklist_owned WHERE period = %s OR period IS NULL "
            "GROUP BY 1 ORDER BY 2 DESC", (PERIOD,)):
        r.line("note", row["owner_portfolio"] or "(unrouted)",
               f"{row['n']:,} open"
               + (f", {row['blocking']} blocking" if row["blocking"] else ""))


def requests(r: Report) -> None:
    """What has been asked for from outside, and what has come back.

    A reply that is filed and not accepted is the easiest thing in this system
    to lose: it is on the record, it changes nothing, and no control reads it
    because it is not in a register yet. Heidi's floor plan sat in exactly
    that state, and it is the single largest adjustment in the rate model.
    """
    r.head("Asked for from outside")
    rows = query("""SELECT form, state::text AS state, received_from,
                           received_at, rows_accepted, sent_to,
                           form_version
                      FROM information_request
                     WHERE period = %s ORDER BY issued_at""", (PERIOD,))
    if not rows:
        r.line("note", "nothing has been asked for",
               "the three things the record cannot infer are the asset "
               "funding source, the square footage and the roster")
        return
    # **The version is part of the name here.** A second pass over the same
    # form is the ordinary case — v2 of the space book asks the tenancy
    # question v1 could not — and two rows reading `SPACE_INVENTORY` in
    # different states, with nothing saying which is which, is two true
    # figures about one thing on one page.
    for x in rows:
        who = f"{x['form']} v{x['form_version']}"
        if x["state"] == "ACCEPTED":
            r.line("ok", who,
                   f"accepted — {x['rows_accepted'] or 0} row(s) written")
        elif x["state"] == "RECEIVED":
            r.line("waiting", who,
                   f"came back from {x['received_from'] or 'somebody'} and is "
                   f"**not accepted** — it is filed as evidence and no "
                   f"register has it yet, so it moves no figure until "
                   f"somebody presses Accept on /requests")
        else:
            r.line("waiting", who,
                   f"{x['state'].lower()} — sent to {x['sent_to'] or 'nobody named'}")


def determinations(r: Report) -> None:
    """200.331, per party over the 200.1 cap."""
    r.head("Contractor or subrecipient — 2 CFR 200.331")
    rows = query("""SELECT payee, objective_id, amount, determination, at_stake,
                           state FROM v_subaward_exposure
                     WHERE period = %s ORDER BY at_stake DESC""", (PERIOD,))
    if not rows:
        r.line("note", "no party clears the 200.1 cap", "nothing to determine")
        return
    open_ = [x for x in rows if x["determination"] == "UNDETERMINED"]
    stake = sum((Decimal(str(x["at_stake"])) for x in open_), Decimal(0))
    for x in rows:
        if x["determination"] == "UNDETERMINED":
            r.line("waiting", (x["payee"] or "(no payee on the ledger line)")[:40],
                   f"{money(x['amount'])} on {x['objective_id']} — "
                   f"{money(x['at_stake'])} of MTDC turns on it")
        else:
            r.line("ok", (x["payee"] or "(no payee)")[:40],
                   f"{x['determination'].lower()}")
    if open_:
        r.line("waiting", f"{len(open_)} undetermined",
               f"{money(stake)} of MTDC, and UNDETERMINED is NO DATA rather "
               f"than a pass. The substance of the relationship governs, so "
               f"it is read off an agreement and not off an invoice category.")


def rate_decisions(r: Report) -> None:
    """What is waiting on the controller before a rate can leave the building."""
    r.head("On the controller's desk, before anything goes to a sponsor")

    pend = query("""SELECT d.pool, round(sum(l.amount), 2) AS amt
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND d.federal = 'PENDING'
                       AND d.pool IN ('OVERHEAD', 'G&A', 'FRINGE')
                     GROUP BY 1""")
    for x in pend:
        r.line("waiting", f"{x['pool']} at PENDING",
               f"{money(x['amt'])} — the federal treatment is unresolved. The "
               f"fixed-asset register now answers the funding source on every "
               f"asset, which is the document this judgment named as its own "
               f"release condition.")
    if not pend:
        r.line("ok", "federal treatment", "every indirect judgment is resolved")

    # Appendix IV B.2.a asks for an organisation's activities to be
    # segregated, and the same segregation that keeps let occupancy out of the
    # federal overhead pool makes the letting an activity that bears general
    # administration. `cost_objective` has carried a RENTAL row since the
    # master was built; if nothing is on it, the letting is in no base
    # anywhere and the G&A rate is taken over the programmes alone.
    let = one("""SELECT o.objective_id,
                        (SELECT count(*) FROM decision d
                          JOIN decision_set ds ON ds.set_id = d.set_id
                         WHERE d.reversed_at IS NULL AND ds.period = %s
                           AND d.objective_id = o.objective_id) AS judged,
                        (SELECT count(*) FROM allocation a
                          JOIN rate r USING (rate_id)
                         WHERE r.period = %s AND r.status <> 'SUPERSEDED'
                           AND a.objective_id = o.objective_id) AS allocated
                   FROM cost_objective o
                  WHERE o.objective_type = 'RENTAL'""", (PERIOD, PERIOD))
    if let and not let["judged"] and not let["allocated"]:
        r.line("waiting", f"the letting carries nothing ({let['objective_id']})",
               "no cost is classified to it and no indirect is allocated to "
               "it, so the letting bears no share of G&A — which the same "
               "Appendix IV B.2.a segregation that sizes the overhead pool "
               "asks for. See docs/RATE_HEADROOM_2025.md; it is worth points "
               "of rate and it runs against YBI.")
    elif let:
        r.line("ok", f"the letting is an activity ({let['objective_id']})",
               f"{let['judged']} judgment(s), {let['allocated']} allocation(s)")

    cert = one("""SELECT * FROM v_rate_certified
                   WHERE period = %s""", (PERIOD,))
    # A drive's signature is not a signature, and this report exists to say
    # what is outstanding. Reading `certified` alone reported the rate signed
    # over a certificate `drive_the_close.py` had made.
    if cert and cert.get("rehearsal"):
        r.line("waiting", "the rate is not certified",
               "the signature standing on it was made by a drive to prove "
               "the mechanism; no person gave it")
    elif cert and cert["certified"]:
        r.line("ok", "the rate is certified", f"by {cert['certified_by']}")
    else:
        r.line("waiting", "the rate is not certified",
               (cert or {}).get("why_not") or "nobody has signed it")

    for x in query("""SELECT objective_id, status, still_agrees,
                             register_invoices, invoices
                        FROM v_restatement
                       WHERE period = %s AND status <> 'SUPERSEDED'
                       ORDER BY objective_id""", (PERIOD,)):
        if x["still_agrees"] is False:
            r.line("waiting", f"restatement {x['objective_id']}",
                   f"measured {x['invoices']} invoice(s) and the register now "
                   f"holds {x['register_invoices']} — recompute before sending")
        else:
            r.line("note", f"restatement {x['objective_id']}",
                   f"{x['status'].lower()}, and still agrees with the register")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="print the findings as data")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()

    r = Report()
    print(f"{BOLD}Readiness — {PERIOD}{OFF}")
    print(f"{DIM}Read-only. Nothing in this report writes to the record.{OFF}")
    for section in (baseline, reconciliation, classification, certification,
                    rate_stack, requests, determinations, rate_decisions,
                    worklist):
        try:
            section(r)
        except Exception as exc:                       # noqa: BLE001
            r.head(section.__name__)
            r.line("blocked", section.__name__, f"{type(exc).__name__}: {exc}")

    print(f"\n{BOLD}Summary{OFF}")
    if r.blocked:
        print(f"  {BAD}{len(r.blocked)} blocked{OFF} — the machinery, not the work:")
        for x in r.blocked:
            print(f"      {x}")
    else:
        print(f"  {OK}the machinery is sound{OFF}")
    if r.waiting:
        print(f"  {WARN}{len(r.waiting)} waiting on a person{OFF} — "
              f"which is the normal state, not a fault:")
        for x in r.waiting:
            print(f"      {x}")

    if args.json:
        print(json.dumps({"blocked": r.blocked, "waiting": r.waiting,
                          "findings": r.notes}, indent=2))
    return 2 if r.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
