-- The building's own figure had no door either, and four columns behind it.
--
-- Tom reached the last thing standing between him and the rate: Semple, with
-- `rooms are 2,857 over`. He read the measured plan and found row 30 — a
-- 2,857 sq ft common area — and reported that it was *"not being counted
-- towards the total usable space"*, correctly.
--
-- Her three Semple rows are 3,630 + 14,142 + 2,857 = 20,629. The register
-- holds 17,772, which is the first two and no common area, and 17,772
-- appears nowhere in her workbook. Every other building on the record equals
-- her rows to the decimal, common area included — YBI Incubator at 40,948.7
-- against 40,948.7, Tech Block 5 at 54,871.0 with 29,888.2 of common inside
-- it. Semple is the only one, and the gap is exactly one row.
--
-- So the rooms are right and the building is short, and correcting it is one
-- number. **`FacilityForm` is `+ Add a building` and nothing else.** The
-- rooms gained an Edit in `127`; the building did not, and the building is
-- the figure this one needs. `put_facility` has upserted on `facility_id`
-- since it was written, so the capability has always been there.
--
-- And pre-filling that form from `v_facility_summary` would have cleared
-- four columns it does not carry — `year_built`, `market_basis`,
-- `source_document`, `note`. `source_document` is the worst of the four: it
-- is what a measurement rests on, so an edit that dropped it would leave the
-- estate asserting a figure with nothing behind it. Same defect as `127`,
-- one register up, found the same way — by asking what the form writes
-- against what the screen can read.
CREATE OR REPLACE VIEW v_facility_summary AS
SELECT f.facility_id,
    f.period,
    f.code,
    f.name,
    f.address,
    f.owned,
    f.usable_sqft,
    f.rentable_sqft,
    f.market_rate_psf,
    f.landlord,
    f.annual_lease_cost,
    COALESCE(sum(e.sqft_years), 0::numeric) AS units_sqft_years,
    count(e.unit_id) AS units,
    count(e.unit_id) FILTER (WHERE e.status = 'OCCUPIED'::occupancy_status) AS occupied_units,
    COALESCE(sum(e.actual_annual_charge), 0::numeric) AS charged,
    COALESCE(sum(e.market_value), 0::numeric) AS market_value,
    COALESCE(sum(e.subsidy), 0::numeric) AS subsidy,
    count(*) FILTER (WHERE e.market_unknown) AS units_without_market,
    ( SELECT COALESCE(sum(a.footprint_sqft), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.facility_id = f.facility_id AND a.period = f.period) AS equipment_sqft,
    f.year_built,
    f.market_basis,
    f.source_document,
    f.note
   FROM facility f
     LEFT JOIN v_space_economics e ON e.facility_id = f.facility_id AND e.period = f.period
  GROUP BY f.facility_id, f.period, f.code, f.name, f.address, f.owned, f.usable_sqft, f.rentable_sqft, f.market_rate_psf, f.landlord, f.annual_lease_cost;
