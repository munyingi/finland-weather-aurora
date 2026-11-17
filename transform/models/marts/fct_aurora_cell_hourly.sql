-- Hourly aurora visibility score (0-100) for every res-4 hexagon in Finland.
--
--   score = geomagnetic chance x darkness x clear sky
--
-- geomagnetic chance: the auroral oval's southern edge moves south as Kp rises
--   (edge = oval_base_mlat - oval_kp_slope * Kp). Aurora is visible low on the
--   northern horizon a few degrees south of the edge. A logistic curve turns the
--   cell's distance from that line into a 0-1 chance. Strongly southward Bz and
--   fast solar wind nudge the effective Kp up, because they drive activity before
--   the 3-hour Kp catches up.
-- darkness: 0 in daylight and civil twilight (sun above -6 deg), 1 from nautical
--   dusk (-12 deg), linear in between.
-- clear sky: 1 - cloud cover.
--
-- This is a transparent heuristic for portfolio purposes, not an official forecast.

with cells as (
    select cell_id, lat, lon, region_code, region_name, magnetic_latitude_deg
    from {{ ref('dim_cells') }}
    where h3_res = 4
),

base as (
    select
        c.cell_id,
        c.lat,
        c.lon,
        c.region_code,
        c.region_name,
        c.magnetic_latitude_deg,
        cl.valid_at,
        cl.cloud_cover_pct,
        sw.kp,
        sw.kp_status,
        sw.bz_mean_nt,
        sw.speed_mean_kms
    from cells as c
    inner join {{ ref('stg_openmeteo__cloud') }} as cl using (cell_id)
    left join {{ ref('int_space_weather_hourly') }} as sw on sw.hour_at = cl.valid_at
),

factors as (
    select
        *,
        {{ sun_altitude_deg('lat', 'lon', 'valid_at') }} as sun_altitude_deg,
        least(9.0, kp
            + case when bz_mean_nt <= -10 then 1.0 when bz_mean_nt <= -5 then 0.5 else 0.0 end
            + case when speed_mean_kms >= 600 then 0.5 else 0.0 end
        ) as kp_effective
    from base
),

scored as (
    select
        *,
        {{ var('oval_base_mlat') }} - {{ var('oval_kp_slope') }} * kp_effective - {{ var('view_offset_deg') }} as visible_edge_mlat,
        1.0 / (1.0 + exp(-(magnetic_latitude_deg
            - ({{ var('oval_base_mlat') }} - {{ var('oval_kp_slope') }} * kp_effective - {{ var('view_offset_deg') }}))
            / {{ var('geo_softness_deg') }})) as geomagnetic_chance,
        case
            when sun_altitude_deg <= -12 then 1.0
            when sun_altitude_deg >= -6 then 0.0
            else (-6 - sun_altitude_deg) / 6.0
        end as darkness_factor,
        1.0 - cloud_cover_pct / 100.0 as clear_sky_factor
    from factors
)

select
    cell_id,
    valid_at,
    lat,
    lon,
    region_code,
    region_name,
    round(magnetic_latitude_deg, 2) as magnetic_latitude_deg,
    kp,
    kp_status,
    round(kp_effective, 2) as kp_effective,
    round(bz_mean_nt, 1) as bz_mean_nt,
    round(speed_mean_kms, 0) as speed_mean_kms,
    round(visible_edge_mlat, 2) as visible_edge_mlat,
    round(sun_altitude_deg, 1) as sun_altitude_deg,
    cloud_cover_pct,
    round(geomagnetic_chance, 3) as geomagnetic_chance,
    round(darkness_factor, 3) as darkness_factor,
    round(clear_sky_factor, 3) as clear_sky_factor,
    cast(round(100 * geomagnetic_chance * darkness_factor * clear_sky_factor) as integer) as aurora_score,
    case
        when kp is null then 'no_data'
        when 100 * geomagnetic_chance * darkness_factor * clear_sky_factor >= 60 then 'excellent'
        when 100 * geomagnetic_chance * darkness_factor * clear_sky_factor >= 35 then 'good'
        when 100 * geomagnetic_chance * darkness_factor * clear_sky_factor >= 15 then 'possible'
        else 'unlikely'
    end as aurora_category
from scored
