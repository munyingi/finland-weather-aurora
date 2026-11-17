select
    cell_id,
    h3_res,
    case h3_res when 5 then 'weather' when 4 then 'aurora' end as grid_purpose,
    parent_cell_id,
    lat,
    lon,
    region_code,
    region_name,
    region_name_fi,
    {{ magnetic_latitude_deg('lat', 'lon') }} as magnetic_latitude_deg
from {{ ref('stg_grid__cells') }}
