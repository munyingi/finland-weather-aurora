-- Best viewing hour per spot over the next `tonight_hours`, ranked. This is the
-- "where should I drive tonight?" table on the dashboard.
with window_ as (
    select *
    from {{ ref('mart_aurora_spots_hourly') }}
    where valid_at >= date_trunc('hour', {{ utc_now() }})
      and valid_at < date_trunc('hour', {{ utc_now() }}) + interval {{ var('tonight_hours') }} hour
),

best as (
    select
        spot_name,
        municipality,
        region_name,
        spot_lat,
        spot_lon,
        max(aurora_score) as best_score,
        arg_max(valid_at_local, aurora_score) as best_hour_local,
        arg_max(kp, aurora_score) as kp_at_best,
        arg_max(cloud_cover_pct, aurora_score) as cloud_cover_at_best_pct,
        count(*) filter (where aurora_score >= 35) as good_hours,
        max(magnetic_latitude_deg) as magnetic_latitude_deg
    from window_
    group by all
)

select
    rank() over (order by best_score desc, magnetic_latitude_deg desc) as spot_rank,
    *,
    case
        when best_score >= 60 then 'excellent'
        when best_score >= 35 then 'good'
        when best_score >= 15 then 'possible'
        else 'unlikely'
    end as outlook,
    {{ utc_now() }} as computed_at
from best
