-- 061: an over-collection is not a negative under-recovery.
--
-- `app/routers/restate.py` opens by naming three things it will not do. The
-- third:
--
--     It will not net an over-collection against an under-recovery. They are
--     two different conversations: one is money to ask for, the other is
--     money to give back, and a single net figure hides both.
--
-- And `v_restatement` carried this:
--
--     r.under_recovered - r.over_collected AS net_movement
--
-- which is that figure exactly. The handler refuses to produce it and the
-- view offers it, pre-computed, to whatever reads the view.
--
-- **Nothing read it, because nothing could.** `POST /api/restate` and its
-- four sibling routes have been complete since they were written and there
-- has never been a screen — no page, no route in `App.jsx`, no call in
-- `api.js`. The restatement is the point of the whole system and no person
-- could reach it, so the trap in front of it was never sprung.
--
-- That is the same shape as every other dead column here — `space_partition`,
-- `rate.superseded_by`, `award_budget_line`, the lane tables — with one
-- difference that makes it worse. Those were empty and answered nothing. This
-- one answers, plausibly, in a column named as though it were the summary
-- figure, and the first screen to show a restatement would reasonably have
-- reached for it.
--
-- $120,000 to ask NCDMM for and $120,000 to give back is not a quiet year.
--
-- The two figures stay, side by side, and there is no third.

-- Dropped and recreated rather than replaced: CREATE OR REPLACE can add a
-- column to a view and never take one away.
DROP VIEW v_restatement;

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
  'Every restatement, with what it was measured against. `under_recovered` '
  'and `over_collected` are reported apart and never netted: one is money to '
  'ask a sponsor for and the other is money to give back, and a single figure '
  'hides both. The handler refuses to produce that figure; this view used to '
  'offer it anyway, as `net_movement`, to a screen that did not yet exist.';
