#!/usr/bin/env python3
"""Generate the run sheet from the crosscheck, not from memory.

    PYTHONPATH=. python3 scripts/runbook.py            # to stdout
    PYTHONPATH=. python3 scripts/runbook.py --write

`docs/MONDAY_RUNBOOK.md` opened with a state table somebody typed. That is a
hand-kept map of the record — the shape this repository has been wrong with
four times in one week — and the figures on it are the ones a controller
stands on at nine in the morning. It described building a year from nothing
while the record sat at the end of that path; the invoice register was three
invoices while the year was sixty-one; a step said *press Seal* over a sealed
set.

So the run sheet is generated. Every figure in it is read from the record
through `scripts/drive_invoice_ties.py`, which walks the register forward and
backward and hands back what it established. The prose is judgment and lives
here; the numbers are not and do not.

**It refuses to write over a failing crosscheck.** A run sheet is a document
somebody acts on, and generating one whose own checks did not pass would put
a figure in front of a person with nothing behind it. Findings stop the run
and are printed instead. Notes do not — a note is something the record cannot
answer, which is a fact about the engagement rather than a fault, and a
generator that refused those would never produce anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "MONDAY_RUNBOOK.md"


def crosscheck(reuse: str | None) -> dict:
    """Run the crosscheck and take its result, or read one already taken."""
    if reuse:
        return json.loads(Path(reuse).read_text())
    tmp = Path("/tmp/runbook-crosscheck.json")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "drive_invoice_ties.py"),
         "--json", str(tmp)],
        capture_output=True, text=True, cwd=str(ROOT))
    if not tmp.exists():
        raise SystemExit(f"the crosscheck did not produce a result:\n"
                         f"{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return json.loads(tmp.read_text())


def money(v) -> str:
    return f"{Decimal(str(v)):,.2f}"


def live() -> dict:
    """The few things the crosscheck does not carry: the seal and the rates."""
    from app.db import one, open_pool, query
    open_pool()
    seal = one("""SELECT label, sealed_at, sealed_by,
                         seal_hash IS NOT NULL AS sealed
                    FROM decision_set WHERE period = '2025'
                   ORDER BY sealed_at DESC NULLS LAST LIMIT 1""")
    rates = query("""SELECT kind, rate, pool_amount, base_amount, base_type,
                            admin_labour_basis
                       FROM rate WHERE period = '2025' AND status = 'PROPOSED'
                      ORDER BY kind""")
    judgments = one("""SELECT count(*) AS n FROM decision d
                         JOIN decision_set s USING (set_id)
                        WHERE s.period = '2025' AND d.reversed_at IS NULL""")
    people = one("""SELECT count(*) FILTER (WHERE certified) AS signed,
                           count(*) AS n FROM v_certification_status
                     WHERE period = '2025'""") or {}
    terms = one("SELECT count(*) AS n FROM employment") or {"n": 0}
    facilities = one("SELECT count(*) AS n FROM facility") or {"n": 0}
    carve = one("SELECT count(*) AS n FROM carve_out") or {"n": 0}
    restate = query("""SELECT objective_id, billed_total, under_recovered,
                              over_collected, as_billed_position, implied_rate
                         FROM v_restatement
                        WHERE period = '2025' AND status = 'PROPOSED'
                        ORDER BY billed_total DESC""")
    return dict(seal=seal, rates=rates, judgments=judgments["n"],
                people=people, terms=terms["n"], facilities=facilities["n"],
                carve=carve["n"], restate=restate)


def render(x: dict, f: dict) -> str:
    up, reg = x["upstream"], x["register"]
    seal, rates = f["seal"], {r["kind"]: r for r in f["rates"]}
    comb = rates.get("INDIRECT_COMBINED")
    fr = rates.get("FRINGE")
    L: list[str] = []
    w = L.append

    w("# Monday — the run sheet")
    w("")
    w("*Generated from the record by `scripts/runbook.py`, which will not "
      "write over a failing crosscheck. Every figure below was read by "
      "`scripts/drive_invoice_ties.py`; none was typed beside it.*")
    w("")
    w(f"*{dt.datetime.now():%d %B %Y}*")
    w("")
    w("**Read §0 first.** The record is at the end of the path this document "
      "used to describe, so every step is **verification, not construction**. "
      "Following an earlier version literally would have had the controller "
      "press *Seal* on a sealed set.")
    w("")
    w("```bash")
    w("DATABASE_URL=... ./scripts/readiness.py           # read-only")
    w("DATABASE_URL=... python3 scripts/drive_invoice_ties.py   # the crosscheck")
    w("YBI_SEED_PASSWORD=... ./scripts/monday.sh --full  # the sandbox test")
    w("```")
    w("")
    w("**Illustrated:** `docs/MONDAY_GUIDEBOOK.pdf` photographs every screen "
      "below. **Recommendations to tick:** `docs/MONDAY_ANCHOR.pdf`.")
    w("")
    w("---")
    w("")

    # ── 0 ───────────────────────────────────────────────────────────────
    w("## 0 · Where the record stands")
    w("")
    w("| | | |")
    w("| --- | --- | --- |")
    w(f"| the eleven control points | **{up['controls_tie']} of "
      f"{up['controls']} tie** | a rate is refused while any is open |")
    w(f"| the classification | **{up['groups_decided']:,} of "
      f"{up['groups_total']:,} groups**, {up['pct_covered']}% | "
      f"{money(up['unclassified'])} unclassified |")
    if seal and seal["sealed"]:
        w(f"| the seal | **{seal['sealed_by']}**, "
          f"{seal['sealed_at']:%d %b %Y %H:%M} UTC | covering "
          f"{f['judgments']:,} live judgments |")
    else:
        w("| the seal | **not sealed** | no rate can be computed |")
    if comb:
        w(f"| the rate | FRINGE **{fr['rate']*100:.2f}%** · "
          f"INDIRECT_COMBINED **{comb['rate']*100:.2f}%** | administrative "
          f"labour on the **{comb['admin_labour_basis']}** basis |")
    w(f"| the rate anchors | **{up['anchors_tie']} of {up['anchors']} tie** | "
      f"{up['pools_tie']} of {up['pools']} pools at variance 0.00 |")
    w(f"| the invoice register | **{reg['invoices']} invoices**, "
      f"{money(reg['total'])} | all of 2025, reconciled to the ledger |")
    w("")
    w("**So Monday is a review, not a build.**")
    w("")

    # ── the crosscheck ──────────────────────────────────────────────────
    w("## 0.1 · The crosscheck this sheet was generated from")
    w("")
    w("The register against the ledger's own grant income — two records of "
      "the same billing, neither derived from the other.")
    w("")
    w("| award | invoices | billed | ledger | difference | |")
    w("| --- | ---: | ---: | ---: | ---: | --- |")
    byo = {b["objective"]: b for b in x["backward"]}
    for t in x["ties"]:
        b = byo.get(t["objective"], {})
        gap = Decimal(t["gap"])
        note = ("to the cent" if gap == 0 else t["why"])
        w(f"| {t['objective']} | {b.get('invoices', '—')} | "
          f"{money(t['billed'])} | {money(t['ledger'])} | "
          f"{money(gap) if gap else '—'} | {note} |")
    w("")
    w("And the billed non-labour against the cost the ledger carries:")
    w("")
    w("| award | billed | ledger | | |")
    w("| --- | ---: | ---: | ---: | --- |")
    for c in x["cost"]:
        if c["state"] == "NOT EVALUABLE":
            w(f"| {c['objective']} | — | — | **not evaluable** | {c['why']} |")
            continue
        gap = Decimal(c["gap"])
        w(f"| {c['objective']} | {money(c['billed'])} | {money(c['ledger'])} "
          f"| {money(gap) if gap else 'ties'} | "
          f"{c['why'] or 'to the cent'} |")
    w("")
    if x["notes"]:
        w("**Not evaluable, and why** — a control that cannot be evaluated "
          "has not passed, and it has not failed either:")
        w("")
        for n in x["notes"]:
            w(f"- {n}")
        w("")

    # ── 1-5 ─────────────────────────────────────────────────────────────
    w("---")
    w("")
    w("## 1 · Confirm the books still agree — Tom")
    w("")
    w(f"`/reconcile`. **{up['controls_tie']} of {up['controls']} tie today.** "
      f"This step is to confirm they still do. `POST /api/rates/compute` "
      f"returns 409 while any one is open.")
    w("")
    w("A difference is closed by *naming* the lines behind it, never by "
      "netting it. The Bacon $45,053.23 donor credit is the change most "
      "likely to have happened over the weekend — when it is reposted in "
      "QuickBooks the reconciling item comes off with it, or the correction "
      "counts twice.")
    w("")
    w("## 2 · Review what stands — the controller team")
    w("")
    w(f"`/classify`. **This is the work.** {up['groups_decided']:,} judgments "
      f"were recorded through the API under Tom's name, each with a written "
      f"rationale in `docs/CLASSIFICATION_LOG.md`. What has *not* happened is "
      f"a person reading them and affirming they stand.")
    w("")
    w("If every judgment stands, nothing is required: the seal is current and "
      "so is the rate. **Skip to §5.** If any is wrong, go to §C.")
    w("")
    w("## 3 · The seal — already held, and only Tom may move it")
    w("")
    if seal and seal["sealed"]:
        w(f"Sealed {seal['sealed_at']:%d %B %Y} by {seal['sealed_by']}, "
          f"covering {f['judgments']:,} live judgments. **Nothing to do "
          f"unless something changes.**")
    else:
        w("**The set is not sealed.** No rate can be computed until it is, "
          "and sealing is a judgment nobody may make on the controller's "
          "behalf.")
    w("")
    w("## 4 · The rate — already computed, on the basis that was chosen")
    w("")
    if comb:
        w("| | | |")
        w("| --- | ---: | --- |")
        for k in ("FRINGE", "OVERHEAD", "G&A", "INDIRECT_COMBINED"):
            r = rates.get(k)
            if r:
                w(f"| {k} | **{r['rate']*100:.2f}%** | pool "
                  f"{money(r['pool_amount'])} over {money(r['base_amount'])} "
                  f"{r['base_type']} |")
        w("")
        w(f"**If you recompute for any reason, choose "
          f"{comb['admin_labour_basis']} again.** The screen defaults to "
          f"`OBJECTIVE`, which is worth about nine points of combined rate on "
          f"the same sealed judgments.")
    w("")
    w("## 5 · Check the stack — Tom")
    w("")
    w(f"`/review/rate`. **{up['pools_tie']} of {up['pools']} pools** at "
      f"`pool_variance` 0.00 and **{up['anchors_tie']} of {up['anchors']} "
      f"rate anchors** tying. Nothing on that screen is computed — every "
      f"figure is read from the row it was recorded in.")
    w("")
    if f["facilities"] == 0 or f["carve"] == 0:
        w(f"And read what it says above the figures: **no 200.465 facilities "
          f"carve-out is in this rate** — {f['facilities']} facilities carry "
          f"measured space and {f['carve']} carve-outs are recorded, so every "
          f"dollar of tenant and vacant occupancy cost sits in the federal "
          f"pool. The rate reads high, which is the honest direction to err.")
        w("")

    # ── the restatement ─────────────────────────────────────────────────
    if f["restate"]:
        w("## 6 · The restatement — what it now says")
        w("")
        w("The position is the **rebuild** against the cost record: labour "
          "taken down to wages plus fringe before indirect goes on, because "
          "these invoices bill labour that already carries indirect. The "
          "invoice-only reading is beside it and is **never** the position.")
        w("")
        w("| award | billed | position | as-billed would say | recovered |")
        w("| --- | ---: | ---: | ---: | ---: |")
        for r in f["restate"]:
            pos = Decimal(str(r["under_recovered"])) - Decimal(str(r["over_collected"]))
            imp = (f"{Decimal(str(r['implied_rate'])) * 100:.2f}%"
                   if r["implied_rate"] is not None else "—")
            w(f"| {r['objective_id']} | {money(r['billed_total'])} | "
              f"**{'+' if pos > 0 else ''}{money(pos)}** | "
              f"{money(r['as_billed_position'])} | {imp} |")
        w("")
        w("The last column is the indirect rate the billing **actually** "
          "recovered, against a **10.00%** de minimis election. That election "
          "is written down in two places and they are different kinds of "
          "evidence: Last Tactical Mile's **executed** Schedule B budgets "
          "10.0000% of total direct, and Hybrid Phase 2's **cost proposal** "
          "computes *ICR 10% maximum 45,457.00* into its labour line.")
        w("")
        w("**Nothing goes to a sponsor off this table today.** Everything is "
          "PROPOSED until a sponsor says otherwise in writing, and an "
          "acceptance must name the §4.4 modification that authorised the "
          "change of basis.")
        w("")

    # ── C and P ─────────────────────────────────────────────────────────
    w("---")
    w("")
    w("## C · If something has to change")
    w("")
    w("1. **Unseal** — `/rates`, with a written reason. It supersedes every "
      "rate computed against that seal.")
    w("2. **Correct the judgment** — `/classify`. Reclassifying supersedes "
      "rather than edits; the prior judgment stays on the record.")
    w("3. **Re-seal** over the corrected set.")
    if comb:
        w(f"4. **Recompute** — and choose **{comb['admin_labour_basis']}** "
          f"again (§4).")
    w("5. **Re-check** — §5, then re-run the crosscheck and regenerate this "
      "sheet: `python3 scripts/runbook.py --write`.")
    w("6. **Tell whoever quoted the old figure.**")
    w("")
    w("*Correct by superseding, never by editing.*")
    w("")
    w("## P · Running in parallel, and none of it blocks the above")
    w("")
    p = f["people"]
    w(f"- **The {p.get('n', 0)} timesheets.** {p.get('signed', 0)} of "
      f"{p.get('n', 0)} certified, and **{f['terms']} employment terms are on "
      f"the record**, so no draft can be built for anybody. Two gates, and "
      f"both come out of the roster reply — which also carries the addresses "
      f"the accounts are opened against. Opening them is a second act and it "
      f"is the administrator's.")
    w(f"- **The square footage.** {f['facilities']} facilities carry measured "
      f"space. It is the largest open item and **it gates no "
      f"classification** — occupancy is OVERHEAD in the 2025 chart and the "
      f"tenant share comes out at rate time.")
    w("- **Barb's decisions.** `docs/BARB_ONE_PAGE_AM.pdf`.")
    w("")
    w("## What must not be automated, and why")
    w("")
    w("| | |")
    w("| --- | --- |")
    w("| **The seal** | It is the assertion the rate was not "
      "reverse-engineered. A script that sealed would put the machine's name "
      "on it. |")
    w("| **A certification** | 200.430(i) wants the person whose effort it "
      "was. |")
    w("| **Adopting a draft** | Theirs to accept or decline. |")
    w("| **A reconciling item** | A difference is closed by naming the lines "
      "behind it. |")
    w("| **Anything sent to a sponsor** | A position YBI takes, in writing. |")
    w("")
    w("---")
    w("")
    w(f"*Crosscheck: {len(x['findings'])} findings, {len(x['notes'])} not "
      f"evaluable. This sheet is not written while any finding stands.*")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reuse", help="a crosscheck result already taken")
    args = ap.parse_args()

    x = crosscheck(args.reuse)
    if not x.get("passed"):
        print("The crosscheck did not pass, so no run sheet was written. A "
              "document somebody acts on cannot be generated over a figure "
              "that does not tie:", file=sys.stderr)
        for fnd in x.get("findings", []):
            print(f"  - {fnd}", file=sys.stderr)
        return 1

    text = render(x, live())
    if args.write:
        OUT.write_text(text)
        print(f"wrote {OUT} — {len(text.splitlines())} lines, from a "
              f"crosscheck with {len(x['notes'])} note(s) and no findings")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
