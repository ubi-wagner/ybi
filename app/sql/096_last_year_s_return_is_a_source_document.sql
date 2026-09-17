-- 096 — the 2024 return is a source document, so its figures live on the record
--
-- `docs/FORM_990_2025_vs_2024.md` compares this year's return with last
-- year's line for line. The prior-year figures could sit in the script that
-- writes it, and that is exactly the shape this file has been wrong about
-- more than once: *figures in a document for somebody else get read from the
-- record, not recalled.* Three dates in `FOR_TOM_TO_VERIFY.md` were written
-- from memory and were wrong by weeks.
--
-- The 2024 Form 990 has been on file since the foundation was loaded —
-- `2024_Form-990_ProPublica_full-filing.pdf`, 36 pages, text extracted. This
-- is its Part IX and Part VIII transcribed as printed, line by line, so the
-- comparison reads the document rather than a memory of it and
-- `v_form_990_prior_check` can ask whether the transcription foots.
--
-- **Transcribed as printed, and nothing adjusted.** Line 3 reports $63,568 of
-- assistance to foreign organisations, which is a surprising line for an
-- incubator in Mahoning County and is what the return says. A loader that
-- moved it to line 1 to make the years comparable would be correcting a filed
-- return, which is not this system's to do.

CREATE TABLE IF NOT EXISTS form_990_prior_year (
    period       text NOT NULL,
    line_id      text NOT NULL REFERENCES form_990_line(line_id),
    total        numeric(14,2) NOT NULL DEFAULT 0,
    program      numeric(14,2) NOT NULL DEFAULT 0,
    management   numeric(14,2) NOT NULL DEFAULT 0,
    fundraising  numeric(14,2) NOT NULL DEFAULT 0,
    source       text NOT NULL DEFAULT '',

    PRIMARY KEY (period, line_id),
    CONSTRAINT prior_year_columns_foot
      CHECK (total = program + management + fundraising
             OR program + management + fundraising = 0)
);

COMMENT ON TABLE form_990_prior_year IS
  'A filed Form 990, transcribed as printed. The 2024 return is on file as a '
  'document and its figures belong on the record rather than inside the '
  'script that reads them — the rule this file states as: figures in a '
  'document for somebody else get read from the record, not recalled.';

INSERT INTO form_990_prior_year
  (period, line_id, total, program, management, fundraising, source) VALUES
  -- Part IX, Statement of Functional Expenses, page 10 of the filing.
  ('2024', '1',   549977,   549977,        0,       0, '2024 Form 990 Part IX'),
  ('2024', '3',    63568,    63568,        0,       0, '2024 Form 990 Part IX'),
  ('2024', '5',   167967,   134775,    26568,    6624, '2024 Form 990 Part IX'),
  ('2024', '7',  1470691,  1175980,   234470,   60241, '2024 Form 990 Part IX'),
  ('2024', '9',   159611,   135500,    21890,    2221, '2024 Form 990 Part IX'),
  ('2024', '10',  142532,   114658,    22057,    5817, '2024 Form 990 Part IX'),
  ('2024', '11b',   8390,     6751,     1315,     324, '2024 Form 990 Part IX'),
  ('2024', '11c',  90290,    72656,    14148,    3486, '2024 Form 990 Part IX'),
  ('2024', '11g', 649104,   640895,     6414,    1795, '2024 Form 990 Part IX'),
  ('2024', '12',   97887,        0,        0,   97887, '2024 Form 990 Part IX'),
  ('2024', '13',    8965,     7188,     1426,     351, '2024 Form 990 Part IX'),
  ('2024', '16',  445109,   358179,    69749,   17181, '2024 Form 990 Part IX'),
  ('2024', '20',   81318,    65437,    12743,    3138, '2024 Form 990 Part IX'),
  ('2024', '22',  704131,   566614,   110337,   27180, '2024 Form 990 Part IX'),
  ('2024', '23',   56041,    45096,     8782,    2163, '2024 Form 990 Part IX'),
  ('2024', '24a',  64167,    51709,     9996,    2462, '2024 Form 990 Part IX · DUES AND SUBSCRIPTIONS'),
  ('2024', '24b',  37517,    32269,     2546,    2702, '2024 Form 990 Part IX · TRAINING AND SEMINARS'),
  ('2024', '24c',  34812,    28013,     5455,    1344, '2024 Form 990 Part IX · REAL ESTATE TAXES'),
  ('2024', '24d',  22728,    18286,     3403,    1039, '2024 Form 990 Part IX · MEALS'),
  ('2024', '24e',  64196,    51562,    10040,    2594, '2024 Form 990 Part IX · All other expenses'),
  -- Part VIII, Statement of Revenue, page 9 of the filing.
  ('2024', 'V1',  6683962,        0,        0,       0, '2024 Form 990 Part VIII line 1h'),
  ('2024', 'V2',        0,        0,        0,       0, '2024 Form 990 Part VIII line 2g'),
  ('2024', 'V3',        0,        0,        0,       0, '2024 Form 990 Part VIII line 3'),
  ('2024', 'V6',   616045,        0,        0,       0, '2024 Form 990 Part VIII line 6a'),
  ('2024', 'V8',   367629,        0,        0,       0, '2024 Form 990 Part VIII line 8a'),
  ('2024', 'V11',   18262,        0,        0,       0, '2024 Form 990 Part VIII line 11a'),
  ('2024', '8b',   139739,        0,        0,  139739, '2024 Form 990 Part VIII line 8b')
ON CONFLICT (period, line_id) DO UPDATE
  SET total = EXCLUDED.total, program = EXCLUDED.program,
      management = EXCLUDED.management, fundraising = EXCLUDED.fundraising,
      source = EXCLUDED.source;


CREATE OR REPLACE VIEW v_form_990_prior_check AS
SELECT p.period,
       sum(p.total) FILTER (WHERE l.part = 'IX')        AS part_ix_total,
       sum(p.program) FILTER (WHERE l.part = 'IX')      AS part_ix_program,
       sum(p.management) FILTER (WHERE l.part = 'IX')   AS part_ix_management,
       sum(p.fundraising) FILTER (WHERE l.part = 'IX')  AS part_ix_fundraising,
       -- Total revenue takes fundraising events **net**, which is what the
       -- form's own line 12 adds: 8a less 8b, not 8a.
       sum(p.total) FILTER (WHERE l.part = 'VIII' AND p.line_id <> '8b')
         - sum(p.total) FILTER (WHERE p.line_id = '8b') AS total_revenue,
       CASE WHEN sum(p.total) FILTER (WHERE l.part = 'IX')
               = sum(p.program + p.management + p.fundraising)
                 FILTER (WHERE l.part = 'IX')
            THEN 'TIES' ELSE 'OPEN' END                 AS state
  FROM form_990_prior_year p
  JOIN form_990_line l ON l.line_id = p.line_id
 GROUP BY p.period;

COMMENT ON VIEW v_form_990_prior_check IS
  'Whether the transcription of a filed return foots the way the return does '
  '— the three functional columns to the total, and Part VIII line 12 taking '
  'fundraising events net of their direct expenses. A transcription nobody '
  'checked is a recollection with a citation on it.';
