-- The SQL solar-position macro must agree with an independent implementation
-- (astral, refraction off) to within 0.5 degrees. Reference values are hard-coded.
with cases as (
    select * from (values
        ('Helsinki, midsummer noon', 60.17, 24.94, timestamp '2026-06-21 10:20:00', 53.27),
        ('Helsinki, midwinter noon', 60.17, 24.94, timestamp '2026-12-21 10:20:00', 6.39),
        ('Utsjoki, polar night noon', 69.90, 27.03, timestamp '2026-12-21 10:00:00', -3.35),
        ('Helsinki, November midnight', 60.17, 24.94, timestamp '2026-11-17 22:00:00', -48.97),
        ('Kilpisjärvi, equinox afternoon', 69.04, 20.80, timestamp '2026-03-20 15:30:00', 6.55)
    ) as t(case_name, lat, lon, ts, expected_deg)
)

select case_name, expected_deg, {{ sun_altitude_deg('lat', 'lon', 'ts') }} as computed_deg
from cases
where abs({{ sun_altitude_deg('lat', 'lon', 'ts') }} - expected_deg) > 0.5
