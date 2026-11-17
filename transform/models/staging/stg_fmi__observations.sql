-- One row per station position, hour and measure, with a validity flag from the parameter seed.
select
    o.position_key,
    o.station_lat,
    o.station_lon,
    o.observed_at,
    o.parameter,
    p.measure,
    p.unit,
    o.value,
    o.value between p.min_valid and p.max_valid as is_valid,
    o.loaded_at
from {{ source('raw', 'fmi_observations') }} as o
inner join {{ ref('fmi_parameters') }} as p using (parameter)
where not isnan(o.value)
