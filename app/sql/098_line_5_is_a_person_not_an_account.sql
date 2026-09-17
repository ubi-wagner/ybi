-- 098 — line 5 is a person, and the ledger has no column for one
--
-- `094` printed Part IX line 5 — *compensation of current officers,
-- directors, trustees and key employees* — **empty**, and said why: the 2024
-- return reported $167,967 there, `5140 Employee Wages` is undifferentiated,
-- and no column on this record says who is an officer. The comparison named
-- it as the one line the return could not produce.
--
-- It is answerable, and the answer was two documents away.
--
-- **Part VII of the 2024 return is the roster.** Twenty-seven people:
-- twenty-four directors at nil, five of them also holding office as
-- chairperson, vice chairperson, treasurer, secretary and executive committee
-- member; the CEO; and two vice presidents marked in column (v), *highest
-- compensated employee*, which is not an officer and does not reach line 5.
-- So the 2024 line 5 is **one person** — Barb Ewing, $158,507 reportable plus
-- $9,460 of other compensation, which is $167,967 to the dollar. That is not
-- an inference; it is the return's own arithmetic reproduced.
--
-- And the instruction that makes 2025 answerable is *same officers and
-- directors as 2024*. So the roster carries forward, the titles carry
-- forward, and **the compensation does not** — 2025's is read from the
-- payroll register, where Barb Ewing is $192,087.13.
--
-- Three things this has to get right:
--
--   * **The ledger cannot make this split and the register can.** Payroll
--     posts as two lump journal entries a pay period with no employee, project
--     or class dimension — which is why `labor_allocation` exists at all. So
--     line 5 is not a routing like every other line in `form_990_account_line`;
--     it is an amount lifted out of line 7 **by person**, and line 5 plus line
--     7 still add to the wage accounts, which a test holds.
--   * **The register and the ledger differ by $45,053.23** and always have —
--     the donor credit that sat in an intern wage account for a year, which
--     the eleventh statement control names. Line 5 is a register figure and
--     line 7 is the ledger's wage accounts less it, so the whole of that
--     difference sits in line 7, where it belongs, rather than being spread.
--   * **Her functional split is her own.** `092` splits the compensation
--     block by the estate-wide effort distribution because it is many people;
--     line 5 is one person and `v_labor_effective` holds *her* distribution —
--     81.6% programme, 13.6% administration, 4.8% fundraising. Using the
--     estate's average for a line that is one person would be answering a
--     question with somebody else's data.
--
-- What it still cannot say is the **other compensation** — the $9,460 the
-- 2024 return reported inside line 5. The fringe pool is six accounts and
-- nothing on this record allocates it by employee, so that element stays in
-- line 9 with everybody else's. It is $9,460 on $167,967 and the comparison
-- says so rather than apportioning it.

CREATE TABLE IF NOT EXISTS form_990_officer (
    period        text NOT NULL,
    seq           integer NOT NULL,
    name          text NOT NULL,
    title         text NOT NULL,
    position      text NOT NULL,
    employee_key  text,
    reportable    numeric(14,2),
    other         numeric(14,2),
    source        text NOT NULL DEFAULT '',

    PRIMARY KEY (period, seq),
    CONSTRAINT officer_position_is_known CHECK (position IN (
      'DIRECTOR', 'OFFICER', 'OFFICER_AND_DIRECTOR', 'KEY_EMPLOYEE',
      'HIGHEST_COMPENSATED', 'FORMER')),
    -- A figure transcribed from a filed return says where it came from; one
    -- read from the payroll register is left NULL so the view fills it, and
    -- nobody has to work out which of the two they are looking at.
    CONSTRAINT transcribed_pay_names_its_source
      CHECK (reportable IS NULL OR length(btrim(source)) > 0)
);

COMMENT ON TABLE form_990_officer IS
  'Form 990 Part VII Section A — who the officers, directors, trustees and '
  'key employees are, which is the only thing that can tell Part IX line 5 '
  'from line 7. The ledger cannot: payroll posts as lump journal entries with '
  'no employee dimension. A compensation figure is transcribed where it comes '
  'from a filed return and NULL where it is read from the payroll register.';

-- 2024, transcribed from Part VII Section A of the filed return.
INSERT INTO form_990_officer (period, seq, name, title, position,
                              employee_key, reportable, other, source) VALUES
  ('2024',  1, 'JOHN REED',              'CHAIRPERSON',                'OFFICER_AND_DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  2, 'EVAN MORRISON',          'VICE CHAIRPERSON',           'OFFICER_AND_DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  3, 'CHRIS MEDIATE',          'TREASURER',                  'OFFICER_AND_DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  4, 'STUART A STRASFELD',     'SECRETARY',                  'OFFICER_AND_DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  5, 'SAM HUSTON',             'EXECUTIVE COMMITTEE MEMBER', 'OFFICER_AND_DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  6, 'JEFF BARBER',            'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  7, 'JOE CHAHINE',            'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  8, 'ELLE CLEMENTI',          'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024',  9, 'MICHELLE CRAWFORD',      'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 10, 'JAMES DASCENZO',         'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 11, 'BONNIE DEUTSCH BURDMAN', 'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 12, 'LENA ESMAIL',            'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 13, 'MICHAEL GARVEY',         'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 14, 'STEPHANIE GILCHRIST',    'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 15, 'PAUL HORNING',           'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 16, 'BRIAN JACKSON',          'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 17, 'JOHN MCNALLY',           'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 18, 'PAUL OLIVIER',           'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 19, 'WILL RAUBER',            'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 20, 'DOUG ROSS',              'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 21, 'BRIEN SMITH',            'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 22, 'KELLY WILKINSON',        'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 23, 'HASHEEN WILSON',         'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 24, 'BOB WOLLET',             'MEMBER', 'DIRECTOR', NULL, 0, 0, '2024 Form 990 Part VII'),
  ('2024', 25, 'BARB EWING',    'CEO',                       'OFFICER',             'EWING',   158507, 9460, '2024 Form 990 Part VII'),
  ('2024', 26, 'STEPHANIE GAFFNEY', 'VP-ADV.MANUFACTURING PRO', 'HIGHEST_COMPENSATED', 'GAFFNEY', 128308, 9460, '2024 Form 990 Part VII'),
  ('2024', 27, 'COLLEEN KELLY', 'SENIOR VP',                 'HIGHEST_COMPENSATED', 'KELLY',   105385, 9460, '2024 Form 990 Part VII')
ON CONFLICT (period, seq) DO UPDATE
  SET name = EXCLUDED.name, title = EXCLUDED.title,
      position = EXCLUDED.position, employee_key = EXCLUDED.employee_key,
      reportable = EXCLUDED.reportable, other = EXCLUDED.other,
      source = EXCLUDED.source;

-- 2025: the same people and the same titles, carried forward on the
-- instruction that the board and the officers are unchanged. **No
-- compensation figure is carried with them** — 2025's is the payroll
-- register's, read by the view, which is the whole point of separating the
-- two.
INSERT INTO form_990_officer (period, seq, name, title, position,
                              employee_key, reportable, other, source)
SELECT '2025', seq, name, title, position, employee_key, NULL, NULL,
       'Carried forward from 2024 Part VII: same officers and directors. '
       'Compensation is read from the 2025 payroll register.'
  FROM form_990_officer WHERE period = '2024'
ON CONFLICT (period, seq) DO UPDATE
  SET name = EXCLUDED.name, title = EXCLUDED.title,
      position = EXCLUDED.position, employee_key = EXCLUDED.employee_key,
      source = EXCLUDED.source;


CREATE OR REPLACE VIEW v_form_990_officer AS
SELECT o.period, o.seq, o.name, o.title, o.position, o.employee_key,
       COALESCE(o.reportable, reg.wages)              AS reportable,
       o.other,
       o.reportable IS NULL AND reg.wages IS NOT NULL AS from_the_register,
       -- **Line 5 is officers and key employees and nobody else.** A highest
       -- compensated employee who holds no office belongs on line 7, which is
       -- what the 2024 return did with both vice presidents — and is why its
       -- line 5 is one person rather than three.
       o.position IN ('OFFICER', 'OFFICER_AND_DIRECTOR', 'KEY_EMPLOYEE')
                                                      AS on_line_5,
       o.source
  FROM form_990_officer o
  LEFT JOIN (SELECT period, employee_key, max(payroll_wages) AS wages
               FROM labor_allocation GROUP BY period, employee_key) reg
    ON reg.period = o.period AND reg.employee_key = o.employee_key;

COMMENT ON VIEW v_form_990_officer IS
  'Part VII Section A with each person''s compensation: transcribed where it '
  'came from a filed return, and read from the payroll register otherwise. '
  '`on_line_5` is the rule Part IX turns on — an officer or key employee '
  'reaches line 5 and a merely highest-compensated employee does not.';


-- ── The two cohorts of the effort distribution ───────────────────────
--
-- `092`'s share view is the whole payroll, which is right for a line that is
-- many people and wrong for one that is one person.

CREATE OR REPLACE VIEW v_labour_function_share_by_cohort AS
WITH effort AS (
  SELECT le.period,
         CASE WHEN EXISTS (SELECT 1 FROM v_form_990_officer f
                            WHERE f.period = le.period
                              AND f.employee_key = le.employee_key
                              AND f.on_line_5)
              THEN 'OFFICER' ELSE 'STAFF' END              AS cohort,
         CASE o.objective_type
           WHEN 'ADMINISTRATION'  THEN 'MANAGEMENT_AND_GENERAL'
           WHEN 'FUNDRAISING/B&P' THEN 'FUNDRAISING'
           WHEN 'UNALLOWABLE'     THEN 'MANAGEMENT_AND_GENERAL'
           ELSE 'PROGRAM'
         END                                               AS function_990,
         le.distributed_wages                              AS wages
    FROM v_labor_effective le
    JOIN cost_objective o ON o.objective_id = le.objective_id)
SELECT period, cohort, function_990,
       sum(wages)                                          AS wages,
       round(sum(wages) / NULLIF(sum(sum(wages))
             OVER (PARTITION BY period, cohort), 0), 6)     AS share
  FROM effort
 GROUP BY period, cohort, function_990;

COMMENT ON VIEW v_labour_function_share_by_cohort IS
  'How the effort distribution divides between the three functions the return '
  'prints, separately for the people who reach Part IX line 5 and everybody '
  'else. Line 5 is one person here and the estate''s average is somebody '
  'else''s data.';


CREATE OR REPLACE VIEW v_form_990_officer_pay AS
SELECT period,
       sum(reportable) FILTER (WHERE on_line_5)     AS line_5_wages,
       count(*) FILTER (WHERE on_line_5
                          AND COALESCE(reportable, 0) > 0)
                                                    AS compensated_officers,
       count(*) FILTER (WHERE on_line_5
                          AND employee_key IS NOT NULL
                          AND reportable IS NULL)   AS not_on_the_register,
       sum(other) FILTER (WHERE on_line_5)          AS line_5_other
  FROM v_form_990_officer
 GROUP BY period;

COMMENT ON VIEW v_form_990_officer_pay IS
  'What Part IX line 5 carries, and what it cannot: `line_5_other` is the '
  'other compensation a filed return reports inside line 5, which this record '
  'cannot produce because the fringe pool is six accounts and nothing '
  'allocates it by employee.';
