{# Great-circle distance in km. Pure SQL, so no spatial extension is needed. #}
{% macro haversine_km(lat1, lon1, lat2, lon2) -%}
    (2 * 6371.0 * asin(sqrt(
        pow(sin(radians(({{ lat2 }}) - ({{ lat1 }})) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
          * pow(sin(radians(({{ lon2 }}) - ({{ lon1 }})) / 2), 2)
    )))
{%- endmacro %}

{# Geomagnetic latitude from a centred dipole. Good to about 1 degree over Finland, which is plenty for a visibility heuristic. #}
{% macro magnetic_latitude_deg(lat, lon) -%}
    degrees(asin(
        sin(radians({{ lat }})) * sin(radians({{ var('mag_pole_lat') }}))
        + cos(radians({{ lat }})) * cos(radians({{ var('mag_pole_lat') }}))
          * cos(radians(({{ lon }}) - ({{ var('mag_pole_lon') }})))
    ))
{%- endmacro %}

{#
  Solar altitude in degrees for a UTC timestamp (NOAA general solar position
  equations). Accurate to a fraction of a degree, enough to tell day from
  civil, nautical and astronomical twilight.
#}
{% macro sun_altitude_deg(lat, lon, ts_utc) -%}
    {%- set g -%}(2 * pi() / 365.0 * (dayofyear({{ ts_utc }}) - 1 + (hour({{ ts_utc }}) + minute({{ ts_utc }}) / 60.0 - 12) / 24.0)){%- endset -%}
    {%- set decl -%}(0.006918 - 0.399912 * cos({{ g }}) + 0.070257 * sin({{ g }}) - 0.006758 * cos(2 * {{ g }}) + 0.000907 * sin(2 * {{ g }}) - 0.002697 * cos(3 * {{ g }}) + 0.00148 * sin(3 * {{ g }})){%- endset -%}
    {%- set eqtime -%}(229.18 * (0.000075 + 0.001868 * cos({{ g }}) - 0.032077 * sin({{ g }}) - 0.014615 * cos(2 * {{ g }}) - 0.040849 * sin(2 * {{ g }}))){%- endset -%}
    {%- set true_solar_min -%}((hour({{ ts_utc }}) * 60 + minute({{ ts_utc }})) + {{ eqtime }} + 4 * ({{ lon }})){%- endset -%}
    {%- set hour_angle -%}radians({{ true_solar_min }} / 4.0 - 180){%- endset -%}
    degrees(asin(greatest(-1.0, least(1.0,
        sin(radians({{ lat }})) * sin({{ decl }})
        + cos(radians({{ lat }})) * cos({{ decl }}) * cos({{ hour_angle }})
    ))))
{%- endmacro %}
