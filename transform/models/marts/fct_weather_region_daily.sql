-- Daily weather per region (maakunta) on the Helsinki calendar day, averaged over the
-- region's hexagons so a dense station cluster in one town does not dominate.
with hourly as (
    select
        f.*,
        c.region_code,
        c.region_name,
        cast({{ to_helsinki('f.observed_at') }} as date) as local_date
    from {{ ref('fct_weather_cell_hourly') }} as f
    inner join {{ ref('dim_cells') }} as c using (cell_id)
),

per_cell as (
    select
        region_code,
        region_name,
        local_date,
        cell_id,
        min(air_temperature_c) as t_min,
        avg(air_temperature_c) as t_mean,
        max(air_temperature_c) as t_max,
        max(wind_gust_ms) as gust_max,
        avg(wind_speed_ms) as wind_mean,
        sum(precipitation_mm) as precip_total,
        avg(snow_depth_cm) as snow_mean,
        count(*) as hours_observed
    from hourly
    group by all
)

select
    region_code,
    region_name,
    local_date,
    round(min(t_min), 1) as air_temperature_min_c,
    round(avg(t_mean), 1) as air_temperature_mean_c,
    round(max(t_max), 1) as air_temperature_max_c,
    round(avg(wind_mean), 1) as wind_speed_mean_ms,
    round(max(gust_max), 1) as wind_gust_max_ms,
    round(avg(precip_total), 1) as precipitation_mean_mm,
    round(max(precip_total), 1) as precipitation_max_cell_mm,
    round(avg(snow_mean), 0) as snow_depth_mean_cm,
    count(*) as cells,
    round(avg(hours_observed), 1) as avg_hours_observed
from per_cell
group by all
