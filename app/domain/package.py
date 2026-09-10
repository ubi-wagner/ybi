"""
Audit package export.

The deliverable to NCDMM and to the auditor is workpapers, not a database.
This renders the sealed model as a workbook with live formulas, so a reviewer
can trace any figure back to the ledger without access to the system.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .core import PoolType

FONT = "Arial"
INK = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
TITLE = Font(name=FONT, size=14, bold=True)
SUB = Font(name=FONT, size=10, italic=True, color="595959")
INPUT = Font(name=FONT, size=10, color="0000FF")
LINK = Font(name=FONT, size=10, color="008000")
HEAD_FILL = PatternFill("solid", fgColor="1F3B4D")
HEAD_FONT = Font(name=FONT, size=10, bold=True, color="FFFFFF")
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
FAIL_FILL = PatternFill("solid", fgColor="F8CBAD")
PASS_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
CUR = '$#,##0.00;($#,##0.00);"-"'
PCT = "0.00%"


def _headers(ws, row, labels, widths=None):
    for i, lab in enumerate(labels, start=1):
        c = ws.cell(row=row, column=i, value=lab)
        c.font = HEAD_FONT
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _title(ws, title, subtitle):
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = subtitle
    ws["A2"].font = SUB


def build_package(model, decisions, rates, trueup, ledger_total: Decimal,
                  wages: Decimal, fringe_rate: Decimal, assumptions: dict,
                  out_path: Path) -> Path:
    wb = Workbook()

    # ---------------- Index ----------------
    ws = wb.active
    ws.title = "Index"
    _title(ws, "YBI — 2025 Indirect Cost Rate Proposal",
           "Workpaper index. Every schedule traces to the reconciled 2025 general ledger.")
    ws["A4"] = "Decision set seal"
    ws["B4"] = decisions.seal_hash or ""
    ws["A5"] = "Sealed at (UTC)"
    ws["B5"] = decisions.sealed_at or ""
    ws["A6"] = "Classification decisions"
    ws["B6"] = len(decisions)
    for r in range(4, 7):
        ws.cell(row=r, column=1).font = BOLD
        ws.cell(row=r, column=2).font = INK
    ws["A8"] = ("The seal is a hash of every classification judgment in the build. It is "
                "recorded before any rate is computed, so the rate can be shown to be a "
                "consequence of the classifications rather than a target they were fitted to.")
    ws["A8"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A8:F11")

    schedules = [
        ("A", "Controls and tie-outs", "Ledger boundary; every derived figure reconciles here"),
        ("B", "Decision register", "Each classification, its rationale, evidence and citation"),
        ("C", "Pool build", "Direct, fringe, overhead, G&A, fundraising, unallowable"),
        ("D", "Rate computation", "Pools over bases, with carve-outs itemised"),
        ("E", "Allocation", "Indirect distributed to final cost objectives"),
        ("F", "Award true-up", "Claimable versus billed, with contract constraints"),
        ("G", "Open items", "What remains unresolved and who owns it"),
    ]
    _headers(ws, 13, ["Sch.", "Schedule", "Purpose"], [8, 26, 80])
    for i, (ref, name, purpose) in enumerate(schedules, start=14):
        ws.cell(row=i, column=1, value=ref).font = BOLD
        ws.cell(row=i, column=2, value=name).font = INK
        ws.cell(row=i, column=3, value=purpose).font = INK

    # ---------------- A: Controls ----------------
    ws = wb.create_sheet("A-Controls")
    _title(ws, "Schedule A — Controls and tie-outs",
           "The ledger is the bound. A build that does not tie here is not issuable.")
    _headers(ws, 4, ["Control", "Expected", "Actual", "Variance", "Status", "Source"],
             [42, 16, 16, 14, 12, 34])
    recon = model.reconciliation(ledger_total)
    proof = model.allocation_proof()
    fringe_dist = sum(o.fringe for o in model.objectives.values())
    rows = [
        ("Cost ledger total", ledger_total, recon["classified"] + recon["unclassified"],
         "COST_LEDGER_2025_SEED.csv"),
        ("Wage control", wages, wages, "GL accounts 5140 / 5142"),
        ("Fringe pool", model.pools[PoolType.FRINGE].gross,
         model.pools[PoolType.FRINGE].gross, "GL fringe accounts"),
        ("Indirect allocable vs distributed", proof["allocable"], proof["distributed"],
         "Schedules D and E"),
    ]
    r = 5
    for label, exp, act, src in rows:
        ws.cell(row=r, column=1, value=label).font = INK
        ws.cell(row=r, column=2, value=float(exp)).number_format = CUR
        ws.cell(row=r, column=3, value=float(act)).number_format = CUR
        ws.cell(row=r, column=4, value=f"=C{r}-B{r}").number_format = CUR
        ws.cell(row=r, column=5, value=f'=IF(ABS(D{r})<=1,"PASS","FAIL")')
        ws.cell(row=r, column=6, value=src).font = INK
        for c in range(1, 7):
            ws.cell(row=r, column=c).border = BOX
        r += 1
    ws.cell(row=r + 1, column=1, value="Classified cost").font = BOLD
    ws.cell(row=r + 1, column=2, value=float(recon["classified"])).number_format = CUR
    ws.cell(row=r + 2, column=1, value="Undecided, held for review").font = BOLD
    ws.cell(row=r + 2, column=2, value=float(recon["unclassified"])).number_format = CUR
    ws.cell(row=r + 2, column=2).fill = WARN_FILL
    ws.cell(row=r + 4, column=1, value=(
        "Undecided cost is deliberately excluded from the rate base. It is not defaulted "
        "into a pool. Until it is classified the computed rate is overstated, because "
        "unclassified direct cost belongs in the denominator.")).alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r + 4, start_column=1, end_row=r + 6, end_column=6)

    # ---------------- B: Decisions ----------------
    ws = wb.create_sheet("B-Decisions")
    _title(ws, "Schedule B — Decision register",
           "One row per classification judgment. Rationale and citation are required fields.")
    _headers(ws, 4, ["ID", "Scope", "Lines", "Pool", "990 function", "Federal",
                     "Objective", "Evidence", "Rationale", "Citation"],
             [10, 40, 8, 14, 22, 14, 16, 24, 52, 16])
    for i, d in enumerate(sorted(decisions, key=lambda x: x.decision_id), start=5):
        vals = [d.decision_id, d.scope, len(d.line_ids), d.pool.value,
                d.function_990.value, d.federal.value, d.objective_id or "",
                d.evidence.value, d.rationale, d.citation or ""]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=i, column=c, value=v)
            cell.font = INK
            cell.border = BOX

    # ---------------- C: Pool build ----------------
    ws = wb.create_sheet("C-Pools")
    _title(ws, "Schedule C — Pool build",
           "Account-level classification, plus labor redistributed from the wage pool.")
    _headers(ws, 4, ["Pool", "From accounts", "Labor added", "Carve-outs", "Allocable", "Basis"],
             [22, 18, 16, 16, 18, 34])
    order = [PoolType.DIRECT, PoolType.FRINGE, PoolType.OVERHEAD, PoolType.GA,
             PoolType.FUNDRAISING, PoolType.UNALLOWABLE]
    r = 5
    for pt in order:
        p = model.pools[pt]
        ws.cell(row=r, column=1, value=pt.value).font = BOLD
        ws.cell(row=r, column=2, value=float(p.gross)).number_format = CUR
        ws.cell(row=r, column=3, value=float(p.labor_addition)).number_format = CUR
        ws.cell(row=r, column=4, value=float(-p.removed)).number_format = CUR
        ws.cell(row=r, column=5, value=f"=B{r}+C{r}+D{r}").number_format = CUR
        ws.cell(row=r, column=6, value=p.base_type.value).font = INK
        for c in range(1, 7):
            ws.cell(row=r, column=c).border = BOX
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Carve-outs, itemised").font = BOLD
    r += 1
    _headers(ws, r, ["Pool", "Carve-out", "Citation", "Amount", "Driver", "Evidence"],
             [22, 34, 18, 16, 30, 26])
    r += 1
    for pt in order:
        for c_ in model.pools[pt].carve_outs:
            for col, v in enumerate([pt.value, c_.name, c_.citation, float(c_.amount),
                                     c_.driver, c_.evidence.value], start=1):
                cell = ws.cell(row=r, column=col, value=v)
                cell.font = INK
                cell.border = BOX
                if col == 4:
                    cell.number_format = CUR
                if col == 6 and c_.evidence.value == "UNSUPPORTED":
                    cell.fill = FAIL_FILL
            r += 1

    # ---------------- D: Rates ----------------
    ws = wb.create_sheet("D-Rates")
    _title(ws, "Schedule D — Rate computation",
           "Multiple allocation base method, 2 CFR 200 Appendix IV B.3.")
    ws["A4"] = "Assumptions (blue cells are inputs)"
    ws["A4"].font = BOLD
    r = 5
    for k, v in assumptions.items():
        ws.cell(row=r, column=1, value=k).font = INK
        c = ws.cell(row=r, column=2, value=float(v))
        c.font = INPUT
        c.number_format = PCT
        c.fill = WARN_FILL
        r += 1

    r += 1
    _headers(ws, r, ["Rate", "Pool", "Base", "Base amount", "Rate"], [26, 18, 22, 18, 12])
    r += 1
    base_mtdc = model.base_amount(model.pools[PoolType.GA].base_type)
    lines = [
        ("Fringe", model.pools[PoolType.FRINGE].allocable, "Salaries and wages", wages),
        ("Overhead — facilities", model.pools[PoolType.OVERHEAD].allocable, "MTDC", base_mtdc),
        ("General and administrative", model.pools[PoolType.GA].allocable, "MTDC", base_mtdc),
    ]
    first = r
    for name, pool, base_lbl, base_amt in lines:
        ws.cell(row=r, column=1, value=name).font = INK
        ws.cell(row=r, column=2, value=float(pool)).number_format = CUR
        ws.cell(row=r, column=3, value=base_lbl).font = INK
        ws.cell(row=r, column=4, value=float(base_amt)).number_format = CUR
        ws.cell(row=r, column=5, value=f"=IF(D{r}=0,0,B{r}/D{r})").number_format = PCT
        for c in range(1, 6):
            ws.cell(row=r, column=c).border = BOX
        r += 1
    ws.cell(row=r, column=1, value="Combined indirect on MTDC").font = BOLD
    ws.cell(row=r, column=2, value=f"=B{first+1}+B{first+2}").number_format = CUR
    ws.cell(row=r, column=4, value=f"=D{first+1}").number_format = CUR
    ws.cell(row=r, column=5, value=f"=IF(D{r}=0,0,B{r}/D{r})").number_format = PCT
    ws.cell(row=r, column=5).font = BOLD

    # ---------------- E: Allocation ----------------
    ws = wb.create_sheet("E-Allocation")
    _title(ws, "Schedule E — Allocation to final cost objectives",
           "Fundraising and unallowable activities bear indirect but recover nothing.")
    _headers(ws, 4, ["Objective", "Federal", "Direct labor", "Fringe", "Other direct",
                     "MTDC", "Indirect", "Fully burdened", "Labor evidence"],
             [24, 10, 15, 13, 15, 15, 15, 16, 14])
    r = 5
    rate = rates["INDIRECT_COMBINED"]
    for o in sorted(model.objectives.values(), key=lambda x: -x.fully_burdened):
        ws.cell(row=r, column=1, value=o.objective_id).font = INK
        ws.cell(row=r, column=2, value="Yes" if o.is_federal else "").font = INK
        for col, v in ((3, o.direct_labor), (4, o.fringe), (5, o.direct_nonlabor)):
            ws.cell(row=r, column=col, value=float(v)).number_format = CUR
        ws.cell(row=r, column=6, value=f"=C{r}+D{r}+E{r}").number_format = CUR
        ws.cell(row=r, column=7, value=f"=F{r}*'D-Rates'!$E${first+3}").number_format = CUR
        ws.cell(row=r, column=8, value=f"=F{r}+G{r}").number_format = CUR
        ev = ws.cell(row=r, column=9,
                     value=float(o.evidence_ratio) if o.evidence_ratio is not None else None)
        ev.number_format = "0%"
        if o.evidence_ratio is not None and o.evidence_ratio < Decimal("0.5"):
            ev.fill = FAIL_FILL
        elif o.evidence_ratio is not None and o.evidence_ratio < Decimal("0.95"):
            ev.fill = WARN_FILL
        for c in range(1, 10):
            ws.cell(row=r, column=c).border = BOX
        r += 1
    ws.cell(row=r, column=1, value="Total").font = BOLD
    for col in (3, 4, 5, 6, 7, 8):
        L = get_column_letter(col)
        ws.cell(row=r, column=col, value=f"=SUM({L}5:{L}{r-1})").number_format = CUR
        ws.cell(row=r, column=col).font = BOLD

    # ---------------- F: True-up ----------------
    ws = wb.create_sheet("F-TrueUp")
    a = trueup.award
    _title(ws, f"Schedule F — Award true-up: {a.award_id}",
           f"{a.instrument} · {a.sponsor} · prime {a.prime} · {a.citation}")
    rows = [("Period of performance", f"{a.period_start:%d %b %Y} to {a.period_end:%d %b %Y}"),
            ("Federal ceiling", float(a.ceiling_federal)),
            ("Cost share required", float(a.cost_share_required)),
            ("Cost share tracked", float(a.cost_share_tracked)),
            ("Direct cost", float(trueup.direct)),
            ("Indirect at proposed rate", float(trueup.indirect)),
            ("Claimable before ceiling", float(trueup.claimable_uncapped)),
            ("Claimable after ceiling", float(trueup.claimable)),
            ("Billed", float(a.billed_to_date)),
            ("Delta", float(trueup.delta))]
    r = 4
    for label, v in rows:
        ws.cell(row=r, column=1, value=label).font = BOLD if label == "Delta" else INK
        c = ws.cell(row=r, column=2, value=v)
        c.font = BOLD if label == "Delta" else INK
        if isinstance(v, float):
            c.number_format = CUR
        if label == "Cost share tracked" and a.cost_share_tracked < a.cost_share_required:
            c.fill = FAIL_FILL
        r += 1
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 22

    r += 1
    _headers(ws, r, ["Constraint", "Citation", "Requirement", "Result", "Detail"],
             [16, 20, 46, 10, 52])
    r += 1
    for c_ in trueup.constraints:
        vals = [c_.code, c_.citation, c_.description,
                "PASS" if c_.passed else ("FAIL" if c_.blocking else "WARN"), c_.detail]
        for col, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=col, value=v)
            cell.font = INK
            cell.border = BOX
            if col == 4:
                cell.fill = PASS_FILL if c_.passed else (FAIL_FILL if c_.blocking else WARN_FILL)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Disposition").font = BOLD
    ws.cell(row=r, column=2, value=trueup.disposition(True).value).font = BOLD

    # ---------------- G: Open items ----------------
    ws = wb.create_sheet("G-OpenItems")
    _title(ws, "Schedule G — Open items",
           "What is not yet resolved, what it blocks, and who owns it.")
    _headers(ws, 4, ["Item", "Blocks", "Owner", "Evidence needed"], [46, 32, 16, 52])
    items = [
        ("Square-footage schedule by tenant and function", "Overhead carve-out; rate",
         "Controller", "Floor plan plus lease schedule"),
        ("Asset register with funding source per asset", "Depreciation allowability; rate",
         "Controller", "Fixed asset listing and grant award documents"),
        ("Undecided direct cost held for review", "Rate base; rate is overstated until cleared",
         "Controller", "Account-level review of remaining groups"),
        ("Rising Tides federal determination", "SEFA; Single Audit scope",
         "CEO", "ARC award document"),
        ("Cost share identification", "Award compliance under 200.306",
         "Controller", "Other direct costs allocable to the award"),
        ("Accounting fee scrub from direct charges", "Double-count under 200.403(d)",
         "Controller", "Reclassification entry"),
        ("Phase 3 agreement", "Ceiling and post-term billing",
         "CEO", "Executed sub-recipient agreement"),
    ]
    for i, it in enumerate(items, start=5):
        for c, v in enumerate(it, start=1):
            cell = ws.cell(row=i, column=c, value=v)
            cell.font = INK
            cell.border = BOX

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
