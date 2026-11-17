-- Every observing position, enriched with current station metadata (SCD2 snapshot)
-- and the region of the nearest weather cell. Positions with no metadata keep a
-- position-based key instead of being dropped.
with positions as (
    select
        position_key,
        any_value(station_lat) as lat,
        any_value(station_lon) as lon,
        min(observed_at) as first_observed_at,
        max(observed_at) as last_observed_at,
        count(distinct measure) as measures_reported
    from {{ ref('stg_fmi__observations') }}
    group by position_key
),

meta as (
    select * from {{ ref('snap_fmi_stations') }}
    where dbt_valid_to is null
),

cells as (
    select cell_id, lat, lon, region_code, region_name
    from {{ ref('stg_grid__cells') }}
    where h3_res = 5
),

nearest_cell as (
    select
        p.position_key,
        c.region_code,
        c.region_name,
        {{ haversine_km('p.lat', 'p.lon', 'c.lat', 'c.lon') }} as cell_distance_km
    from positions as p
    cross join cells as c
    where abs(p.lat - c.lat) < 0.6 and abs(p.lon - c.lon) < 1.2
    qualify row_number() over (partition by p.position_key order by cell_distance_km) = 1
)

select
    coalesce('fmi-' || m.fmisid, 'pos-' || p.position_key) as station_key,
    m.fmisid,
    coalesce(m.station_name, 'Unknown station ' || p.position_key) as station_name,
    m.municipality,
    p.position_key,
    p.lat,
    p.lon,
    n.region_code,
    n.region_name,
    m.networks,
    p.first_observed_at,
    p.last_observed_at,
    p.measures_reported,
    m.fmisid is not null as has_metadata
from positions as p
left join meta as m using (position_key)
left join nearest_cell as n using (position_key)
