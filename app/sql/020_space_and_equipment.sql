-- =====================================================================
-- Five buildings, the equipment in them, and what it is all worth
--
-- Three jobs that share one set of facts.
--
-- The first is the rate. Space cost follows the activity that uses it, and
-- until the square footage is partitioned the facilities carve-out is an
-- estimate. 009 built that. What it could not do is say which suite, which
-- tenant, or what was charged.
--
-- The second is the story. YBI is an incubator: it lets space below market
-- and lends equipment for nothing. That subsidy is the mission, and nobody
-- has ever counted it.
--
-- The third is cost share, and this is where the schema has to be careful,
-- because the first two make it tempting.
--
--   *Space YBI owns and lets cheaply is not cost share.* Under 2 CFR 200.465
--   a less-than-arm's-length rental is allowable only up to what ownership
--   would have cost — depreciation, maintenance, taxes, insurance — so an
--   organisation cannot charge itself market rent and claim the discount.
--   Forgone revenue on your own property is not a cost you incurred.
--
--   What *is* claimable is property or use donated to YBI by a third party
--   (200.306(h)), and unrecovered indirect cost, but only with the awarding
--   agency's prior written approval (200.306(c)).
--
-- So value is captured for everything and the claim is typed, with a check
-- that refuses to mark a subsidy on YBI's own property as cost share. The
-- number is still worth having — for the 990 narrative, for the board, for
-- the state, and for arguing a facilities component on 2026 proposals — it
-- just is not that number.
-- =====================================================================

ALTER TABLE facility
  ADD COLUMN code            text,
  ADD COLUMN rentable_sqft   numeric(12,2),
  ADD COLUMN year_built      integer,
  ADD COLUMN landlord        text NOT NULL DEFAULT '',
  ADD COLUMN annual_lease_cost numeric(14,2),
  ADD COLUMN market_rate_psf numeric(10,2),
  ADD COLUMN market_basis    text NOT NULL DEFAULT '',
  ADD CONSTRAINT facility_rentable_sane
    CHECK (rentable_sqft IS NULL OR rentable_sqft >= usable_sqft),
  ADD CONSTRAINT leased_names_a_landlord
    CHECK (owned OR length(btrim(landlord)) > 0);

COMMENT ON COLUMN facility.market_rate_psf IS
  'Comparable market rent per square foot per year, with market_basis saying '
  'where it came from. Used to value the subsidy YBI provides; never a cost '
  'YBI incurred.';


-- ── Lettable detail ──────────────────────────────────────────────────
--
-- space_partition answers "how much of this building serves what", which is
-- what the rate needs. It cannot answer "what is suite 210 and who is in it",
-- which is what a rent roll is and what the market comparison needs. Both,
-- reconciled to each other by a control rather than one quietly overriding
-- the other.

CREATE TYPE occupancy_status AS ENUM (
  'OCCUPIED', 'VACANT', 'INTERNAL', 'COMMITTED', 'COMMON');

CREATE TABLE space_unit (
  unit_id         text PRIMARY KEY,
  facility_id     text NOT NULL REFERENCES facility,
  period          text NOT NULL REFERENCES fiscal_period,
  label           text NOT NULL,                     -- "Suite 210", "Lab 1"
  floor           text NOT NULL DEFAULT '',
  usable_sqft     numeric(12,2) NOT NULL,
  use             space_use NOT NULL,
  status          occupancy_status NOT NULL,
  objective_id    text REFERENCES cost_objective,    -- when the use is PROGRAM
  occupant        text NOT NULL DEFAULT '',
  months_occupied numeric(4,1) NOT NULL DEFAULT 12,

  -- What was actually charged, and what the space would fetch.
  actual_annual_charge numeric(14,2),
  market_rate_psf      numeric(10,2),
  market_basis         text NOT NULL DEFAULT '',
  market_source        text NOT NULL DEFAULT '',
  evidence_id          text REFERENCES evidence,
  note                 text NOT NULL DEFAULT '',

  CONSTRAINT unit_sqft_sane CHECK (usable_sqft > 0),
  CONSTRAINT unit_months_sane CHECK (months_occupied > 0 AND months_occupied <= 12),
  CONSTRAINT unit_program_names_objective
    CHECK (use <> 'PROGRAM' OR objective_id IS NOT NULL),
  CONSTRAINT unit_occupied_names_occupant
    CHECK (status <> 'OCCUPIED' OR length(btrim(occupant)) > 0),
  -- A market rate asserted with no basis is a number somebody made up.
  CONSTRAINT unit_market_needs_basis
    CHECK (market_rate_psf IS NULL OR length(btrim(market_basis)) > 10)
);
CREATE INDEX ON space_unit (facility_id, period);


-- The control: units have to reconcile to the building, and to the partition
-- that drives the rate. Reported rather than enforced — a rent roll arriving
-- before a floor plan is a normal Tuesday, and refusing the first until the
-- second agrees would mean neither ever gets entered.
CREATE VIEW v_space_unit_control AS
SELECT f.facility_id, f.period, f.name, f.usable_sqft,
       COALESCE(sum(u.usable_sqft), 0)                   AS unit_sqft,
       COALESCE(sum(u.usable_sqft * u.months_occupied / 12), 0)
                                                         AS unit_sqft_weighted,
       round(COALESCE(sum(u.usable_sqft), 0) - f.usable_sqft, 2) AS variance,
       (abs(COALESCE(sum(u.usable_sqft), 0) - f.usable_sqft) <= 1) AS ties,
       count(u.unit_id)                                  AS units
  FROM facility f
  LEFT JOIN space_unit u ON u.facility_id = f.facility_id AND u.period = f.period
 GROUP BY f.facility_id, f.period, f.name, f.usable_sqft;


-- ── What the space is worth, and what was charged for it ─────────────

CREATE VIEW v_space_economics AS
SELECT u.unit_id, u.facility_id, f.name AS facility_name, u.period, u.label,
       u.use, u.status, u.occupant, u.objective_id,
       u.usable_sqft, u.months_occupied,
       round(u.usable_sqft * u.months_occupied / 12, 2)  AS sqft_years,
       u.actual_annual_charge,
       COALESCE(u.market_rate_psf, f.market_rate_psf)    AS market_rate_psf,
       CASE WHEN COALESCE(u.market_rate_psf, f.market_rate_psf) IS NOT NULL
            THEN round(u.usable_sqft * u.months_occupied / 12
                       * COALESCE(u.market_rate_psf, f.market_rate_psf), 2)
       END                                               AS market_value,
       CASE WHEN COALESCE(u.market_rate_psf, f.market_rate_psf) IS NOT NULL
            THEN round(u.usable_sqft * u.months_occupied / 12
                       * COALESCE(u.market_rate_psf, f.market_rate_psf)
                       - COALESCE(u.actual_annual_charge, 0), 2)
       END                                               AS subsidy,
       COALESCE(NULLIF(u.market_basis, ''), f.market_basis) AS market_basis,
       (COALESCE(u.market_rate_psf, f.market_rate_psf) IS NULL) AS market_unknown,
       f.owned
  FROM space_unit u
  JOIN facility f ON f.facility_id = u.facility_id AND f.period = u.period;

COMMENT ON VIEW v_space_economics IS
  'What each space would fetch against what was charged for it. On property '
  'YBI owns the difference is mission value, not cost share: 2 CFR 200.465 '
  'allows a less-than-arm''s-length rental only up to what ownership cost.';


-- ── Equipment ────────────────────────────────────────────────────────
--
-- Two things the register could not say. The first is where a machine
-- physically is and how much room it takes — program equipment standing in a
-- shared lab consumes space that the square-footage carve-out otherwise
-- treats as serving everybody. The second is what its use was worth: an
-- incubator lends equipment for nothing, and nobody has counted that either.

CREATE TYPE access_policy AS ENUM ('FREE', 'SUBSIDIZED', 'CHARGED', 'INTERNAL');

ALTER TABLE asset
  ADD COLUMN unit_id            text REFERENCES space_unit,
  ADD COLUMN footprint_sqft     numeric(10,2),
  ADD COLUMN is_program_equipment boolean NOT NULL DEFAULT false,
  ADD COLUMN access             access_policy NOT NULL DEFAULT 'INTERNAL',
  ADD COLUMN market_hourly_rate numeric(10,2),
  ADD COLUMN actual_hourly_rate numeric(10,2),
  ADD COLUMN rate_basis         text NOT NULL DEFAULT '',
  ADD CONSTRAINT asset_footprint_sane
    CHECK (footprint_sqft IS NULL OR footprint_sqft > 0),
  ADD CONSTRAINT asset_market_rate_needs_basis
    CHECK (market_hourly_rate IS NULL OR length(btrim(rate_basis)) > 10);

COMMENT ON COLUMN asset.footprint_sqft IS
  'Floor area the machine occupies, including the clearance it needs. '
  'Equipment dedicated to one programme standing in a shared lab consumes '
  'space the carve-out would otherwise spread across everything.';


-- Hours somebody used a machine, and who for. The unit of the equipment
-- subsidy, and the driver for allocating lab cost by use rather than by
-- floor area alone.
CREATE TABLE equipment_use (
  use_id        bigserial PRIMARY KEY,
  asset_id      text NOT NULL REFERENCES asset,
  period        text NOT NULL REFERENCES fiscal_period,
  objective_id  text REFERENCES cost_objective,
  user_name     text NOT NULL DEFAULT '',
  hours         numeric(10,2) NOT NULL,
  charged       numeric(14,2) NOT NULL DEFAULT 0,
  source_document text NOT NULL DEFAULT '',
  note          text NOT NULL DEFAULT '',
  recorded_by   uuid REFERENCES actor,
  recorded_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT equipment_hours_sane CHECK (hours > 0),
  CONSTRAINT equipment_charged_sane CHECK (charged >= 0)
);
CREATE INDEX ON equipment_use (asset_id, period);


CREATE VIEW v_equipment_subsidy AS
SELECT a.asset_id, a.period, a.description, a.facility_id, a.unit_id,
       a.access::text                                   AS access,
       a.is_program_equipment, a.footprint_sqft,
       a.market_hourly_rate, a.actual_hourly_rate, a.rate_basis,
       COALESCE(sum(u.hours), 0)                        AS hours_used,
       COALESCE(sum(u.charged), 0)                      AS charged,
       CASE WHEN a.market_hourly_rate IS NOT NULL
            THEN round(COALESCE(sum(u.hours), 0) * a.market_hourly_rate, 2)
       END                                              AS market_value,
       CASE WHEN a.market_hourly_rate IS NOT NULL
            THEN round(COALESCE(sum(u.hours), 0) * a.market_hourly_rate
                       - COALESCE(sum(u.charged), 0), 2)
       END                                              AS subsidy,
       (a.market_hourly_rate IS NULL AND a.access IN ('FREE', 'SUBSIDIZED'))
                                                        AS rate_unknown
  FROM asset a
  LEFT JOIN equipment_use u ON u.asset_id = a.asset_id AND u.period = a.period
 GROUP BY a.asset_id, a.period, a.description, a.facility_id, a.unit_id,
          a.access, a.is_program_equipment, a.footprint_sqft,
          a.market_hourly_rate, a.actual_hourly_rate, a.rate_basis;


-- Shared lab space consumed by equipment that serves one programme. The
-- footprint is not really shared, and treating it as shared moves cost onto
-- programmes that never touched the machine.
CREATE VIEW v_lab_space_consumed AS
SELECT u.unit_id, u.facility_id, u.period, u.label, u.use, u.usable_sqft,
       COALESCE(sum(a.footprint_sqft), 0)                  AS equipment_sqft,
       COALESCE(sum(a.footprint_sqft) FILTER (WHERE a.is_program_equipment), 0)
                                                           AS program_equipment_sqft,
       round(u.usable_sqft - COALESCE(sum(a.footprint_sqft), 0), 2)
                                                           AS free_sqft,
       CASE WHEN u.usable_sqft > 0
            THEN round(COALESCE(sum(a.footprint_sqft), 0) / u.usable_sqft, 4)
       END                                                 AS occupied_share,
       count(a.asset_id)                                   AS machines
  FROM space_unit u
  LEFT JOIN asset a ON a.unit_id = u.unit_id AND a.period = u.period
 WHERE u.use IN ('SHARED_LAB', 'COMMON', 'PROGRAM')
 GROUP BY u.unit_id, u.facility_id, u.period, u.label, u.use, u.usable_sqft;


-- ── In-kind: what may be claimed, and what may only be told ──────────

CREATE TYPE in_kind_kind AS ENUM (
  'THIRD_PARTY_SPACE',      -- somebody gave YBI space:      200.306(h)
  'THIRD_PARTY_EQUIPMENT',  -- somebody gave YBI use:        200.306(h)
  'THIRD_PARTY_SERVICES',   -- volunteer services:           200.306(e)-(f)
  'OWN_SPACE_SUBSIDY',      -- YBI let its own space cheaply: NOT cost share
  'OWN_EQUIPMENT_SUBSIDY',  -- YBI lent its own kit:          NOT cost share
  'UNRECOVERED_INDIRECT');  -- 200.306(c): prior approval only

CREATE TABLE in_kind_claim (
  claim_id        bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  kind            in_kind_kind NOT NULL,
  objective_id    text REFERENCES cost_objective,
  award_id        text REFERENCES award,
  description     text NOT NULL,
  measured        text NOT NULL DEFAULT '',    -- "1,240 sqft-years", "310 hours"
  value           numeric(14,2) NOT NULL,
  valuation_basis text NOT NULL,
  source_document text NOT NULL DEFAULT '',
  evidence_id     text REFERENCES evidence,
  -- Whether this is being offered as cost share, and the approval if it needs
  -- one. The check below is the whole point of the table.
  claimed_as_cost_share boolean NOT NULL DEFAULT false,
  agency_approval text NOT NULL DEFAULT '',
  recorded_by     uuid REFERENCES actor,
  recorded_name   text NOT NULL DEFAULT '',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  superseded_at   timestamptz,

  CONSTRAINT in_kind_value_sane CHECK (value >= 0),
  CONSTRAINT in_kind_basis_present CHECK (length(btrim(valuation_basis)) > 10),

  -- The rule, in the schema rather than in a handler or a habit. YBI's own
  -- subsidy is mission value and cannot be offered as cost share at all;
  -- unrecovered indirect can, but only with the awarding agency's prior
  -- written approval under 200.306(c).
  CONSTRAINT own_subsidy_is_not_cost_share
    CHECK (NOT claimed_as_cost_share
           OR kind NOT IN ('OWN_SPACE_SUBSIDY', 'OWN_EQUIPMENT_SUBSIDY')),
  CONSTRAINT unrecovered_indirect_needs_approval
    CHECK (NOT claimed_as_cost_share
           OR kind <> 'UNRECOVERED_INDIRECT'
           OR length(btrim(agency_approval)) > 0)
);
CREATE INDEX ON in_kind_claim (period) WHERE superseded_at IS NULL;

CREATE TRIGGER in_kind_claim_immutable
  BEFORE UPDATE OF period, kind, value, valuation_basis, claimed_as_cost_share,
                   recorded_by, recorded_at
  ON in_kind_claim FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER in_kind_claim_no_delete
  BEFORE DELETE ON in_kind_claim FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


CREATE VIEW v_in_kind_summary AS
SELECT c.period, c.kind::text AS kind, c.claimed_as_cost_share,
       CASE c.kind
         WHEN 'OWN_SPACE_SUBSIDY'     THEN 'Mission value — not cost share'
         WHEN 'OWN_EQUIPMENT_SUBSIDY' THEN 'Mission value — not cost share'
         WHEN 'UNRECOVERED_INDIRECT'  THEN 'Cost share only with prior approval'
         ELSE 'Third-party in-kind — cost share eligible'
       END                                            AS standing,
       CASE c.kind
         WHEN 'OWN_SPACE_SUBSIDY'     THEN '2 CFR 200.465'
         WHEN 'OWN_EQUIPMENT_SUBSIDY' THEN '2 CFR 200.465'
         WHEN 'UNRECOVERED_INDIRECT'  THEN '2 CFR 200.306(c)'
         WHEN 'THIRD_PARTY_SERVICES'  THEN '2 CFR 200.306(e)-(f)'
         ELSE '2 CFR 200.306(h)'
       END                                            AS citation,
       count(*)                                       AS claims,
       sum(c.value)                                   AS value
  FROM in_kind_claim c
 WHERE c.superseded_at IS NULL
 GROUP BY c.period, c.kind, c.claimed_as_cost_share;


-- The five buildings at a glance, with the subsidy they carry.
CREATE VIEW v_facility_summary AS
SELECT f.facility_id, f.period, f.code, f.name, f.address, f.owned,
       f.usable_sqft, f.rentable_sqft, f.market_rate_psf, f.landlord,
       f.annual_lease_cost,
       COALESCE(sum(e.sqft_years), 0)                       AS units_sqft_years,
       count(e.unit_id)                                     AS units,
       count(e.unit_id) FILTER (WHERE e.status = 'OCCUPIED') AS occupied_units,
       COALESCE(sum(e.actual_annual_charge), 0)             AS charged,
       COALESCE(sum(e.market_value), 0)                     AS market_value,
       COALESCE(sum(e.subsidy), 0)                          AS subsidy,
       count(*) FILTER (WHERE e.market_unknown)             AS units_without_market,
       (SELECT COALESCE(sum(a.footprint_sqft), 0) FROM asset a
         WHERE a.facility_id = f.facility_id AND a.period = f.period)
                                                            AS equipment_sqft
  FROM facility f
  LEFT JOIN v_space_economics e
         ON e.facility_id = f.facility_id AND e.period = f.period
 GROUP BY f.facility_id, f.period, f.code, f.name, f.address, f.owned,
          f.usable_sqft, f.rentable_sqft, f.market_rate_psf, f.landlord,
          f.annual_lease_cost;
