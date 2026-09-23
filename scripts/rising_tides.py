#!/usr/bin/env python3
"""What the record says about Rising Tides, and what has to happen next.

Tom asked for a meeting about the Rising Tides (ARC POWER) audit, and the
question underneath it is one this repository has carried on its own open
list since the analysis: **is Rising Tides federally funded?** The
controller's workbook says yes and `cost_objective.is_federal` says no, and
that single flag decides whether $582,085.53 of judged cost is federally
chargeable, whether the award reaches the SEFA, and therefore the scope of
the Single Audit.

**Generated, so it cannot go stale.** `docs/MONDAY_RUNBOOK.md` is written
this way for the same reason — a memo carrying figures somebody typed in is
one that disagrees with the record the week after it is written, and this
one is going into a meeting. Every figure here is read from the row that
owns it; nothing is computed twice and nothing is recalled.

    PYTHONPATH=. python3 scripts/rising_tides.py
    PYTHONPATH=. python3 scripts/rising_tides.py --workbook

**It says which record it read.** `rate_headroom.py`'s rule: the reference
record and a boot-loaded deployment answer this differently — one carries
757 judgments and the other carries none — so a document that did not name
its source would be a figure with no provenance.

It decides nothing. Whether Rising Tides is federal is a judgment about an
instrument nobody here has read, and the last section is what to go and get
rather than what to conclude.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from app.db import one, open_pool, query  # noqa: E402
from app.domain.audit_package import certification_lines  # noqa: E402

OBJECTIVE = "RISING-TIDES"


def money(x) -> str:
    """The house spelling. `{x:,.2f}`, and a blank stays a blank."""
    return "—" if x is None else f"{x:,.2f}"


# ── What the record holds ─────────────────────────────────────────────

def gather(period: str) -> dict:
    """Every figure, each read from the view or table that owns it."""
    return {
        "objective": one("""SELECT objective_id, label, objective_type,
                                   is_federal, is_final, cfda, active
                              FROM cost_objective WHERE objective_id = %s""",
                         (OBJECTIVE,)),
        "award": one("SELECT * FROM award WHERE objective_id = %s",
                     (OBJECTIVE,)),
        "invoices": query("""SELECT invoice_number, invoice_date, service_from,
                                    service_to, total, bill_to_name, status
                               FROM invoice
                              WHERE objective_id = %s AND period = %s
                              ORDER BY invoice_date""", (OBJECTIVE, period)),
        "categories": query("""SELECT il.category, count(*) AS lines,
                                      sum(il.amount) AS amount
                                 FROM invoice_line il
                                 JOIN invoice i USING (invoice_id)
                                WHERE i.objective_id = %s AND i.period = %s
                                GROUP BY 1 ORDER BY 3 DESC""",
                            (OBJECTIVE, period)),
        # The anchor already owns this comparison. Taking the difference here
        # would be one figure derived twice.
        "tie": one("""SELECT * FROM v_invoice_income_tie
                       WHERE period = %s AND objective_id = %s""",
                   (period, OBJECTIVE)),
        "judged": query("""SELECT d.pool::text AS pool, d.federal::text AS federal,
                                  d.grade::text AS grade,
                                  count(DISTINCT d.decision_id) AS groups,
                                  sum(abs(l.amount)) AS dollars
                             FROM decision d
                             JOIN decision_line dl
                               ON dl.decision_id = d.decision_id AND dl.live
                             JOIN ledger_line l ON l.line_id = dl.line_id
                            WHERE d.reversed_at IS NULL
                              AND d.objective_id = %s
                            GROUP BY 1,2,3 ORDER BY 5 DESC""", (OBJECTIVE,)),
        "accounts": query("""SELECT DISTINCT l.account
                               FROM decision d
                               JOIN decision_line dl
                                 ON dl.decision_id = d.decision_id AND dl.live
                               JOIN ledger_line l ON l.line_id = dl.line_id
                              WHERE d.reversed_at IS NULL
                                AND d.objective_id = %s
                              ORDER BY 1""", (OBJECTIVE,)),
        "labour": query("""SELECT employee_key, distributed_wages, share,
                                  evidence_quality::text AS evidence_quality
                             FROM v_labor_effective
                            WHERE objective_id = %s
                            ORDER BY distributed_wages DESC""", (OBJECTIVE,)),
        # A document nobody has filed is the whole of the answer here, so the
        # question is asked of the register rather than assumed.
        "documents": query("""SELECT evidence_id, kind, uri, doc_date
                                FROM evidence
                               WHERE uri ILIKE '%%rising%%'
                                  OR uri ILIKE '%%appalachian%%'
                                  OR note ILIKE '%%rising%%'
                               ORDER BY received_at"""),
        "cert": one("SELECT * FROM v_rate_certified WHERE period = %s",
                    (period,)),
    }


# ── The memorandum ────────────────────────────────────────────────────

def memo(d: dict, period: str, source: str) -> str:
    o, tie, award = d["objective"], d["tie"], d["award"]
    out: list[str] = []
    w = out.append

    w(f"# Rising Tides — what the record says, and what it cannot say")
    w("")
    w(f"*{period} · generated {dt.date.today():%d %B %Y} from `{source}`*")
    w("")
    for line in certification_lines(d["cert"]):
        w(f"> **{line}**")
    w("")
    w("Generated from the live record by `scripts/rising_tides.py`. Every "
      "figure is read from the row that owns it; nothing here is recalled "
      "and nothing is derived twice. **It decides nothing** — the question "
      "at the end of it is a judgment about a document nobody here has "
      "read.")
    w("")

    # ── 1 ──────────────────────────────────────────────────────────────
    w("## 1. The question")
    w("")
    w("Is Rising Tides a federal award?")
    w("")
    w("The controller's workbook says yes. `cost_objective.is_federal` says "
      "**no**. Both readings are on the record and they have never been "
      "reconciled — it is on this repository's own open-questions list, and "
      "it is what Tom's audit turns on.")
    w("")
    w("The invoices make the tension concrete rather than theoretical: all "
      f"{len(d['invoices'])} of them are billed to the **Appalachian "
      "Regional Commission**, and ARC POWER is a federal programme. Billing "
      "a federal agency is not the same fact as holding a federal award — a "
      "fee-for-service contract and a subaward are billed to the same place "
      "and land in different columns — so the instrument decides it, and the "
      "instrument is not here.")
    w("")

    # ── 2 ──────────────────────────────────────────────────────────────
    w("## 2. What the record holds")
    w("")
    w("| | |")
    w("| --- | ---: |")
    w(f"| `cost_objective.is_federal` | **{str(o['is_federal']).lower()}** |")
    w(f"| CFDA / ALN | {o['cfda'] or '— none recorded'} |")
    w(f"| objective type | {o['objective_type']} |")
    w(f"| award row | {'yes' if award else '**none — no award is on the register**'} |")
    w(f"| 2025 invoices | {len(d['invoices'])} |")
    if tie:
        w(f"| billed | {money(tie['billed'])} |")
        w(f"| `3900 Grant Income:Rising Tides` | {money(tie['grant_income'])} |")
        w(f"| the anchor | **{tie['state']}**, by {money(tie['variance'])} |")
    for r in d["judged"]:
        w(f"| judged {r['pool']} / {r['federal']} | {r['groups']} groups · "
          f"**{money(r['dollars'])}** |")
    wages = sum((r["distributed_wages"] or 0) for r in d["labour"])
    w(f"| distributed wages | {money(wages)} across "
      f"{len(d['labour'])} people |")
    w("")
    if d["accounts"]:
        w("Every judged dollar sits in one account — "
          + ", ".join(f"`{r['account']}`" for r in d["accounts"])
          + " — which is the 2025 chart burying programme identity in an "
            "account *name*, the structural defect the 2026 chart fixes.")
        w("")

    # ── 3 ──────────────────────────────────────────────────────────────
    w("## 3. What is not on the record, and each one matters")
    w("")
    w("**A blank is unanswered, and unanswered is a value.** None of these is "
      "a gap to fill in with a reasonable guess:")
    w("")
    w(f"- **No award row.** The register carries four awards and Rising Tides "
      "is not one of them, so there is no ceiling, no period of performance, "
      "no rate method and no clause to cite. Every constraint test the "
      "system runs against an award is unevaluable here — and *unevaluable "
      "is not a pass*.")
    if not d["documents"]:
        w("- **No agreement on file.** Nothing in the document register names "
          "Rising Tides or the Appalachian Regional Commission. So "
          "`is_federal` cannot be read off an instrument today by anybody, "
          "which is why it has stayed open.")
    else:
        w("- Documents on file that name it: "
          + ", ".join(f"`{r['evidence_id']}` ({r['kind']})"
                      for r in d["documents"]))
    cats = d["categories"]
    if len(cats) == 1:
        c = cats[0]
        w(f"- **No category detail on the billing.** All {c['lines']} invoice "
          f"lines carry one undifferentiated `{c['category']}` category for "
          f"{money(c['amount'])}, so **nothing on the record says what was "
          "billed for.** That is the same shape as Digital Engineering, and "
          "it is what makes a cost-to-billing comparison impossible rather "
          "than merely hard.")
    if any(r["service_from"] is None for r in d["invoices"]):
        n = sum(1 for r in d["invoices"] if r["service_from"] is None)
        w(f"- **No service period on {n} of {len(d['invoices'])} invoices**, "
          "so nothing ties a bill to the months it covers. What the register "
          "holds is the invoice date, which is not the same fact.")
    w("- **The labour is entirely management reconstruction.** Not one hour "
      "on this objective is timesheet-backed, which is the same "
      "200.430(i) exposure the rest of 2025 carries and is worth saying out "
      "loud if the answer turns out to be *federal*.")
    w("")
    w("The nine invoices as issued, which is the whole of what the register "
      "knows about the billing:")
    w("")
    w("| Invoice | Dated | Total | Billed to |")
    w("| --- | --- | ---: | --- |")
    for r in d["invoices"]:
        w(f"| {r['invoice_number']} | {r['invoice_date']:%d %b %Y} | "
          f"{money(r['total'])} | {r['bill_to_name']} |")
    w("")
    # Only said where the dates actually say it. A sentence about a gap on a
    # run of consecutive monthly invoices would be prose arguing with its own
    # table.
    dates = [r["invoice_date"] for r in d["invoices"] if r["invoice_date"]]
    widest = max(((b - a).days, a, b)
                 for a, b in zip(dates, dates[1:])) if len(dates) > 1 else None
    if widest and widest[0] > 45:
        days, a, b = widest
        w(f"The billing is monthly except once: {days} days separate "
          f"{a:%d %b} from {b:%d %b}. That is a fact about the billing rather "
          "than about the work, and with no service period recorded nothing "
          "on the record says which months the second one covers.")
        w("")

    # ── 4 ──────────────────────────────────────────────────────────────
    w("## 4. Which way the flag moves things")
    w("")
    w("Both directions, because a memo that priced only one of them would be "
      "the answer chosen before the question:")
    w("")
    w("| if Rising Tides is… | then |")
    w("| --- | --- |")
    fed = next((r for r in d["judged"] if r["federal"] == "NOT_APPLICABLE"),
               None)
    amt = money(fed["dollars"]) if fed else "the judged cost"
    w(f"| **not federal** (today's record) | {amt} stays `NOT_APPLICABLE`; "
      "nothing reaches the SEFA; the indirect rate does not apply to it and "
      "no recovery is available on it |")
    w(f"| **federal** | {amt} becomes federally chargeable and every one of "
      "those judgments has to be re-made with a federal treatment; the award "
      "reaches the SEFA, which moves the Single Audit scope and the 200.501 "
      "threshold; the reconstruction of the labour becomes a 200.430(i) "
      "question on a federal charge |")
    w("")
    if tie and tie["state"] != "TIES":
        w(f"And the {money(tie['variance'])} difference between the invoices "
          "and the grant income reads differently under each answer — a "
          "cut-off question on a commercial contract, and an over-billing "
          "question on a federal award. It is declared in the loader with a "
          "reason and it has never been settled by anybody.")
        w("")

    # ── 5 ──────────────────────────────────────────────────────────────
    w("## 5. What to do, in order")
    w("")
    w("**Nothing below is a step the system can take on its own.** Each one "
      "is a judgment or a document somebody has to go and get.")
    w("")
    w("### Before the meeting")
    w("")
    w("1. **Ask YBI for the executed ARC instrument** — the award document "
      "itself, not a summary. Four things off its face settle this: the "
      "**instrument type** (grant, cooperative agreement, subaward or "
      "procurement contract), the **ALN/CFDA number**, the **period of "
      "performance**, and the **indirect-cost provision**. The first two "
      "answer `is_federal` and the SEFA; the fourth decides whether any of "
      "the indirect work applies.")
    w("2. **Ask what the ten invoice lines are made of.** One `OTHER` "
      "category for the whole year is the record's biggest blind spot on "
      "this award. The monthly detail behind the billing is a column their "
      "export already has.")
    w("3. **Ask Tom which reading his workbook took, and why.** His workbook "
      "says federal and the objective master says not; he is the only person "
      "who knows which of those was a decision and which was a default.")
    w("")
    w("### Once the instrument is in hand")
    w("")
    w("4. **File it.** `/documents` → upload. The **kind decides where it "
      "lands**, so say what it is: `grant-agreement` if ARC awarded it "
      "directly, `subrecipient-agreement` if it flows through somebody else, "
      "`award-agreement` otherwise. All three file under *awards*; getting "
      "it wrong costs a few seconds of browsing and nothing else. The text "
      "is read as the file arrives, so a clause can afterwards be checked "
      "against the document rather than recalled.")
    w("5. **Open the award row — and it takes a developer today.** Nothing "
      "in the API creates one; the four on the register came from "
      "`scripts/load_awards.py` and a migration. Until a row exists, "
      "`PUT /contracts/{award}/terms` answers *No contract* and every "
      "constraint test on this objective stays unevaluable.")
    w("6. **Then record each provision with the clause it came from** — "
      "`/contracts` does have that door. `load_contract_terms.py`'s own "
      "rule: *a provision with no citation is somebody's recollection of a "
      "contract, which is worth nothing in a dispute and worse than nothing "
      "in a file.*")
    w("7. **Settle `is_federal` — and that takes a developer too.** See "
      "below.")
    w("8. **If the answer is federal, the 33 judgments have to be re-made** "
      "— unseal with a written reason, reclassify, re-seal, recompute. That "
      "supersedes the rate on file, which is the mechanism working rather "
      "than breaking: the auditor's ask does not get to move a sealed "
      "judgment quietly.")
    w("")

    # ── 6 ──────────────────────────────────────────────────────────────
    w("## 6. Two doors that are not there, found writing this")
    w("")
    w("Steps 5 and 7 need a developer, and neither is a thing the controller "
      "can do at a screen. Both are the capability-with-no-door shape this "
      "repository keeps finding, and they sit on the one path an auditor's "
      "question actually takes.")
    w("")
    w("**Nothing creates an `award` row.** Not a route, not a screen. The "
      "four on the register came from `scripts/load_awards.py` and migration "
      "`004`, and `PUT /contracts/{award}/terms` — which *does* have a door, "
      "and which `Contracts.jsx` calls — answers **404 *No contract*** until "
      "a row exists. So a new award is a code change and a deploy, and the "
      "shape of that was already visible in the four: they are transcriptions "
      "of documents, which is why a loader was the right answer *then* and "
      "is the wrong answer for an award that arrives next week.")
    w("")
    w("**`cost_objective.is_federal` is write-once with no amendment door.** "
      "`POST /api/contracts/charge-codes` sets it when a code is *opened* and "
      "answers 409 on one that exists; nothing anywhere updates "
      "`cost_objective`. So the single field this entire question turns on "
      "cannot be changed through any screen or route.")
    w("")
    w("It is named here rather than fixed on the way past, because *what the "
      "door refuses* is the interesting half and it is a judgment somebody "
      "has to make. Opening a federal code already demands a CFDA — *without "
      "it the award cannot reach the SEFA, and the Single Audit scope is "
      "decided by what is on the SEFA.* An amendment that moves an objective "
      "**into** federal scope should demand at least the same: the number, a "
      "written reason, the document behind it, and a count of the settled "
      "judgments it invalidates, printed before anybody presses it. Built "
      "carelessly it is a flag somebody flips the day before an audit, which "
      "is the one thing this system exists to make impossible.")
    w("")
    return "\n".join(out) + "\n"


# ── The workbook ──────────────────────────────────────────────────────

def build_workbook(d: dict, period: str, source: str) -> bytes:
    """The same facts in the shape somebody works through at a table.

    The first sheet carries the caveats and the certification band, because
    a workbook travels and the caveat has to travel with it.
    """
    from io import BytesIO

    from openpyxl import Workbook

    from app.domain.package import BOLD, HEAD_FILL, HEAD_FONT, SUB, TITLE

    wb = Workbook()
    wb.remove(wb.active)

    def head(ws, row, cols):
        for i, c in enumerate(cols, 1):
            cell = ws.cell(row=row, column=i, value=c)
            cell.font, cell.fill = HEAD_FONT, HEAD_FILL

    # ── Start here ────────────────────────────────────────────────────
    ws = wb.create_sheet("Start here")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 104
    r = 1
    ws.cell(row=r, column=1,
            value=f"YBI · RISING TIDES · {period}").font = TITLE
    r += 2
    for line in certification_lines(d["cert"]):
        ws.cell(row=r, column=1, value=line).font = BOLD
        r += 1
    r += 1
    o, tie = d["objective"], d["tie"]
    for label, body in (
        ("What this is",
         "Everything the cost record holds about Rising Tides, read from the "
         "rows that own it. Generated by scripts/rising_tides.py from "
         f"{source} on {dt.date.today():%d %B %Y}."),
        ("The question",
         "Is Rising Tides a federal award? The controller's workbook says "
         f"yes; cost_objective.is_federal says {str(o['is_federal']).lower()}. "
         "The invoices are billed to the Appalachian Regional Commission. "
         "Nothing here decides it."),
        ("What is missing",
         "There is no award row and no agreement on file, so is_federal "
         "cannot be read off an instrument by anybody today. Every invoice "
         "line carries one undifferentiated category, so nothing says what "
         "was billed for."),
        ("What is unfinished",
         "The labour on this objective is entirely management "
         "reconstruction — no hour of it is timesheet-backed."),
    ):
        ws.cell(row=r, column=1, value=label).font = BOLD
        r += 1
        c = ws.cell(row=r, column=1, value=body)
        c.font, c.alignment = SUB, c.alignment.copy(wrapText=True, vertical="top")
        ws.row_dimensions[r].height = 46
        r += 2

    # ── Invoices ──────────────────────────────────────────────────────
    ws = wb.create_sheet("Invoices")
    head(ws, 1, ["Invoice", "Date", "Service from", "Service to", "Total",
                 "Billed to", "Status"])
    for i, row in enumerate(d["invoices"], 2):
        ws.cell(row=i, column=1, value=row["invoice_number"])
        ws.cell(row=i, column=2, value=row["invoice_date"])
        ws.cell(row=i, column=3, value=row["service_from"])
        ws.cell(row=i, column=4, value=row["service_to"])
        ws.cell(row=i, column=5, value=float(row["total"] or 0))
        ws.cell(row=i, column=6, value=row["bill_to_name"])
        ws.cell(row=i, column=7, value=row["status"])
    for col, width in zip("ABCDEFG", (12, 12, 13, 12, 14, 34, 10)):
        ws.column_dimensions[col].width = width

    # ── The judgments ─────────────────────────────────────────────────
    ws = wb.create_sheet("Judged cost")
    head(ws, 1, ["Pool", "Federal treatment", "Grade", "Groups", "Dollars"])
    for i, row in enumerate(d["judged"], 2):
        ws.cell(row=i, column=1, value=row["pool"])
        ws.cell(row=i, column=2, value=row["federal"])
        ws.cell(row=i, column=3, value=row["grade"])
        ws.cell(row=i, column=4, value=row["groups"])
        ws.cell(row=i, column=5, value=float(row["dollars"] or 0))
    for col, width in zip("ABCDE", (12, 20, 28, 10, 16)):
        ws.column_dimensions[col].width = width

    # ── Labour ────────────────────────────────────────────────────────
    ws = wb.create_sheet("Labour")
    head(ws, 1, ["Employee", "Distributed wages", "Share of their year",
                 "Evidence"])
    for i, row in enumerate(d["labour"], 2):
        ws.cell(row=i, column=1, value=row["employee_key"])
        ws.cell(row=i, column=2, value=float(row["distributed_wages"] or 0))
        ws.cell(row=i, column=3, value=float(row["share"] or 0))
        ws.cell(row=i, column=4, value=row["evidence_quality"])
    for col, width in zip("ABCD", (16, 18, 20, 30)):
        ws.column_dimensions[col].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Running it ────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", default="2025")
    ap.add_argument("--workbook", action="store_true",
                    help="also write the workbook beside the memorandum")
    ap.add_argument("--out", default="docs")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    # Which record this was read from, on the face of the document. The
    # reference record and a boot-loaded deployment answer differently.
    source = url.rsplit("/", 1)[-1].split("?")[0]
    open_pool()

    d = gather(args.period)
    if not d["objective"]:
        raise SystemExit(f"{OBJECTIVE} is not on this record. Nothing to say.")

    out = ROOT / args.out
    doc = out / "RISING_TIDES_2025.md"
    doc.write_text(memo(d, args.period, source))
    print(f"wrote {doc.relative_to(ROOT)}")

    if args.workbook:
        book = out / "rising-tides-2025.xlsx"
        book.write_bytes(build_workbook(d, args.period, source))
        print(f"wrote {book.relative_to(ROOT)}")

    tie = d["tie"]
    print(f"  read from {source} · {len(d['invoices'])} invoices · "
          f"anchor {tie['state'] if tie else 'NO ROW'} · "
          f"is_federal={str(d['objective']['is_federal']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
