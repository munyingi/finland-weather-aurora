-- Kp per 3-hour block. Several products describe the same block, so each row gets
-- a priority: a definitive observation beats an estimate, which beats a prediction.
select
    block_start,
    block_start + interval 3 hour as block_end,
    kp,
    lower(status) as status,
    product,
    noaa_scale,
    case
        when product = 'observed' then 1
        when lower(status) = 'observed' then 2
        when lower(status) = 'estimated' then 3
        else 4
    end as source_priority,
    loaded_at
from {{ source('raw', 'swpc_kp') }}
where kp between 0 and 9
