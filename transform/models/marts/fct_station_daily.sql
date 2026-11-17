-- Station-day metrics used by event detection. Events are taken from real station
-- readings, not interpolated values, so a reported frost actually happened somewhere.
with obs as (
    select
        station_key,
        cast({{ to_helsinki('observed_at') }} as date) as local_date,
        observed_at,
        measure,
        value
    from {{ ref('int_observations_valid') }}
)

select
    station_key,
    local_date,
    min(value) filter (where measure = 'air_temperature_c') as t_min_c,
    max(value) filter (where measure = 'air_temperature_c') as t_max_c,
    max(value) filter (where measure = 'wind_speed_ms') as wind_max_ms,
    max(value) filter (where measure = 'wind_gust_ms') as gust_max_ms,
    max(value) filter (where measure = 'precipitation_mm') as precip_max_1h_mm,
    sum(value) filter (where measure = 'precipitation_mm') as precip_total_mm,
    max(value) filter (where measure = 'snow_depth_cm')
        - arg_min(value, observed_at) filter (where measure = 'snow_depth_cm') as snow_increase_cm,
    case
        when min(value) filter (where measure = 'air_temperature_c') < 0
         and max(value) filter (where measure = 'air_temperature_c') > 0 then 1 else 0
    end as freeze_thaw_flag,
    count(distinct observed_at) as hours_reported
from obs
group by station_key, local_date
