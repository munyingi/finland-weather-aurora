-- One row per source: last successful load, freshness and volume. Powers the
-- dashboard's "Pipeline health" tab and the published health.json.
with runs as (
    select
        source,
        max(finished_at) filter (where status = 'success') as last_success_at,
        max(started_at) filter (where status = 'failed') as last_failure_at,
        arg_max(error, started_at) filter (where status = 'failed') as last_error,
        count(*) filter (where started_at >= {{ utc_now() }} - interval 24 hour) as runs_24h,
        count(*) filter (where status = 'failed' and started_at >= {{ utc_now() }} - interval 24 hour) as failures_24h
    from {{ source('raw', 'ingest_runs') }}
    group by source
),

data_latest as (
    select 'fmi_observations' as source, max(observed_at) as latest_data_at, count(*) as total_rows from {{ source('raw', 'fmi_observations') }}
    union all select 'swpc_kp', max(block_start), count(*) from {{ source('raw', 'swpc_kp') }}
    union all select 'swpc_solar_wind', max(observed_at), count(*) from {{ source('raw', 'swpc_solar_wind') }}
    union all select 'openmeteo_cloud', max(valid_at), count(*) from {{ source('raw', 'openmeteo_cloud') }}
    union all select 'fmi_stations', max(loaded_at), count(*) from {{ source('raw', 'fmi_stations') }}
    union all select 'grid', max(loaded_at), count(*) from {{ source('raw', 'grid_cells') }}
),

quality as (
    select
        'fmi_observations' as source,
        count(*) filter (where not is_valid and observed_at >= {{ utc_now() }} - interval 24 hour) as invalid_values_24h
    from {{ ref('stg_fmi__observations') }}
)

select
    r.source,
    r.last_success_at,
    r.last_failure_at,
    r.last_error,
    r.runs_24h,
    r.failures_24h,
    d.latest_data_at,
    d.total_rows,
    q.invalid_values_24h,
    case
        when r.last_success_at is null then 'never_loaded'
        when r.last_success_at < {{ utc_now() }} - interval 24 hour then 'stale'
        when r.last_failure_at > r.last_success_at then 'degraded'
        else 'healthy'
    end as status
from runs as r
left join data_latest as d using (source)
left join quality as q using (source)
