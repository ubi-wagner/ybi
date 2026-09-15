#!/usr/bin/env python3
"""The 2025 return against the 2024 one, line for line.

    DATABASE_URL=... python3 scripts/form_990_comparison.py \
        [--period 2025] [--prior 2024] [--out docs/FORM_990_2025_vs_2024.md]

Everything here is read from the record. The 2025 figures come from
`v_form_990_part_ix` and `v_form_990_part_viii`, which are the return on its
own numbered lines; the 2024 figures come from `form_990_prior_year`, which is
the filed return transcribed as printed. **Nothing is computed twice** — the
variance is a subtraction and the shares are a division, and both are taken
here because neither is a figure anybody records.

It writes nothing to the cost record.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query                          # noqa: E402

D = lambda x: Decimal(str(x or 0))                                # noqa: E731


def money(x) -> str:
    v = D(x)
    return "—" if v == 0 else f"{v:,.2f}"


def pct(num, den) -> str:
    n, d = D(num), D(den)
    return "—" if d == 0 else f"{n / d:.1%}"


def delta(now, then) -> str:
    n, t = D(now), D(then)
    if n == 0 and t == 0:
        return "—"
    if t == 0:
        return "**new**"
    if n == 0:
        return "**gone**"
    return f"{(n - t) / t:+.1%}"


def rows(period: str, prior: str) -> list[dict]:
    """Every line of the return, both years, in the form's own order."""
    return query("""
        SELECT l.line_id, l.seq, l.part, l.label, l.note,
               -- Part IX and Part VIII are different views and a line
               -- belongs to exactly one of them. `COALESCE(ix.total,
               -- viii.amount, 0)` reads as though it picked whichever had an
               -- answer and does not: the expense view emitted every revenue
               -- line at 0.00 (097), so the COALESCE took the zero and the
               -- report printed total revenue of -154,663.63.
               CASE WHEN l.part = 'VIII' AND l.line_id <> '8b'
                    THEN COALESCE(viii.amount, 0)
                    ELSE COALESCE(ix.total, 0) END        AS total,
               COALESCE(ix.program, 0)                 AS program,
               COALESCE(ix.management, 0)              AS management,
               COALESCE(ix.fundraising, 0)             AS fundraising,
               CASE WHEN l.part = 'VIII' AND l.line_id <> '8b'
                    THEN COALESCE(viii.lines, 0)
                    ELSE COALESCE(ix.lines, 0) END        AS lines,
               COALESCE(p.total, 0)                    AS prior_total,
               COALESCE(p.program, 0)                  AS prior_program,
               COALESCE(p.management, 0)               AS prior_management,
               COALESCE(p.fundraising, 0)              AS prior_fundraising,
               p.line_id IS NOT NULL                   AS prior_filed
          FROM form_990_line l
          LEFT JOIN v_form_990_part_ix ix
                 ON ix.line_id = l.line_id AND ix.period = %s
          LEFT JOIN v_form_990_part_viii viii
                 ON viii.line_id = l.line_id AND viii.period = %s
          LEFT JOIN form_990_prior_year p
                 ON p.line_id = l.line_id AND p.period = %s
         ORDER BY l.seq""", (period, period, prior))


def accounts_on(line_id: str, period: str) -> list[dict]:
    return query("""
        SELECT m.account_prefix, m.note,
               (SELECT COALESCE(sum(x.amount), 0) FROM ledger_line x
                 WHERE x.period = %s
                   AND (x.account = m.account_prefix
                        OR x.account LIKE m.account_prefix || ':%%')
                   AND NOT EXISTS (
                         SELECT 1 FROM form_990_account_line m2
                          WHERE length(m2.account_prefix)
                                > length(m.account_prefix)
                            AND (x.account = m2.account_prefix
                                 OR x.account LIKE m2.account_prefix || ':%%'))
               ) AS amount
          FROM form_990_account_line m
         WHERE m.line_id = %s
         ORDER BY 3 DESC""", (period, line_id))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2025")
    ap.add_argument("--prior", default="2024")
    ap.add_argument("--out", default="docs/FORM_990_2025_vs_2024.md")
    args = ap.parse_args()
    if not os.getenv("DATABASE_URL"):
        print("set DATABASE_URL", file=sys.stderr)
        return 2
    open_pool()
    period, prior = args.period, args.prior

    all_rows = rows(period, prior)
    ix = [r for r in all_rows if r["part"] == "IX"]
    viii = [r for r in all_rows if r["part"] == "VIII" and r["line_id"] != "8b"]
    netted = next(r for r in all_rows if r["line_id"] == "8b")

    exp = one("SELECT * FROM v_form_990_line_check WHERE period = %s", (period,))
    rev = one("SELECT * FROM v_form_990_revenue_check WHERE period = %s",
              (period,))
    pri = one("SELECT * FROM v_form_990_prior_check WHERE period = %s",
              (prior,))
    cert = one("""SELECT certified, certified_by, certified_at
                    FROM v_rate_certified WHERE period = %s""", (period,))
    walk = query("""SELECT step, state, detail FROM v_audit_walk
                     WHERE period = %s AND state <> 'DONE' ORDER BY seq""",
                 (period,))

    t = lambda k: sum(D(r[k]) for r in ix)                        # noqa: E731
    now_total, now_prog = t("total"), t("program")
    now_mg, now_fr = t("management"), t("fundraising")
    pr_total = D(pri["part_ix_total"]) if pri else Decimal(0)
    pr_prog = D(pri["part_ix_program"]) if pri else Decimal(0)
    pr_mg = D(pri["part_ix_management"]) if pri else Decimal(0)
    pr_fr = D(pri["part_ix_fundraising"]) if pri else Decimal(0)

    rev_total = sum(D(r["total"]) for r in viii) - D(netted["total"])
    pr_rev = D(pri["total_revenue"]) if pri else Decimal(0)

    out: list[str] = []
    w = out.append

    w(f"# Form 990 — {period} against {prior}, line for line\n")
    if cert and cert["certified"]:
        w(f"**The {period} rate is certified — {cert['certified_by']}, "
          f"{cert['certified_at']:%d %B %Y}.** Nothing on this return depends "
          f"on the indirect rate; it is stated because every document this "
          f"system produces says where the signature stands.\n")
    else:
        w("**NOT CERTIFIED.** No signature stands on the rate. Nothing on "
          "this return depends on it.\n")
    w(f"The {period} figures are read from `v_form_990_part_ix` and "
      f"`v_form_990_part_viii` — the ledger on the return's own numbered "
      f"lines. The {prior} figures are `form_990_prior_year`, the filed "
      f"return transcribed as printed from "
      f"`{prior}_Form-990_ProPublica_full-filing.pdf`, which has been on file "
      f"since the foundation was loaded.\n")

    # ── The three controls, first ────────────────────────────────────
    w("## Does everything land on a line\n")
    w("| | | |")
    w("| --- | --- | --- |")
    w(f"| every expense account is on exactly one line | `v_form_990_line_check` "
      f"| **{exp['state']}** — {exp['unmapped_accounts']} unmapped, variance "
      f"{money(exp['variance'])} |")
    w(f"| every income account is on exactly one line | "
      f"`v_form_990_revenue_check` | **{rev['state']}** — "
      f"{rev['unmapped_accounts']} unmapped, variance {money(rev['variance'])} |")
    w(f"| the {prior} transcription foots the way the return does | "
      f"`v_form_990_prior_check` | **{pri['state'] if pri else 'NO DATA'}** |")
    w("")
    w(f"The profit and loss carries **{money(exp['ledger_expense'])}** of "
      f"expense. **{money(exp['part_ix_total'])}** of it is on Part IX and "
      f"**{money(exp['netted_in_part_viii'])}** is netted against the "
      f"fundraising events it belongs to, in Part VIII line 8b — which the "
      f"form excludes from Part IX by its own instruction at the head of the "
      f"part. Those two add to the ledger to the cent, which is what the "
      f"first control says.\n")

    # ── Part I ───────────────────────────────────────────────────────
    w("## Part I — the summary the reader sees first\n")
    w(f"| | {prior} | {period} | |")
    w("| --- | ---: | ---: | ---: |")
    w(f"| 12 Total revenue | {money(pr_rev)} | {money(rev_total)} | "
      f"{delta(rev_total, pr_rev)} |")
    w(f"| 18 Total expenses | {money(pr_total)} | {money(now_total)} | "
      f"{delta(now_total, pr_total)} |")
    w(f"| 19 Revenue less expenses | {money(pr_rev - pr_total)} | "
      f"{money(rev_total - now_total)} | |")
    w("")
    w(f"| functional column | {prior} | share | {period} | share |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for label, a, b in (("Program service", pr_prog, now_prog),
                        ("Management and general", pr_mg, now_mg),
                        ("Fundraising", pr_fr, now_fr)):
        w(f"| {label} | {money(a)} | {pct(a, pr_total)} | {money(b)} | "
          f"{pct(b, now_total)} |")
    w(f"| **Total functional expenses** | **{money(pr_total)}** | | "
      f"**{money(now_total)}** | |")
    w("")

    # ── Part IX ──────────────────────────────────────────────────────
    w("## Part IX — Statement of Functional Expenses\n")
    w(f"| line | | {prior} total | {period} total | Δ | {period} program | "
      f"{period} M&G | {period} fundraising |")
    w("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in ix:
        w(f"| **{r['line_id']}** | {r['label'][:62]} | "
          f"{money(r['prior_total'])} | {money(r['total'])} | "
          f"{delta(r['total'], r['prior_total'])} | {money(r['program'])} | "
          f"{money(r['management'])} | {money(r['fundraising'])} |")
    w(f"| **25** | **Total functional expenses** | **{money(pr_total)}** | "
      f"**{money(now_total)}** | **{delta(now_total, pr_total)}** | "
      f"**{money(now_prog)}** | **{money(now_mg)}** | **{money(now_fr)}** |")
    w("")
    w(f"And the line the form takes out of Part IX rather than into it:\n")
    w(f"| line | | {prior} | {period} |")
    w("| --- | --- | ---: | ---: |")
    w(f"| **8b** | {netted['label'][:70]} | {money(netted['prior_total'])} | "
      f"{money(netted['total'])} |")
    w("")

    # ── Part VIII ────────────────────────────────────────────────────
    w("## Part VIII — Statement of Revenue\n")
    w(f"| line | | {prior} | {period} | Δ |")
    w("| --- | --- | ---: | ---: | ---: |")
    for r in viii:
        w(f"| **{r['line_id'].lstrip('V')}** | {r['label'][:64]} | "
          f"{money(r['prior_total'])} | {money(r['total'])} | "
          f"{delta(r['total'], r['prior_total'])} |")
    w(f"| **12** | **Total revenue** (line 8 taken net of 8b) | "
      f"**{money(pr_rev)}** | **{money(rev_total)}** | "
      f"**{delta(rev_total, pr_rev)}** |")
    w("")

    # ── Where the two returns differ in kind ─────────────────────────
    w("## Where the two returns differ in kind, not in amount\n")

    only_prior = [r for r in all_rows
                  if D(r["prior_total"]) != 0 and D(r["total"]) == 0]
    only_now = [r for r in all_rows
                if D(r["total"]) != 0 and not r["prior_filed"]]
    if only_prior:
        w(f"**Lines the {prior} return carries and {period} does not.**\n")
        for r in only_prior:
            w(f"* **Line {r['line_id']} — {r['label']}**, "
              f"{money(r['prior_total'])} in {prior}."
              + (f" {r['note']}" if r["note"] else ""))
        w("")
    if only_now:
        w(f"**Lines {period} carries and the {prior} return did not.**\n")
        for r in only_now:
            w(f"* **Line {r['line_id'].lstrip('V')} — {r['label']}**, "
              f"{money(r['total'])}."
              + (f" {r['note']}" if r["note"] else ""))
        w("")

    # The functional method, which is the substantive difference.
    w("### The two years allocate the functional columns by different methods\n")
    w(f"On the {prior} return, ten indirect lines carry the **same three "
      f"percentages** — occupancy, depreciation, insurance, interest, "
      f"accounting, legal, office, dues, real estate taxes and meals are each "
      f"split 80.5% / 15.7% / 3.9%. That is one overhead allocation ratio "
      f"applied across the return.\n")
    w(f"The {period} figures do not do that. Every line takes the 990 "
      f"function recorded on the classification behind it, so a line is "
      f"wholly one column or wholly another — except the compensation block, "
      f"which is split by the effort distribution. Both methods are permitted; "
      f"they are not the same method, and the lines where it shows most are "
      f"these:\n")
    w(f"| line | | {period} amount | {period} program | {prior} program |")
    w("| --- | --- | ---: | ---: | ---: |")
    bimodal = []
    for r in ix:
        if D(r["total"]) == 0 or D(r["prior_total"]) == 0:
            continue
        here = D(r["program"]) / D(r["total"])
        there = D(r["prior_program"]) / D(r["prior_total"])
        if abs(here - there) >= Decimal("0.15"):
            bimodal.append((r, here, there))
    for r, here, there in sorted(bimodal, key=lambda x: -D(x[0]["total"])):
        w(f"| **{r['line_id']}** | {r['label'][:52]} | {money(r['total'])} | "
          f"{here:.1%} | {there:.1%} |")
    w("")
    # **Signed and gross are different questions and only one of them is
    # the answer.** A signed sum nets a line that moved into Program against
    # one that moved out and reports the residue, which on these ten lines is
    # 68,574.82 — a sixth of what actually changed column. The reader wants
    # both: how much was reassigned, and where it left the return net.
    into = sum(D(r["total"]) * (D(r["program"]) / D(r["total"])
                                - D(r["prior_program"]) / D(r["prior_total"]))
               for r, _, _ in bimodal
               if D(r["program"]) / D(r["total"])
               > D(r["prior_program"]) / D(r["prior_total"]))
    outof = sum(D(r["total"]) * (D(r["prior_program"]) / D(r["prior_total"])
                                 - D(r["program"]) / D(r["total"]))
                for r, _, _ in bimodal
                if D(r["program"]) / D(r["total"])
                < D(r["prior_program"]) / D(r["prior_total"]))
    w(f"Applying the {prior} ratio to those ten lines instead would move "
      f"**{money(outof)} out of Program** and **{money(into)} into it** — "
      f"{money(into + outof)} reassigned, netting {money(abs(into - outof))}. "
      f"The netting is the point: a single figure for the difference would "
      f"report a sixth of what actually changed column.\n")
    w(f"At the whole-return level the two methods land within a few points of "
      f"each other — program {pct(now_prog, now_total)} against "
      f"{pct(pr_prog, pr_total)}, management and general "
      f"{pct(now_mg, now_total)} against {pct(pr_mg, pr_total)} — which is "
      f"worth knowing before anybody treats the line-level differences as "
      f"errors. They are a different allocation basis, and the {period} basis "
      f"is the one recorded on each judgment rather than one ratio applied "
      f"across the return.\n")

    # ── What actually moved ─────────────────────────────────────────
    w(f"### What moved, largest first\n")
    w(f"Total expenses rose {delta(now_total, pr_total).strip('*')} and total "
      f"revenue fell {delta(rev_total, pr_rev).strip('*')}, so the surplus "
      f"went from {money(pr_rev - pr_total)} to "
      f"**{money(rev_total - now_total)}**. Six lines carry most of it.\n")
    movers = sorted(
        ((r, D(r["total"]) - D(r["prior_total"])) for r in all_rows
         if r["part"] == "IX" and (D(r["total"]) or D(r["prior_total"]))),
        key=lambda x: -abs(x[1]))[:8]
    w(f"| line | | {prior} | {period} | change |")
    w("| --- | --- | ---: | ---: | ---: |")
    for r, ch in movers:
        w(f"| **{r['line_id']}** | {r['label'][:54]} | "
          f"{money(r['prior_total'])} | {money(r['total'])} | "
          f"{'+' if ch > 0 else ''}{ch:,.2f} |")
    w("")
    rmovers = sorted(
        ((r, D(r["total"]) - D(r["prior_total"])) for r in all_rows
         if r["part"] == "VIII" and r["line_id"] != "8b"
         and (D(r["total"]) or D(r["prior_total"]))),
        key=lambda x: -abs(x[1]))[:4]
    w(f"And on the revenue side:\n")
    w(f"| line | | {prior} | {period} | change |")
    w("| --- | --- | ---: | ---: | ---: |")
    for r, ch in rmovers:
        w(f"| **{r['line_id'].lstrip('V')}** | {r['label'][:54]} | "
          f"{money(r['prior_total'])} | {money(r['total'])} | "
          f"{'+' if ch > 0 else ''}{ch:,.2f} |")
    w("")

    # ── What the mapping rests on ────────────────────────────────────
    w("## Every account, and the line it lands on\n")
    w("The map is `form_990_account_line`: a transcription of a preparer's "
      "judgment, held as data so it can be read and amended. Longest matching "
      "prefix wins, so a child can be routed away from its parent.\n")
    for r in all_rows:
        got = accounts_on(r["line_id"], period)
        got = [a for a in got if D(a["amount"]) != 0 or a["note"]]
        if not got:
            continue
        w(f"**Line {r['line_id'].lstrip('V')} — {r['label']}** · "
          f"{money(r['total'])}\n")
        for a in got:
            note = f" — {a['note']}" if a["note"] else ""
            w(f"* `{a['account_prefix']}` · {money(a['amount'])}{note}")
        w("")

    # ── What it cannot produce ───────────────────────────────────────
    w("## What this return cannot say, and what it is waiting for\n")
    gaps = [r for r in all_rows if D(r["total"]) == 0 and r["note"]]
    for r in gaps:
        w(f"* **Line {r['line_id'].lstrip('V')} — {r['label']}.** {r['note']}")
    for r in all_rows:
        if r["note"] and D(r["total"]) != 0 and r["part"] == "VIII":
            w(f"* **Line {r['line_id'].lstrip('V')} — {r['label']}** carries "
              f"{money(r['total'])}. {r['note']}")
    w("")
    if walk:
        w("And the steps of the year's own walk that are not finished, which "
          "every document this system produces repeats above its figures:\n")
        for s in walk:
            w(f"* **{s['step']} — {s['state']}.** {s['detail']}")
        w("")
    w("---\n")
    w(f"Generated from the record by `scripts/form_990_comparison.py`. "
      f"Nothing in this run writes to the cost record.")

    path = Path(args.out)
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    print(f"  Part IX   {money(pr_total):>14} -> {money(now_total):>14}")
    print(f"  Part VIII {money(pr_rev):>14} -> {money(rev_total):>14}")
    print(f"  controls  expenses {exp['state']} · revenue {rev['state']} · "
          f"{prior} transcription {pri['state'] if pri else 'NO DATA'}")
    return 0 if exp["state"] == "TIES" and rev["state"] == "TIES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
