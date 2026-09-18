-- An edit has to put back everything it read.
--
-- `put_unit` is a full upsert, and the rent roll — which is where the
-- controller sees a room and wants to correct it — carries every column the
-- form holds except `floor` and `market_source`. Editing from there would
-- have written both back empty: not a refusal, not a warning, two columns
-- quietly cleared on a row somebody was fixing. It is `084`'s merge defect
-- in the other direction, where a partial proposal laid over a row invented
-- a combination nobody asked for; here a partial *read* would do the same.
--
-- So the view carries them, and the screen can round-trip a room without
-- losing anything it did not show. Lifted from the definition in force;
-- only the two columns are added, at the end, because `CREATE OR REPLACE
-- VIEW` may append and may not reorder.
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
    u.occupancy_basis,
    u.floor,
    u.market_source
   FROM space_unit u
     JOIN facility f ON f.facility_id = u.facility_id AND f.period = u.period;
