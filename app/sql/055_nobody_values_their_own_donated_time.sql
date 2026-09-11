-- 055: a controller may not put a price on their own donated hours.
--
-- `donation_rate` was created in `019` with this comment above it:
--
--     The rate donated hours are valued at. The controller sets it and says
--     what it rests on, because a volunteer valuing their own time is the
--     whole problem 200.306(e) is guarding against.
--
-- The gate delivers the first half and not the second. `require_controller`
-- keeps out everybody who does not hold the portfolio — the auditor, the
-- organisation's administrator, anybody on a timesheet — and lets a
-- controller through. Heidi holds `CONTROLLER` and is on the payroll like
-- everybody else, so she could record six donated hours and value them at
-- whatever she liked. Tested against the live record: 403, 403, 200.
--
-- 2 CFR 200.306(e) wants a rate consistent with what the organisation pays
-- for similar work, or with the labour market where it has no such work.
-- That is a judgment about somebody's time, and the person whose time it is
-- is the one person who cannot make it.
--
-- ── The rule this already is ─────────────────────────────────────────
--
-- Three times over, and each time in both places:
--
--   nobody grants themselves a portfolio     actor_portfolio, and the handler
--   nobody assigns themselves a charge code  charge_authority, and the handler
--   a manager cannot sign a certification    v_certification_chase is a list
--                                            to go and ask, never an action
--
-- The schema half is what makes it hold when a handler is wrong, and it is
-- the half that would have been missing here. `set_by` is an actor and
-- `employee_key` is a person on the payroll; the trigger joins them.
--
-- Three people hold `CONTROLLER` on this engagement, so this costs a
-- conversation rather than a workflow. If it ever came down to one, the
-- answer is still not to let them value their own time — it is that the
-- valuation is somebody else's, and the system should say so rather than
-- quietly accept it.

CREATE FUNCTION nobody_values_their_own_time() RETURNS trigger AS $$
DECLARE mine text;
BEGIN
  SELECT a.employee_key INTO mine
    FROM actor a WHERE a.actor_id = NEW.set_by;
  -- An account with no employee_key is not on the payroll and cannot be
  -- valuing itself. NULL never equals anything, but saying so is cheaper
  -- than making a reader work it out.
  IF mine IS NOT NULL AND mine = NEW.employee_key THEN
    RAISE EXCEPTION
      'A donated hour cannot be valued by the person who gave it. 2 CFR '
      '200.306(e) wants a rate consistent with what YBI pays for similar '
      'work, and that is a judgment about your time rather than yours to '
      'make. Ask one of the other controllers.'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER donation_rate_not_self
  BEFORE INSERT ON donation_rate
  FOR EACH ROW EXECUTE FUNCTION nobody_values_their_own_time();

COMMENT ON FUNCTION nobody_values_their_own_time() IS
  'The second half of what the comment on donation_rate has always claimed. '
  'require_controller keeps out everybody without the portfolio; this keeps '
  'out the one person the rule is actually about, who is very likely to have '
  'it.';


-- And the record should say who has hours nobody else can value yet, rather
-- than leaving somebody to discover it at the point of being refused.
CREATE VIEW v_donation_rate_conflict AS
SELECT d.period,
       d.employee_key,
       sum(d.hours)                                          AS hours,
       bool_or(d.rate_missing)                               AS unvalued,
       -- Controllers who are not this person. Empty means the only people
       -- who could set this rate are the person themselves, which is a
       -- staffing fact rather than a defect — and one worth seeing before
       -- the deadline rather than at it.
       (SELECT count(*) FROM actor a
          JOIN actor_portfolio p ON p.actor_id = a.actor_id
         WHERE p.portfolio = 'CONTROLLER' AND p.revoked_at IS NULL
           AND a.is_active
           AND (a.employee_key IS DISTINCT FROM d.employee_key))  AS others_who_could
  FROM v_donated_time d
 GROUP BY d.period, d.employee_key;

COMMENT ON VIEW v_donation_rate_conflict IS
  'Donated hours by person, with how many controllers other than that person '
  'could value them. Zero is not a defect — it is one controller who is also '
  'the volunteer — but it is the kind of thing to find out about in October '
  'rather than in the week the return is due.';
