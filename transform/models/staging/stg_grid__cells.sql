select
    cell_id,
    h3_res,
    parent_cell_id,
    lat,
    lon,
    region_code,
    region_name,
    region_name_fi
from {{ source('raw', 'grid_cells') }}
