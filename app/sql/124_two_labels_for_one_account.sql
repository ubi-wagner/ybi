-- 124 — the general ledger and the balance sheet have two names for one account
--
-- The ledger prints the accumulated surplus as **Retained Earnings** and the
-- balance sheet prints it as **3000 Fund Balance**. Same account, same
-- balance, two labels — and until somebody says so, the balance sheet cannot
-- be proved off the ledger: `v_gl_bs_account` reports an account the sheet
-- omits which does not close at zero, at 13,535,775.43.
--
-- It lived in `scripts/reconcile.py --record` as a hard-coded pair with its
-- reason attached, which is the right *content* in the wrong *place*. It is
-- not a judgment about cost and it is not a reconciling item: it is a fact
-- about what two documents call one thing, and the books cannot agree with
-- themselves without it. Anything that only exists because a person
-- remembered to run a script does not survive a recovery — so the boot, which
-- now transcribes the books themselves, would come back with the ledger in
-- and the balance sheet unprovable.
--
-- `recorded_by` is the migration and not a person, for the same reason
-- `deployment bootstrap` is used elsewhere: naming somebody here would put
-- their signature on a reading they were not present for.
--
-- `reconcile.py --record` still posts it and is now a no-op on a record that
-- has it, which is what re-runnable means. The reconciling **items** stay
-- with a person: naming a difference is the controller's act and `/reconcile`
-- has the Propose button for it.

INSERT INTO account_alias
  (period, gl_account, statement, statement_account, reason, recorded_by)
SELECT p.period, 'Retained Earnings', 'BALANCE_SHEET', '3000 Fund Balance',
       'The general ledger prints the accumulated surplus as Retained '
       'Earnings and the balance sheet prints it as 3000 Fund Balance. '
       'Same account, same balance, two labels.',
       'migration 124'
  FROM fiscal_period p
 WHERE p.period = '2025'
ON CONFLICT (period, gl_account, statement) DO NOTHING;
