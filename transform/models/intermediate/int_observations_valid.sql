{{ config(materialized='view') }}
-- Valid observations keyed by station. Out-of-range readings are kept in staging
-- (and counted in mart_pipeline_health) but never reach interpolation or events.
select
    s.station_key,
    o.observed_at,
    o.measure,
    o.value
from {{ ref('stg_fmi__observations') }} as o
inner join {{ ref('int_stations') }} as s using (position_key)
where o.is_valid
