{{ config(
    materialized='incremental',
    unique_key=['cell_id', 'observed_at'],
    incremental_strategy='delete+insert',
    on_schema_change='append_new_columns'
) }}
-- Station observations interpolated onto the H3 res-5 grid with inverse distance
-- weighting (power 2). For every cell, hour and measure, only the nearest
-- `idw_neighbours` stations that actually reported that measure are used, so a
-- station without a snow sensor never drags snow depth towards zero.

with obs as (
    select station_key, observed_at, measure, value
    from {{ ref('int_observations_valid') }}
    {% if is_incremental() %}
    where observed_at >= (
        select coalesce(max(observed_at), timestamp '1970-01-01') - interval {{ var('incremental_lookback_hours') }} hour
        from {{ this }}
    )
    {% endif %}
),

candidates as (
    select
        p.cell_id,
        o.observed_at,
        o.measure,
        o.value,
        p.distance_km,
        row_number() over (partition by p.cell_id, o.observed_at, o.measure order by p.distance_km, p.station_key) as station_rank
    from obs as o
    inner join {{ ref('int_cell_station_pairs') }} as p using (station_key)
),

idw as (
    select
        cell_id,
        observed_at,
        measure,
        sum(value / pow(greatest(distance_km, 1.0), 2)) / sum(1 / pow(greatest(distance_km, 1.0), 2)) as value,
        count(*) as n_stations,
        min(distance_km) as nearest_km
    from candidates
    where station_rank <= {{ var('idw_neighbours') }}
    group by cell_id, observed_at, measure
)

select
    cell_id,
    observed_at,
    round(max(value) filter (where measure = 'air_temperature_c'), 1) as air_temperature_c,
    round(max(value) filter (where measure = 'wind_speed_ms'), 1) as wind_speed_ms,
    round(max(value) filter (where measure = 'wind_gust_ms'), 1) as wind_gust_ms,
    round(max(value) filter (where measure = 'precipitation_mm'), 2) as precipitation_mm,
    round(max(value) filter (where measure = 'snow_depth_cm'), 0) as snow_depth_cm,
    round(max(value) filter (where measure = 'relative_humidity_pct'), 0) as relative_humidity_pct,
    round(max(value) filter (where measure = 'pressure_hpa'), 1) as pressure_hpa,
    max(n_stations) filter (where measure = 'air_temperature_c') as temperature_station_count,
    round(max(nearest_km) filter (where measure = 'air_temperature_c'), 1) as nearest_station_km,
    {{ utc_now() }} as transformed_at
from idw
group by cell_id, observed_at
