{#
  SCD Type 2 history of FMI station metadata: renames, moves, network changes
  and closures each open a new version instead of overwriting the old one.
#}
{% snapshot snap_fmi_stations %}
{{ config(unique_key='fmisid', strategy='check',
          check_cols=['station_name', 'municipality', 'lat', 'lon', 'networks', 'active_to']) }}
select fmisid, station_name, municipality, lat, lon, position_key, networks, active_from, active_to
from {{ source('raw', 'fmi_stations') }}
{% endsnapshot %}
