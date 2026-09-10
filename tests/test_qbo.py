"""QBO parsing. No database required."""

import textwrap
from decimal import Decimal
from pathlib import Path

from app.domain.qbo import QBO_GENERAL_LEDGER, parse_general_ledger, qbo_amount

REPORT = textwrap.dedent("""\
    Youngstown Business Incubator,,,,,,,,
    General Ledger,,,,,,,,
    "January 1 - December 31, 2025",,,,,,,,
    ,,,,,,,,
    ,Date,Transaction Type,Num,Name,Memo/Description,Split,Amount,Balance
    5010 Depreciation Expense,,,,,,,,
    ,01/01/2025,,,,Beginning Balance,,,0.00
    ,01/31/2025,Journal Entry,JE-1,,Monthly depreciation,1500 Accum,"70,865.24","70,865.24"
    ,02/28/2025,Journal Entry,JE-2,,Monthly depreciation,1500 Accum,"70,865.24","141,730.48"
    Total for 5010 Depreciation Expense,,,,,,,"141,730.48",
    ,,,,,,,,
    5250 Meals & Entertainment,,,,,,,,
    ,03/04/2025,Expense,,Acme Catering,Board lunch,1000 Checking,"1,200.00","1,200.00"
    ,03/09/2025,Credit,,Acme Catering,Refund,1000 Checking,"(200.00)","1,000.00"
    Total for 5250 Meals & Entertainment,,,,,,,"1,000.00",
    """)


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "gl.csv"
    p.write_text(REPORT, encoding="utf-8")
    return p


def test_amount_formats():
    # Decimal throughout — a float in a cost model produces variances that
    # take hours to chase down.
    assert qbo_amount("1,234.56") == Decimal("1234.56")
    assert qbo_amount("(1,234.56)") == Decimal("-1234.56")
    assert qbo_amount("$1,234.56") == Decimal("1234.56")
    assert qbo_amount("") == Decimal(0)
    assert qbo_amount(None) == Decimal(0)


def test_section_headers_become_accounts(tmp_path):
    st = parse_general_ledger(_write(tmp_path), QBO_GENERAL_LEDGER)
    accounts = {l.account for l in st.lines}
    assert accounts == {"5010 Depreciation Expense", "5250 Meals & Entertainment"}


def test_beginning_balance_is_not_a_transaction(tmp_path):
    st = parse_general_ledger(_write(tmp_path), QBO_GENERAL_LEDGER)
    assert len(st.lines) == 4
    assert all("Beginning Balance" not in l.memo for l in st.lines)


def test_subtotals_reconcile(tmp_path):
    st = parse_general_ledger(_write(tmp_path), QBO_GENERAL_LEDGER)
    for account, printed, parsed, variance in st.subtotal_check():
        assert abs(variance) < 0.005, f"{account} off by {variance}"


def test_total_rows_are_not_data(tmp_path):
    st = parse_general_ledger(_write(tmp_path), QBO_GENERAL_LEDGER)
    assert st.total == Decimal("142730.48")
    assert len(st.subtotals) == 2


def test_customer_job_becomes_objective_hint(tmp_path):
    p = tmp_path / "gl2.csv"
    p.write_text(REPORT.replace("Acme Catering", "NCDMM - America Makes:Drive AM"),
                 encoding="utf-8")
    st = parse_general_ledger(p, QBO_GENERAL_LEDGER)
    hints = {l.objective_hint for l in st.lines if l.objective_hint}
    assert hints == {"Drive AM"}
