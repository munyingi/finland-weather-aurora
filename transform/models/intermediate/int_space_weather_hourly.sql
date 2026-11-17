-- One row per UTC hour across the Kp record: best Kp for the hour plus solar wind.
-- Solar wind is measured at L1, roughly 30 to 60 minutes upstream of Earth, so the
-- latest reading is carried forward one hour as a short nowcast.
with kp_best as (
    select *
    from {{ ref('stg_swpc__kp') }}
    qualify row_number() over (partition by block_start order by source_priority, loaded_at desc) = 1
),

spine as (
    select unnest(generate_series(
        (select min(block_start) from kp_best),
        (select max(block_end) from kp_best) - interval 1 hour,
        interval 1 hour
    )) as hour_at
),

wind_hourly as (
    select
        observed_hour as hour_at,
        avg(bz_gsm_nt) as bz_mean_nt,
        min(bz_gsm_nt) as bz_min_nt,
        avg(speed_kms) as speed_mean_kms,
        avg(density_cm3) as density_mean_cm3
    from {{ ref('stg_swpc__solar_wind') }}
    group by observed_hour
),

latest_wind as (
    select * from wind_hourly order by hour_at desc limit 1
)

select
    s.hour_at,
    k.kp,
    k.status as kp_status,
    k.noaa_scale,
    coalesce(w.bz_mean_nt, case when s.hour_at > l.hour_at and s.hour_at <= l.hour_at + interval 1 hour then l.bz_mean_nt end) as bz_mean_nt,
    coalesce(w.speed_mean_kms, case when s.hour_at > l.hour_at and s.hour_at <= l.hour_at + interval 1 hour then l.speed_mean_kms end) as speed_mean_kms,
    w.bz_min_nt,
    w.density_mean_cm3,
    w.hour_at is null and s.hour_at > l.hour_at and s.hour_at <= l.hour_at + interval 1 hour as solar_wind_carried_forward
from spine as s
left join kp_best as k on s.hour_at >= k.block_start and s.hour_at < k.block_end
left join wind_hourly as w on w.hour_at = s.hour_at
left join latest_wind as l on true  -- keeps the spine when solar wind is empty
