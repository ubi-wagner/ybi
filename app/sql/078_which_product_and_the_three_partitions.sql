-- 078  Which product a piece of outstanding work belongs to, and the three
--      partitions the 2025 audit has to close
--
-- ── The worklist did not know which job it was ───────────────────────
--
-- The tabs were split into two products — a year being closed and a company
-- being run — and the worklist was not, so the controller's audit home
-- opened on `NEEDS_CERTIFICATION` (43) and `EMPLOYMENT_UNKNOWN` (43): two of
-- its six rows were timesheet-system work behind the wrong door, and both
-- were things the controller is specifically unable to do — 200.430(i) wants
-- the signature of the person whose effort it was.
--
-- `owner_product` goes beside `owner_portfolio` and `goes_to`, in the same
-- CASE, for the reason those two are there: what a kind *means* is written
-- down once. There were three hand-kept maps of worklist kinds once and
-- every one was missing different ones; `tests/test_worklist_ownership.py`
-- derives from this view and keeps no list of its own, so a new kind that
-- falls on the ELSE is caught by a test rather than by somebody noticing.
--
-- The body below is **lifted from the definition in force**, not retyped.
-- Only the CASE is new.
--
-- ── Three partitions, one shape ──────────────────────────────────────
--
-- The 2025 audit divides three things and each has to reach the whole:
--
--     the P&L's cost        into pools                v_classification_coverage
--     each building         into space units          v_space_unit_control
--     the asset register    into funding sources      v_asset_control
--
-- They are the same question asked of three registers — *does this account
-- for all of it* — and until now they answered in three different shapes.
-- Coverage reported a percentage with no state; the space control reported
-- `ties` and returns **no row at all** where no building exists; the asset
-- control was already right, with `evaluable`, a `state` and a `needs`
-- saying what it would take to mean anything.
--
-- `v_partition_coverage` is the asset control's shape applied to all three,
-- so the classification screen can put them side by side and a reader can
-- tell at a glance which of the three is finished.
--
-- **And none of them may report TIES over nothing.** Space returns no rows
-- on a record with no building, which is not zero-equals-zero, it is the
-- absence of the comparison — so the union manufactures the row and says
-- NO DATA. That is `029` in its newest place: an empty set matches an empty
-- set perfectly, and a control that cannot be evaluated has not passed.

CREATE OR REPLACE VIEW v_worklist_owned AS
WITH all_items AS (
         SELECT v_worklist.kind,
            v_worklist.severity,
            v_worklist.period,
            v_worklist.label,
            v_worklist.entity,
            v_worklist.entity_id,
            v_worklist.amount,
            v_worklist.detail
           FROM v_worklist
        UNION ALL
         SELECT v_worklist_extra.kind,
            v_worklist_extra.severity,
            v_worklist_extra.period,
            v_worklist_extra.label,
            v_worklist_extra.entity,
            v_worklist_extra.entity_id,
            v_worklist_extra.amount,
            v_worklist_extra.detail
           FROM v_worklist_extra
        )
 SELECT kind,
    severity,
    period,
    label,
    entity,
    entity_id,
    amount,
    detail,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN 'CONTROLLER'::text
            WHEN 'BLOCKS_SEAL'::text THEN 'CONTROLLER'::text
            WHEN 'STALE_DECISION'::text THEN 'CONTROLLER'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN 'CONTROLLER'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN 'OFFICE'::text
            WHEN 'SPACE_UNMEASURED'::text THEN 'FACILITIES'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN 'FACILITIES'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN 'INVENTORY'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN 'PROJECT'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN 'PROJECT'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN 'PROJECT'::text
            WHEN 'AWARD_NO_CEILING'::text THEN 'PROJECT'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN 'PROJECT'::text
            WHEN 'STALE_CERTIFICATION'::text THEN 'PROJECT'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN 'PROJECT'::text
            ELSE 'CONTROLLER'::text
        END AS owner_portfolio,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN '/classify'::text
            WHEN 'BLOCKS_SEAL'::text THEN '/classify'::text
            WHEN 'STALE_DECISION'::text THEN '/classify'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN '/timesheet'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN '/evidence'::text
            WHEN 'SPACE_UNMEASURED'::text THEN '/space'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN '/space'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN '/inventory'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN '/contracts'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN '/contracts'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN '/contracts/codes'::text
            WHEN 'AWARD_NO_CEILING'::text THEN '/contracts'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN '/contracts/people'::text
            WHEN 'STALE_CERTIFICATION'::text THEN '/contracts/people'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN '/timesheet'::text
            ELSE '/'::text
        END AS goes_to,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN 'audit'::text
            WHEN 'BLOCKS_SEAL'::text THEN 'audit'::text
            WHEN 'STALE_DECISION'::text THEN 'audit'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN 'audit'::text
            WHEN 'SPACE_UNMEASURED'::text THEN 'audit'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN 'audit'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN 'audit'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN 'audit'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN 'audit'::text
            WHEN 'AWARD_NO_CEILING'::text THEN 'audit'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN 'fcs'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN 'fcs'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN 'fcs'::text
            WHEN 'STALE_CERTIFICATION'::text THEN 'fcs'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN 'fcs'::text
            ELSE 'audit'::text
        END AS owner_product
   FROM all_items a;

COMMENT ON VIEW v_worklist_owned IS
  'Outstanding work, with the portfolio that can act on it, the screen it is '
  'dealt with on, and which of the two products it belongs to.';


CREATE VIEW v_partition_coverage AS
WITH cost AS (
  SELECT c.period,
         'COST'::text                                    AS partition,
         'The 2025 profit and loss, into cost pools'      AS divides,
         'dollars'::text                                  AS unit,
         c.classified                                     AS covered,
         c.scope_dollars                                  AS whole,
         c.groups_decided                                 AS parts_done,
         c.groups_total                                   AS parts,
         -- Evaluable the moment there is anything to divide. An empty ledger
         -- is not a complete classification, it is no classification.
         (c.scope_dollars > 0)                            AS evaluable,
         'the general ledger and the profit and loss'::text AS needs,
         '/classify'::text                                AS goes_to
    FROM v_classification_coverage c
), space AS (
  -- LEFT JOIN from the period rather than FROM the control: the control has
  -- no row where no facility exists, and "no row" would drop the partition
  -- off the screen entirely rather than saying it has not been measured.
  SELECT p.period,
         'SPACE'::text,
         'Each building, into tenant, programme and vacant space',
         'square feet'::text,
         COALESCE(s.unit_sqft, 0),
         COALESCE(s.usable_sqft, 0),
         COALESCE(s.units, 0),
         (SELECT count(*) FROM facility)::bigint,
         COALESCE(s.usable_sqft, 0) > 0,
         'the square footage per building, and what each part is used for'::text,
         '/classify/space'::text
    FROM fiscal_period p
    LEFT JOIN (SELECT period, sum(usable_sqft) usable_sqft, sum(unit_sqft) unit_sqft,
                      sum(units) units
                 FROM v_space_unit_control GROUP BY period) s ON s.period = p.period
), assets AS (
  SELECT a.period,
         'ASSETS'::text,
         'The fixed-asset register, into funding sources',
         'dollars'::text,
         a.gross_cost - a.funding_unknown,
         a.gross_cost,
         (a.assets - a.funding_unknown)::bigint,
         a.assets::bigint,
         a.evaluable,
         a.needs,
         '/classify/assets'::text
    FROM v_asset_control a
)
SELECT period, partition, divides, unit, covered, whole, parts_done, parts,
       evaluable, needs, goes_to,
       CASE WHEN whole > 0
            THEN round(100.0 * covered / whole, 1) ELSE NULL END AS pct,
       CASE WHEN NOT evaluable                    THEN 'NO DATA'
            WHEN covered = whole                  THEN 'TIES'
            ELSE 'OPEN' END                                      AS state,
       whole - covered                                           AS outstanding
  FROM (SELECT * FROM cost UNION ALL SELECT * FROM space
        UNION ALL SELECT * FROM assets) x;

COMMENT ON VIEW v_partition_coverage IS
  'The three things the 2025 audit divides and whether each accounts for all '
  'of itself. Three-state: NO DATA where there is nothing to divide yet, '
  'because an empty set matches an empty set perfectly.';
