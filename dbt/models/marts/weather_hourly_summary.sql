-- Hourly aggregates per city: used for trend analysis and dashboards

select
    city_name,
    state_code,
    observed_hour,

    -- Temperature summary
    round(avg(temp_f), 2)               as avg_temp_f,
    round(min(temp_min_f), 2)           as min_temp_f,
    round(max(temp_max_f), 2)           as max_temp_f,

    -- Feels like
    round(avg(feels_like_f), 2)         as avg_feels_like_f,

    -- Atmosphere
    round(avg(humidity_pct), 1)         as avg_humidity_pct,
    round(avg(pressure_hpa), 1)         as avg_pressure_hpa,

    -- Wind
    round(avg(wind_speed_mph), 2)       as avg_wind_speed_mph,
    round(max(wind_gust_mph), 2)        as max_wind_gust_mph,

    -- Cloud cover
    round(avg(clouds_pct), 1)           as avg_clouds_pct,

    -- Dominant condition (most frequent)
    max_by(condition_main, count(*))    as dominant_condition,

    count(*)                            as reading_count

from {{ ref('stg_weather_raw') }}
group by city_name, state_code, observed_hour
