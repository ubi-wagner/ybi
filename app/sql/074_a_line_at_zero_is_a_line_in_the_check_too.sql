-- 074 — the budget check could not see the restatement's own exposure
--
-- `040` exempted INDIRECT and OTHER from `billed_not_budgeted`, and said why:
--
--     "An indirect line is claimed under a rate or a de minimis provision
--      rather than a budget line — that is the whole subject of the
--      restatement"
--
-- That was true of the record it was written against. It is not true now.
-- `052` transcribed all four America Makes schedules and **two of them budget
-- INDIRECT** — ICAM at $27,500 and Last Tactical Mile at $81,772.76 — while
-- Drive AM's and Hybrid's contain no INDIRECT category at all. So an indirect
-- line is a budget line on two of these awards and is outside the schedule on
-- the other two, and the exemption means the check cannot say which.
--
-- Measured, not reasoned about: a $16,537.56 indirect line added to invoice
-- 10018, on an award whose Schedule B has no INDIRECT category, produces an
-- empty `billed_not_budgeted`. That is the single largest thing the
-- restatement puts on an invoice, on the award with the largest variance,
-- and the one view built to catch it is blind to it.
--
-- **And `funded` conflated two facts the record keeps apart.** It read
-- `federal + cost_share > 0`, so a category the schedule *names at zero* was
-- indistinguishable from one the schedule never names. The rule is written
-- down and this view was the exception to it:
--
--     A category at zero was named in the schedule with nothing against it;
--     a category absent was not in the schedule.
--
-- Which is why invoice 10039 reported `billed_not_budgeted = {MATERIALS,
-- TRAVEL}` — two categories Last Tactical Mile's Schedule B *does* name, at
-- zero, with $0.00 billed against them. A flag with no money behind it, on
-- the one invoice that has a real exposure, while `OTHER` — genuinely absent
-- from that schedule — went unreported because it was exempt.
--
-- Three facts, kept apart:
--
--   billed_outside_the_schedule   the schedule never names this category.
--                                 The finding. INDIRECT is no longer exempt.
--   billed_against_a_zero_line    the schedule names it, at zero, and the
--                                 invoice carries money against it. Also a
--                                 finding, and a different one: the category
--                                 was available and unfunded.
--   budgeted_not_billed           a *funded* category missing from the
--                                 invoice. Unchanged, and still the weak
--                                 one — the format convention says every
--                                 funded category appears.
--
-- A category named at zero and billed at zero is now none of the three,
-- which is the whole point: *a line at zero is a line*, and 10018 carries
-- three of them because Drive AM's Schedule B does.
--
-- `OTHER` stays out of `billed_outside_the_schedule` only where it carries
-- nothing: these invoices use it to print a project title rather than a
-- cost, and a title is not a claim. With money against it, it is a claim
-- outside the schedule like any other.
--
-- `evaluable` is unchanged and still guards every list, because both sides
-- of this comparison are empty sets on an award nobody has transcribed.

DROP VIEW IF EXISTS v_invoice_budget_check;

CREATE VIEW v_invoice_budget_check AS
WITH named AS (
  -- Every category the schedule names, at whatever figure. A line at zero
  -- is a line.
  SELECT award_id, category, federal + cost_share AS budgeted
    FROM award_budget
),
funded AS (
  SELECT award_id, category FROM award_budget WHERE federal + cost_share > 0
),
billed AS (
  SELECT i.invoice_id, i.invoice_number, i.award_id, l.category,
         sum(l.amount) AS amount
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
       (SELECT count(*) FROM named n WHERE n.award_id = i.award_id)
                                                            AS named_categories,
       (SELECT count(*) FROM billed x WHERE x.invoice_id = i.invoice_id)
                                                            AS billed_categories,
       -- Billed a category the schedule does not contain. INDIRECT belongs
       -- here like anything else: it is a budget line on ICAM and on LTM and
       -- absent from Drive AM and Hybrid, and which of those is true is
       -- exactly what a reader needs told.
       CASE WHEN EXISTS (SELECT 1 FROM award_budget b
                          WHERE b.award_id = i.award_id)
            THEN (SELECT array_agg(x.category::text ORDER BY x.category::text)
                    FROM billed x
                   WHERE x.invoice_id = i.invoice_id
                     AND NOT (x.category = 'OTHER' AND x.amount = 0)
                     AND NOT EXISTS (SELECT 1 FROM named n
                                      WHERE n.award_id = x.award_id
                                        AND n.category = x.category))
       END                                       AS billed_outside_the_schedule,
       -- Named in the schedule at zero, with money against it on the
       -- invoice. Available and unfunded is a different finding from absent.
       CASE WHEN EXISTS (SELECT 1 FROM award_budget b
                          WHERE b.award_id = i.award_id)
            THEN (SELECT array_agg(x.category::text ORDER BY x.category::text)
                    FROM billed x
                    JOIN named n ON n.award_id = x.award_id
                                AND n.category = x.category
                   WHERE x.invoice_id = i.invoice_id
                     AND n.budgeted = 0
                     AND x.amount <> 0)
       END                                       AS billed_against_a_zero_line,
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
  'departure from the format. Billed outside the schedule and billed against '
  'a line the schedule names at zero are two different findings and are '
  'reported separately; INDIRECT is not exempt from either, because it is a '
  'budget line on ICAM and on LTM and absent from Drive AM and Hybrid.';


-- ── What has been claimed against an award, against what it budgets ──
--
-- The per-invoice check above compares *sets of categories*. It cannot say
-- that a category has been billed for more than the schedule funds, and one
-- invoice against a whole award's budget is the wrong comparison to make:
-- a monthly invoice is meant to be a fraction of the budget, so a per-invoice
-- over-budget test would never fire and would mean nothing if it did.
--
-- Cumulative is the comparison that means something. This is the answer to
-- *has anything been invoiced for more than the agreement supports*, by
-- category, across every invoice on the award.
--
-- Five states, and only two of them are findings:
--
--   NOT READ            no schedule transcribed. Unevaluable, not a pass —
--                       an empty set matches an empty set perfectly.
--   OUTSIDE SCHEDULE    claimed under a category the schedule never names.
--   OVER                claimed more than the category budgets.
--   WITHIN              claimed, and inside the line.
--   UNBILLED            funded and nothing claimed against it.
--
-- Cost share is deliberately *not* added to the comparison. `federal` is
-- what the sponsor pays and an invoice claims against that; adding YBI's own
-- share would report headroom nobody may invoice for. The column is on
-- `award_budget` for the cost-share obligation, which is a different
-- control.

DROP VIEW IF EXISTS v_award_claim_check;

CREATE VIEW v_award_claim_check AS
WITH claimed AS (
  SELECT i.award_id, l.category, sum(l.amount) AS claimed,
         count(DISTINCT i.invoice_id) AS invoices
    FROM invoice i JOIN invoice_line l USING (invoice_id)
   WHERE i.award_id IS NOT NULL
   GROUP BY i.award_id, l.category
),
budget AS (
  SELECT award_id, category, federal FROM award_budget
),
-- Every category either side knows about. A first draft joined the two and
-- filtered on the award, which dropped exactly the row that matters: a
-- category claimed with no budget line behind it had no award on its side of
-- the join, so `OUTSIDE SCHEDULE` could never be reported. The union is the
-- shape, because the question is asked of both registers at once.
universe AS (
  SELECT award_id, category FROM budget
  UNION
  SELECT award_id, category FROM claimed
)
SELECT u.award_id,
       u.category,
       b.federal                                            AS budgeted,
       COALESCE(c.claimed, 0)                               AS claimed,
       COALESCE(c.invoices, 0)                              AS invoices,
       b.federal - COALESCE(c.claimed, 0)                   AS headroom,
       EXISTS (SELECT 1 FROM award_budget x WHERE x.award_id = u.award_id)
                                                            AS evaluable,
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM award_budget x
                           WHERE x.award_id = u.award_id)  THEN 'NOT READ'
         WHEN b.category IS NULL                           THEN 'OUTSIDE SCHEDULE'
         WHEN COALESCE(c.claimed, 0) > b.federal           THEN 'OVER'
         WHEN COALESCE(c.claimed, 0) = 0                   THEN 'UNBILLED'
         ELSE 'WITHIN'
       END                                                  AS state
  FROM universe u
  LEFT JOIN budget b  ON b.award_id = u.award_id AND b.category = u.category
  LEFT JOIN claimed c ON c.award_id = u.award_id AND c.category = u.category;

COMMENT ON VIEW v_award_claim_check IS
  'Cumulative claimed against budgeted, by award and category. The per-invoice '
  'check compares sets of categories; this compares money, which is the only '
  'way to ask whether anything has been invoiced for more than the agreement '
  'supports. Cumulative rather than per-invoice, because a monthly invoice is '
  'meant to be a fraction of the budget. NOT READ is unevaluable, not a pass.';
