-- Prior fiscal periods, so a prior-year document can carry its own year.
--
-- The foundational documents in the engagement are not all from 2025. The
-- 2023 and 2024 audited financial statements, the 2023 and 2024 Forms 990
-- and the two NCDMM subrecipient agreements all pre-date the period under
-- review and all bear on it: the agreements govern cost incurred in 2025,
-- and the prior-year statements are where a reviewer looks to see whether
-- this year's treatment is a change in accounting.
--
-- evidence.period is a foreign key to this table. Without a 2023 row, the
-- 2023 Form 990 either cannot be filed at all or has to be filed under 2025,
-- which is a lie told in a column that is queried. Adding the period costs
-- nothing and keeps the register honest about what year a document is from.
--
-- Not marked closed. 2023 and 2024 are closed in the ordinary sense, but
-- `closed` in this schema gates writes to a period's cost record, and
-- nothing in the application writes to those years. Setting a flag that no
-- code reads would be a claim the system does not enforce.

INSERT INTO fiscal_period (period, start_date, end_date)
VALUES ('2023', '2023-01-01', '2023-12-31')
ON CONFLICT (period) DO NOTHING;
