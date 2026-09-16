-- 118 — The rent roll carries the agreement, so the screen can show it back.
--
-- `116` added `space_unit.occupancy_basis` and `117` made both write doors
-- ask for it on the one case that moves the rate. `v_space_economics` is what
-- `GET /api/facilities/space` answers with, and without the column the screen
-- would take an answer and never show it back — which is how somebody types a
-- lease reference twice and cannot tell whether the first one landed.
--
-- Lifted from the definition in force rather than retyped — and the column is
-- **appended, never inserted**. `CREATE OR REPLACE VIEW` can only add at the
-- end: putting it beside `market_basis`, where it belongs to a reader, renames
-- every column after it and Postgres refuses outright. `084` records the same
-- constraint on `v_recommendation`; this is the second time it has been met.

CREATE OR REPLACE VIEW v_space_economics AS
SELECT u.unit_id,
    u.facility_id,
    f.name AS facility_name,
    u.period,
    u.label,
    u.use,
    u.status,
    u.occupant,
    u.objective_id,
    u.usable_sqft,
    u.months_occupied,
    round(u.usable_sqft * u.months_occupied / 12::numeric, 2) AS sqft_years,
    u.actual_annual_charge,
    COALESCE(u.market_rate_psf, f.market_rate_psf) AS market_rate_psf,
        CASE
            WHEN COALESCE(u.market_rate_psf, f.market_rate_psf) IS NOT NULL THEN round(u.usable_sqft * u.months_occupied / 12::numeric * COALESCE(u.market_rate_psf, f.market_rate_psf), 2)
            ELSE NULL::numeric
        END AS market_value,
        CASE
            WHEN COALESCE(u.market_rate_psf, f.market_rate_psf) IS NOT NULL THEN round(u.usable_sqft * u.months_occupied / 12::numeric * COALESCE(u.market_rate_psf, f.market_rate_psf) - COALESCE(u.actual_annual_charge, 0::numeric), 2)
            ELSE NULL::numeric
        END AS subsidy,
    COALESCE(NULLIF(u.market_basis, ''::text), f.market_basis) AS market_basis,
    COALESCE(u.market_rate_psf, f.market_rate_psf) IS NULL AS market_unknown,
    f.owned,
    u.occupancy_basis
   FROM space_unit u
     JOIN facility f ON f.facility_id = u.facility_id AND f.period = u.period;
