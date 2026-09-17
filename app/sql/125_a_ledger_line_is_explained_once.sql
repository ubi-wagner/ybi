-- A ledger line is explained once.
--
-- `reconciling_lines_total` has always checked that the lines named by an
-- item add to the amount it claims — which is what separates a reconciling
-- item from a plug. What nothing checked is whether the *same* line had
-- already been named by another item. Each item ties to itself perfectly
-- and the difference is explained several times over.
--
-- Found on a deployed record inside an hour of the payroll register gaining
-- a screen: `Name this` on the Bacon line, pressed four times, recorded four
-- SOURCE_DEFECT items of -45,000.00 each. Named read (180,000.00) against a
-- difference of 45,053.23 and the control went (134,946.77) in the other
-- direction — over-explained, which reads exactly like a plug and is worse,
-- because every individual item is impeccable.
--
-- It is the supersession rule in a register that had never needed it: a
-- ledger line carries one live explanation, the way a ledger line carries
-- one live decision (`one_live_decision_per_unit`) and a person carries one
-- live grant per charge code. Retracted items do not hold a line, because a
-- retraction is how this register expresses a correction.
--
-- A partial unique index cannot say it: liveness is `retracted_at` on
-- `reconciling_item`, a different table, which is the same reason `082`'s
-- one-live-certificate rule is a trigger rather than an index.

CREATE OR REPLACE FUNCTION a_ledger_line_is_explained_once() RETURNS trigger AS $$
DECLARE held bigint;
BEGIN
  SELECT rl.item_id INTO held
    FROM reconciling_item_line rl
    JOIN reconciling_item i ON i.item_id = rl.item_id
   WHERE rl.line_id = NEW.line_id
     AND rl.item_id <> NEW.item_id
     AND i.retracted_at IS NULL
   ORDER BY rl.item_id
   LIMIT 1;

  IF held IS NOT NULL THEN
    RAISE EXCEPTION
      'Ledger line % is already named by reconciling item %.', NEW.line_id, held
      USING ERRCODE = 'unique_violation',
            HINT = 'A difference is explained once. Retract that item first '
                   'if this one is meant to replace it.';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reconciling_line_explained_once ON reconciling_item_line;
CREATE TRIGGER reconciling_line_explained_once
  BEFORE INSERT ON reconciling_item_line
  FOR EACH ROW EXECUTE FUNCTION a_ledger_line_is_explained_once();

-- And the rows already recorded. Self-limiting, in `089`'s shape: it acts
-- only where two or more LIVE items name one line, keeps the earliest — the
-- one that was correct when it was made — and retracts the rest with the
-- reason on the row. It does not delete: a position somebody took stays on
-- the record, and retraction is what this register already uses to correct.
--
-- On a database where nobody double-pressed, this does nothing and says so
-- by touching no rows.
WITH duplicated AS (
  SELECT rl.line_id, rl.item_id,
         row_number() OVER (PARTITION BY rl.line_id ORDER BY rl.item_id) AS seq
    FROM reconciling_item_line rl
    JOIN reconciling_item i ON i.item_id = rl.item_id
   WHERE i.retracted_at IS NULL
),
surplus AS (
  SELECT DISTINCT item_id FROM duplicated WHERE seq > 1
)
UPDATE reconciling_item i
   SET retracted_at = now(),
       retracted_by = 'migration 125',
       retracted_reason =
         'A second live reconciling item naming a ledger line another item '
         'already explained. Every such item ties to itself, so nothing '
         'refused it and the difference read as explained several times '
         'over. The earliest item naming each line stands; this one is '
         'retracted rather than deleted, because it is a position somebody '
         'took. Recorded by migration 125, which also closes the hole.'
  FROM surplus s
 WHERE i.item_id = s.item_id
   AND i.retracted_at IS NULL;

INSERT INTO audit_log (actor, action, entity, entity_id, after_state, reason)
SELECT 'migration 125', 'RECONCILE_RETRACT', 'reconciling_item',
       i.item_id::text,
       jsonb_build_object('amount', i.amount, 'control', i.control,
                          'from', i.from_account, 'to', i.to_account),
       'Retracted as a duplicate explanation of a ledger line already named.'
  FROM reconciling_item i
 WHERE i.retracted_by = 'migration 125';
