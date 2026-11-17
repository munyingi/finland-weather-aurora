select
    cell_id,
    valid_at,
    least(greatest(cloud_cover_pct, 0), 100) as cloud_cover_pct,
    cloud_cover_low_pct,
    loaded_at
from {{ source('raw', 'openmeteo_cloud') }}
