-- Extreme and notable weather per station and day. Rules live in the
-- event_thresholds seed, so adding an event type is a CSV edit, not new SQL.
with metrics as (
    unpivot {{ ref('fct_station_daily') }}
    on t_min_c, t_max_c, wind_max_ms, gust_max_ms, precip_max_1h_mm, snow_increase_cm, freeze_thaw_flag
    into name metric value metric_value
)

select
    m.station_key || '|' || m.local_date || '|' || t.event_type as event_id,
    m.station_key,
    s.station_name,
    s.region_code,
    s.region_name,
    s.lat,
    s.lon,
    m.local_date,
    t.event_type,
    t.severity,
    t.description,
    m.metric,
    round(m.metric_value, 1) as metric_value,
    t.threshold
from metrics as m
inner join {{ ref('event_thresholds') }} as t
    on t.metric = m.metric
   and ((t.operator = '<=' and m.metric_value <= t.threshold)
     or (t.operator = '>=' and m.metric_value >= t.threshold))
inner join {{ ref('dim_stations') }} as s using (station_key)
