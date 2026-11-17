-- Sanity bounds for the dipole approximation at two anchor towns.
with towns as (
    select * from (values ('Helsinki', 60.17, 24.94, 57.0, 58.8), ('Kilpisjärvi', 69.05, 20.79, 65.8, 67.5))
        as t(town, lat, lon, lo, hi)
)
select town, {{ magnetic_latitude_deg('lat', 'lon') }} as mlat
from towns
where {{ magnetic_latitude_deg('lat', 'lon') }} not between lo and hi
