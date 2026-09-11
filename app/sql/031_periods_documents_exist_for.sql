-- The remaining periods the engagement holds documents for.
--
-- 030 added 2023 for the prior-year statements and Forms 990. The award file
-- reaches further in both directions:
--
--   2021  the EDA award, Form CD-450, executed 13 July 2021 on project
--         06-79-06300. It funded building assets that are still being
--         depreciated, which is the 200.436(b) question.
--   2022  the JobsOhio grant agreement, effective 2 February 2022.
--   2026  Modification 001 to NCDMM 20240061, effective 22 January 2026,
--         which extends the Hybrid period of performance to 30 June 2026 —
--         and the 2026 fixed asset schedule.
--
-- evidence.period is a foreign key to this table, so a document from a year
-- with no row here can only be filed under a year it is not from. The
-- register is queried on that column; a document filed under the wrong year
-- is a wrong answer rather than a missing one.
--
-- These are calendar years because YBI's fiscal year is the calendar year —
-- the 2025 general ledger runs 1 January to 31 December.

INSERT INTO fiscal_period (period, start_date, end_date)
VALUES ('2021', '2021-01-01', '2021-12-31'),
       ('2022', '2022-01-01', '2022-12-31'),
       ('2026', '2026-01-01', '2026-12-31')
ON CONFLICT (period) DO NOTHING;
