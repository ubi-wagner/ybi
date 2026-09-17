-- 100 — line 5's note was written when it was empty
--
-- `094` gave line 5 the note *"Nothing on this record separates officer
-- compensation from other wages. The 2024 return reported 167,967 here."*
-- That was true when it was written and `098` made it false, which is the
-- defect this file keeps finding in prose rather than in code: a sentence
-- that describes a state the record has moved out of. `086` is the same
-- shape on the walk, `093` on the partitions.
--
-- What line 5 still cannot carry is the **other compensation** — the $9,460
-- the 2024 return reported inside it, which is an estimate of the CEO's
-- benefits. The fringe pool is six accounts and nothing on this record
-- allocates it by employee, so that element sits in line 9 with everybody
-- else's. The note says that instead, because it is what is true now.
--
-- And a control, because a roster is exactly the shape that goes stale: an
-- officer who is no longer on the payroll register, or a compensated person
-- on the register who is on nobody's roster, is what "same officers and
-- directors as last year" stops being true by.

UPDATE form_990_line
   SET note = 'Officers and key employees only. A highest compensated '
              'employee who holds no office is on line 7, which is what the '
              '2024 return did with both vice presidents. The **other '
              'compensation** a filed return reports inside this line — '
              '9,460 in 2024 — cannot be produced here: the fringe pool is '
              'six accounts and nothing allocates it by employee, so it sits '
              'in line 9 with everybody else''s.'
 WHERE line_id = '5';

UPDATE form_990_line
   SET note = 'Everybody except the officers and key employees on line 5. '
              'The split is by person from the payroll register, because '
              'payroll posts to the ledger as lump journal entries with no '
              'employee dimension.'
 WHERE line_id = '7';


CREATE OR REPLACE VIEW v_form_990_officer_check AS
WITH roster AS (
  SELECT period,
         count(*)                                             AS people,
         count(*) FILTER (WHERE on_line_5)                    AS officers,
         count(*) FILTER (WHERE on_line_5 AND employee_key IS NOT NULL
                            AND reportable IS NULL)           AS missing_pay,
         count(*) FILTER (WHERE employee_key IS NULL
                            AND COALESCE(reportable, 0) > 0)  AS paid_unkeyed
    FROM v_form_990_officer GROUP BY period),
-- Somebody the payroll register pays more than the least-paid person on the
-- roster and who is on nobody's roster is the question Part VII exists to
-- ask. Not a defect on its own — a vice president is not an officer — but it
-- is how a roster carried forward stops being true.
unrostered AS (
  SELECT r.period, count(*) AS n
    FROM (SELECT period, employee_key, max(payroll_wages) AS wages
            FROM labor_allocation GROUP BY period, employee_key) r
   WHERE NOT EXISTS (SELECT 1 FROM form_990_officer f
                      WHERE f.period = r.period
                        AND f.employee_key = r.employee_key)
     AND r.wages >= 100000
   GROUP BY r.period)
SELECT p.period,
       COALESCE(ro.people, 0)      AS people_on_the_roster,
       COALESCE(ro.officers, 0)    AS reach_line_5,
       COALESCE(ro.missing_pay, 0) AS on_the_roster_not_on_the_payroll,
       COALESCE(ro.paid_unkeyed, 0) AS paid_with_no_payroll_key,
       COALESCE(un.n, 0)           AS paid_over_100k_and_not_on_the_roster,
       CASE WHEN COALESCE(ro.people, 0) = 0                THEN 'NO DATA'
            WHEN COALESCE(ro.missing_pay, 0) > 0
              OR COALESCE(ro.paid_unkeyed, 0) > 0          THEN 'OPEN'
            ELSE 'TIES' END        AS state,
       CASE WHEN COALESCE(ro.people, 0) = 0
              THEN 'Part VII of a filed return, or the board''s own roster'
            WHEN COALESCE(ro.missing_pay, 0) > 0
              THEN format('%s officer(s) name a payroll key the register '
                          'does not carry, so line 5 is short by whatever '
                          'they were paid.', ro.missing_pay)
            WHEN COALESCE(ro.paid_unkeyed, 0) > 0
              THEN format('%s compensated person(s) on the roster have no '
                          'payroll key, so their pay cannot be read from the '
                          'register.', ro.paid_unkeyed)
            ELSE '' END            AS needs
  FROM fiscal_period p
  LEFT JOIN roster ro ON ro.period = p.period
  LEFT JOIN unrostered un ON un.period = p.period;

COMMENT ON VIEW v_form_990_officer_check IS
  'Whether the Part VII roster and the payroll register still describe the '
  'same organisation. A roster carried forward from last year is exactly the '
  'shape that goes stale, and the two ways it does are an officer the '
  'register no longer pays and somebody the register pays well who is on '
  'nobody''s roster.';
