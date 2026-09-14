-- 076  A restatement rebuilds; it does not add
--
-- `POST /api/restate` measured indirect on `mtdc_as_billed` — the direct cost
-- on the face of the invoice. That base contains labour which already carries
-- embedded indirect, so the rate went on top of a figure that already held it
-- and the claim was counted twice.
--
-- YBI's own Hybrid Phase 2 cost proposal shows the arithmetic: $403,570 of
-- personnel and fringe plus $45,457 of 10% ICR, presented as a single labour
-- line of $449,043.40. The loading multiples say the same thing without the
-- document — Drive AM billed labour at 1.70x wages-plus-fringe against a
-- fully burdened 1.7552x, and Hybrid at 2.25x.
--
-- Measured across the four America Makes awards on the 2025 register, the
-- old reading reports $435,301.76 owed TO YBI where the rebuild shows
-- $286,793.73 owed BACK — a spread of $722,095.49, in the direction that
-- would have YBI ask a federal pass-through for money it cannot support.
--
-- The rebuild is the method both published workpapers used, and it
-- reproduces them to the cent: LTM $107,683.52 and Drive AM $(58,786.31).
--
-- ── What the columns are ─────────────────────────────────────────────
--
-- The position now recorded in `under_recovered` / `over_collected` is the
-- REBUILD: the cost record's own direct cost, plus indirect at the sealed
-- rate on the MTDC base, against what was billed.
--
-- The as-billed reading is kept beside it rather than removed. It is what a
-- reader gets from the invoice alone, it is what the route used to report,
-- and an auditor comparing this file to anything written before today needs
-- to see why the two differ. Removing it would make the $722,095.49 invisible
-- everywhere, which is the opposite of the point.
--
-- `elected_rate` is the de minimis every one of these awards is set to.
-- Written down in two places and BOTH are cited, because they are different
-- kinds of evidence and an auditor will want to know which is which:
--
--   * Last Tactical Mile — the only EXECUTED agreement that budgets it.
--     Schedule B carries 10.0000% of total direct, to four decimal places,
--     and LTM's invoices are the only ones in the register with an indirect
--     line on them at all.
--   * Hybrid Phase 2 — a COST PROPOSAL, not an executed schedule. Its ODCs
--     tab computes "ICR 10% maximum 45,457.00" over a $454,570 base and puts
--     the result inside the labour line. It is the document that proves the
--     indirect is embedded rather than absent.
--
-- `implied_rate` is the rate actually recovered: what was billed, less the
-- direct cost the record carries, over the MTDC base. It is the figure the
-- election should be compared against, and on the live record it is 60.25%,
-- 179.21%, 11.41% and 104.18% against an elected 10.00%.
--
-- A high implied rate has two readings and this column does not choose
-- between them: YBI billed above cost, or the classification has not
-- attributed enough cost to that objective. Digital Engineering at 179.21%
-- carries $207,398.87 of classified cost against $579,074.25 of billing, and
-- which of those it is has to be settled by a person.

ALTER TABLE restatement
  ADD COLUMN direct_supported      numeric(14,2) NOT NULL DEFAULT 0,
  ADD COLUMN indirect_rebuilt      numeric(14,2) NOT NULL DEFAULT 0,
  ADD COLUMN supported_total       numeric(14,2) NOT NULL DEFAULT 0,
  ADD COLUMN as_billed_base        numeric(14,2) NOT NULL DEFAULT 0,
  ADD COLUMN as_billed_indirect    numeric(14,2) NOT NULL DEFAULT 0,
  ADD COLUMN elected_rate          numeric(9,6),
  ADD COLUMN elected_indirect      numeric(14,2),
  ADD COLUMN implied_rate          numeric(9,6),
  ADD COLUMN method                text NOT NULL DEFAULT 'REBUILD';

COMMENT ON COLUMN restatement.direct_supported IS
  'Wages plus fringe plus classified direct non-labour, from the cost record.';
COMMENT ON COLUMN restatement.as_billed_indirect IS
  'The superseded reading: the rate applied to the invoice base as billed. '
  'Kept for comparison and never the position.';
COMMENT ON COLUMN restatement.implied_rate IS
  'The indirect rate actually recovered: billed less direct cost, over MTDC. '
  'High values mean over-billing OR under-attributed cost, and this column '
  'does not decide which.';

ALTER TABLE restatement
  ADD CONSTRAINT restatement_method_is_named
  CHECK (method IN ('REBUILD', 'AS_BILLED'));

-- A rebuilt position has to foot to its own parts, or it is two figures that
-- can disagree. The same rule the invoice header already follows.
ALTER TABLE restatement
  ADD CONSTRAINT restatement_supported_foots
  CHECK (abs(supported_total - (direct_supported + indirect_rebuilt)) <= 0.01);

-- The new money columns join the immutable set. A restatement is corrected by
-- superseding it, never by editing what it said — and a column added later is
-- exactly the one somebody would reach for.
DROP TRIGGER IF EXISTS restatement_immutable ON restatement;
CREATE TRIGGER restatement_immutable
  BEFORE UPDATE OF period, award_id, objective_id, rate_id, seal_hash,
                   billed_total, base_total, indirect_supported, computed_at,
                   direct_supported, indirect_rebuilt, supported_total,
                   as_billed_base, as_billed_indirect, elected_rate,
                   elected_indirect, implied_rate, method
  ON restatement FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ── The view carries both readings, and says which is the position ───

-- The body below is LIFTED from 061, which is the definition in force, and
-- extended. The first draft of this migration retyped it from the column list
-- and silently dropped rate_kind, rate_applied, rate_base and lines —
-- `test_sql_is_real` caught it within the minute, on a SELECT in
-- restate.py:402 that had been correct for months. A view body is lifted, not
-- remembered; this file is the third time that has been written down here.
DROP VIEW IF EXISTS v_restatement;
CREATE VIEW v_restatement AS
SELECT r.restatement_id,
       r.period,
       r.award_id,
       r.objective_id,
       r.rate_id,
       r.seal_hash,
       r.status::text                                    AS status,
       r.invoices,
       r.billed_total,
       r.base_total,
       r.indirect_billed,
       r.indirect_supported,
       -- Money to ask for.
       r.under_recovered,
       -- Money to give back. Never subtracted from the line above.
       r.over_collected,
       r.ceiling_headroom,
       r.capped_by_ceiling,
       r.basis,
       r.modification_ref,
       r.computed_by,
       r.computed_at,
       r.submitted_at,
       r.decided_at,
       r.decided_note,
       -- ── added by 076 ────────────────────────────────────────────
       r.direct_supported,
       r.indirect_rebuilt,
       r.supported_total,
       r.as_billed_base,
       r.as_billed_indirect,
       r.elected_rate,
       r.elected_indirect,
       r.implied_rate,
       r.method,
       -- What the superseded reading would have said, so the difference
       -- between the two methods is on the row rather than in a memo.
       (r.as_billed_indirect - r.indirect_billed)        AS as_billed_position,
       -- Against the election, on the rebuilt base. Positive is money the
       -- de minimis would have supported and the invoice did not claim.
       (r.elected_indirect - r.indirect_billed)          AS elected_position,
       -- ────────────────────────────────────────────────────────────
       a.sponsor,
       a.ceiling_federal,
       a.cost_share_required,
       a.rate_method::text                               AS billed_under,
       rt.kind                                           AS rate_kind,
       rt.rate                                           AS rate_applied,
       rt.base_type::text                                AS rate_base,
       (SELECT count(*) FROM restatement_line l
         WHERE l.restatement_id = r.restatement_id)      AS lines
  FROM restatement r
  LEFT JOIN award a ON a.award_id = r.award_id
  LEFT JOIN rate rt ON rt.rate_id = r.rate_id;

COMMENT ON VIEW v_restatement IS
  'Both readings of a restatement. under_recovered/over_collected are the '
  'REBUILD and are the position; as_billed_* is the invoice-only reading the '
  'route used before migration 076 and is never the position. There is '
  'deliberately no net of the two directions — money to ask for and money to '
  'give back are two conversations.';
