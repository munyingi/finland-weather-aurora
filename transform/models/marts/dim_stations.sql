select
    station_key,
    fmisid,
    station_name,
    municipality,
    region_code,
    region_name,
    lat,
    lon,
    networks,
    first_observed_at,
    last_observed_at,
    measures_reported,
    has_metadata,
    last_observed_at >= {{ utc_now() }} - interval 6 hour as is_reporting
from {{ ref('int_stations') }}
