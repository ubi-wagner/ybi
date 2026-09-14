-- 052: a budget schedule has a printed total, and it is a different question
-- from the award's ceiling.
--
-- Three of the four America Makes schedules are now transcribed rather than
-- one, and reading them raised two things that `sum(award_budget.federal)`
-- alone cannot tell apart.
--
-- **Last Tactical Mile's Schedule B does not foot to its own printed
-- total.** The federal categories add to $899,500.76 against a printed
-- $899,500, and the cost-share categories to $513,065.12 against $513,065 —
-- rounding inside the schedule, 88 cents across the two. That is a fact
-- about the executed agreement and not about this system, and the rule this
-- codebase already applies to every QuickBooks export applies here too:
-- **every printed subtotal must equal what sits under it**, and where it
-- does not, the difference is named rather than smoothed. A loader that
-- quietly wrote 899,500.00 into LABOR's neighbours to make it come out would
-- be inventing a budget.
--
-- **Hybrid Phase 2's schedule is $500,043 and its ceiling is $512,409.**
-- Both are right. The schedule is the one attached to the agreement executed
-- on 8 September 2023; the ceiling is that figure as amended by Modification
-- 001 of 22 January 2026, which `049` brought into the register. Comparing
-- the schedule's categories against the current ceiling would report a
-- $12,366 failure on a document that is simply older than the amendment.
--
-- So the schedule's own header figures are recorded beside it, and the two
-- questions are asked separately:
--
--   does the schedule foot?          categories against the printed total
--   does it reach the ceiling?       printed total against award.ceiling_federal
--
-- The second is allowed to differ and says why in `note`; the first is not.

CREATE TABLE award_budget_schedule (
  award_id            text PRIMARY KEY REFERENCES award ON DELETE CASCADE,
  citation            text NOT NULL,
  -- What the schedule prints as its own totals, transcribed from the page.
  printed_federal     numeric(14,2) NOT NULL,
  printed_cost_share  numeric(14,2) NOT NULL DEFAULT 0,
  -- Why the printed total may differ from the award's current ceiling. A
  -- modification, a descoping, an option not exercised. Empty means they are
  -- expected to agree.
  ceiling_differs_because text NOT NULL DEFAULT '',
  note                text NOT NULL DEFAULT '',
  recorded_by         text NOT NULL DEFAULT '',
  recorded_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT schedule_needs_citation CHECK (length(trim(citation)) > 3),
  CONSTRAINT schedule_totals_sane
    CHECK (printed_federal >= 0 AND printed_cost_share >= 0)
);

COMMENT ON TABLE award_budget_schedule IS
  'The header figures a budget schedule prints for itself, so "do the '
  'categories add up to what the page says" and "does the page reach the '
  'award ceiling" are two questions rather than one. The second is allowed '
  'to differ — a modification moves a ceiling and not a schedule — and must '
  'say why.';


CREATE VIEW v_award_budget_check AS
SELECT a.award_id,
       a.objective_id,
       s.citation,
       (SELECT count(*) FROM award_budget b
         WHERE b.award_id = a.award_id)                      AS categories,
       COALESCE((SELECT sum(b.federal) FROM award_budget b
                  WHERE b.award_id = a.award_id), 0)         AS categories_federal,
       COALESCE((SELECT sum(b.cost_share) FROM award_budget b
                  WHERE b.award_id = a.award_id), 0)         AS categories_cost_share,
       s.printed_federal,
       s.printed_cost_share,
       a.ceiling_federal,
       a.cost_share_required,
       -- Does the schedule foot? The printed-subtotal rule, applied to an
       -- agreement instead of to a QuickBooks export.
       COALESCE((SELECT sum(b.federal) FROM award_budget b
                  WHERE b.award_id = a.award_id), 0)
         - s.printed_federal                                 AS foots_by,
       COALESCE((SELECT sum(b.cost_share) FROM award_budget b
                  WHERE b.award_id = a.award_id), 0)
         - s.printed_cost_share                              AS cost_share_foots_by,
       -- Does the schedule reach the ceiling? Allowed to differ, with a
       -- reason. A blank reason and a difference is a question nobody has
       -- answered.
       s.printed_federal - a.ceiling_federal                 AS against_ceiling,
       s.ceiling_differs_because,
       s.note,
       CASE
         WHEN s.award_id IS NULL                  THEN 'NO SCHEDULE READ'
         WHEN abs(COALESCE((SELECT sum(b.federal) FROM award_budget b
                             WHERE b.award_id = a.award_id), 0)
                  - s.printed_federal) > 0.005    THEN 'DOES NOT FOOT'
         WHEN s.printed_federal <> a.ceiling_federal
              AND length(trim(s.ceiling_differs_because)) = 0
                                                  THEN 'CEILING UNEXPLAINED'
         ELSE 'TIES'
       END                                                   AS state,
       -- An award whose schedule nobody has been through cannot be said to
       -- tie, for the same reason a control over no data has not passed.
       s.award_id IS NOT NULL                                AS evaluable
  FROM award a
  LEFT JOIN award_budget_schedule s ON s.award_id = a.award_id;

COMMENT ON VIEW v_award_budget_check IS
  'Per award: whether its budget schedule adds up to the total printed on '
  'it, and whether that total reaches the ceiling in the register. The first '
  'may not differ; the second may, and has to say why — a modification moves '
  'a ceiling and leaves the schedule where it was. NO SCHEDULE READ is not a '
  'pass.';


-- ── And a third register of one fact ─────────────────────────────────
--
-- `award_budget_line` was created in `001` and written once, in `004`, with
-- Hybrid Phase 2's four Schedule B categories. **Nothing has ever read it**
-- — not a view, not a route, not a script. `v_invoice_budget_check` and
-- `v_award_indirect_provision` both read `award_budget` (`040`), so Hybrid
-- reported `evaluable = false` for the whole engagement while the numbers
-- sat in the database from the first migration.
--
-- The third instance of this shape after `space_partition` and
-- `rate.superseded_by`, and the same lesson: a table that looks usable and
-- is filled by nothing is an invitation to fill it again. The four rows are
-- transcribed into `award_budget` by `scripts/load_award_budgets.py`, from
-- the schedule itself rather than from these rows — the page is the source,
-- and a copy of a copy is not a transcription.
DROP TABLE award_budget_line;
