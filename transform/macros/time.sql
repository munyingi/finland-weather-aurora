{# All warehouse timestamps are naive UTC. These helpers keep the conversions in one place. #}
{% macro utc_now() -%}
    cast(timezone('UTC', now()) as timestamp)
{%- endmacro %}

{% macro to_helsinki(ts_utc) -%}
    timezone('Europe/Helsinki', timezone('UTC', {{ ts_utc }}))
{%- endmacro %}
