-- Columns the import pipeline and classification queue rely on.
-- Kept as a separate migration so 001_core.sql stays readable as the design.

ALTER TABLE ledger_line
  ADD COLUMN IF NOT EXISTS customer_job_hint text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS class_name        text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS location          text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ledger_line_hint_idx
  ON ledger_line (period, customer_job_hint)
  WHERE customer_job_hint <> '';

-- The UPDATE rule in 001 blocks amendments, which is intended for data but
-- would also block the ALTER above from backfilling. Nothing to backfill on a
-- fresh install; on an existing one, drop the rule, backfill, recreate.
