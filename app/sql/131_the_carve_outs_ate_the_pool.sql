-- 131: the two carve-outs consumed the pool they come out of
--
-- `POST /api/rates/compute` answered **422 rate_rate_check** on a record with
-- every building measured and every square foot allocated. That constraint is
-- `CHECK (rate >= 0)`: the overhead rate had gone negative.
--
-- It is not a coverage problem and no amount of classifying reaches it. At the
-- measured estate the pool would have to be $1,908,147 for the rate to stay
-- positive and a **complete** classification produces $1,497,879.12. The
-- refusal was the schema being right about arithmetic that had no answer.
--
-- Two defects, and they compound:
--
-- **200.465 was taken over the whole OVERHEAD pool.** The driver is square
-- footage, so it may only reach the cost square footage drives. The pool also
-- carries T1 access, telephone, insurance and equipment — $181,276.15 — which
-- a tenant's floor area does not cause and which `DEFENSIBLE_RATE_2025.md`
-- already names, to the cent, as the part the space split must not touch.
--
-- **200.436(b) was subtracted unscaled.** Depreciation sits *inside*
-- occupancy, so 200.465 has already removed the let share of it. Taking the
-- whole federally funded figure again double-counts `share × 261,988.65`.
-- `defensible_rate.py` records finding and correcting exactly this — *"The
-- 436(b) carve was subtracted twice ... 2.85 points against YBI"* — **in the
-- script, and it was never carried into the engine.** Fixing one instance is
-- not fixing the rule, for the umpteenth time in this file.
--
-- Corrected, the rate **cannot go negative from the carve-outs at all**, and
-- that is the property worth having rather than the points. Write the pool as
-- G, the occupancy inside it as C and the federally funded depreciation as D,
-- with D <= C <= G. Allocable is
--
--         G - C*s - D*(1-s)
--
-- which is linear in the let share s, equals G-D at s=0 and G-C at s=1, and
-- both are non-negative. So it is non-negative for every share in between.
-- The floor is G-C, the part floor area does not drive. `rate_rate_check`
-- becomes unreachable from this direction instead of being a cliff nobody
-- could see coming.
--
-- **Which accounts floor area drives is a transcription, not a rule.** It is
-- the same shape as the six fringe accounts named by hand inside
-- `v_payroll_reconciliation` and as `form_990_account_line`: somebody read the
-- chart and decided. Inventing a regex to derive it would be guessing at that
-- judgment — and the first draft of this migration did exactly that, matched
-- "Utilities" inside `…:5051 Utilities:5056 T1 Access`, and quietly called a
-- data circuit occupancy.
--
-- **The default is that floor area drives it**, so an account nobody has
-- considered is carved. That is the conservative direction — more carved is a
-- lower rate and a smaller claim — and it keeps *nothing changes by default*
-- for every account already in the pool. The exception list can only be added
-- to deliberately, and `v_overhead_driver` shows what is on it and what it is
-- worth, because a silent exception is the defect wearing a permission slip.

CREATE TABLE overhead_driver (
  account_fragment  text PRIMARY KEY,
  driven_by_area    boolean NOT NULL,
  reason            text    NOT NULL,
  CONSTRAINT driver_reason_is_a_reason CHECK (length(btrim(reason)) >= 25)
);

COMMENT ON TABLE overhead_driver IS
  'Which overhead cost a tenant''s square footage actually causes. Read by '
  'the 2 CFR 200.465 carve-out so it reaches occupancy and nothing else. A '
  'transcription of a judgment somebody made reading the chart, not a rule '
  'derived from the account name.';

INSERT INTO overhead_driver (account_fragment, driven_by_area, reason) VALUES
  ('5056 T1 Access',  false,
   'A data circuit serves the organisation, not the floor area. A tenant '
   'taking another suite does not cause another circuit.'),
  ('5065 Telephone',  false,
   'Telephony is a headcount and handset cost. Square footage is not its '
   'driver and a let suite does not carry a share of it.'),
  ('5075 Insurance',  false,
   'Property and general liability are one account here and only the first '
   'half is floor area. Splitting it needs the policy schedule, which is '
   'outstanding; until then it is left whole and out of the space split, '
   'because a guessed split is a judgment nobody made.'),
  ('5015 Equipment Expenses', false,
   'Equipment purchases, rentals and leases follow the machine and the '
   'programme that uses it, never the square footage it stands on.');

-- What the exception is worth, so it is visible rather than assumed. One row
-- per period, reading the live pool: an exception that stops being worth
-- anything should be seen to have stopped, and one that grows should be seen
-- to have grown.
CREATE OR REPLACE VIEW v_overhead_driver AS
WITH pool AS (
  SELECT l.period, l.account, sum(l.amount) AS amount
    FROM decision d
    JOIN decision_line dl USING (decision_id)
    JOIN ledger_line l USING (line_id)
   WHERE d.reversed_at IS NULL AND dl.live AND d.pool = 'OVERHEAD'
   GROUP BY l.period, l.account),
marked AS (
  SELECT p.period, p.account, p.amount,
         COALESCE(bool_and(od.driven_by_area), true) AS driven_by_area,
         max(od.reason)                              AS reason
    FROM pool p
    LEFT JOIN overhead_driver od
           ON position(od.account_fragment in p.account) > 0
   GROUP BY p.period, p.account, p.amount)
SELECT period, account, amount, driven_by_area, reason
  FROM marked;

-- And the two figures the handler needs, in one place so the screen, the
-- control and the computation cannot hold three opinions about them.
CREATE OR REPLACE VIEW v_overhead_split AS
SELECT period,
       sum(amount)                                        AS pool_gross,
       sum(amount) FILTER (WHERE driven_by_area)          AS occupancy,
       sum(amount) FILTER (WHERE NOT driven_by_area)      AS not_area_driven
  FROM v_overhead_driver
 GROUP BY period;
