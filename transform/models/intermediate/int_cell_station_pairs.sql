-- Candidate stations for each weather cell, pre-filtered by a lat/lon box before the
-- exact haversine so the cross join stays small.
select
    c.cell_id,
    s.station_key,
    {{ haversine_km('c.lat', 'c.lon', 's.lat', 's.lon') }} as distance_km
from {{ ref('stg_grid__cells') }} as c
cross join {{ ref('int_stations') }} as s
where c.h3_res = 5
  and abs(c.lat - s.lat) < {{ var('idw_max_km') }} / 111.0
  and abs(c.lon - s.lon) < {{ var('idw_max_km') }} / 35.0
  and {{ haversine_km('c.lat', 'c.lon', 's.lat', 's.lon') }} <= {{ var('idw_max_km') }}
