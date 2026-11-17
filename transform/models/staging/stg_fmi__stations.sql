select
    fmisid,
    station_name,
    municipality,
    lat,
    lon,
    position_key,
    networks,
    active_from,
    active_to,
    loaded_at
from {{ source('raw', 'fmi_stations') }}
