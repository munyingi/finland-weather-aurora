-- Hourly aurora score at well-known viewing spots, taken from the hexagon each spot falls nearest to.
with spot_cell as (
    select
        s.spot_name,
        s.municipality,
        s.lat as spot_lat,
        s.lon as spot_lon,
        c.cell_id
    from {{ ref('aurora_spots') }} as s
    cross join {{ ref('dim_cells') }} as c
    where c.h3_res = 4
    qualify row_number() over (
        partition by s.spot_name
        order by {{ haversine_km('s.lat', 's.lon', 'c.lat', 'c.lon') }}
    ) = 1
)

select
    sc.spot_name,
    sc.municipality,
    sc.spot_lat,
    sc.spot_lon,
    a.region_name,
    a.valid_at,
    {{ to_helsinki('a.valid_at') }} as valid_at_local,
    a.kp,
    a.kp_status,
    a.cloud_cover_pct,
    a.sun_altitude_deg,
    a.magnetic_latitude_deg,
    a.aurora_score,
    a.aurora_category
from spot_cell as sc
inner join {{ ref('fct_aurora_cell_hourly') }} as a using (cell_id)
