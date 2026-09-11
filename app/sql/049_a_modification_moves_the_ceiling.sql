-- 049: the award register did not carry a modification the record already had.
--
-- Hybrid Phase 2 was seeded in 004 from the executed agreement: ceiling
-- $500,043, performance to 10 October 2025. Modification 001 of 22 January
-- 2026 is on file as a document, was read into `award_term` by the controller
-- — "§4.2, as amended by Modification 001: $512,409 federal funds and
-- $104,000 cost share", "Period of performance extended to 30 June 2026" —
-- and the award row was never brought into line with it.
--
-- So two records of one fact disagreed by $12,366 and eight months, and the
-- one the ceiling test reads is the stale one. `POST /api/restate` caps a
-- claim at `award.ceiling_federal`, which would have capped Hybrid $12,366
-- below what the agreement now allows and reported the difference as headroom
-- YBI does not have.
--
-- Two parts, and the second matters more than the first: bring the row into
-- line, and then make the disagreement impossible to have again without
-- somebody seeing it.

UPDATE award
   SET ceiling_federal     = 512409,
       cost_share_required = 104000,
       period_end          = DATE '2026-06-30',
       citation            = '§4.2 as amended by Modification 001, '
                             '22 January 2026'
 WHERE award_id = 'AM-HYBRID-P2';


-- ── The control ──────────────────────────────────────────────────────
--
-- Every derived figure ties to a control. The ceiling is not derived — it is
-- read off a clause — so the control is that the register says what the
-- clause says.
--
-- It compares against the `Total obligation` term because that is the one the
-- controller records the money limit under, and it reads the first dollar
-- figure out of the term text rather than asking for a second numeric column
-- nobody would keep in step. `evaluable` is false where no such term has been
-- read in, which is the honest answer for an award whose agreement nobody has
-- been through yet — an unread award must not report as tying.

CREATE VIEW v_award_ceiling_check AS
WITH stated AS (
  SELECT t.award_id,
         t.citation,
         t.term_value,
         -- The first money figure in the clause, e.g. "$512,409 federal
         -- funds and $104,000 cost share" -> 512409.
         NULLIF(regexp_replace(
                  COALESCE(substring(t.term_value from '\$[0-9][0-9,]*'), ''),
                  '[^0-9]', '', 'g'), '')::numeric            AS clause_amount
    FROM award_term t
   WHERE t.term_key = 'Total obligation')
SELECT a.award_id,
       a.objective_id,
       a.ceiling_federal                                      AS register,
       s.clause_amount                                        AS clause,
       s.citation,
       (s.clause_amount IS NOT NULL)                          AS evaluable,
       CASE WHEN s.clause_amount IS NULL THEN NULL
            ELSE a.ceiling_federal - s.clause_amount END      AS variance,
       CASE WHEN s.clause_amount IS NULL THEN 'NO CLAUSE READ'
            WHEN a.ceiling_federal = s.clause_amount THEN 'TIES'
            ELSE 'OPEN' END                                   AS state,
       s.term_value
  FROM award a
  LEFT JOIN stated s ON s.award_id = a.award_id;

COMMENT ON VIEW v_award_ceiling_check IS
  'The ceiling the register enforces against the ceiling the agreement states. '
  'Hybrid Phase 2 carried the pre-modification figure for as long as the '
  'modification had been on file, which would have capped a restatement '
  '$12,366 below what the agreement allows. NO CLAUSE READ is not a pass: an '
  'award whose agreement nobody has been through cannot be said to tie.';
