-- 089 · The record is 2025, and the three April-2026 invoices were examples
--
-- *"Get rid of the 2026 examples unless they were for the period 2025 — they
-- were examples and will be re-entered when they do 2026."*
--
-- `YBI_Invoices_1.pdf` carried three invoices — 10018 Drive AM, 10023 Hybrid
-- Phase II, 10039 Last Tactical Mile, all dated 1 May 2026 for April 2026
-- service — and `load_invoices.py` filed them. They were a sample of the
-- *shape* of an America Makes invoice, loaded before the year's own register
-- existed, and they are not YBI's 2025 billing. The 2025 register holds 61
-- invoices across six objectives and is loaded from the invoices as issued.
--
-- **This is not editing history.** `invoice_no_delete` exists for a reason
-- and states it: *"Issued invoices are what the pass-through entity holds.
-- Correct by issuing a restatement or a credit, never by editing history."*
-- That premise is about invoices YBI issued and a sponsor is holding. These
-- three are example data in a register of record, which is the opposite case:
-- leaving them as `WITHDRAWN` would assert YBI withdrew three invoices NCDMM
-- holds, which is a thing that did not happen. So the trigger is stood down
-- for this statement and put straight back, and the removal is recorded.
--
-- What goes with them, and why:
--
--   * their 15 `invoice_line` rows, by cascade;
--   * **every restatement measured against them** — all six on the record,
--     three standing as claims. `088` gave `v_restatement.still_agrees` so a
--     claim overtaken by its register says so; a claim whose whole
--     population was example data does not need saying so, it needs to not
--     be there. `restatement_line.invoice_id` has no cascade, so these are
--     removed first and deliberately.
--
-- What stays, and this is the half worth reading. Twelve documents carry a
-- period that is not 2025 and **every one of them supports 2025**: the five
-- executed agreements the year was worked under (2021–2024), two prior-year
-- Forms 990 and two audited statements an auditor reads as comparatives,
-- Hybrid's **Modification 001 of 22 January 2026** — which is what
-- `v_award_ceiling_check` ties the fourth award on — and
-- `2026_YBI_Fixed-Asset-Schedule.xls`, which is where the 263 assets came
-- from. A governing document carries its own date; only a *transaction*
-- belongs to a period. The ledger, the assets, the labour distribution and
-- every decision are 2025 and nothing else, and
-- `tests/test_the_record_is_one_year.py` holds that from the schema rather
-- than from a list here.
--
-- And what this costs, said out loud rather than discovered later: the
-- `TERM` failure on Drive AM — *the whole of invoice 10018's $37,593.90
-- bills April 2026 service against an award that ended 4 January 2026* — was
-- a finding about example data and goes with it. `INVOICE_GAP_TABLE.md` and
-- `AMERICA_MAKES_RESTATEMENT.md` §2 both rest on these three and carry a
-- notice saying so.

DO $$
DECLARE
  ex     uuid[];
  n      integer;
  killed integer;
BEGIN
  -- Self-limiting: exactly the three, by number, period and total. On a
  -- database where they never landed this finds nothing and does nothing —
  -- which is the state a clean seed is in once `load_awards.py` stops
  -- loading them. Anything that matches partially is a database this
  -- migration does not understand, and it refuses rather than guessing.
  SELECT array_agg(invoice_id), count(*) INTO ex, n
    FROM invoice
   WHERE period = '2026'
     AND (invoice_number, total) IN (('10018', 37593.90),
                                     ('10023',  1374.00),
                                     ('10039', 18993.52));

  IF n = 0 THEN
    RAISE NOTICE '089: no example invoices on this database.';
    RETURN;
  END IF;
  IF n <> 3 THEN
    RAISE EXCEPTION '089 found % of the three example invoices, not 3. '
                    'Refusing to guess which rows are examples.', n;
  END IF;

  -- Every restatement whose whole population is example data. Expressed as
  -- "has a line, and every line names one of the three" rather than "has any
  -- such line", so a restatement that somehow mixed real and example
  -- invoices would survive and be visible rather than vanish.
  WITH doomed AS (
    SELECT r.restatement_id
      FROM restatement r
      JOIN restatement_line l USING (restatement_id)
     GROUP BY r.restatement_id
    HAVING count(*) FILTER (WHERE l.invoice_id = ANY(ex)) = count(*)
  )
  INSERT INTO audit_log (actor, action, entity, entity_id, before_state, reason)
  SELECT 'migration 089', 'RESTATEMENT_REMOVE', 'restatement',
         r.restatement_id::text,
         to_jsonb(r) - 'basis',
         'Measured only the three April 2026 example invoices, which were a '
         'sample of the invoice format and not YBI''s billing.'
    FROM restatement r WHERE r.restatement_id IN (SELECT restatement_id FROM doomed);

  -- `restatement` is append-only for the same reason and with the same
  -- premise: *correct by superseding, never by editing* is about a position
  -- somebody took. A measurement of example data is not a position.
  ALTER TABLE restatement DISABLE TRIGGER restatement_no_delete;
  DELETE FROM restatement r
   WHERE r.restatement_id IN (
     SELECT r2.restatement_id
       FROM restatement r2 JOIN restatement_line l USING (restatement_id)
      GROUP BY r2.restatement_id
     HAVING count(*) FILTER (WHERE l.invoice_id = ANY(ex)) = count(*));
  GET DIAGNOSTICS killed = ROW_COUNT;
  ALTER TABLE restatement ENABLE TRIGGER restatement_no_delete;
  RAISE NOTICE '089: % restatement(s) removed.', killed;

  INSERT INTO audit_log (actor, action, entity, entity_id, before_state, reason)
  SELECT 'migration 089', 'INVOICE_REMOVE', 'invoice', i.invoice_id::text,
         jsonb_build_object('invoice_number', i.invoice_number,
                            'period', i.period, 'objective_id', i.objective_id,
                            'award_id', i.award_id,
                            'invoice_date', i.invoice_date, 'total', i.total),
         'April 2026 example invoice from YBI_Invoices_1.pdf. The record is '
         '2025; 2026 billing is entered when 2026 is worked.'
    FROM invoice i WHERE i.invoice_id = ANY(ex);

  ALTER TABLE invoice DISABLE TRIGGER invoice_no_delete;
  DELETE FROM invoice WHERE invoice_id = ANY(ex);
  GET DIAGNOSTICS killed = ROW_COUNT;
  ALTER TABLE invoice ENABLE TRIGGER invoice_no_delete;
  RAISE NOTICE '089: % example invoice(s) removed.', killed;
END $$;
