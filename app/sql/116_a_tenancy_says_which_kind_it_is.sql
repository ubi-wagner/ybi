-- 116 — An incubator client in residence is not a commercial letting, and
--       the difference is worth points of rate.
--
-- `SPACE_INVENTORY` v1 asked "what it is used for" and explained TENANT as
-- *leased to a third party*. That is literally true of an incubator's own
-- client companies — they sign something and they pay rent — so all
-- twenty-six tenancies on the floor plan came back TENANT, and every one of
-- them left the federal overhead pool under 200.465.
--
-- Two of those occupants are plainly commercial (Steelite in two buildings)
-- and one is a co-located federal institute (NCDMM / America Makes). The
-- other twenty-one are small suites in YBI Main and Tech Block 5 — which is
-- what an incubator's portfolio companies look like. Housing them **is** the
-- programme; renting to a manufacturer is not. `docs/RATE_HEADROOM_2025.md`
-- prices the difference: 2.72 points of combined rate with their rent
-- credited under 200.406, and it is the largest single reading still open.
--
-- The form could not have got this right, because its own column said the
-- opposite. So v2 asks the question that actually decides it — and asks for
-- the document, which is this column.
--
-- **`market_basis` is the precedent, one column along.** `unit_market_needs_
-- basis` already refuses a market rate with nothing behind it, on the stated
-- ground that *a rate with no basis behind it is a number somebody made up*.
-- A reclassification worth 2.72 points resting on nobody's agreement is the
-- same thing, and this repository has paid for the citation-with-no-document
-- shape three times: `award_term.evidence_id` on thirty-nine rows,
-- `contractor_identity`'s note, `chart_split_driver.evidence_id`.
--
-- The fence is **narrow on purpose.** Space YBI's own team occupies is
-- PROGRAM and has no agreement to name; the estate already carries ten such
-- rows and a blanket rule would refuse them. What must name its document is
-- the case that moves the rate: space somebody is **charged rent for** and
-- which is nonetheless called programme space. Nothing on the record is in
-- that state today, so this breaks nothing and stands in front of the first
-- row that tries it.

ALTER TABLE space_unit
  ADD COLUMN IF NOT EXISTS occupancy_basis text NOT NULL DEFAULT '';

COMMENT ON COLUMN space_unit.occupancy_basis IS
  'The agreement that settles what kind of occupancy this is — a commercial '
  'lease, or an incubation/residency agreement making the space programme '
  'delivery. Blank is honest and means nobody has read one; it is never a '
  'claim that none exists.';

ALTER TABLE space_unit DROP CONSTRAINT IF EXISTS unit_paid_program_names_its_agreement;
ALTER TABLE space_unit ADD CONSTRAINT unit_paid_program_names_its_agreement CHECK (
    use <> 'PROGRAM'
    OR COALESCE(actual_annual_charge, 0) <= 0
    OR length(btrim(occupancy_basis)) > 10);

-- The control. Three states, because a period with no measured estate has
-- nothing to report and "0 of 0 named" is `029` in a new place.
CREATE OR REPLACE VIEW v_tenancy_basis_check AS
WITH charged AS (
    SELECT u.period, u.unit_id, u.use::text AS use, u.occupant,
           u.usable_sqft, u.actual_annual_charge,
           length(btrim(u.occupancy_basis)) > 10 AS named
      FROM space_unit u
     WHERE COALESCE(u.actual_annual_charge, 0) > 0
)
SELECT p.period,
       count(c.unit_id)                                    AS charged_units,
       count(c.unit_id) FILTER (WHERE c.named)             AS named_units,
       COALESCE(sum(c.usable_sqft), 0)                     AS charged_sqft,
       COALESCE(sum(c.usable_sqft) FILTER (WHERE c.named), 0) AS named_sqft,
       COALESCE(sum(c.actual_annual_charge), 0)            AS charged_rent,
       CASE WHEN count(c.unit_id) = 0 THEN 'NO DATA'
            WHEN count(c.unit_id) FILTER (WHERE NOT c.named) = 0 THEN 'TIES'
            ELSE 'OPEN' END                                AS state,
       CASE WHEN count(c.unit_id) = 0
              THEN 'No charged space is on the record, so nothing can be '
                   'asked whether it is a letting or a client in residence.'
            WHEN count(c.unit_id) FILTER (WHERE NOT c.named) = 0 THEN ''
            ELSE to_char(count(c.unit_id) FILTER (WHERE NOT c.named),
                         'FM999,999')
                 || ' charged tenancy(ies) name no agreement saying whether '
                    'the occupant is a commercial tenant or an incubator '
                    'client in residence — which decides whether their '
                    'occupancy cost leaves the federal pool under 200.465.'
       END                                                 AS needs
  FROM fiscal_period p
  LEFT JOIN charged c ON c.period = p.period
 GROUP BY p.period;

COMMENT ON VIEW v_tenancy_basis_check IS
  'Does every tenancy somebody is charged for say which kind of occupancy it '
  'is, and name the document that says so. NO DATA where no charged space is '
  'on the record — an empty set matching an empty set is not a pass.';
