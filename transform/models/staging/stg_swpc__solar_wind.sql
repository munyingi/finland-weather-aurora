select
    observed_at,
    date_trunc('hour', observed_at) as observed_hour,
    bz_gsm_nt,
    bt_nt,
    speed_kms,
    density_cm3
from {{ source('raw', 'swpc_solar_wind') }}
where (bz_gsm_nt is null or bz_gsm_nt between -100 and 100)
  and (speed_kms is null or speed_kms between 150 and 3000)
