-- Hourly aggregates per city: used for trend analysis and dashboards

with base as (
    select * from {{ ref('stg_weather_raw') }}
),

-- Pre-compute condition frequency so we can use max_by without nesting aggregates
condition_counts as (
    select
        city_name,
        state_code,
        observed_hour,
        condition_main,
        count(*) as condition_count
    from base
    group by city_name, state_code, observed_hour, condition_main
),

dominant as (
    select
        city_name,
        state_code,
        observed_hour,
        max_by(condition_main, condition_count) as dominant_condition
    from condition_counts
    group by city_name, state_code, observed_hour
)

select
    b.city_name,
    b.state_code,
    b.observed_hour,

    -- Temperature summary
    round(avg(b.temp_f), 2)               as avg_temp_f,
    round(min(b.temp_min_f), 2)           as min_temp_f,
    round(max(b.temp_max_f), 2)           as max_temp_f,

    -- Feels like
    round(avg(b.feels_like_f), 2)         as avg_feels_like_f,

    -- Atmosphere
    round(avg(b.humidity_pct), 1)         as avg_humidity_pct,
    round(avg(b.pressure_hpa), 1)         as avg_pressure_hpa,

    -- Wind
    round(avg(b.wind_speed_mph), 2)       as avg_wind_speed_mph,
    round(max(b.wind_gust_mph), 2)        as max_wind_gust_mph,

    -- Cloud cover
    round(avg(b.clouds_pct), 1)           as avg_clouds_pct,

    -- Dominant condition (most frequent)
    d.dominant_condition,

    count(*)                              as reading_count

from base b
join dominant d
    on  b.city_name    = d.city_name
    and b.state_code   = d.state_code
    and b.observed_hour = d.observed_hour
group by b.city_name, b.state_code, b.observed_hour, d.dominant_condition
