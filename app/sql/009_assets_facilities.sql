-- =====================================================================
-- Assets and facilities
--
-- The two evidence gaps that decide the rate. Depreciation and occupancy are
-- together about $1.5M of 2025 cost against $6.74M of total expense, and the
-- modelled rate range of 36-46% is almost entirely these two items.
--
-- The asset fields are 2 CFR 200.313(d)(1) rather than a list of our own, so
-- a register that satisfies this table is compliant on its own merits.
-- =====================================================================

CREATE TYPE funding_kind AS ENUM (
  'FEDERAL', 'STATE', 'LOCAL', 'PRIVATE', 'DEBT', 'UNRESTRICTED');

CREATE TYPE space_use AS ENUM (
  'TENANT',        -- leased to a third party; recovered through rent
  'PROGRAM',       -- used to deliver a specific program
  'ADMINISTRATIVE',
  'SHARED_LAB',    -- serves several programs; square footage is the wrong driver alone
  'COMMON',        -- corridors, restrooms, mechanical; prorated over the rest
  'VACANT',        -- a cost of the rental operation, never a federal cost
  'COMMITTED');    -- promised to a third party, e.g. the YSU joint use space


CREATE TABLE asset (
  asset_id            text PRIMARY KEY,
  period              text NOT NULL REFERENCES fiscal_period,
  description         text NOT NULL,
  serial_number       text NOT NULL DEFAULT '',      -- 200.313(d)(1)
  gl_account          text NOT NULL DEFAULT '',
  facility_id         text,                          -- set once facilities land
  title_holder        text NOT NULL DEFAULT '',      -- 200.313(d)(1)

  acquired_on         date,
  in_service_on       date,
  disposed_on         date,
  disposal_proceeds   numeric(14,2),

  -- The gross cost BEFORE any reimbursement was netted against it. Finding
  -- 2024-001 records that federal and state reimbursements were netted against
  -- capital cost, so the book value understates the basis and cannot be used
  -- to derive federal participation. Rebuilding from book value would carry
  -- the finding into the rate.
  gross_cost          numeric(14,2) NOT NULL,
  book_cost           numeric(14,2),                 -- as currently recorded, for the bridge

  useful_life_years   numeric(6,2),
  method              text NOT NULL DEFAULT 'STRAIGHT_LINE',
  salvage_value       numeric(14,2) NOT NULL DEFAULT 0,
  accum_depr_open     numeric(14,2) NOT NULL DEFAULT 0,
  accum_depr_close    numeric(14,2) NOT NULL DEFAULT 0,
  depreciation        numeric(14,2) NOT NULL DEFAULT 0,   -- current year

  depreciable         boolean NOT NULL DEFAULT true,      -- land is not
  in_use              boolean NOT NULL DEFAULT true,      -- 200.436 wants it in use
  condition           text NOT NULL DEFAULT '',
  last_inventory_on   date,                               -- 200.313(d)(2)

  source_document     text NOT NULL DEFAULT '',
  evidence_grade      evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  note                text NOT NULL DEFAULT '',
  loaded_at           timestamptz NOT NULL DEFAULT now(),
  loaded_by           text NOT NULL DEFAULT '',

  CONSTRAINT asset_gross_cost_sane CHECK (gross_cost >= 0),
  CONSTRAINT asset_land_is_not_depreciated
    CHECK (depreciable OR depreciation = 0),
  CONSTRAINT asset_disposal_pair
    CHECK ((disposed_on IS NULL) OR (disposal_proceeds IS NOT NULL))
);
CREATE INDEX ON asset (period, gl_account);
CREATE INDEX ON asset (facility_id);


-- One asset can be funded from several sources. This is the field that decides
-- allowability, and it is the one most often missing from a register.
CREATE TABLE asset_funding (
  asset_id            text NOT NULL REFERENCES asset ON DELETE CASCADE,
  kind                funding_kind NOT NULL,
  amount              numeric(14,2) NOT NULL,
  award_reference     text NOT NULL DEFAULT '',   -- FAIN, grant number, ALN
  funder              text NOT NULL DEFAULT '',
  -- Where non-federal money was itself counted as cost share on a federal
  -- award, it has already been used once. Depreciating it into a federal
  -- indirect pool may be a second recovery of the same dollars, so it is
  -- flagged for judgment rather than netted automatically.
  counted_as_cost_share boolean NOT NULL DEFAULT false,
  evidence_id         text REFERENCES evidence,
  note                text NOT NULL DEFAULT '',
  PRIMARY KEY (asset_id, kind, award_reference),
  CONSTRAINT asset_funding_amount_sane CHECK (amount >= 0)
);


-- Funding cannot exceed what the asset cost. Deferred so a whole asset's
-- funding lands as a set.
CREATE FUNCTION asset_funding_within_cost() RETURNS trigger AS $$
DECLARE
  target text := COALESCE(NEW.asset_id, OLD.asset_id);
  funded numeric(14,2);
  cost   numeric(14,2);
BEGIN
  SELECT COALESCE(sum(amount), 0) INTO funded
    FROM asset_funding WHERE asset_id = target;
  SELECT gross_cost INTO cost FROM asset WHERE asset_id = target;
  IF cost IS NOT NULL AND funded - cost > 0.01 THEN
    RAISE EXCEPTION
      'Asset % is funded %, more than its gross cost of %. Funding that '
      'exceeds cost means a source is double counted or the cost is stated '
      'net of a reimbursement.', target, funded, cost
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER asset_funding_within_cost
  AFTER INSERT OR UPDATE OR DELETE ON asset_funding
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION asset_funding_within_cost();


-- ── Allowable depreciation ───────────────────────────────────────────
--
-- 2 CFR 200.436: depreciation is not allowable on the portion of asset cost
-- borne by the Federal Government. Unfunded cost is treated as YBI's own,
-- because an asset with no recorded funding source is not thereby federal —
-- but it is also not evidenced, which is what evidence_grade carries.

CREATE VIEW v_asset_allowability AS
SELECT a.asset_id,
       a.period,
       a.description,
       a.gl_account,
       a.facility_id,
       a.gross_cost,
       a.depreciation,
       a.evidence_grade,
       a.in_use,
       COALESCE(f.federal, 0)                                  AS federal_funding,
       COALESCE(f.state, 0)                                    AS state_funding,
       COALESCE(f.other, 0)                                    AS other_funding,
       COALESCE(f.total, 0)                                    AS total_funding,
       GREATEST(a.gross_cost - COALESCE(f.total, 0), 0)        AS unfunded_cost,
       CASE WHEN a.gross_cost > 0
            THEN LEAST(COALESCE(f.federal, 0) / a.gross_cost, 1)
            ELSE 0 END                                         AS federal_share,
       -- The number the rate uses.
       CASE
         WHEN NOT a.in_use THEN 0
         WHEN a.gross_cost <= 0 THEN 0
         ELSE round(a.depreciation
                    * (1 - LEAST(COALESCE(f.federal, 0) / a.gross_cost, 1)), 2)
       END                                                     AS allowable_depreciation,
       COALESCE(f.cost_shared, 0)                              AS cost_shared_funding,
       (COALESCE(f.total, 0) = 0)                              AS funding_unknown
  FROM asset a
  LEFT JOIN (
    SELECT asset_id,
           sum(amount) FILTER (WHERE kind = 'FEDERAL')                 AS federal,
           sum(amount) FILTER (WHERE kind = 'STATE')                   AS state,
           sum(amount) FILTER (WHERE kind NOT IN ('FEDERAL','STATE'))  AS other,
           sum(amount)                                                 AS total,
           sum(amount) FILTER (WHERE counted_as_cost_share)            AS cost_shared
      FROM asset_funding GROUP BY asset_id) f ON f.asset_id = a.asset_id;

COMMENT ON VIEW v_asset_allowability IS
  'Allowable depreciation per 2 CFR 200.436: the federally funded share of an '
  'asset does not depreciate into a federal indirect pool. funding_unknown '
  'marks assets whose funding source has not been established — their '
  'depreciation is currently treated as fully allowable, which is the '
  'optimistic reading and must not survive to a sealed rate.';


-- The control: the register must tie to the ledger, or explain the gap.
CREATE VIEW v_asset_control AS
SELECT p.period,
       (SELECT count(*) FROM asset WHERE period = p.period)              AS assets,
       (SELECT count(*) FROM asset a WHERE a.period = p.period
          AND NOT EXISTS (SELECT 1 FROM asset_funding f
                           WHERE f.asset_id = a.asset_id))               AS funding_unknown,
       (SELECT COALESCE(sum(gross_cost), 0) FROM asset
         WHERE period = p.period)                                        AS gross_cost,
       (SELECT COALESCE(sum(depreciation), 0) FROM asset
         WHERE period = p.period)                                        AS register_depreciation,
       (SELECT COALESCE(sum(allowable_depreciation), 0)
          FROM v_asset_allowability WHERE period = p.period)             AS allowable_depreciation,
       (SELECT COALESCE(sum(amount), 0) FROM ledger_line
         WHERE period = p.period AND account LIKE '%5010%')              AS ledger_depreciation,
       (SELECT COALESCE(sum(depreciation), 0) FROM asset
         WHERE period = p.period)
       - (SELECT COALESCE(sum(amount), 0) FROM ledger_line
           WHERE period = p.period AND account LIKE '%5010%')            AS variance
  FROM fiscal_period p;


-- ── Facilities and space ─────────────────────────────────────────────

CREATE TABLE facility (
  facility_id       text PRIMARY KEY,
  period            text NOT NULL REFERENCES fiscal_period,
  name              text NOT NULL,
  address           text NOT NULL DEFAULT '',
  owned             boolean NOT NULL DEFAULT true,
  usable_sqft       numeric(12,2) NOT NULL,
  source_document   text NOT NULL DEFAULT '',
  evidence_grade    evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  note              text NOT NULL DEFAULT '',
  CONSTRAINT facility_sqft_sane CHECK (usable_sqft > 0)
);


CREATE TABLE space_partition (
  partition_id      bigserial PRIMARY KEY,
  facility_id       text NOT NULL REFERENCES facility,
  period            text NOT NULL REFERENCES fiscal_period,
  use               space_use NOT NULL,
  objective_id      text REFERENCES cost_objective,   -- when use = PROGRAM
  sqft              numeric(12,2) NOT NULL,
  months            numeric(4,1) NOT NULL DEFAULT 12, -- vacancy moves during a year
  tenant            text NOT NULL DEFAULT '',
  rationale         text NOT NULL DEFAULT '',
  evidence_id       text REFERENCES evidence,
  CONSTRAINT partition_sqft_sane CHECK (sqft >= 0),
  CONSTRAINT partition_months_sane CHECK (months > 0 AND months <= 12),
  CONSTRAINT program_space_names_an_objective
    CHECK (use <> 'PROGRAM' OR objective_id IS NOT NULL)
);
CREATE INDEX ON space_partition (facility_id, period);


-- A facility's partitions must account for its usable space. Weighted by
-- months, so a suite vacant for half the year counts as half a suite.
CREATE FUNCTION space_must_account_for_facility() RETURNS trigger AS $$
DECLARE
  fid   text := COALESCE(NEW.facility_id, OLD.facility_id);
  per   text := COALESCE(NEW.period, OLD.period);
  usable numeric(12,2);
  placed numeric(12,2);
BEGIN
  SELECT usable_sqft INTO usable FROM facility WHERE facility_id = fid;
  IF usable IS NULL THEN RETURN NULL; END IF;

  SELECT COALESCE(sum(sqft * months / 12), 0) INTO placed
    FROM space_partition WHERE facility_id = fid AND period = per;

  IF placed = 0 THEN RETURN NULL; END IF;   -- not yet partitioned

  IF abs(placed - usable) > 1 THEN
    RAISE EXCEPTION
      'Facility % partitions to % square feet for %, against % usable. Space '
      'must be accounted for in full, including what is common and what is '
      'vacant.', fid, placed, per, usable
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER space_accounts_for_facility
  AFTER INSERT OR UPDATE OR DELETE ON space_partition
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION space_must_account_for_facility();


-- ── The occupancy carve-out ──────────────────────────────────────────
--
-- 2 CFR 200.465: space cost follows the activity that uses it. Tenant space is
-- recovered through rent and vacant space is a cost of the rental operation;
-- neither reaches a federal pool. Common area is prorated across the
-- assignable uses it serves rather than assigned.

CREATE VIEW v_facility_occupancy AS
WITH weighted AS (
  SELECT facility_id, period, use, sqft * months / 12 AS sqft
    FROM space_partition),
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
  'Per facility, the share of occupancy cost that may reach a federal indirect '
  'pool. Facility-specific by design: a building that is 90% leased and one '
  'housing the additive manufacturing laboratory cannot share one percentage.';
