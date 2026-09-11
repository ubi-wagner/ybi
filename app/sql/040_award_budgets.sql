-- 040 — what each award budgets, by category
--
-- The zero lines on the America Makes invoices are not noise and not an
-- oversight. Invoice 10018 carries TRAVEL 0.00, MATERIALS 0.00 and
-- CONSULTANT 0.00 in a month when none of those were spent, and it carries
-- them because the invoice lists **the categories the contract allows**, not
-- the categories that had activity.
--
-- Drive AM's Schedule B settles it. Seven lines are budgeted:
--
--     LABOR 583,594 · TRAVEL 40,000 · SUBCONTRACT 0 · MATERIALS 5,000
--     EQUIPMENT 0 · CONSULTANT 60,000 · ODC 415,000  =  1,103,594
--
-- and invoice 10018 carries exactly the five with a non-zero budget.
-- SUBCONTRACT and EQUIPMENT, budgeted at nothing, do not appear at all. The
-- line set mirrors the budget.
--
-- Which means the thing that matters most about that invoice is a *fact about
-- its format*: it has no indirect line because **Schedule B has no indirect
-- line**. That is not a biller who forgot. It is an invoice being faithful to
-- a budget that never provided for indirect at all, on $583,594 of labour —
-- and it is the strongest single piece of evidence the restatement has,
-- because the document YBI issued is itself the record of what it was never
-- allowed to claim.
--
-- Recording the budget makes that checkable rather than remembered, and lets
-- a restated invoice carry the right line set instead of copying whatever the
-- last one happened to have.

CREATE TABLE award_budget (
  award_id        text NOT NULL REFERENCES award ON DELETE CASCADE,
  category        invoice_category NOT NULL,
  federal         numeric(14,2) NOT NULL DEFAULT 0,
  cost_share      numeric(14,2) NOT NULL DEFAULT 0,
  -- Where it was read from. A budget line with no citation is somebody's
  -- recollection of a schedule, which is the same objection as a provision
  -- with no clause.
  citation        text NOT NULL,
  note            text NOT NULL DEFAULT '',
  recorded_by     text NOT NULL DEFAULT '',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (award_id, category),
  CONSTRAINT award_budget_needs_citation CHECK (length(trim(citation)) > 3)
);

COMMENT ON TABLE award_budget IS
  'What an award budgets, by category, as read off its budget schedule. A '
  'category present at zero is allowable and nothing was proposed for it; a '
  'category absent was not in the budget at all. The two are different '
  'things and the invoice format depends on the difference.';

COMMENT ON COLUMN award_budget.federal IS
  'The sponsor-funded amount proposed for this category. Zero means the '
  'category was named in the schedule with nothing against it — which is '
  'why it does not appear on an invoice.';


-- ── Does the invoice show what the contract allows? ──────────────────
--
-- Two things worth knowing, and they are not the same:
--
--   billed_not_budgeted   a category billed that the budget does not fund.
--                         A finding — money claimed outside the budget.
--   budgeted_not_billed   a funded category missing from the invoice. Weaker,
--                         but the format convention says every funded
--                         category appears, so its absence is worth a look.
--
-- INDIRECT and OTHER are exempt from the first test. An indirect line is
-- claimed under a rate or a de minimis provision rather than a budget line —
-- that is the whole subject of the restatement — and OTHER is how these
-- invoices carry a project title rather than a cost.
--
-- `evaluable` is false where no budget has been read into the record, so an
-- award whose schedule nobody has transcribed reads NO DATA rather than
-- passing. Both sides of this comparison are empty sets on an award with no
-- budget, and an empty set matches an empty set perfectly.

CREATE VIEW v_invoice_budget_check AS
WITH funded AS (
  SELECT award_id, category FROM award_budget WHERE federal + cost_share > 0
),
billed AS (
  SELECT i.invoice_id, i.invoice_number, i.award_id, l.category
    FROM invoice i JOIN invoice_line l USING (invoice_id)
   WHERE i.award_id IS NOT NULL
   GROUP BY i.invoice_id, i.invoice_number, i.award_id, l.category
)
SELECT i.invoice_id,
       i.invoice_number,
       i.award_id,
       EXISTS (SELECT 1 FROM award_budget b WHERE b.award_id = i.award_id)
                                                            AS evaluable,
       (SELECT count(*) FROM funded f WHERE f.award_id = i.award_id)
                                                            AS funded_categories,
       (SELECT count(*) FROM billed x WHERE x.invoice_id = i.invoice_id)
                                                            AS billed_categories,
       -- Both lists are NULL, not empty and not full, where no budget has
       -- been read. Without the guard every category on an unread award
       -- reads as "billed outside the budget", which is a finding the data
       -- cannot support: you cannot say a category is unbudgeted when
       -- nobody has read the budget. `evaluable` says which case this is,
       -- and the same rule the control register follows applies — a check
       -- that cannot be evaluated has not passed, and must not fail either.
       CASE WHEN EXISTS (SELECT 1 FROM award_budget b
                          WHERE b.award_id = i.award_id)
            THEN (SELECT array_agg(x.category::text ORDER BY x.category::text)
                    FROM billed x
                   WHERE x.invoice_id = i.invoice_id
                     AND x.category NOT IN ('INDIRECT', 'OTHER')
                     AND NOT EXISTS (SELECT 1 FROM funded f
                                      WHERE f.award_id = x.award_id
                                        AND f.category = x.category))
       END                                                  AS billed_not_budgeted,
       CASE WHEN EXISTS (SELECT 1 FROM award_budget b
                          WHERE b.award_id = i.award_id)
            THEN (SELECT array_agg(f.category::text ORDER BY f.category::text)
                    FROM funded f
                   WHERE f.award_id = i.award_id
                     AND NOT EXISTS (SELECT 1 FROM billed x
                                      WHERE x.invoice_id = i.invoice_id
                                        AND x.category = f.category))
       END                                                  AS budgeted_not_billed
  FROM invoice i
 WHERE i.award_id IS NOT NULL;

COMMENT ON VIEW v_invoice_budget_check IS
  'Whether an invoice shows the categories its contract funds. The zero-value '
  'lines on the America Makes invoices are the allowable categories, not the '
  'month''s activity, so a funded category missing from an invoice is a '
  'departure from the format and a billed category with no funding is money '
  'claimed outside the budget. evaluable is false where no budget schedule '
  'has been read in — an award with no budget cannot fail this and must not '
  'pass it either.';


-- What an award budgets for indirect, stated rather than inferred from an
-- absence. Drive AM's answer is "nothing at all", and the restatement rests
-- on being able to say that from the record.
CREATE VIEW v_award_indirect_provision AS
SELECT a.award_id,
       a.objective_id,
       EXISTS (SELECT 1 FROM award_budget b WHERE b.award_id = a.award_id)
                                                        AS budget_on_file,
       COALESCE((SELECT b.federal + b.cost_share FROM award_budget b
                  WHERE b.award_id = a.award_id AND b.category = 'INDIRECT'),
                0)                                      AS indirect_budgeted,
       COALESCE((SELECT sum(b.federal + b.cost_share) FROM award_budget b
                  WHERE b.award_id = a.award_id
                    AND b.category IN ('LABOR', 'FRINGE')), 0)
                                                        AS labour_budgeted,
       COALESCE((SELECT sum(b.federal + b.cost_share) FROM award_budget b
                  WHERE b.award_id = a.award_id), 0)     AS budget_total
  FROM award a;

COMMENT ON VIEW v_award_indirect_provision IS
  'What each award provides for indirect cost. budget_on_file distinguishes '
  '"budgets nothing for indirect" from "nobody has read the schedule yet", '
  'which an absence alone cannot.';
