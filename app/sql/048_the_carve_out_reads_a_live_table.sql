-- 048: the facilities carve-out reads the table something actually writes.
--
-- There were two registers of one fact. `space_partition` (009) answered "how
-- much of this building serves what"; `space_unit` (020) answered the same
-- question one suite at a time, with the rent roll attached. Both were
-- defensible on the day they were written and nobody reconciled them
-- afterwards.
--
-- What made it a defect rather than a duplication: `v_facility_occupancy` is
-- the only thing the rate model reads for the 200.465 carve-out, it read
-- `space_partition`, and **nothing in the system has ever written
-- `space_partition`** — not a route, not a script, not a migration. So the
-- carve-out could not fire however much space anybody entered. `PUT
-- /api/facilities/space` wrote a row, the screen showed it, the control in
-- `v_space_unit_control` tied, and the rate carried tenant and vacant space
-- into the federal pool regardless.
--
-- It reads `space_unit` now. `space_partition` is left in place and empty
-- rather than dropped: several worklist views test `NOT EXISTS` against it to
-- decide whether space has been attributed at all, and rewriting six views to
-- chase a table nobody has ever put a row in is a larger change than this
-- one, made on a weekend. It is dead and 049 should drop it, together with
-- those six tests.
--
-- The body below is lifted from 009 unchanged but for the two lines that
-- name the table and the columns that weight it. Retyping a view body from
-- memory silently rewrote how every line of the 990 was categorised once
-- already.

CREATE OR REPLACE VIEW v_facility_occupancy AS
WITH weighted AS (
  SELECT facility_id, period, use,
         usable_sqft * months_occupied / 12 AS sqft
    FROM space_unit),
totals AS (
  SELECT facility_id, period,
         sum(sqft)                                             AS placed,
         sum(sqft) FILTER (WHERE use = 'COMMON')               AS common,
         sum(sqft) FILTER (WHERE use <> 'COMMON')              AS assignable
    FROM weighted GROUP BY facility_id, period)
SELECT f.facility_id,
       f.period,
       f.name,
       f.usable_sqft,
       t.assignable,
       t.common,
       COALESCE(w.tenant, 0)                                   AS tenant_sqft,
       COALESCE(w.vacant, 0)                                   AS vacant_sqft,
       COALESCE(w.committed, 0)                                AS committed_sqft,
       COALESCE(w.program, 0)                                  AS program_sqft,
       COALESCE(w.admin, 0)                                    AS admin_sqft,
       COALESCE(w.shared_lab, 0)                               AS shared_lab_sqft,
       -- Common area rides along with the assignable space it serves.
       CASE WHEN t.assignable > 0
            THEN round((COALESCE(w.program, 0) + COALESCE(w.admin, 0)
                        + COALESCE(w.shared_lab, 0)) / t.assignable, 6)
            ELSE 0 END                                         AS allocable_share,
       CASE WHEN t.assignable > 0
            THEN round((COALESCE(w.tenant, 0) + COALESCE(w.vacant, 0)
                        + COALESCE(w.committed, 0)) / t.assignable, 6)
            ELSE 0 END                                         AS rental_share
  FROM facility f
  JOIN totals t ON t.facility_id = f.facility_id AND t.period = f.period
  LEFT JOIN (
    SELECT facility_id, period,
           sum(sqft) FILTER (WHERE use = 'TENANT')          AS tenant,
           sum(sqft) FILTER (WHERE use = 'VACANT')          AS vacant,
           sum(sqft) FILTER (WHERE use = 'COMMITTED')       AS committed,
           sum(sqft) FILTER (WHERE use = 'PROGRAM')         AS program,
           sum(sqft) FILTER (WHERE use = 'ADMINISTRATIVE')  AS admin,
           sum(sqft) FILTER (WHERE use = 'SHARED_LAB')      AS shared_lab
      FROM weighted GROUP BY facility_id, period) w
    ON w.facility_id = f.facility_id AND w.period = f.period;

COMMENT ON VIEW v_facility_occupancy IS
  'Per facility, the share of occupancy cost that may reach a federal '
  'indirect pool, read from space_unit — the table the facilities screen and '
  'the space workbook write. It read space_partition until 048, which nothing '
  'has ever written, so the carve-out could not fire at all. Facility-'
  'specific by design: a building that is 90% leased and one housing the '
  'additive manufacturing laboratory cannot share one percentage.';
